"""Set up a MySQL server (such as Aiven) for the PulseCRM web dashboard.

    python web/setup_cloud_db.py              build everything from scratch
    python web/setup_cloud_db.py --keep-data  keep pulse_crm and the pulse_web password;
                                              add or update only the sign-in tables

1. Builds pulse_crm by running database/pulse_crm.sql unchanged (skipped with --keep-data).
2. Adds the sign-in tables from database/web_access.sql.
3. Creates pulse_web with a random password (kept with --keep-data) and the grants in
   database/web_app_user.sql: SELECT on everything, writes only on the sign-in tables.
4. Creates the first administrator, "admin", if no active account can manage users. Its
   temporary password goes to web/.env.admin (git-ignored); it must be changed at first sign-in.
5. Checks that pulse_web can read the CRM data but not change it.
6. Writes DATABASE_URL, DATABASE_CA_CERT and SECRET_KEY for Vercel to web/.env.vercel (git-ignored).

Before running, put the administrator connection in web/.env:
    AIVEN_ADMIN_URL=mysql://avnadmin:<password>@<host>:<port>/defaultdb?ssl-mode=REQUIRED
and the server's CA certificate in web/ca.pem. Run from the repository root.
Needs the mysql command-line client (MySQL 8.0), PyMySQL and Flask (for the password hash).
"""
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urlparse

import pymysql
from werkzeug.security import generate_password_hash

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
CA = os.path.join(WEB, "ca.pem")
WEB_USER = "pulse_web"
FIRST_ADMIN = "admin"


def read_env(path):
    values = {}
    if os.path.exists(path):
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


def run_sql_file(server, name, database=None):
    """Run a script from database/ with the mysql client (password kept out of the command line)."""
    host, port, admin, password = server
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as cnf:
        cnf.write(f"[client]\nuser={admin}\npassword=\"{password}\"\nhost={host}\nport={port}\n")
    tls = ["--ssl-mode=VERIFY_IDENTITY", f"--ssl-ca={CA}"] if os.path.exists(CA) else []
    try:
        with open(os.path.join(ROOT, "database", name), encoding="utf-8") as script:
            run = subprocess.run([mysql_client(), f"--defaults-extra-file={cnf.name}", *tls, "--table",
                                  *([database] if database else [])],
                                 stdin=script, capture_output=True, text=True)
    finally:
        os.remove(cnf.name)
    if run.returncode != 0:
        sys.exit(f"Running database/{name} failed:\n{run.stderr}")
    return run.stdout


