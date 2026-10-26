"""PulseCRM web dashboard: a Flask app on top of the pulse_crm MySQL database.

Visitors sign in with a web account (database/web_access.sql). Each account has privileges
that decide which pages it may open; accounts with the manage_users privilege create
accounts, grant privileges and reset passwords on the Users page. Passwords are stored
only as salted scrypt hashes, forms carry a CSRF token, and five wrong passwords lock an
account for 15 minutes.

The CRM pages read the reporting views of database/pulse_crm.sql in READ ONLY sessions.
The MySQL account used by the app (database/web_app_user.sql) can read every table but can
change only the sign-in tables.

Environment variables:
  DATABASE_URL      mysql://user:password@host:port/pulse_crm
  DATABASE_CA_CERT  PEM text of the server's CA certificate (turns on verified TLS)
  SECRET_KEY        long random string that signs the session cookie (required to sign in)
"""
import os
import re
import secrets
import ssl
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or None,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),   # Vercel serves the site over HTTPS only
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

GITHUB = "https://github.com/iftikhardba-svg/PulseCRM"
ERD_IMAGE = "https://raw.githubusercontent.com/iftikhardba-svg/PulseCRM/main/docs/erd.png"

# (endpoint, tab label, privilege needed to open it)
NAV = [
    ("overview", "Overview", "view_overview"),
    ("pipeline", "Pipeline", "view_pipeline"),
    ("accounts", "Accounts", "view_accounts"),
    ("team", "Sales Team", "view_team"),
    ("leads", "Leads", "view_leads"),
    ("support", "Support", "view_support"),
    ("invoices", "Invoices", "view_invoices"),
    ("database", "Database", "view_database"),
    ("users", "Users", "manage_users"),
]

TABLES = ["roles", "users", "industries", "accounts", "contacts", "lead_sources", "leads", "campaigns",
          "campaign_leads", "pipeline_stages", "opportunities", "products", "opportunity_products",
          "activities", "opportunity_stage_history", "tickets", "invoices", "payments"]

USERNAME_RULE = re.compile(r"^[a-z0-9._-]{3,40}$")
MIN_PASSWORD_LENGTH = 10
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
DUMMY_HASH = generate_password_hash("not-a-real-password")   # same work for unknown user names


# --------------------------------------------------------------------------- database
class DatabaseUnavailable(Exception):
    pass


def database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def ca_cert():
    return os.environ.get("DATABASE_CA_CERT", "").strip().replace("\\n", "\n")


def connect(read_only=True):
    if not database_url():
        raise DatabaseUnavailable("DATABASE_URL is not set")
    url = urlparse(database_url())
    if ca_cert():
        tls = ssl.create_default_context(cadata=ca_cert())
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
    if read_only:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def fetch(**queries):
    """Run each named SELECT on one READ ONLY connection and return {name: rows}."""
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


