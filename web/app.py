"""PulseCRM web dashboard: a read-only Flask app on top of the pulse_crm MySQL database.

Every page reads the reporting views and tables with SELECT statements only. The
database account used by the app has SELECT privileges and nothing else, and each
session is also set to READ ONLY, so the dashboard cannot change data.

Environment variables:
  DATABASE_URL      mysql://user:password@host:port/pulse_crm
  DATABASE_CA_CERT  PEM text of the server's CA certificate (turns on verified TLS)
"""
import os
import ssl
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
from flask import Flask, jsonify, render_template

app = Flask(__name__)

GITHUB = "https://github.com/iftikhardba-svg/PulseCRM"
ERD_IMAGE = "https://raw.githubusercontent.com/iftikhardba-svg/PulseCRM/main/docs/erd.png"

NAV = [
    ("overview", "Overview"),
    ("pipeline", "Pipeline"),
    ("accounts", "Accounts"),
    ("team", "Sales Team"),
    ("leads", "Leads"),
    ("support", "Support"),
    ("invoices", "Invoices"),
    ("database", "Database"),
]

TABLES = ["roles", "users", "industries", "accounts", "contacts", "lead_sources", "leads", "campaigns",
          "campaign_leads", "pipeline_stages", "opportunities", "products", "opportunity_products",
          "activities", "opportunity_stage_history", "tickets", "invoices", "payments"]


# --------------------------------------------------------------------------- database
class DatabaseUnavailable(Exception):
    pass


