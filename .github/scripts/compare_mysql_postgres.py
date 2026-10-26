"""Check that database/pulse_crm_postgres.sql is a faithful translation of database/pulse_crm.sql.

Expects pulse_crm built in both systems:
  MYSQL_URL     mysql://root:<password>@127.0.0.1:3307/pulse_crm   (docker-compose.yml)
  web/.env.vercel, written by web/setup_supabase.py, holding the read-only PostgreSQL DATABASE_URL
  SUPABASE_DB_URL  the PostgreSQL administrator connection used by setup_supabase.py

Checks, in order:
  1. PostgreSQL object counts and the 305 sample rows
  2. every table and view holds identical data in both systems
  3. the web dashboard renders identical pages from both, through read-only accounts
  4. the seven integrity tests fail in both, with matching errors, and change nothing
  5. the procedures make the same changes in both (convert a lead, win a deal, take a payment)
"""
import os
import re
import secrets
import sys
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import unquote, urlparse

import psycopg
import pymysql

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
import setup_supabase  # noqa: E402

TABLES = ["roles", "users", "industries", "accounts", "contacts", "lead_sources", "leads", "pipeline_stages",
          "opportunities", "products", "opportunity_products", "activities", "campaigns", "campaign_leads",
          "tickets", "invoices", "payments", "opportunity_stage_history"]
VIEWS = ["vw_sales_pipeline", "vw_account_360", "vw_sales_rep_performance", "vw_lead_conversion_by_source",
         "vw_ticket_resolution", "vw_invoice_balance"]
NOW_COLUMNS = {"created_at", "converted_at", "changed_at"}   # set from the clock, so they differ by seconds
# MySQL's INSERT ... SELECT reserves AUTO_INCREMENT values in blocks and leaves gaps; PostgreSQL
# identities do not. The history rows are compared without this internal key.
SURROGATE = {"opportunity_stage_history": {"history_id"}}
failures = []


def check(ok, message):
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def mysql_connect(url, **kw):
    u = urlparse(url)
    return pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username),
                           password=unquote(u.password or ""), database=u.path.lstrip("/"), autocommit=True, **kw)