def rows(sql, args=()):
    """One parameterised SELECT on a READ ONLY connection."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        conn.close()


@contextmanager
def transaction():
    """A writable connection for the sign-in tables: commits at the end, rolls back on any error."""
    conn = connect(read_only=False)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(cur, account_id, action, detail=None):
    cur.execute("INSERT INTO web_audit_log (account_id, action, detail) VALUES (%s, %s, %s)",
                (account_id, action, detail[:255] if detail else None))


@app.errorhandler(pymysql.err.OperationalError)
@app.errorhandler(DatabaseUnavailable)
def database_unavailable(error):
    app.logger.error("Database error: %s", error)
    return render_template("offline.html", page="offline"), 503


@app.errorhandler(400)
@app.errorhandler(404)
def client_error(error):
    titles = {400: "This form has expired", 404: "Page not found"}
    texts = {400: "Go back, reload the page and try again.", 404: "There is no page at this address."}
    return render_template("message.html", page=None, title=titles[error.code], text=texts[error.code]), error.code


# sort orders and the open-ticket test used by several queries
PRIORITY_ORDER = "CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
LEAD_STATUS_ORDER = ("CASE status WHEN 'New' THEN 1 WHEN 'Contacted' THEN 2 WHEN 'Qualified' THEN 3 "
                     "WHEN 'Unqualified' THEN 4 ELSE 5 END")
IS_OPEN_TICKET = "CASE WHEN status IN ('Open', 'In Progress') THEN 1 ELSE 0 END"


# --------------------------------------------------------------------------- sign-in
ACCOUNT_SQL = """
    SELECT a.account_id, a.username, a.display_name, a.user_id, a.is_active, a.must_change_password,
           a.last_login_at, a.created_at, a.locked_until > NOW() AS locked,
           u.full_name AS crm_name, r.role_name,
           GROUP_CONCAT(ap.privilege_code) AS privileges
    FROM web_accounts a
    LEFT JOIN users u                  ON a.user_id = u.user_id
    LEFT JOIN roles r                  ON u.role_id = r.role_id
    LEFT JOIN web_account_privileges ap ON ap.account_id = a.account_id
    WHERE a.account_id = %s
    GROUP BY a.account_id, a.username, a.display_name, a.user_id, a.is_active, a.must_change_password,
             a.last_login_at, a.created_at, a.locked_until, u.full_name, r.role_name"""


def load_account(account_id):
    found = rows(ACCOUNT_SQL, (account_id,))
    if not found:
        return None
    account = found[0]
    account["privileges"] = set((account["privileges"] or "").split(",")) - {""}
    return account


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def home_endpoint(user):
    """The first tab the account may open."""
    for endpoint, _, privilege in NAV:
        if privilege in user["privileges"]:
            return endpoint
    return "account"


def safe_next(target):
    """Only follow redirects to pages of this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def password_problem(password, confirm, username):
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Passwords need at least {MIN_PASSWORD_LENGTH} characters."
    if password != confirm:
        return "The two passwords do not match."
    if username and username in password.lower():
        return "The password must not contain the user name."
    return None


def requires(privilege):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if privilege not in g.user["privileges"]:
                return render_template("message.html", page=None, title="No access",
                                       text="Your account does not have the privilege to open this page. "
                                            "Ask an administrator if you need it."), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.before_request
def sign_in_required():
    g.user = None
    if request.endpoint in ("health", "static"):
        return None
    if not app.secret_key:
        return render_template("message.html", page=None, title="Sign-in is not set up",
                               text="The SECRET_KEY setting is missing on the server, so nobody can sign in "
                                    "yet. The site owner has to add it."), 503
    if request.method == "POST":
        expected = session.get("csrf")
        if not expected or not secrets.compare_digest(request.form.get("csrf", ""), expected):
            abort(400)
    if session.get("account_id"):
        account = load_account(session["account_id"])
        if account and account["is_active"]:
            g.user = account
        else:
            session.clear()
    if request.endpoint == "login":
        return None
    if g.user is None:
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    if g.user["must_change_password"] and request.endpoint not in ("account", "logout"):
        flash("Choose a new password to continue.", "info")
        return redirect(url_for("account"))
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "health":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for(home_endpoint(g.user)))
    error, username = None, ""
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        found = rows("""SELECT account_id, password_hash, is_active, locked_until > NOW() AS locked
                        FROM web_accounts WHERE username = %s""", (username,))
        account = found[0] if found else None
        password_ok = check_password_hash(account["password_hash"] if account else DUMMY_HASH, password)
        if account and account["locked"]:
            error = f"Too many wrong passwords. This account is locked for up to {LOCK_MINUTES} minutes."
            with transaction() as cur:
                audit(cur, account["account_id"], "login_failed", "account locked")
        elif account and password_ok and account["is_active"]:
            with transaction() as cur:
                cur.execute("""UPDATE web_accounts
                               SET failed_logins = 0, locked_until = NULL, last_login_at = NOW()
                               WHERE account_id = %s""", (account["account_id"],))
                audit(cur, account["account_id"], "login")
            session.clear()
            session.permanent = True
            session["account_id"] = account["account_id"]
            user = load_account(account["account_id"])
            return redirect(safe_next(request.args.get("next")) or url_for(home_endpoint(user)))
        else:
            with transaction() as cur:
                if account:
                    # the CASE for locked_until reads failed_logins before it is changed on the next line
                    cur.execute(f"""UPDATE web_accounts
                                    SET locked_until  = CASE WHEN failed_logins + 1 >= {MAX_FAILED_LOGINS}
                                                             THEN NOW() + INTERVAL {LOCK_MINUTES} MINUTE
                                                             ELSE locked_until END,
                                        failed_logins = CASE WHEN failed_logins + 1 >= {MAX_FAILED_LOGINS}
                                                             THEN 0 ELSE failed_logins + 1 END
                                    WHERE account_id = %s""", (account["account_id"],))
                audit(cur, account["account_id"] if account else None, "login_failed",
                      None if account else "unknown user name")
            error = "Wrong user name or password."
    return render_template("login.html", page="login", error=error, username=username)