def main():
    keep_data = "--keep-data" in sys.argv[1:]
    env = read_env(os.path.join(WEB, ".env"))
    admin_url = os.environ.get("ADMIN_DATABASE_URL") or env.get("AIVEN_ADMIN_URL") or env.get("ADMIN_DATABASE_URL")
    if not admin_url:
        sys.exit("Put AIVEN_ADMIN_URL=mysql://... in web/.env first.")
    url = urlparse(admin_url)
    server = (url.hostname, url.port or 3306, unquote(url.username), unquote(url.password))
    ssl = {"ca": CA} if os.path.exists(CA) else None
    vercel_path = os.path.join(WEB, ".env.vercel")
    vercel = read_env(vercel_path)

    # 1. CRM database
    if keep_data:
        print("1. pulse_crm kept as it is (--keep-data)")
    else:
        run_sql_file(server, "pulse_crm.sql")
        print("1. pulse_crm built from database/pulse_crm.sql")

    # 2. sign-in tables
    run_sql_file(server, "web_access.sql", "pulse_crm")
    print("2. sign-in tables added from database/web_access.sql")

    # 3. the web application's MySQL account
    grants_sql = open(os.path.join(ROOT, "database", "web_app_user.sql"), encoding="utf-8").read()
    with pymysql.connect(host=server[0], port=server[1], user=server[2], password=server[3], ssl=ssl,
                         database="pulse_crm", autocommit=True) as conn, conn.cursor() as cur:
        if keep_data:
            if not vercel.get("DATABASE_URL"):
                sys.exit("--keep-data needs the existing DATABASE_URL in web/.env.vercel; run without it instead.")
            database_url = vercel["DATABASE_URL"]
        else:
            web_password = secrets.token_urlsafe(24) + "aA1-"
            # '%%' is the any-host wildcard '%', escaped because these queries take a %s parameter
            cur.execute(f"CREATE USER IF NOT EXISTS '{WEB_USER}'@'%%' IDENTIFIED BY %s", (web_password,))
            cur.execute(f"ALTER USER '{WEB_USER}'@'%%' IDENTIFIED BY %s", (web_password,))
            database_url = f"mysql://{WEB_USER}:{quote(web_password, safe='')}@{server[0]}:{server[1]}/pulse_crm"
        for stmt in re.findall(r"^(GRANT .*?);", grants_sql, flags=re.M):
            cur.execute(stmt)
        cur.execute(f"SHOW GRANTS FOR '{WEB_USER}'@'%'")
        grants = [row[0] for row in cur.fetchall()]
        print(f"3. {WEB_USER} {'kept, grants updated' if keep_data else 'created'}:")
        for grant in grants:
            print("    ", grant)

        # 4. first administrator
        cur.execute("""SELECT COUNT(*) FROM web_accounts a
                       JOIN web_account_privileges ap ON ap.account_id = a.account_id
                                                    AND ap.privilege_code = 'manage_users'
                       WHERE a.is_active = TRUE""")
        if cur.fetchone()[0]:
            print("4. an administrator account already exists; none created")
        else:
            temporary = secrets.token_urlsafe(12)
            cur.execute("""INSERT INTO web_accounts (username, display_name, password_hash, must_change_password)
                           VALUES (%s, 'Administrator', %s, TRUE)
                           ON DUPLICATE KEY UPDATE password_hash = %s, must_change_password = TRUE,
                                                   is_active = TRUE, failed_logins = 0, locked_until = NULL""",
                        (FIRST_ADMIN, generate_password_hash(temporary), generate_password_hash(temporary)))
            cur.execute("""INSERT IGNORE INTO web_account_privileges (account_id, privilege_code)
                           SELECT a.account_id, p.privilege_code
                           FROM web_accounts a CROSS JOIN web_privileges p
                           WHERE a.username = %s""", (FIRST_ADMIN,))
            admin_file = os.path.join(WEB, ".env.admin")
            with open(admin_file, "w", encoding="utf-8") as f:
                f.write(f"ADMIN_USERNAME={FIRST_ADMIN}\nADMIN_TEMPORARY_PASSWORD={temporary}\n")
            print(f"4. administrator '{FIRST_ADMIN}' created; temporary password in {admin_file} (git-ignored)")

    # 5. the web account can read CRM data but not change it
    u = urlparse(database_url)
    with pymysql.connect(host=u.hostname, port=u.port, user=unquote(u.username), password=unquote(u.password),
                         database="pulse_crm", ssl=ssl) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vw_account_360")
        readable = cur.fetchone()[0]
        try:
            cur.execute("UPDATE leads SET lead_score = lead_score WHERE lead_id = 301")
            sys.exit(f"ERROR: {WEB_USER} was allowed to UPDATE leads. Check its grants.")
        except pymysql.err.MySQLError as error:
            print(f"5. {WEB_USER} reads vw_account_360 ({readable} rows) and cannot UPDATE leads "
                  f"(MySQL error {error.args[0]})")

    # 6. settings for Vercel
    ca_text = ""
    if os.path.exists(CA):
        with open(CA, encoding="utf-8") as f:
            ca_text = f.read().strip().replace("\r\n", "\n").replace("\n", "\\n")
    secret_key = vercel.get("SECRET_KEY") or secrets.token_urlsafe(48)
    with open(vercel_path, "w", encoding="utf-8") as f:
        f.write(f'DATABASE_URL="{database_url}"\n')
        if ca_text:
            f.write(f'DATABASE_CA_CERT="{ca_text}"\n')
        f.write(f'SECRET_KEY="{secret_key}"\n')
    print(f"6. Vercel settings written to {vercel_path} (git-ignored): DATABASE_URL, "
          f"{'DATABASE_CA_CERT, ' if ca_text else ''}SECRET_KEY{' (new)' if not vercel.get('SECRET_KEY') else ''}")


if __name__ == "__main__":
    main()