def connect():
    if not os.environ.get("DATABASE_URL"):
        raise DatabaseUnavailable("DATABASE_URL is not set")
    url = urlparse(os.environ["DATABASE_URL"])
    ca = os.environ.get("DATABASE_CA_CERT", "").strip()
    if ca:
        tls = ssl.create_default_context(cadata=ca.replace("\\n", "\n"))
    elif parse_qs(url.query).get("ssl-mode", [""])[0].upper() == "REQUIRED":
        # Encrypted but unverified; set DATABASE_CA_CERT to verify the server
        tls = ssl.create_default_context()
        tls.check_hostname = False
        tls.verify_mode = ssl.CERT_NONE
    else:
        tls = None
    conn = pymysql.connect(host=url.hostname, port=url.port or 3306,
                           user=unquote(url.username or ""), password=unquote(url.password or ""),
                           database=url.path.lstrip("/") or "pulse_crm", charset="utf8mb4", ssl=tls,
                           connect_timeout=10, read_timeout=20, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def fetch(**queries):
    """Run each named SELECT on one connection and return {name: rows}."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            result = {}
            for name, sql in queries.items():
                cur.execute(sql)
                result[name] = cur.fetchall()
            return result
    finally:
        conn.close()


@app.errorhandler(pymysql.err.OperationalError)
@app.errorhandler(DatabaseUnavailable)
def database_unavailable(error):
    app.logger.error("Database error: %s", error)
    return render_template("offline.html", page="offline"), 503


# --------------------------------------------------------------------------- formatting
@app.template_filter("pkr")
def pkr(value):
    return "–" if value is None else f"PKR {float(value):,.0f}"


@app.template_filter("amount")
def amount(value):
    return "–" if value is None else f"{float(value):,.0f}"


@app.template_filter("num")
def num(value, digits=0):
    if value is None:
        return "–"
    return f"{float(value):,.{digits}f}" if isinstance(value, (float, Decimal)) else f"{value:,}"


@app.template_filter("pct")
def pct(value):
    return "–" if value is None else f"{float(value):.1f}%"


@app.template_filter("day")
def day(value):
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    return "–" if value is None else value


@app.context_processor
def layout():
    return {"nav": NAV, "github": GITHUB}


def share(part, whole):
    """Width of a CSS bar as a percentage of the largest value."""
    return 0 if not whole else max(2, round(float(part) * 100 / float(whole)))


# --------------------------------------------------------------------------- pages
@app.route("/")
def overview():
    data = fetch(
        kpi="""
            SELECT (SELECT COUNT(*) FROM accounts)                                            AS accounts,
                   (SELECT COUNT(*) FROM accounts WHERE account_type = 'Customer')            AS customers,
                   (SELECT COUNT(*) FROM leads)                                               AS leads,
                   (SELECT COUNT(*) FROM vw_sales_pipeline WHERE is_closed = FALSE)           AS open_deals,
                   (SELECT COALESCE(SUM(amount), 0) FROM vw_sales_pipeline
                     WHERE is_closed = FALSE)                                                 AS open_pipeline,
                   (SELECT COALESCE(SUM(weighted_amount), 0) FROM vw_sales_pipeline
                     WHERE is_closed = FALSE)                                                 AS weighted_pipeline,
                   (SELECT COALESCE(SUM(amount), 0) FROM vw_sales_pipeline WHERE is_won = TRUE) AS won_revenue,
                   (SELECT COUNT(*) FROM tickets WHERE status IN ('Open', 'In Progress'))     AS open_tickets,
                   (SELECT COALESCE(SUM(balance_due), 0) FROM vw_invoice_balance
                     WHERE status <> 'Cancelled')                                             AS balance_due""",
        stages="""
            SELECT s.stage_name, s.win_probability, s.is_closed, s.is_won,
                   COUNT(o.opportunity_id) AS deals, COALESCE(SUM(o.amount), 0) AS amount
            FROM pipeline_stages s
            LEFT JOIN opportunities o ON o.stage_id = s.stage_id
            GROUP BY s.stage_id, s.stage_name, s.stage_order, s.win_probability, s.is_closed, s.is_won
            ORDER BY s.stage_order""",
        top_accounts="""
            SELECT account_name, industry_name, account_type, won_revenue, open_pipeline_value
            FROM vw_account_360
            ORDER BY won_revenue DESC, open_pipeline_value DESC
            LIMIT 5""",
        sources="""
            SELECT source_name, total_leads, converted_leads, conversion_rate_pct
            FROM vw_lead_conversion_by_source
            ORDER BY total_leads DESC, source_name""",
    )
    top = max((r["amount"] for r in data["stages"]), default=0)
    for r in data["stages"]:
        r["bar"] = share(r["amount"], top)
    top = max((r["total_leads"] for r in data["sources"]), default=0)
    for r in data["sources"]:
        r["bar"] = share(r["total_leads"], top)
    kpi = data.pop("kpi")[0]
    return render_template("overview.html", page="overview", kpi=kpi, **data)


@app.route("/pipeline")
def pipeline():
    data = fetch(
        open_deals="""
            SELECT opportunity_name, account_name, owner_name, stage_name, win_probability,
                   amount, weighted_amount, expected_close_date
            FROM vw_sales_pipeline
            WHERE is_closed = FALSE
            ORDER BY stage_order DESC, amount DESC""",
        closed_deals="""
            SELECT opportunity_name, account_name, owner_name, stage_name, is_won, amount, actual_close_date
            FROM vw_sales_pipeline
            WHERE is_closed = TRUE
            ORDER BY actual_close_date DESC, amount DESC""",
    )
    return render_template("pipeline.html", page="pipeline", **data)


@app.route("/accounts")
def accounts():
    data = fetch(rows="""
        SELECT account_name, industry_name, account_type, city, account_owner, contacts,
               open_opportunities, open_pipeline_value, won_revenue, open_tickets
        FROM vw_account_360
        ORDER BY won_revenue DESC, open_pipeline_value DESC, account_name""")
    return render_template("accounts.html", page="accounts", **data)


@app.route("/team")
def team():
    data = fetch(rows="""
        SELECT sales_rep, role_name, leads_owned, leads_converted, opportunities, won_deals,
               lost_deals, won_revenue, open_pipeline, win_rate_pct
        FROM vw_sales_rep_performance
        ORDER BY won_revenue DESC, open_pipeline DESC""")
    top = max((r["won_revenue"] for r in data["rows"]), default=0)
    for r in data["rows"]:
        r["bar"] = share(r["won_revenue"], top)
    return render_template("team.html", page="team", **data)


@app.route("/leads")
def leads():
    data = fetch(
        sources="""
            SELECT source_name, total_leads, converted_leads, conversion_rate_pct, avg_lead_score
            FROM vw_lead_conversion_by_source
            ORDER BY conversion_rate_pct DESC, total_leads DESC""",
        statuses="""
            SELECT status, COUNT(*) AS leads
            FROM leads
            GROUP BY status
            ORDER BY FIELD(status, 'New', 'Contacted', 'Qualified', 'Unqualified', 'Converted')""",
        hot="""
            SELECT CONCAT(l.first_name, ' ', l.last_name) AS lead_name, l.company_name, ls.source_name,
                   l.lead_score, l.status, u.full_name AS owner_name
            FROM leads l
            JOIN lead_sources ls ON l.source_id = ls.source_id
            JOIN users u         ON l.owner_user_id = u.user_id
            WHERE l.status IN ('New', 'Contacted', 'Qualified')
            ORDER BY l.lead_score DESC
            LIMIT 10""",
    )
    top = max((r["leads"] for r in data["statuses"]), default=0)
    for r in data["statuses"]:
        r["bar"] = share(r["leads"], top)
    return render_template("leads.html", page="leads", **data)


@app.route("/support")
def support():
    data = fetch(
        priorities="""
            SELECT priority, COUNT(*) AS tickets,
                   SUM(status IN ('Open', 'In Progress')) AS open_tickets,
                   ROUND(AVG(resolution_hours), 1)        AS avg_hours,
                   ROUND(AVG(satisfaction_score), 1)      AS avg_score
            FROM vw_ticket_resolution
            GROUP BY priority
            ORDER BY FIELD(priority, 'Critical', 'High', 'Medium', 'Low')""",
        tickets="""
            SELECT ticket_id, account_name, subject, priority, status, assigned_to,
                   opened_at, resolution_hours, satisfaction_score
            FROM vw_ticket_resolution
            ORDER BY (status IN ('Open', 'In Progress')) DESC,
                     FIELD(priority, 'Critical', 'High', 'Medium', 'Low'), opened_at DESC""",
    )
    return render_template("support.html", page="support", **data)


@app.route("/invoices")
def invoices():
    data = fetch(rows="""
        SELECT invoice_number, account_name, opportunity_name, invoice_date, due_date,
               total_amount, amount_paid, balance_due, status
        FROM vw_invoice_balance
        ORDER BY balance_due DESC, invoice_date DESC""")
    return render_template("invoices.html", page="invoices", **data)


@app.route("/database")
def database():
    counts = " UNION ALL ".join(f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in TABLES)
    data = fetch(tables=counts, version="SELECT VERSION() AS version")
    total = sum(r["row_count"] for r in data["tables"])
    return render_template("database.html", page="database", tables=data["tables"], total=total,
                           version=data["version"][0]["version"], erd=ERD_IMAGE)


@app.route("/health")
def health():
    row = fetch(n="SELECT DATABASE() AS db, VERSION() AS version, COUNT(*) AS accounts FROM accounts")["n"][0]
    return jsonify(status="ok", database=row["db"], mysql=row["version"], accounts=row["accounts"])


if __name__ == "__main__":
    app.run(debug=True)