@app.route("/logout", methods=["POST"])
def logout():
    with transaction() as cur:
        audit(cur, g.user["account_id"], "logout")
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        stored = rows("SELECT password_hash FROM web_accounts WHERE account_id = %s", (g.user["account_id"],))[0]
        if not check_password_hash(stored["password_hash"], current):
            problem = "Your current password is not correct."
        elif new == current:
            problem = "The new password must be different from the current one."
        else:
            problem = password_problem(new, request.form.get("confirm", ""), g.user["username"])
        if problem:
            flash(problem, "error")
        else:
            with transaction() as cur:
                cur.execute("""UPDATE web_accounts SET password_hash = %s, must_change_password = FALSE
                               WHERE account_id = %s""", (generate_password_hash(new), g.user["account_id"]))
                audit(cur, g.user["account_id"], "password_changed")
            flash("Your password has been changed.", "ok")
            return redirect(url_for(home_endpoint(g.user)))
    return render_template("account.html", page="account")


# --------------------------------------------------------------------------- user management
PRIVILEGES_SQL = "SELECT privilege_code, privilege_name, description FROM web_privileges ORDER BY sort_order"


def crm_staff(account_id):
    """Active CRM users without a web account (plus the one linked to account_id), with role defaults."""
    staff = rows("""
        SELECT u.user_id, u.full_name, r.role_name, GROUP_CONCAT(rp.privilege_code) AS defaults
        FROM users u
        JOIN roles r                    ON u.role_id = r.role_id
        LEFT JOIN web_role_privileges rp ON rp.role_id = r.role_id
        LEFT JOIN web_accounts a         ON a.user_id = u.user_id
        WHERE u.is_active = TRUE AND (a.account_id IS NULL OR a.account_id = %s)
        GROUP BY u.user_id, u.full_name, r.role_name
        ORDER BY u.full_name""", (account_id,))
    for person in staff:
        person["defaults"] = person["defaults"] or ""
    return staff


def other_admins(account_id):
    """Active accounts, other than this one, that can manage users."""
    return rows("""SELECT COUNT(*) AS n
                   FROM web_accounts a
                   JOIN web_account_privileges ap ON ap.account_id = a.account_id
                                                AND ap.privilege_code = 'manage_users'
                   WHERE a.is_active = TRUE AND a.account_id <> %s""", (account_id,))[0]["n"]


def form_user_id():
    value = request.form.get("user_id", "")
    return int(value) if value.isdigit() else None