def norm(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value != 0 else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def rows(cur, name, skip=()):
    cur.execute(f"SELECT * FROM {name}")
    cols = [d[0].lower() for d in cur.description]
    keep = [i for i, c in enumerate(cols) if c not in skip]
    data = sorted(tuple(norm(r[i]) for i in keep) for r in cur.fetchall())
    return [cols[i] for i in keep], data


def compare_data(my, pg, label, skip=()):
    with my.cursor() as mc, pg.cursor() as pc:
        for name in TABLES + VIEWS:
            ignore = set(skip) | SURROGATE.get(name, set())
            mcols, mrows = rows(mc, name, ignore)
            pcols, prows = rows(pc, name, ignore)
            same = mcols == pcols and mrows == prows
            if not same:
                diff = [r for r in mrows if r not in prows][:3] + [("PG",) + r for r in prows if r not in mrows][:3]
                check(False, f"{label}: {name} differs (columns {mcols == pcols}); sample: {diff}")
            else:
                check(True, f"{label}: {name} identical ({len(mrows)} rows)")


def pg_counts(pg):
    with pg.cursor() as cur:
        cur.execute("""
            SELECT (SELECT COUNT(*) FROM information_schema.tables
                     WHERE table_schema = 'pulse_crm' AND table_type = 'BASE TABLE'),
                   (SELECT COUNT(*) FROM information_schema.views WHERE table_schema = 'pulse_crm'),
                   (SELECT COUNT(*) FROM pg_proc WHERE pronamespace = 'pulse_crm'::regnamespace AND prokind = 'p'),
                   (SELECT COUNT(*) FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
                     WHERE c.relnamespace = 'pulse_crm'::regnamespace AND NOT t.tgisinternal),
                   (SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'pulse_crm'::regnamespace AND contype = 'f'),
                   (SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'pulse_crm'::regnamespace AND contype = 'c'),
                   (SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'pulse_crm'::regnamespace AND contype = 'u')""")
        counts = cur.fetchone()
        cur.execute(" UNION ALL ".join(f"SELECT COUNT(*) FROM {t}" for t in TABLES))
        total = sum(r[0] for r in cur.fetchall())
    expected = (18, 6, 5, 1, 31, 34, 14)
    check(tuple(counts) == expected, f"PostgreSQL objects (tables, views, procedures, triggers, FKs, CHECKs, UNIQUEs) "
                                     f"= {tuple(counts)}, expected {expected}")
    check(total == 305, f"PostgreSQL sample rows = {total}, expected 305")


def compare_pages(mysql_web_url, pg_web_url):
    import app as web
    client = web.app.test_client()

    def render(url, path):
        os.environ["DATABASE_URL"] = url
        response = client.get(path)
        return response.status_code, response.get_data(as_text=True)

    for path in ["/", "/pipeline", "/accounts", "/team", "/leads", "/support", "/invoices", "/database"]:
        ms, mh = render(mysql_web_url, path)
        ps, ph = render(pg_web_url, path)
        if path == "/database":   # the first paragraph names the database system on purpose
            mh, ph = (re.sub(r'<p class="lead">.*?</p>', "", h, count=1, flags=re.S) for h in (mh, ph))
        check(ms == ps == 200 and mh == ph, f"web page {path}: MySQL {ms}, PostgreSQL {ps}, "
                                            f"{'identical HTML' if mh == ph else 'HTML differs'}")
        if mh != ph:
            ml, pl = mh.splitlines(), ph.splitlines()
            print("   first difference:", next(((a, b) for a, b in zip(ml, pl) if a != b), None))
    _, health = render(pg_web_url, "/health")
    check('"engine":"PostgreSQL"' in health and '"database":"pulse_crm"' in health, f"/health on PostgreSQL: {health.strip()}")


def integrity_tests(my, pg):
    tests = [
        ("UPDATE leads SET lead_score = 150 WHERE lead_id = 317", 3819, "23514"),
        ("INSERT INTO contacts (account_id, first_name, last_name, email) "
         "VALUES (102, 'Test', 'Duplicate', 'asif.mahmood@indusweave.example')", 1062, "23505"),
        ("INSERT INTO opportunities (opportunity_name, account_id, owner_user_id, stage_id, expected_close_date) "
         "VALUES ('Ghost Deal', 999, 3, 1, '2027-01-01')", 1452, "23503"),
        ("DELETE FROM accounts WHERE account_id = 101", 1451, "23503"),
        ("CALL sp_record_payment(903, 99999999.00, 'Card', 'CARD-TEST-01')", 1644, "45000"),
        ("CALL sp_update_opportunity_stage(411, 'Closed Lost', 3, NULL)", 1644, "45000"),
        ("CALL sp_convert_lead(322, 'Test Deal', 1000.00, '2027-01-01', {out})", 1644, "45000"),
    ]
    for sql_text, my_code, pg_code in tests:
        my_got = pg_got = my_msg = pg_msg = None
        try:
            with my.cursor() as cur:
                cur.execute(sql_text.format(out="@x"))
        except pymysql.MySQLError as e:
            my_got, my_msg = e.args[0], e.args[1]
        try:
            with pg.cursor() as cur:
                cur.execute(sql_text.format(out="NULL"))
        except psycopg.Error as e:
            pg_got, pg_msg = e.sqlstate, e.diag.message_primary
        same_msg = my_code != 1644 or my_msg == pg_msg
        check(my_got == my_code and pg_got == pg_code and same_msg,
              f"integrity test rejected: MySQL {my_got}, PostgreSQL {pg_got} | {sql_text[:60]}"
              + ("" if my_code != 1644 else f" | '{pg_msg}'"))


def procedures(my, pg):
    with my.cursor() as mc, pg.cursor() as pc:
        mc.execute("CALL sp_convert_lead(307, 'Gwadar Port ERP', 2500000.00, '2027-01-31', @new_id)")
        mc.execute("SELECT @new_id")
        my_id = mc.fetchone()[0]
        pc.execute("CALL sp_convert_lead(307, 'Gwadar Port ERP', 2500000.00, '2027-01-31', NULL)")
        pg_id = pc.fetchone()[0]
        # 421 was used up by the failed 'Ghost Deal' insert in both systems, so the new deal is 422
        check(my_id == pg_id is not None, f"sp_convert_lead returns opportunity {my_id} (MySQL) and {pg_id} (PostgreSQL)")

        for cur in (mc, pc):
            cur.execute("CALL sp_update_opportunity_stage(410, 'Closed Won', 2, NULL)")
            cur.execute("CALL sp_record_payment(907, 500000.00, 'Bank Transfer', 'BT-TEST-0410')")

        mc.execute("CALL sp_sales_rep_pipeline(3, @open, @weighted)")
        mc.execute("SELECT @open, @weighted")
        my_out = tuple(norm(v) for v in mc.fetchone())
        pc.execute("CALL sp_sales_rep_pipeline(3, NULL, NULL)")
        pg_out = tuple(norm(v) for v in pc.fetchone())
        check(my_out == pg_out, f"sp_sales_rep_pipeline OUT values: MySQL {my_out}, PostgreSQL {pg_out}")

        mc.execute("CALL sp_account_summary(101)")
        my_sets = [sorted(tuple(norm(v) for v in r) for r in mc.fetchall())]
        mc.nextset()
        my_sets.append(sorted(tuple(norm(v) for v in r) for r in mc.fetchall()))
        while mc.nextset():
            pass
    with pg.transaction(), pg.cursor() as pc:
        pc.execute("CALL sp_account_summary(101)")
        pc.execute("FETCH ALL FROM account_360")
        pg_sets = [sorted(tuple(norm(v) for v in r) for r in pc.fetchall())]
        pc.execute("FETCH ALL FROM open_deals")
        pg_sets.append(sorted(tuple(norm(v) for v in r) for r in pc.fetchall()))
    check(my_sets == pg_sets, f"sp_account_summary result sets: {len(my_sets[0])} + {len(my_sets[1])} rows, "
                              f"{'identical' if my_sets == pg_sets else 'different'}")

    with pg.cursor() as pc:
        pc.execute("SELECT changed_by FROM opportunity_stage_history "
                   "WHERE opportunity_id = 410 AND to_stage_id = 5")
        who = pc.fetchall()
    check(who == [(2,)], f"trigger recorded the stage change by user 2 in PostgreSQL: {who}")


def main():
    mysql_url = os.environ["MYSQL_URL"]
    pg_admin = setup_supabase.admin_url()
    pg_web = setup_supabase.read_env(os.path.join(ROOT, "web", ".env.vercel"))["DATABASE_URL"]

    my = mysql_connect(mysql_url)
    pg = psycopg.connect(pg_admin, autocommit=True, prepare_threshold=None, options="-c search_path=pulse_crm")

    print("== 1. PostgreSQL objects")
    pg_counts(pg)

    print("== 2. Data after the build")
    compare_data(my, pg, "build")

    print("== 3. Web pages through read-only accounts")
    my_password = secrets.token_urlsafe(18)
    sql_text = open(os.path.join(ROOT, "database", "web_readonly_user.sql"), encoding="utf-8").read()
    with my.cursor() as cur:
        for stmt in re.findall(r"^(CREATE USER.*?;|GRANT SELECT.*?;)", sql_text, flags=re.M):
            cur.execute(stmt.replace("replace-with-a-strong-password", my_password))
    u = urlparse(mysql_url)
    compare_pages(f"mysql://pulse_web:{my_password}@{u.hostname}:{u.port}/pulse_crm", pg_web)

    print("== 4. Integrity tests")
    integrity_tests(my, pg)
    compare_data(my, pg, "after the failed tests")

    print("== 5. Procedures")
    procedures(my, pg)
    compare_data(my, pg, "after the procedures", skip=NOW_COLUMNS)

    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
