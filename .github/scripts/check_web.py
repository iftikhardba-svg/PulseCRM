"""Check the web dashboard, its sign-in and its user management against a MySQL database.

Expects pulse_crm built with database/pulse_crm.sql and database/web_access.sql.
  MYSQL_URL   mysql://root:<password>@127.0.0.1:3307/pulse_crm   administrator connection
  WEB_DB_URL  optional; the connection the app should use. When it is not set, the script
              creates the pulse_web account from database/web_app_user.sql and also checks
              that this account cannot change CRM data.
"""
import os
import re
import secrets
import sys
from urllib.parse import unquote, urlparse

import pymysql
from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
PAGES = ["/", "/pipeline", "/accounts", "/team", "/leads", "/support", "/invoices", "/database"]
failures = []


def check(ok, message):
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def connect(url):
    u = urlparse(url)
    return pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username),
                           password=unquote(u.password or ""), database=u.path.lstrip("/"), autocommit=True)


def token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def post(client, path, data, follow=False):
    data = dict(data)
    data.setdefault("csrf", token(client, "/account" if path != "/login" else "/login"))
    return client.post(path, data=data, follow_redirects=follow)


def sign_in(client, username, password):
    return post(client, "/login", {"username": username, "password": password})


def main():
    admin_url = os.environ["MYSQL_URL"]
    web_url = os.environ.get("WEB_DB_URL")
    db = connect(admin_url)
    cur = db.cursor()

    if not web_url:
        password = secrets.token_urlsafe(18)
        script = open(os.path.join(ROOT, "database", "web_app_user.sql"), encoding="utf-8").read()
        for stmt in re.findall(r"^(CREATE USER.*?;|GRANT .*?;)", script, flags=re.M):
            cur.execute(stmt.replace("replace-with-a-strong-password", password))
        cur.execute("SHOW GRANTS FOR 'pulse_web'@'%'")
        grants = " | ".join(row[0] for row in cur.fetchall())
        check("GRANT SELECT ON `pulse_crm`.*" in grants and "`web_accounts`" in grants
              and "UPDATE ON `pulse_crm`.`leads`" not in grants, f"pulse_web grants: {grants}")
        u = urlparse(admin_url)
        web_url = f"mysql://pulse_web:{password}@{u.hostname}:{u.port}{u.path}"

    # a known administrator for the test
    cur.execute("DELETE FROM web_accounts WHERE username LIKE 'ci.%'")
    admin_password = secrets.token_urlsafe(16)
    cur.execute("""INSERT INTO web_accounts (username, display_name, password_hash, must_change_password)
                   VALUES ('ci.admin', 'CI Administrator', %s, FALSE)""", (generate_password_hash(admin_password),))
    admin_id = cur.lastrowid
    cur.execute("""INSERT INTO web_account_privileges (account_id, privilege_code)
                   SELECT %s, privilege_code FROM web_privileges""", (admin_id,))

    os.environ["DATABASE_URL"] = web_url
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
    import app as web
    web.app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    print("== Signed out")
    anon = web.app.test_client()
    r = anon.get("/")
    check(r.status_code == 302 and "/login" in r.headers["Location"], f"/ redirects to sign-in: {r.status_code}")
    check(anon.get("/health").status_code == 200, "/health stays public")
    r = anon.post("/login", data={"username": "ci.admin", "password": admin_password})
    check(r.status_code == 400, f"sign-in without a CSRF token is rejected: {r.status_code}")
    r = sign_in(anon, "ci.admin", "wrong-password")
    check(r.status_code == 200 and "Wrong user name or password" in r.get_data(as_text=True), "wrong password refused")
    r = sign_in(anon, "nobody.here", "whatever-password")
    check("Wrong user name or password" in r.get_data(as_text=True), "unknown user name gets the same message")

    print("== Administrator")
    admin = web.app.test_client()
    r = sign_in(admin, "ci.admin", admin_password)
    check(r.status_code == 302 and r.headers["Location"].endswith("/"), f"administrator signs in: {r.status_code}")
    for path in PAGES + ["/users", "/account"]:
        r = admin.get(path)
        title = re.search(r"<h1>(.*?)</h1>", r.get_data(as_text=True))
        check(r.status_code == 200, f"{path}: {r.status_code} {title.group(1) if title else ''}")
    check(">Users</a>" in admin.get("/").get_data(as_text=True), "administrator sees the Users tab")

    rep_password = secrets.token_urlsafe(14)
    r = post(admin, "/users", {"username": "ci.rep", "display_name": "CI Rep", "user_id": "4",
                               "password": rep_password, "privileges": ["view_overview", "view_pipeline"]})
    check(r.status_code == 302, f"account ci.rep created: {r.status_code}")
    r = post(admin, "/users", {"username": "ci.rep", "display_name": "Again", "password": rep_password}, follow=True)
    check("already taken" in r.get_data(as_text=True), "duplicate user name refused")
    r = post(admin, f"/users/{admin_id}", {"display_name": "CI Administrator", "is_active": "on",
                                           "privileges": ["view_overview"]}, follow=True)
    check("cannot remove Manage users from your own account" in r.get_data(as_text=True),
          "administrator cannot remove their own Manage users privilege")
    cur.execute("SELECT account_id FROM web_accounts WHERE username = 'ci.rep'")
    rep_id = cur.fetchone()[0]

    print("== Limited account")
    rep = web.app.test_client()
    r = sign_in(rep, "ci.rep", rep_password)
    check(r.status_code == 302, f"ci.rep signs in with the temporary password: {r.status_code}")
    r = rep.get("/pipeline")
    check(r.status_code == 302 and r.headers["Location"].endswith("/account"), "temporary password forces a change first")
    new_password = secrets.token_urlsafe(14)
    r = post(rep, "/account", {"current": rep_password, "new": new_password, "confirm": new_password})
    check(r.status_code == 302, f"ci.rep changes the password: {r.status_code}")
    check(rep.get("/pipeline").status_code == 200, "ci.rep opens Pipeline (granted)")
    check(rep.get("/invoices").status_code == 403, "ci.rep cannot open Invoices (not granted)")
    check(rep.get("/users").status_code == 403, "ci.rep cannot open Users")
    html = rep.get("/").get_data(as_text=True)
    check(">Pipeline</a>" in html and ">Invoices</a>" not in html and ">Users</a>" not in html,
          "ci.rep sees only the granted tabs")

    print("== Lockout")
    other = web.app.test_client()
    for _ in range(5):
        sign_in(other, "ci.rep", "not-the-password")
    r = sign_in(other, "ci.rep", new_password)
    check("locked" in r.get_data(as_text=True), "five wrong passwords lock the account, even for the right one")
    r = post(admin, f"/users/{rep_id}", {"display_name": "CI Rep", "user_id": "4", "is_active": "on", "unlock": "on",
                                         "privileges": ["view_overview", "view_pipeline"]})
    check(r.status_code == 302, "administrator unlocks ci.rep")
    check(sign_in(other, "ci.rep", new_password).status_code == 302, "ci.rep signs in after the unlock")

    print("== Delete and sign out")
    r = post(admin, f"/users/{rep_id}/delete", {})
    check(r.status_code == 302, f"administrator deletes ci.rep: {r.status_code}")
    r = rep.get("/pipeline")
    check(r.status_code == 302 and "/login" in r.headers["Location"], "a deleted account is signed out at once")
    r = post(admin, "/logout", {})
    check(r.status_code == 302 and admin.get("/").status_code == 302, "administrator signs out")

    cur.execute("SELECT DISTINCT action FROM web_audit_log")
    actions = {row[0] for row in cur.fetchall()}
    expected = {"login", "login_failed", "logout", "account_created", "account_updated", "password_changed",
                "account_deleted"}
    check(expected <= actions, f"audit log records {sorted(actions)}")

    if not os.environ.get("WEB_DB_URL"):
        print("== MySQL privileges of pulse_web")
        u = urlparse(web_url)
        with connect(web_url) as conn, conn.cursor() as c:
            for sql_text in ("UPDATE leads SET lead_score = lead_score WHERE lead_id = 301",
                             "INSERT INTO web_privileges VALUES ('x', 'x', 'x', 99)"):
                try:
                    c.execute(sql_text)
                    check(False, f"pulse_web was allowed: {sql_text}")
                except pymysql.MySQLError as error:
                    check(error.args[0] == 1142, f"pulse_web refused ({error.args[0]}): {sql_text[:45]}")

    cur.execute("DELETE FROM web_accounts WHERE username LIKE 'ci.%'")
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