@app.route("/users", methods=["GET", "POST"])
@requires("manage_users")
def users():
    privileges = rows(PRIVILEGES_SQL)
    valid = {p["privilege_code"] for p in privileges}
    me = g.user["account_id"]
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        display = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        chosen = set(request.form.getlist("privileges")) & valid
        if not USERNAME_RULE.match(username):
            problem = "User names have 3 to 40 characters: lower-case letters, digits, dot, dash or underscore."
        elif not display:
            problem = "Enter the person's name."
        else:
            problem = password_problem(password, password, username)
        if not problem:
            try:
                with transaction() as cur:
                    cur.execute("""INSERT INTO web_accounts (username, display_name, user_id, password_hash,
                                                             must_change_password)
                                   VALUES (%s, %s, %s, %s, TRUE)""",
                                (username, display, form_user_id(), generate_password_hash(password)))
                    new_id = cur.lastrowid
                    for code in sorted(chosen):
                        cur.execute("""INSERT INTO web_account_privileges (account_id, privilege_code, granted_by)
                                       VALUES (%s, %s, %s)""", (new_id, code, me))
                    audit(cur, me, "account_created", f"{username}: {', '.join(sorted(chosen)) or 'no privileges'}")
                flash(f"Account {username} created. Give them the temporary password; they must choose their "
                      "own when they first sign in.", "ok")
                return redirect(url_for("users"))
            except pymysql.err.IntegrityError as error:
                problem = ("That user name is already taken." if "uq_web_accounts_username" in str(error)
                           else "That CRM staff member already has an account.")
        flash(problem, "error")
    accounts = rows("""
        SELECT a.account_id, a.username, a.display_name, a.is_active, a.must_change_password, a.last_login_at,
               a.locked_until > NOW() AS locked, u.full_name AS crm_name, r.role_name,
               GROUP_CONCAT(p.privilege_name ORDER BY p.sort_order SEPARATOR ', ') AS privilege_names
        FROM web_accounts a
        LEFT JOIN users u                   ON a.user_id = u.user_id
        LEFT JOIN roles r                   ON u.role_id = r.role_id
        LEFT JOIN web_account_privileges ap ON ap.account_id = a.account_id
        LEFT JOIN web_privileges p          ON p.privilege_code = ap.privilege_code
        GROUP BY a.account_id, a.username, a.display_name, a.is_active, a.must_change_password, a.last_login_at,
                 a.locked_until, u.full_name, r.role_name
        ORDER BY a.username""")
    log = rows("""SELECT l.created_at, a.username, l.action, l.detail
                  FROM web_audit_log l
                  LEFT JOIN web_accounts a ON a.account_id = l.account_id
                  ORDER BY l.log_id DESC
                  LIMIT 25""")
    return render_template("users.html", page="users", accounts=accounts, privileges=privileges,
                           staff=crm_staff(0), log=log, form=request.form)


