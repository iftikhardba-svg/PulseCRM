"""Check the web dashboard, its sign-in and its user management against a MySQL database.

Expects pulse_crm built with database/pulse_crm.sql and database/web_access.sql.
  MYSQL_URL   mysql://root:<password>@127.0.0.1:3307/pulse_crm   administrator connection
  WEB_DB_URL  optional; the connection the app should use. When it is not set, the script
              creates the pulse_web account from database/web_app_user.sql and also checks
              that this account needs TLS and cannot change the audit trail or the schema.
"""
import os
import re
import secrets
import sys
from urllib.parse import unquote, urlparse

import pymysql
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
PAGES = ["/", "/pipeline", "/accounts", "/team", "/leads", "/marketing", "/marketing?tab=audience",
         "/marketing?tab=sources", "/support", "/invoices", "/database"]
# network addresses used by the throttling tests (documentation ranges, plus the test client's default)
ADDRESSES = ("127.0.0.1", "198.51.100.7", "203.0.113.20", "192.0.2.99")
failures = []


def check(ok, message):
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def connect(url, plain=False):
    """plain=True forces an unencrypted connection; PyMySQL otherwise uses TLS whenever the server offers it."""
    u = urlparse(url)
    tls = {"check_hostname": False} if "SSL-MODE=REQUIRED" in u.query.upper() else None   # encrypted, unverified
    return pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username),
                           password=unquote(u.password or ""), database=u.path.lstrip("/"), autocommit=True,
                           ssl=None if plain else tls, ssl_disabled=plain)


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
        for stmt in re.findall(r"^(CREATE USER.*?;|ALTER USER.*?;|GRANT .*?;)", script, flags=re.M):
            cur.execute(stmt.replace("replace-with-a-strong-password", password))
        cur.execute("SHOW GRANTS FOR 'pulse_web'@'%'")
        grants = " | ".join(row[0] for row in cur.fetchall())
        check("GRANT SELECT ON `pulse_crm`.*" in grants and "`web_accounts`" in grants
              and "INSERT, DELETE ON `pulse_crm`.`web_login_failures`" in grants
              and "INSERT, UPDATE, DELETE ON `pulse_crm`.`accounts`" in grants
              and "EXECUTE ON PROCEDURE `pulse_crm`.`sp_convert_lead`" in grants
              and "`opportunity_stage_history`" not in grants, f"pulse_web grants: {grants}")
        cur.execute("SELECT ssl_type FROM mysql.user WHERE user = 'pulse_web' AND host = '%'")
        check(cur.fetchone()[0] == "ANY", "pulse_web is created with REQUIRE SSL")
        u = urlparse(admin_url)
        web_url = f"mysql://pulse_web:{password}@{u.hostname}:{u.port}{u.path}?ssl-mode=REQUIRED"

    # a known administrator for the test
    cur.execute("DELETE FROM web_accounts WHERE username LIKE 'ci.%'")
    cur.execute(f"DELETE FROM web_login_failures WHERE ip_address IN ({', '.join(['%s'] * len(ADDRESSES))})",
                ADDRESSES)
    admin_password = secrets.token_urlsafe(16)
    cur.execute("""INSERT INTO web_accounts (username, display_name, user_id, password_hash, must_change_password)
                   VALUES ('ci.admin', 'CI Administrator', 1, %s, FALSE)""", (generate_password_hash(admin_password),))
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
    html = anon.get("/login").get_data(as_text=True)
    check('id="theme-toggle"' in html and ':root[data-theme="dark"]' in html,
          "every page has the sun/moon button and a dark palette")
    check("#live-web-application" in html, "the sign-in page links visitors to the tour on GitHub")
    check("Try the demo" in html and 'id="use-demo"' in html, "the sign-in page shows the public demo login")
    csp = anon.get("/login").headers.get("Content-Security-Policy", "")
    check("script-src 'nonce-" in csp and "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
          and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0], f"Content-Security-Policy: {csp}")
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
    html = admin.get("/").get_data(as_text=True)
    check('data-nav="users"' in html and 'data-nav="marketing"' in html and 'id="sidebar-toggle"' in html,
          "administrator sees Users and Marketing in the sidebar, with the menu button")
    html = admin.get("/marketing").get_data(as_text=True)
    check("Cloud ERP Webinar 2026" in html and "Campaign engagement" in html and "New campaign" in html
          and 'href="/data/campaigns"' in html, "Marketing page: campaigns, engagement funnel, records bar")
    html = admin.get("/").get_data(as_text=True)
    steps = re.findall(r'class="band f\d" style="clip-path: polygon\(', html)
    check(html.count('class="card kpi ') == 7 and len(steps) == 5 and "of previous" in html,
          f"Dashboard shows 7 KPI cards and a 5-step sales funnel ({len(steps)} steps)")
    check(">Dashboard</span>" in html and "<h1>Dashboard</h1>" in html, "the first page is called Dashboard")
    html = admin.get("/leads").get_data(as_text=True)
    slices = re.findall(r'<path class="s(\d)" d="M100 100 L', html)
    check('class="pie"' in html and slices == ["1", "2", "3", "4", "5"] and ">24</span>" in html,
          f"Leads page: pie of the 5 lead statuses in fixed colour order ({slices}) with a total of 24")
    for path in ["/users", f"/users/{admin_id}", "/data/accounts", "/"]:
        r = admin.get(path)
        html = r.get_data(as_text=True)
        nonce = re.search(r"'nonce-([^']+)'", r.headers.get("Content-Security-Policy", ""))
        tags = re.findall(r"<script[^>]*>", html)
        check(bool(nonce) and bool(tags) and all(f'nonce="{nonce.group(1)}"' in tag for tag in tags)
              and not re.search(r"\son[a-z]+=", html),
              f"{path}: all {len(tags)} script(s) carry this response's nonce and there are no inline handlers")

    print("== Records: add, edit, delete")
    for path in ["/data/accounts", "/data/accounts/new", "/data/leads/new", "/data/opportunity_products",
                 "/data/opportunities/401/edit", "/data/opportunity_stage_history"]:
        check(admin.get(path).status_code == 200, f"{path}: 200")
    account = {"account_name": "CI Test Traders", "account_type": "Prospect", "city": "Karachi",
               "country": "Pakistan", "owner_user_id": "3", "employee_count": "40"}
    r = post(admin, "/data/accounts/new", account)
    cur.execute("SELECT account_id FROM accounts WHERE account_name = 'CI Test Traders'")
    found = cur.fetchone()
    check(r.status_code == 302 and found is not None, f"account added: {r.status_code}")
    account_id = found[0] if found else 0
    html = post(admin, "/data/accounts/new", dict(account, account_name="CI Bad", employee_count="-5"),
                follow=True).get_data(as_text=True)
    check("3819" in html and "chk_accounts_employees" in html, "CHECK violation shown (3819 chk_accounts_employees)")
    html = post(admin, "/data/accounts/new", dict(account, account_name="Indus Weave Textiles"),
                follow=True).get_data(as_text=True)
    check("1062" in html, "duplicate account name refused (1062)")
    html = post(admin, "/data/accounts/new", {"account_type": "Prospect"}, follow=True).get_data(as_text=True)
    check("Account name is required." in html, "missing required value refused before MySQL")
    r = post(admin, f"/data/accounts/{account_id}/edit", dict(account, city="Lahore"))
    cur.execute("SELECT city FROM accounts WHERE account_id = %s", (account_id,))
    check(r.status_code == 302 and cur.fetchone()[0] == "Lahore", "account edited")
    html = post(admin, "/data/accounts/101/delete", {}, follow=True).get_data(as_text=True)
    cur.execute("SELECT COUNT(*) FROM accounts WHERE account_id = 101")
    check("1451" in html and cur.fetchone()[0] == 1, "deleting a referenced account is refused (1451)")
    post(admin, f"/data/accounts/{account_id}/delete", {})
    cur.execute("SELECT COUNT(*) FROM accounts WHERE account_id = %s", (account_id,))
    check(cur.fetchone()[0] == 0, "account deleted")
    r = post(admin, "/data/campaign_leads/new", {"campaign_id": "701", "lead_id": "322", "added_on": "2026-10-27",
                                                 "response": "Sent"})
    post(admin, "/data/campaign_leads/701,322/edit", {"added_on": "2026-10-27", "response": "Opened"})
    cur.execute("SELECT response FROM campaign_leads WHERE campaign_id = 701 AND lead_id = 322")
    check(r.status_code == 302 and cur.fetchone()[0] == "Opened", "two-column key: row added and edited")
    post(admin, "/data/campaign_leads/701,322/delete", {})
    cur.execute("SELECT COUNT(*) FROM campaign_leads WHERE campaign_id = 701 AND lead_id = 322")
    check(cur.fetchone()[0] == 0, "two-column key: row deleted")
    check(admin.get("/data/opportunity_stage_history/new").status_code == 403, "stage history cannot be added to")

    print("== Stored procedures")
    html = post(admin, "/leads/322/convert", {"opportunity_name": "No", "amount": "1000", "expected_close": "2027-01-01"},
                follow=True).get_data(as_text=True)
    check("Unqualified leads cannot be converted" in html, "sp_convert_lead refuses an unqualified lead (1644)")
    r = post(admin, "/leads/307/convert", {"opportunity_name": "Gwadar Port ERP", "amount": "2500000",
                                           "expected_close": "2027-01-31"})
    cur.execute("SELECT status FROM leads WHERE lead_id = 307")
    check(r.status_code == 302 and cur.fetchone()[0] == "Converted", "sp_convert_lead converts lead 307")
    r = post(admin, "/pipeline/410/stage", {"stage_name": "Closed Won", "loss_reason": ""})
    cur.execute("SELECT invoice_id FROM invoices WHERE opportunity_id = 410")
    invoice = cur.fetchone()
    cur.execute("SELECT changed_by FROM opportunity_stage_history WHERE opportunity_id = 410 AND to_stage_id = 5")
    check(r.status_code == 302 and invoice is not None and cur.fetchone() == (1,),
          "sp_update_opportunity_stage wins deal 410 and creates its invoice; the trigger records CRM user 1")
    invoice_id = invoice[0] if invoice else 0
    html = post(admin, f"/invoices/{invoice_id}/payment", {"amount": "99999999", "payment_method": "Card"},
                follow=True).get_data(as_text=True)
    check("cannot exceed the balance due" in html, "sp_record_payment refuses an overpayment")
    r = post(admin, f"/invoices/{invoice_id}/payment", {"amount": "500000", "payment_method": "Bank Transfer",
                                                        "reference_no": "BT-CI-0410"})
    cur.execute("SELECT status FROM invoices WHERE invoice_id = %s", (invoice_id,))
    check(r.status_code == 302 and cur.fetchone()[0] == "Partially Paid", "sp_record_payment records a part payment")

    rep_password = secrets.token_urlsafe(14)
    r = post(admin, "/users", {"username": "ci.rep", "display_name": "CI Rep", "user_id": "4",
                               "password": rep_password,
                               "privileges": ["view_overview", "view_pipeline", "add_pipeline"]})
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
    check(rep.get("/marketing").status_code == 403 and rep.get("/data/campaigns").status_code == 403,
          "ci.rep cannot open Marketing or campaign records (not granted)")
    html = rep.get("/data/opportunities").get_data(as_text=True)
    check("Add a record" in html and "/edit" not in html and ">Delete<" not in html,
          "ci.rep sees Add but no Edit or Delete on deals")
    check(rep.get("/data/opportunities/new").status_code == 200, "ci.rep opens the add form (add_pipeline)")
    check(rep.get("/data/opportunities/401/edit").status_code == 403, "ci.rep cannot edit deals")
    check(post(rep, "/data/opportunities/401/delete", {}).status_code == 403, "ci.rep cannot delete deals")
    check(post(rep, "/pipeline/411/stage", {"stage_name": "Proposal"}).status_code == 403, "ci.rep cannot change stages")
    check(rep.get("/data/accounts").status_code == 403, "ci.rep cannot open account records")
    html = rep.get("/").get_data(as_text=True)
    check('data-nav="pipeline"' in html and 'data-nav="invoices"' not in html and 'data-nav="users"' not in html
          and 'data-nav="marketing"' not in html, "ci.rep sees only the granted pages in the sidebar")

    print("== Throttling per network address")
    prankster = web.app.test_client()
    prankster.environ_base["REMOTE_ADDR"] = "198.51.100.7"
    for _ in range(5):
        sign_in(prankster, "ci.rep", "not-the-password")
    r = sign_in(prankster, "ci.rep", new_password)
    check(r.status_code == 429 and "Too many wrong passwords" in r.get_data(as_text=True),
          "five wrong passwords block that address for ci.rep, even with the right password (429)")
    classmate = web.app.test_client()
    classmate.environ_base["REMOTE_ADDR"] = "203.0.113.20"
    check(sign_in(classmate, "ci.rep", new_password).status_code == 302,
          "ci.rep still signs in from another address: the account itself is never locked")
    html = admin.get(f"/users/{rep_id}").get_data(as_text=True)
    check("198.51.100.7" in html and "Clear the sign-in block" in html, "the Users page shows the blocked address")
    r = post(admin, f"/users/{rep_id}", {"display_name": "CI Rep", "user_id": "4", "is_active": "on", "unlock": "on",
                                         "privileges": ["view_overview", "view_pipeline", "add_pipeline"]})
    check(r.status_code == 302, "administrator clears the block")
    check(sign_in(prankster, "ci.rep", new_password).status_code == 302, "the address signs in after the clear")
    sprayer = web.app.test_client()
    sprayer.environ_base["REMOTE_ADDR"] = "192.0.2.99"
    for i in range(20):
        sign_in(sprayer, f"nobody{i}", "not-a-password")
    check(sign_in(sprayer, "ci.rep", new_password).status_code == 429,
          "20 wrong passwords from one address block it for every account")
    r = sprayer.post("/login", data={"csrf": token(sprayer), "username": "ci.rep", "password": new_password},
                     headers={"X-Forwarded-For": "10.9.9.9", "X-Real-IP": "10.9.9.9"})
    check(r.status_code == 429, "a forged X-Forwarded-For or X-Real-IP header does not get round the block")

    print("== Shared demo account")
    demo_password = "Tour-" + secrets.token_urlsafe(10)
    view_only = ["view_overview", "view_leads"]
    post(admin, "/users", {"username": "ci.demo", "display_name": "CI Demo", "password": demo_password,
                           "privileges": view_only})
    cur.execute("SELECT account_id FROM web_accounts WHERE username = 'ci.demo'")
    demo_id = cur.fetchone()[0]
    r = post(admin, f"/users/{demo_id}", {"display_name": "CI Demo", "is_active": "on", "password_locked": "on",
                                          "new_password": demo_password, "privileges": view_only})
    cur.execute("SELECT password_locked, must_change_password FROM web_accounts WHERE account_id = %s", (demo_id,))
    check(r.status_code == 302 and cur.fetchone() == (1, 0),
          "ci.demo becomes a shared demo account, and a password reset does not ask for a new one")
    visitor = web.app.test_client()
    check(sign_in(visitor, "ci.demo", demo_password).status_code == 302 and visitor.get("/").status_code == 200,
          "ci.demo signs in straight to the Dashboard")
    html = visitor.get("/account").get_data(as_text=True)
    check("shared demo account" in html and 'name="new"' not in html, "My account has no password form for it")
    post(visitor, "/account", {"current": demo_password, "new": "Changed-pass-123", "confirm": "Changed-pass-123"})
    cur.execute("SELECT password_hash FROM web_accounts WHERE account_id = %s", (demo_id,))
    check(check_password_hash(cur.fetchone()[0], demo_password), "its users cannot change its password")
    html = post(admin, f"/users/{demo_id}", {"display_name": "CI Demo", "is_active": "on", "password_locked": "on",
                                             "privileges": view_only + ["manage_users"]}, follow=True).get_data(as_text=True)
    check("cannot have the Manage users privilege" in html, "a shared demo account cannot get Manage users")

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
                "account_deleted", "record_added", "record_updated", "record_deleted", "procedure_called"}
    check(expected <= actions, f"audit log records {sorted(actions)}")

    if not os.environ.get("WEB_DB_URL"):
        print("== MySQL privileges of pulse_web")
        try:
            connect(web_url, plain=True).close()
            check(False, "pulse_web connected without TLS")
        except pymysql.MySQLError as error:
            check(error.args[0] == 1045, f"pulse_web is refused without TLS ({error.args[0]})")
        with connect(web_url) as conn, conn.cursor() as c:
            c.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            cipher = c.fetchone()[1]
            check(bool(cipher), f"pulse_web connects over TLS ({cipher})")
            for sql_text in ("DELETE FROM opportunity_stage_history WHERE history_id = -1",
                             "INSERT INTO web_privileges VALUES ('x', 'x', 'x', 99)",
                             "CREATE TABLE web_probe (id INT PRIMARY KEY)"):
                try:
                    c.execute(sql_text)
                    check(False, f"pulse_web was allowed: {sql_text}")
                except pymysql.MySQLError as error:
                    check(error.args[0] == 1142, f"pulse_web refused ({error.args[0]}): {sql_text[:45]}")

    cur.execute("DELETE FROM web_accounts WHERE username LIKE 'ci.%'")
    cur.execute(f"DELETE FROM web_login_failures WHERE ip_address IN ({', '.join(['%s'] * len(ADDRESSES))})",
                ADDRESSES)
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
