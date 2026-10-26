"""Set up a Supabase (PostgreSQL) database for the PulseCRM web dashboard.

1. Builds the pulse_crm schema by running database/pulse_crm_postgres.sql.
2. Creates pulse_web, a login role that can only read (SELECT) and whose
   transactions are READ ONLY by default.
3. Checks that pulse_web can read but not write.
4. Writes DATABASE_URL for Vercel to web/.env.vercel (git-ignored).

Before running, put the Supabase connection string in web/.env (git-ignored):
    SUPABASE_DB_URL=postgresql://postgres.<project-ref>:<password>@<region>.pooler.supabase.com:5432/postgres
(Supabase dashboard > Connect > Session pooler, with your database password filled in).
Run from the repository root:
    python web/setup_supabase.py
"""
import os
import secrets
import sys
from urllib.parse import quote, unquote, urlparse

import psycopg
from psycopg import sql

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
SCRIPT = os.path.join(ROOT, "database", "pulse_crm_postgres.sql")
ROLE = "pulse_web"
SCHEMA = "pulse_crm"


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


def admin_url():
    url = os.environ.get("SUPABASE_DB_URL") or read_env(os.path.join(WEB, ".env")).get("SUPABASE_DB_URL")
    if not url:
        sys.exit("Put SUPABASE_DB_URL=postgresql://... in web/.env first.")
    if "[YOUR-PASSWORD]" in url:
        sys.exit("Replace [YOUR-PASSWORD] in SUPABASE_DB_URL with your database password.")
    return url


def connect(url):
    return psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=15)


def load_schema(conn):
    """Run the whole PostgreSQL build script; returns the row counts it reports at the end."""
    with open(SCRIPT, encoding="utf-8") as f:
        script = f.read()
    with conn.cursor() as cur:
        cur.execute(script)
        rows = []
        while True:
            if cur.description:
                rows = cur.fetchall()
            if not cur.nextset():
                break
        return rows


def create_readonly_role(conn, password):
    """Create or reset pulse_web with SELECT on every table and view in pulse_crm."""
    role, schema = sql.Identifier(ROLE), sql.Identifier(SCHEMA)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
        verb = "ALTER" if cur.fetchone() else "CREATE"
        cur.execute(sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(role, sql.Literal(password)))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, role))
        cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(schema, role))
        cur.execute(sql.SQL("ALTER ROLE {} SET search_path = {}").format(role, schema))
        cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))


def web_url(admin, password):
    """Connection string for pulse_web on the same server."""
    u = urlparse(admin)
    user = unquote(u.username or "")
    # Supabase's pooler expects <role>.<project-ref> as the user name
    web_user = ROLE + (user[user.index("."):] if "." in user else "")
    port = u.port or 5432
    if u.hostname.endswith(".pooler.supabase.com"):
        port = 6543   # transaction pooler, recommended for serverless functions such as Vercel
    query = "" if u.hostname in ("localhost", "127.0.0.1") else "?sslmode=require"
    return f"postgresql://{quote(web_user, safe='.')}:{quote(password, safe='')}@{u.hostname}:{port}{u.path or '/postgres'}{query}"


def check_readonly(url):
    """pulse_web must read the views and fail to write."""
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pulse_crm.vw_account_360")
            readable = cur.fetchone()[0]
            try:
                cur.execute("UPDATE pulse_crm.leads SET lead_score = lead_score WHERE lead_id = 301")
            except (psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege) as error:
                return readable, f"{error.sqlstate} {type(error).__name__}"
    raise SystemExit(f"ERROR: {ROLE} was allowed to UPDATE. Check its privileges.")


def main():
    admin = admin_url()
    password = secrets.token_urlsafe(24)
    with connect(admin) as conn:
        counts = load_schema(conn)
        print(f"1. {SCHEMA} built: {len(counts)} tables, {sum(r[1] for r in counts)} rows")
        create_readonly_role(conn, password)
        print(f"2. {ROLE} created with SELECT on {SCHEMA} and READ ONLY transactions")
    url = web_url(admin, password)
    readable, refused = check_readonly(url)
    print(f"3. {ROLE} reads vw_account_360 ({readable} rows) and cannot UPDATE ({refused})")
    out = os.path.join(WEB, ".env.vercel")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f'DATABASE_URL="{url}"\n')
    print(f"4. Vercel setting written to {out} (git-ignored). Do not commit or share this file.")


if __name__ == "__main__":
    main()