@app.route("/users/<int:account_id>", methods=["GET", "POST"])
@requires("manage_users")
def user_edit(account_id):
    target = load_account(account_id)
    if not target:
        abort(404)
    privileges = rows(PRIVILEGES_SQL)
    valid = {p["privilege_code"] for p in privileges}
    me = g.user["account_id"]
    is_self = account_id == me
    if request.method == "POST":
        display = request.form.get("display_name", "").strip()
        active = request.form.get("is_active") == "on"
        chosen = set(request.form.getlist("privileges")) & valid
        new_password = request.form.get("new_password", "")
        was_admin = target["is_active"] and "manage_users" in target["privileges"]
        stays_admin = active and "manage_users" in chosen
        problem = None
        if not display:
            problem = "Enter the person's name."
        elif is_self and not active:
            problem = "You cannot deactivate your own account."
        elif is_self and "manage_users" not in chosen:
            problem = "You cannot remove Manage users from your own account."
        elif was_admin and not stays_admin and other_admins(account_id) == 0:
            problem = "At least one active account must keep the Manage users privilege."
        elif new_password:
            problem = password_problem(new_password, new_password, target["username"])
        if not problem:
            try:
                with transaction() as cur:
                    cur.execute("""UPDATE web_accounts SET display_name = %s, user_id = %s, is_active = %s
                                   WHERE account_id = %s""", (display, form_user_id(), active, account_id))
                    for code in sorted(target["privileges"] - chosen):
                        cur.execute("""DELETE FROM web_account_privileges
                                       WHERE account_id = %s AND privilege_code = %s""", (account_id, code))
                    for code in sorted(chosen - target["privileges"]):
                        cur.execute("""INSERT INTO web_account_privileges (account_id, privilege_code, granted_by)
                                       VALUES (%s, %s, %s)""", (account_id, code, me))
                    changes = [f"+{c}" for c in sorted(chosen - target["privileges"])]
                    changes += [f"-{c}" for c in sorted(target["privileges"] - chosen)]
                    if active != bool(target["is_active"]):
                        changes.append("activated" if active else "deactivated")
                    if request.form.get("unlock") == "on":
                        cur.execute("""UPDATE web_accounts SET failed_logins = 0, locked_until = NULL
                                       WHERE account_id = %s""", (account_id,))
                        changes.append("unlocked")
                    audit(cur, me, "account_updated", f"{target['username']}: {', '.join(changes) or 'details'}")
                    if new_password:
                        cur.execute("""UPDATE web_accounts
                                       SET password_hash = %s, must_change_password = TRUE,
                                           failed_logins = 0, locked_until = NULL
                                       WHERE account_id = %s""", (generate_password_hash(new_password), account_id))
                        audit(cur, me, "password_reset", target["username"])
                flash(f"Account {target['username']} saved.", "ok")
                return redirect(url_for("users"))
            except pymysql.err.IntegrityError:
                problem = "That CRM staff member already has an account."
        flash(problem, "error")
    return render_template("user_edit.html", page="users", target=target, privileges=privileges,
                           staff=crm_staff(account_id), is_self=is_self)


@app.route("/users/<int:account_id>/delete", methods=["POST"])
@requires("manage_users")
def user_delete(account_id):
    target = load_account(account_id)
    if not target:
        abort(404)
    if account_id == g.user["account_id"]:
        flash("You cannot delete your own account.", "error")
    elif target["is_active"] and "manage_users" in target["privileges"] and other_admins(account_id) == 0:
        flash("At least one active account must keep the Manage users privilege.", "error")
    else:
        with transaction() as cur:
            cur.execute("DELETE FROM web_accounts WHERE account_id = %s", (account_id,))
            audit(cur, g.user["account_id"], "account_deleted", target["username"])
        flash(f"Account {target['username']} deleted.", "ok")
        return redirect(url_for("users"))
    return redirect(url_for("user_edit", account_id=account_id))


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


@app.template_filter("when")
def when(value):
    return value.strftime("%d %b %Y %H:%M") if isinstance(value, datetime) else "–"


@app.context_processor
def layout():
    user = g.get("user")
    tabs = [(endpoint, label) for endpoint, label, privilege in NAV if user and privilege in user["privileges"]]
    return {"nav": tabs, "github": GITHUB, "user": user, "csrf_token": csrf_token}


def share(part, whole):
    """Width of a CSS bar as a percentage of the largest value."""
    return 0 if not whole else max(2, round(float(part) * 100 / float(whole)))


# --------------------------------------------------------------------------- CRM pages
@app.route("/")
@requires("view_overview")
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
            ORDER BY won_revenue DESC, open_pipeline_value DESC, account_name
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
@requires("view_pipeline")
def pipeline():
    data = fetch(
        open_deals="""
            SELECT opportunity_name, account_name, owner_name, stage_name, win_probability,
                   amount, weighted_amount, expected_close_date
            FROM vw_sales_pipeline
            WHERE is_closed = FALSE
            ORDER BY stage_order DESC, amount DESC, opportunity_id""",
        closed_deals="""
            SELECT opportunity_name, account_name, owner_name, stage_name, is_won, amount, actual_close_date
            FROM vw_sales_pipeline
            WHERE is_closed = TRUE
            ORDER BY actual_close_date DESC, amount DESC, opportunity_id""",
    )
    return render_template("pipeline.html", page="pipeline", **data)


