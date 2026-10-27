"""PulseCRM web dashboard: a Flask app on top of the pulse_crm MySQL database.

Visitors sign in with a web account (database/web_access.sql). Each account has privileges
that decide which pages it may open and which records it may add, edit or delete; accounts
with the manage_users privilege create accounts, grant privileges and reset passwords on the
Users page. Passwords are stored only as salted scrypt hashes and forms carry a CSRF token.
Wrong passwords are throttled per network address: 5 for one account, or 20 in total, block
that address for 15 minutes, while people elsewhere can still sign in to the same account.
A Content-Security-Policy lets only this site's own scripts run.

The CRM pages read the reporting views of database/pulse_crm.sql in READ ONLY sessions.
The MySQL account used by the app (database/web_app_user.sql) connects over TLS only and can
change the CRM tables (not the stage history) and the sign-in tables, but not the schema.

Environment variables:
  DATABASE_URL      mysql://user:password@host:port/pulse_crm[?ssl-mode=REQUIRED]
  DATABASE_CA_CERT  PEM text of the server's CA certificate (turns on verified TLS)
  SECRET_KEY        long random string that signs the session cookie (required to sign in)
"""
import os
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

import pymysql
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import crud
from db import DatabaseUnavailable, audit, fetch, rows, transaction

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
THROTTLE_MINUTES = 15
MAX_FAILURES_PER_ACCOUNT = 5     # wrong passwords for one account from one network address
MAX_FAILURES_PER_ADDRESS = 20    # wrong passwords from one network address, for any accounts
DUMMY_HASH = generate_password_hash("not-a-real-password")   # same work for unknown user names


