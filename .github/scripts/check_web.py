"""Check the web dashboard against the MySQL database started by docker-compose.yml.

Creates the read-only account from database/web_readonly_user.sql, requests every page
through Flask's test client as that account, and checks that the account cannot write.

  MYSQL_URL  mysql://root:<password>@127.0.0.1:3307/pulse_crm
"""
import json
import os
import re
import secrets
import sys
from urllib.parse import unquote, urlparse

import pymysql

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
failures = []


def check(ok, message):
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def connect(user, password, url):
    return pymysql.connect(host=url.hostname, port=url.port, user=user, password=password,
                           database="pulse_crm", autocommit=True)


def main():
    url = urlparse(os.environ["MYSQL_URL"])
    password = secrets.token_urlsafe(18)
    script = open(os.path.join(ROOT, "database", "web_readonly_user.sql"), encoding="utf-8").read()
    with connect(unquote(url.username), unquote(url.password), url) as conn, conn.cursor() as cur:
        for stmt in re.findall(r"^(CREATE USER.*?;|GRANT SELECT.*?;)", script, flags=re.M):
            cur.execute(stmt.replace("replace-with-a-strong-password", password))
        cur.execute("SHOW GRANTS FOR 'pulse_web'@'%'")
        grants = [row[0] for row in cur.fetchall()]
    check(len(grants) == 2 and "GRANT SELECT ON `pulse_crm`.*" in grants[1], f"pulse_web grants: {grants}")

    os.environ["DATABASE_URL"] = f"mysql://pulse_web:{password}@{url.hostname}:{url.port}/pulse_crm"
    import app as web
    client = web.app.test_client()
    for path in ["/", "/pipeline", "/accounts", "/team", "/leads", "/support", "/invoices", "/database"]:
        response = client.get(path)
        title = re.search(r"<h1>(.*?)</h1>", response.get_data(as_text=True))
        check(response.status_code == 200, f"{path}: {response.status_code} {title.group(1) if title else ''}")
    health = json.loads(client.get("/health").get_data(as_text=True))
    check(health.get("accounts") == 12 and health.get("database") == "pulse_crm", f"/health: {health}")

    with connect("pulse_web", password, url) as conn, conn.cursor() as cur:
        try:
            cur.execute("UPDATE leads SET lead_score = lead_score WHERE lead_id = 301")
            check(False, "pulse_web was allowed to UPDATE")
        except pymysql.MySQLError as error:
            check(error.args[0] == 1142, f"pulse_web cannot UPDATE: MySQL error {error.args[0]}")

    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
