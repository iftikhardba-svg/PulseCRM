"""Set up a cloud MySQL server for the PulseCRM web dashboard.

1. Builds pulse_crm on the server by running database/pulse_crm.sql unchanged.
2. Creates the read-only account pulse_web (SELECT only) with a random password.
3. Checks that pulse_web can read but not write.
4. Writes the settings for Vercel to web/.env.vercel (git-ignored).

Before running, put the administrator connection in web/.env:
    AIVEN_ADMIN_URL=mysql://avnadmin:<password>@<host>:<port>/defaultdb?ssl-mode=REQUIRED
and the server's CA certificate in web/ca.pem. Run from the repository root:
    python web/setup_cloud_db.py
Needs the mysql command-line client (MySQL 8.0) and PyMySQL.
"""
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urlparse

import pymysql

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
CA = os.path.join(WEB, "ca.pem")
WEB_USER = "pulse_web"


def read_env(path):
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def mysql_client():
    found = shutil.which("mysql")
    if found:
        return found
    for version in ("8.4", "8.0"):
        path = rf"C:\Program Files\MySQL\MySQL Server {version}\bin\mysql.exe"
        if os.path.exists(path):
            return path
    sys.exit("The mysql command-line client was not found.")


def main():
    env = read_env(os.path.join(WEB, ".env"))
    admin_url = env.get("AIVEN_ADMIN_URL") or env.get("ADMIN_DATABASE_URL")
    if not admin_url:
        sys.exit("Put AIVEN_ADMIN_URL=mysql://... in web/.env first.")
    if not os.path.exists(CA):
        sys.exit("Save the server's CA certificate as web/ca.pem first.")
    url = urlparse(admin_url)
    host, port = url.hostname, url.port or 3306
    admin, password = unquote(url.username), unquote(url.password)

    # 1. Build the database with the unchanged project script (password kept out of the command line)
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as cnf:
        cnf.write(f"[client]\nuser={admin}\npassword=\"{password}\"\nhost={host}\nport={port}\n")
    try:
        with open(os.path.join(ROOT, "database", "pulse_crm.sql"), encoding="utf-8") as script:
            run = subprocess.run([mysql_client(), f"--defaults-extra-file={cnf.name}", "--ssl-mode=VERIFY_IDENTITY",
                                  f"--ssl-ca={CA}", "--table"], stdin=script, capture_output=True, text=True)
    finally:
        os.remove(cnf.name)
    if run.returncode != 0:
        sys.exit("Building pulse_crm failed:\n" + run.stderr)
    print("1. pulse_crm built. Row counts reported by the script:")
    print(run.stdout.strip())

    # 2. Read-only account with a random password
    web_password = secrets.token_urlsafe(24) + "aA1-"
    with pymysql.connect(host=host, port=port, user=admin, password=password, ssl={"ca": CA}) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE USER IF NOT EXISTS '{WEB_USER}'@'%' IDENTIFIED BY %s", (web_password,))
            cur.execute(f"ALTER USER '{WEB_USER}'@'%' IDENTIFIED BY %s", (web_password,))
            cur.execute(f"GRANT SELECT ON pulse_crm.* TO '{WEB_USER}'@'%'")
            cur.execute(f"SHOW GRANTS FOR '{WEB_USER}'@'%'")
            grants = [row[0] for row in cur.fetchall()]
    print(f"2. {WEB_USER} created with these grants:")
    for grant in grants:
        print("   ", grant)

    # 3. The website account can read but not write
    with pymysql.connect(host=host, port=port, user=WEB_USER, password=web_password, database="pulse_crm",
                         ssl={"ca": CA}) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vw_account_360")
            print(f"3. {WEB_USER} reads vw_account_360: {cur.fetchone()[0]} rows")
            try:
                cur.execute("UPDATE leads SET lead_score = lead_score WHERE lead_id = 301")
                sys.exit(f"   ERROR: {WEB_USER} was allowed to UPDATE. Check its grants.")
            except pymysql.err.MySQLError as error:
                print(f"   {WEB_USER} cannot UPDATE, as intended: MySQL error {error.args[0]}")

    # 4. Settings for Vercel
    database_url = f"mysql://{WEB_USER}:{quote(web_password, safe='')}@{host}:{port}/pulse_crm"
    with open(CA, encoding="utf-8") as f:
        ca_text = f.read().strip().replace("\r\n", "\n").replace("\n", "\\n")
    out = os.path.join(WEB, ".env.vercel")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f'DATABASE_URL="{database_url}"\nDATABASE_CA_CERT="{ca_text}"\n')
    print(f"4. Vercel settings written to {out} (git-ignored). Do not commit or share this file.")


if __name__ == "__main__":
    main()