# --------------------------------------------------------------------------- database
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
           a.last_login_at, a.created_at, u.full_name AS crm_name, r.role_name,
           GROUP_CONCAT(ap.privilege_code) AS privileges
    FROM web_accounts a
    LEFT JOIN users u                  ON a.user_id = u.user_id
    LEFT JOIN roles r                  ON u.role_id = r.role_id
    LEFT JOIN web_account_privileges ap ON ap.account_id = a.account_id
    WHERE a.account_id = %s
    GROUP BY a.account_id, a.username, a.display_name, a.user_id, a.is_active, a.must_change_password,
             a.last_login_at, a.created_at, u.full_name, r.role_name"""


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


def client_ip():
    """The visitor's network address. Vercel's proxy sets X-Real-IP itself, so it cannot be forged there;
    anywhere else the header is ignored and the address of the direct connection is used."""
    if os.environ.get("VERCEL"):
        forwarded = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0]
        if forwarded.strip():
            return forwarded.strip()[:45]
    return (request.remote_addr or "unknown")[:45]


def sign_in_blocked(ip, account_id):
    """True after too many recent wrong passwords from this address: for this account, or for any accounts."""
    found = rows(f"""SELECT COUNT(*) AS from_address, COALESCE(SUM(account_id = %s), 0) AS for_account
                     FROM web_login_failures
                     WHERE ip_address = %s AND failed_at > NOW() - INTERVAL {THROTTLE_MINUTES} MINUTE""",
                 (account_id, ip))[0]
    return found["from_address"] >= MAX_FAILURES_PER_ADDRESS or found["for_account"] >= MAX_FAILURES_PER_ACCOUNT


def blocked_addresses(account_id=None):
    """{account_id: [addresses currently blocked for it]}, for one account or for all of them."""
    blocked = {}
    for r in rows(f"""SELECT account_id, ip_address FROM web_login_failures
                      WHERE account_id IS NOT NULL AND (%s IS NULL OR account_id = %s)
                        AND failed_at > NOW() - INTERVAL {THROTTLE_MINUTES} MINUTE
                      GROUP BY account_id, ip_address
                      HAVING COUNT(*) >= {MAX_FAILURES_PER_ACCOUNT}""", (account_id, account_id)):
        blocked.setdefault(r["account_id"], []).append(r["ip_address"])
    return blocked


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


def no_access():
    return render_template("message.html", page=None, title="No access",
                           text="Your account does not have the privilege for this. "
                                "Ask an administrator if you need it."), 403


def requires(privilege):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if privilege not in g.user["privileges"]:
                return no_access()
            return view(*args, **kwargs)
        return wrapped
    return decorator


# privilege codes are <action>_<segment>, for example view_accounts, add_accounts, delete_accounts
ACTIONS = ("view", "add", "edit", "delete")


def can(action, segment):
    user = g.get("user")
    return bool(user) and f"{action}_{segment}" in user["privileges"]


def privilege_matrix(privileges):
    """Rows of (segment label, [(action, code or None), ...]) for the privilege grid on the Users pages."""
    codes = {p["privilege_code"] for p in privileges}
    return [(label, [(action, f"{action}_{segment}" if f"{action}_{segment}" in codes else None)
                     for action in ACTIONS])
            for segment, label, _ in NAV if segment != "users"]


def privilege_summary(codes):
    """'Overview · Pipeline (view, add, edit) · Users' for a set of privilege codes."""
    parts = []
    for segment, label, _ in NAV:
        if segment == "users":
            if "manage_users" in codes:
                parts.append("Users")
            continue
        granted = [action for action in ACTIONS if f"{action}_{segment}" in codes]
        if granted == ["view"]:
            parts.append(label)
        elif granted:
            parts.append(f"{label} ({', '.join(granted)})")
    return " · ".join(parts) or "none"


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


# Scripts run only from <script> tags that carry this response's nonce: no inline event handlers, no
# other sites. Styles may be inline (the templates use style attributes); images may also come from GitHub.
CSP = ("default-src 'none'; script-src 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: https://raw.githubusercontent.com; form-action 'self'; "
       "frame-ancestors 'none'; base-uri 'none'")


def csp_nonce():
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


@app.after_request
def security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP.format(nonce=csp_nonce()))
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
        ip = client_ip()
        found = rows("SELECT account_id, password_hash, is_active FROM web_accounts WHERE username = %s", (username,))
        account = found[0] if found else None
        account_id = account["account_id"] if account else None
        if sign_in_blocked(ip, account_id):
            # the password is not checked at all, so a blocked address learns nothing by guessing
            error = (f"Too many wrong passwords from your network. Wait up to {THROTTLE_MINUTES} minutes, "
                     "or ask an administrator to clear the block.")
            return render_template("login.html", page="login", error=error, username=username), 429
        password_ok = check_password_hash(account["password_hash"] if account else DUMMY_HASH, password)
        if account and password_ok and account["is_active"]:
            with transaction() as cur:
                cur.execute("UPDATE web_accounts SET last_login_at = NOW() WHERE account_id = %s", (account_id,))
                cur.execute("DELETE FROM web_login_failures WHERE ip_address = %s AND account_id = %s",
                            (ip, account_id))
                audit(cur, account_id, "login")
            session.clear()
            session.permanent = True
            session["account_id"] = account_id
            user = load_account(account_id)
            return redirect(safe_next(request.args.get("next")) or url_for(home_endpoint(user)))
        with transaction() as cur:
            cur.execute("DELETE FROM web_login_failures WHERE failed_at < NOW() - INTERVAL 1 DAY")
            cur.execute("INSERT INTO web_login_failures (ip_address, account_id) VALUES (%s, %s)", (ip, account_id))
            audit(cur, account_id, "login_failed", f"from {ip}" if account else f"unknown user name, from {ip}")
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
                    audit(cur, me, "account_created", f"{username}: {privilege_summary(chosen)}")
                flash(f"Account {username} created. Give them the temporary password; they must choose their "
                      "own when they first sign in.", "ok")
                return redirect(url_for("users"))
            except pymysql.err.IntegrityError as error:
                problem = ("That user name is already taken." if "uq_web_accounts_username" in str(error)
                           else "That CRM staff member already has an account.")
        flash(problem, "error")
    accounts = rows("""
        SELECT a.account_id, a.username, a.display_name, a.is_active, a.must_change_password, a.last_login_at,
               u.full_name AS crm_name, r.role_name, GROUP_CONCAT(ap.privilege_code) AS codes
        FROM web_accounts a
        LEFT JOIN users u                   ON a.user_id = u.user_id
        LEFT JOIN roles r                   ON u.role_id = r.role_id
        LEFT JOIN web_account_privileges ap ON ap.account_id = a.account_id
        GROUP BY a.account_id, a.username, a.display_name, a.is_active, a.must_change_password, a.last_login_at,
                 u.full_name, r.role_name
        ORDER BY a.username""")
    blocked = blocked_addresses()
    for a in accounts:
        a["privilege_summary"] = privilege_summary(set((a["codes"] or "").split(",")))
        a["blocked"] = len(blocked.get(a["account_id"], []))
    log = rows("""SELECT l.created_at, a.username, l.action, l.detail
                  FROM web_audit_log l
                  LEFT JOIN web_accounts a ON a.account_id = l.account_id
                  ORDER BY l.log_id DESC
                  LIMIT 25""")
    return render_template("users.html", page="users", accounts=accounts, matrix=privilege_matrix(privileges),
                           staff=crm_staff(0), log=log, form=request.form,
                           checked=set(request.form.getlist("privileges")))


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
                    if request.form.get("unlock") == "on" or new_password:
                        cur.execute("DELETE FROM web_login_failures WHERE account_id = %s", (account_id,))
                        if cur.rowcount and request.form.get("unlock") == "on":
                            changes.append("sign-in block cleared")
                    audit(cur, me, "account_updated", f"{target['username']}: {', '.join(changes) or 'details'}")
                    if new_password:
                        cur.execute("""UPDATE web_accounts SET password_hash = %s, must_change_password = TRUE
                                       WHERE account_id = %s""", (generate_password_hash(new_password), account_id))
                        audit(cur, me, "password_reset", target["username"])
                flash(f"Account {target['username']} saved.", "ok")
                return redirect(url_for("users"))
            except pymysql.err.IntegrityError:
                problem = "That CRM staff member already has an account."
        flash(problem, "error")
    return render_template("user_edit.html", page="users", target=target, matrix=privilege_matrix(privileges),
                           staff=crm_staff(account_id), is_self=is_self, checked=target["privileges"],
                           blocked=blocked_addresses(account_id).get(account_id, []))


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


# --------------------------------------------------------------------------- add, edit and delete CRM records
def database_refused(error):
    """MySQL refused the statement (a rule, a key, a procedure). Connection problems re-raise."""
    code = error.args[0] if error.args else 0
    if 2000 <= code < 3000:               # client-side codes: the server could not be reached
        raise error
    return crud.explain(error)


def set_crm_user(cur):
    """Tell trg_opportunities_stage_history which CRM user makes the change (the linked staff member)."""
    cur.execute("SET @crm_user_id = %s", (g.user["user_id"],))


def data_table(table, action):
    """(table info, segment) when the user may do action on table; otherwise None."""
    info = crud.table_info(table)
    if info is None:
        abort(404)
    segment = crud.TABLE_SEGMENT[table]
    if action != "view" and table in crud.READ_ONLY:
        return None
    return (info, segment) if can(action, segment) else None


def changed_columns(row, values):
    return [c for c, v in values.items() if ("" if row[c] is None else str(row[c])) != ("" if v is None else str(v))]


# extra buttons on some tables: (label, endpoint, privilege action)
ROW_ACTIONS = {
    "leads": [("Convert", "convert_lead", "edit")],
    "opportunities": [("Change stage", "deal_stage", "edit")],
    "invoices": [("Record payment", "record_payment", "add")],
}


@app.route("/data/<table>")
def data_list(table):
    found = data_table(table, "view")
    if not found:
        return no_access()
    info, segment = found
    records = crud.list_rows(table)
    for r in records:
        r["_key"] = crud.key_of(table, r)
    return render_template("data_list.html", page=segment, table=table, title=crud.TABLE_TITLE[table], info=info,
                           records=records, read_only=table in crud.READ_ONLY, row_actions=ROW_ACTIONS.get(table, []))


@app.route("/data/<table>/new", methods=["GET", "POST"])
def data_new(table):
    found = data_table(table, "add")
    if not found:
        return no_access()
    info, segment = found
    values = {c["name"]: crud.input_value(c, c["default"]) for c in info["columns"] if not c["db_time"]}
    if request.method == "POST":
        data, problems = crud.read_form(table, request.form, adding=True)
        if not problems:
            try:
                with transaction() as cur:
                    set_crm_user(cur)
                    new_id = crud.insert(cur, table, data)
                    key = ",".join(str(data[k]) for k in info["pk"]) if len(info["pk"]) > 1 else (new_id or data.get(info["pk"][0]))
                    audit(cur, g.user["account_id"], "record_added", f"{table} #{key}")
                flash(f"{crud.TABLE_TITLE[table]}: record {key} added.", "ok")
                return redirect(url_for("data_list", table=table))
            except pymysql.MySQLError as error:
                problems.append(database_refused(error))
        for problem in problems:
            flash(problem, "error")
        values = request.form
    return render_template("data_form.html", page=segment, table=table, title=crud.TABLE_TITLE[table], info=info,
                           fields=crud.form_fields(table, True), adding=True, values=values, row={},
                           options=crud.options(table))


@app.route("/data/<table>/<key>/edit", methods=["GET", "POST"])
def data_edit(table, key):
    found = data_table(table, "edit")
    if not found:
        return no_access()
    info, segment = found
    parts = crud.parse_key(table, key)
    row = crud.get_row(table, parts) if parts else None
    if row is None:
        abort(404)
    values = {c["name"]: crud.input_value(c, row[c["name"]]) for c in info["columns"]}
    if request.method == "POST":
        data, problems = crud.read_form(table, request.form, adding=False)
        if not problems:
            try:
                with transaction() as cur:
                    set_crm_user(cur)
                    crud.update(cur, table, data, parts)
                    audit(cur, g.user["account_id"], "record_updated",
                          f"{table} #{key}: {', '.join(changed_columns(row, data)) or 'no changes'}")
                flash(f"{crud.TABLE_TITLE[table]}: record {key} saved.", "ok")
                return redirect(url_for("data_list", table=table))
            except pymysql.MySQLError as error:
                problems.append(database_refused(error))
        for problem in problems:
            flash(problem, "error")
        values = request.form
    return render_template("data_form.html", page=segment, table=table, title=crud.TABLE_TITLE[table], info=info,
                           fields=crud.form_fields(table, False), adding=False, values=values, row=row, key=key,
                           options=crud.options(table))


@app.route("/data/<table>/<key>/delete", methods=["POST"])
def data_delete(table, key):
    found = data_table(table, "delete")
    if not found:
        return no_access()
    parts = crud.parse_key(table, key)
    if not parts:
        abort(404)
    try:
        with transaction() as cur:
            set_crm_user(cur)
            deleted = crud.delete(cur, table, parts)
            if deleted:
                audit(cur, g.user["account_id"], "record_deleted", f"{table} #{key}")
        flash(f"{crud.TABLE_TITLE[table]}: record {key} deleted." if deleted else "That record no longer exists.",
              "ok" if deleted else "info")
    except pymysql.MySQLError as error:
        flash(database_refused(error), "error")
    return redirect(url_for("data_list", table=table))


# --------------------------------------------------------------------------- business operations (stored procedures)
def run_procedure(call, args, detail, done_message, back):
    """CALL a stored procedure as the signed-in user; MySQL errors (SIGNAL included) become messages."""
    try:
        with transaction() as cur:
            set_crm_user(cur)
            cur.execute(call, args)
            result = None
            if "@out" in call:
                cur.execute("SELECT @out AS result")
                result = cur.fetchone()["result"]
            audit(cur, g.user["account_id"], "procedure_called", detail.replace("{result}", str(result)))
        flash(done_message.replace("{result}", str(result)), "ok")
        return redirect(back)
    except pymysql.MySQLError as error:
        flash(database_refused(error), "error")
        return None


@app.route("/leads/<int:record_id>/convert", methods=["GET", "POST"])
def convert_lead(record_id):
    if not can("edit", "leads"):
        return no_access()
    found = rows("""SELECT lead_id, CONCAT(first_name, ' ', last_name) AS name, company_name, status, lead_score
                    FROM leads WHERE lead_id = %s""", (record_id,))
    if not found:
        abort(404)
    lead = found[0]
    form = request.form
    if request.method == "POST":
        done = run_procedure("CALL sp_convert_lead(%s, %s, %s, %s, @out)",
                             (record_id, form.get("opportunity_name", "").strip(), form.get("amount") or 0,
                              form.get("expected_close") or None),
                             f"sp_convert_lead({record_id}) -> opportunity " + "{result}",
                             f"Lead {record_id} converted: opportunity " + "{result}" + " created with its account and contact.",
                             url_for("data_list", table="opportunities"))
        if done:
            return done
    fields = [
        {"name": "opportunity_name", "label": "Deal name", "type": "text", "required": True,
         "value": form.get("opportunity_name", f"{lead['company_name']} deal")},
        {"name": "amount", "label": "Deal amount (PKR)", "type": "number", "step": "0.01", "required": True,
         "value": form.get("amount", "")},
        {"name": "expected_close", "label": "Expected close date", "type": "date", "required": True,
         "value": form.get("expected_close", "")},
    ]
    return render_template("action.html", page="leads", title=f"Convert lead {record_id}",
                           summary=[("Lead", lead["name"]), ("Company", lead["company_name"]),
                                    ("Status", lead["status"]), ("Score", lead["lead_score"])],
                           text="sp_convert_lead creates the account (unless the company already exists), the "
                                "contact and the deal, and marks the lead as converted, all in one transaction. "
                                "Only qualified leads can be converted.",
                           fields=fields, button="Convert lead", back=url_for("data_list", table="leads"))


@app.route("/pipeline/<int:record_id>/stage", methods=["GET", "POST"])
def deal_stage(record_id):
    if not can("edit", "pipeline"):
        return no_access()
    found = rows("""SELECT opportunity_id, opportunity_name, account_name, stage_name, amount
                    FROM vw_sales_pipeline WHERE opportunity_id = %s""", (record_id,))
    if not found:
        abort(404)
    deal = found[0]
    form = request.form
    if request.method == "POST":
        done = run_procedure("CALL sp_update_opportunity_stage(%s, %s, %s, %s)",
                             (record_id, form.get("stage_name"), g.user["user_id"],
                              form.get("loss_reason", "").strip() or None),
                             f"sp_update_opportunity_stage({record_id}, {form.get('stage_name')})",
                             f"Deal {record_id} moved to {form.get('stage_name')}.",
                             url_for("data_list", table="opportunities"))
        if done:
            return done
    stages = [r["stage_name"] for r in rows("SELECT stage_name FROM pipeline_stages ORDER BY stage_order")]
    fields = [
        {"name": "stage_name", "label": "New stage", "type": "select", "options": stages, "required": True,
         "value": form.get("stage_name", deal["stage_name"])},
        {"name": "loss_reason", "label": "Loss reason", "type": "text", "required": False,
         "help": "Required for Closed Lost.", "value": form.get("loss_reason", "")},
    ]
    return render_template("action.html", page="pipeline", title=f"Change the stage of deal {record_id}",
                           summary=[("Deal", deal["opportunity_name"]), ("Account", deal["account_name"]),
                                    ("Current stage", deal["stage_name"]), ("Amount", pkr(deal["amount"]))],
                           text="sp_update_opportunity_stage moves the deal; the trigger records the change in the "
                                "stage history, and a deal closed as won gets its invoice in the same transaction.",
                           fields=fields, button="Change stage", back=url_for("data_list", table="opportunities"))


@app.route("/invoices/<int:record_id>/payment", methods=["GET", "POST"])
def record_payment(record_id):
    if not can("add", "invoices"):
        return no_access()
    found = rows("""SELECT invoice_id, invoice_number, account_name, total_amount, amount_paid, balance_due, status
                    FROM vw_invoice_balance WHERE invoice_id = %s""", (record_id,))
    if not found:
        abort(404)
    invoice = found[0]
    form = request.form
    if request.method == "POST":
        done = run_procedure("CALL sp_record_payment(%s, %s, %s, %s)",
                             (record_id, form.get("amount") or 0, form.get("payment_method"),
                              form.get("reference_no", "").strip() or None),
                             f"sp_record_payment({record_id}, {form.get('amount')})",
                             f"Payment recorded on invoice {invoice['invoice_number']}.",
                             url_for("data_list", table="invoices"))
        if done:
            return done
    methods = next(c["choices"] for c in crud.table_info("payments")["columns"] if c["name"] == "payment_method")
    fields = [
        {"name": "amount", "label": "Amount (PKR)", "type": "number", "step": "0.01", "required": True,
         "value": form.get("amount", "")},
        {"name": "payment_method", "label": "Method", "type": "select", "options": methods, "required": True,
         "value": form.get("payment_method", methods[0] if methods else "")},
        {"name": "reference_no", "label": "Reference", "type": "text", "required": False,
         "value": form.get("reference_no", "")},
    ]
    return render_template("action.html", page="invoices", title=f"Record a payment on {invoice['invoice_number']}",
                           summary=[("Account", invoice["account_name"]), ("Total", pkr(invoice["total_amount"])),
                                    ("Paid", pkr(invoice["amount_paid"])), ("Balance due", pkr(invoice["balance_due"])),
                                    ("Status", invoice["status"])],
                           text="sp_record_payment adds the payment and updates the invoice status in one "
                                "transaction, and refuses a payment larger than the balance due.",
                           fields=fields, button="Record payment", back=url_for("data_list", table="invoices"))


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
    return {"nav": tabs, "github": GITHUB, "user": user, "csrf_token": csrf_token, "csp_nonce": csp_nonce, "can": can,
            "segments": crud.SEGMENTS, "privilege_summary": privilege_summary,
            "labels": {endpoint: label for endpoint, label, _ in NAV}}


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