@app.route("/accounts")
@requires("view_accounts")
def accounts():
    data = fetch(rows="""
        SELECT account_name, industry_name, account_type, city, account_owner, contacts,
               open_opportunities, open_pipeline_value, won_revenue, open_tickets
        FROM vw_account_360
        ORDER BY won_revenue DESC, open_pipeline_value DESC, account_name""")
    return render_template("accounts.html", page="accounts", **data)


@app.route("/team")
@requires("view_team")
def team():
    data = fetch(rows="""
        SELECT sales_rep, role_name, leads_owned, leads_converted, opportunities, won_deals,
               lost_deals, won_revenue, open_pipeline, win_rate_pct
        FROM vw_sales_rep_performance
        ORDER BY won_revenue DESC, open_pipeline DESC, sales_rep""")
    top = max((r["won_revenue"] for r in data["rows"]), default=0)
    for r in data["rows"]:
        r["bar"] = share(r["won_revenue"], top)
    return render_template("team.html", page="team", **data)


@app.route("/leads")
@requires("view_leads")
def leads():
    data = fetch(
        sources="""
            SELECT source_name, total_leads, converted_leads, conversion_rate_pct, avg_lead_score
            FROM vw_lead_conversion_by_source
            ORDER BY conversion_rate_pct DESC, total_leads DESC, source_name""",
        statuses=f"""
            SELECT status, COUNT(*) AS leads
            FROM leads
            GROUP BY status
            ORDER BY {LEAD_STATUS_ORDER}""",
        hot="""
            SELECT CONCAT(l.first_name, ' ', l.last_name) AS lead_name, l.company_name, ls.source_name,
                   l.lead_score, l.status, u.full_name AS owner_name
            FROM leads l
            JOIN lead_sources ls ON l.source_id = ls.source_id
            JOIN users u         ON l.owner_user_id = u.user_id
            WHERE l.status IN ('New', 'Contacted', 'Qualified')
            ORDER BY l.lead_score DESC, l.lead_id
            LIMIT 10""",
    )
    top = max((r["leads"] for r in data["statuses"]), default=0)
    for r in data["statuses"]:
        r["bar"] = share(r["leads"], top)
    return render_template("leads.html", page="leads", **data)


@app.route("/support")
@requires("view_support")
def support():
    data = fetch(
        priorities=f"""
            SELECT priority, COUNT(*) AS tickets,
                   SUM({IS_OPEN_TICKET})               AS open_tickets,
                   ROUND(AVG(resolution_hours), 1)     AS avg_hours,
                   ROUND(AVG(satisfaction_score), 1)   AS avg_score
            FROM vw_ticket_resolution
            GROUP BY priority
            ORDER BY {PRIORITY_ORDER}""",
        tickets=f"""
            SELECT ticket_id, account_name, subject, priority, status, assigned_to,
                   opened_at, resolution_hours, satisfaction_score
            FROM vw_ticket_resolution
            ORDER BY {IS_OPEN_TICKET} DESC, {PRIORITY_ORDER}, opened_at DESC, ticket_id""",
    )
    return render_template("support.html", page="support", **data)


@app.route("/invoices")
@requires("view_invoices")
def invoices():
    data = fetch(rows="""
        SELECT invoice_number, account_name, opportunity_name, invoice_date, due_date,
               total_amount, amount_paid, balance_due, status
        FROM vw_invoice_balance
        ORDER BY balance_due DESC, invoice_date DESC, invoice_number""")
    return render_template("invoices.html", page="invoices", **data)


@app.route("/database")
@requires("view_database")
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
