"""Add, edit and delete for the CRM tables, driven by MySQL's own metadata.

The forms follow database/pulse_crm.sql: columns, types, NOT NULL, defaults, primary keys,
foreign keys and CHECK (... IN (...)) lists are read from information_schema. MySQL still
enforces every rule; when a change breaks one, its error message is shown to the user.
Table and column names in the SQL built here come only from information_schema, and every
value is passed as a query parameter.
"""
import re
import time
from datetime import date, datetime

from db import fetch, rows

# segment (tab) -> the tables it manages, in display order
SEGMENTS = {
    "pipeline": [("opportunities", "Deals"), ("opportunity_products", "Deal line items"),
                 ("activities", "Activities"), ("products", "Products"), ("pipeline_stages", "Pipeline stages"),
                 ("opportunity_stage_history", "Stage history")],
    "accounts": [("accounts", "Accounts"), ("contacts", "Contacts"), ("industries", "Industries")],
    "team": [("users", "CRM staff"), ("roles", "Roles")],
    "leads": [("leads", "Leads"), ("campaigns", "Campaigns"), ("campaign_leads", "Campaign members"),
              ("lead_sources", "Lead sources")],
    "support": [("tickets", "Tickets")],
    "invoices": [("invoices", "Invoices"), ("payments", "Payments")],
}
TABLE_SEGMENT = {table: segment for segment, items in SEGMENTS.items() for table, _ in items}
TABLE_TITLE = {table: title for items in SEGMENTS.values() for table, title in items}

# written only by trg_opportunities_stage_history and the stored procedures
READ_ONLY = {"opportunity_stage_history"}

# how a row of each table is named in dropdowns and lists
LABEL_SQL = {
    "roles": "role_name",
    "users": "full_name",
    "industries": "industry_name",
    "accounts": "account_name",
    "contacts": "CONCAT(first_name, ' ', last_name)",
    "lead_sources": "source_name",
    "leads": "CONCAT(first_name, ' ', last_name, ' - ', company_name)",
    "pipeline_stages": "stage_name",
    "opportunities": "opportunity_name",
    "products": "CONCAT(product_code, ' ', product_name)",
    "campaigns": "campaign_name",
    "tickets": "CONCAT('#', ticket_id, ' ', subject)",
    "invoices": "invoice_number",
}

INT_TYPES = {"tinyint", "smallint", "mediumint", "int", "bigint"}
CACHE_SECONDS = 300
_cache = {"at": 0.0, "tables": None}


def q(name):
    """Quote an identifier taken from information_schema."""
    return f"`{name}`"


def humanize(column):
    """owner_user_id -> Owner user, is_active -> Active, discount_pct -> Discount %"""
    words = column[3:] if column.startswith("is_") else column
    words = re.sub(r"_id$", "", words).replace("_pct", " %").replace("_", " ")
    return words[:1].upper() + words[1:]


def metadata():
    """{table: {"columns": [...], "pk": [...]}} for every managed table, cached for a few minutes."""
    if _cache["tables"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["tables"]
    names = ", ".join(f"'{t}'" for t in TABLE_SEGMENT)
    data = fetch(
        columns=f"""
            SELECT table_name AS t, column_name AS c, column_default AS d, is_nullable AS n, data_type AS dt,
                   column_type AS ct, character_maximum_length AS len, numeric_scale AS scale, column_key AS k,
                   extra AS x, column_comment AS comment
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name IN ({names})
            ORDER BY table_name, ordinal_position""",
        fks=f"""
            SELECT table_name AS t, column_name AS c, referenced_table_name AS rt, referenced_column_name AS rc
            FROM information_schema.key_column_usage
            WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL AND table_name IN ({names})""",
        checks=f"""
            SELECT tc.table_name AS t, cc.check_clause AS clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON cc.constraint_schema = tc.constraint_schema AND cc.constraint_name = tc.constraint_name
            WHERE tc.table_schema = DATABASE() AND tc.constraint_type = 'CHECK' AND tc.table_name IN ({names})""")
    fks = {(r["t"], r["c"]): (r["rt"], r["rc"]) for r in data["fks"]}
    choices = {}
    for r in data["checks"]:
        clause = (r["clause"] or "").replace("\\'", "'")
        m = re.match(r"^\(\s*[`\"]?(\w+)[`\"]?\s+in\s*\((.*)\)\s*\)$", clause, re.I | re.S)
        if m:
            choices[(r["t"], m.group(1))] = re.findall(r"'((?:[^']|'')*)'", m.group(2))
    tables = {}
    for r in data["columns"]:
        extra = (r["x"] or "").upper()
        col = {
            "name": r["c"],
            "label": humanize(r["c"]),
            "help": re.sub(r"\s*\(FK [^)]*\)", "", r["comment"] or ""),
            "nullable": r["n"] == "YES",
            "default": r["d"],
            "auto": "AUTO_INCREMENT" in extra,
            "generated": "STORED GENERATED" in extra or "VIRTUAL GENERATED" in extra,
            "db_time": "DEFAULT_GENERATED" in extra or (r["d"] or "").upper().startswith("CURRENT_TIMESTAMP"),
            "fk": fks.get((r["t"], r["c"])),
            "choices": choices.get((r["t"], r["c"])),
            "maxlen": r["len"],
            "scale": r["scale"],
        }
        dt, ct = (r["dt"] or "").lower(), (r["ct"] or "").lower()
        if col["generated"]:
            col["kind"] = "generated"
        elif col["fk"]:
            col["kind"] = "fk"
        elif col["choices"]:
            col["kind"] = "choice"
        elif ct.startswith("tinyint(1)"):
            col["kind"] = "bool"
        elif dt in INT_TYPES:
            col["kind"] = "int"
        elif dt == "decimal":
            col["kind"] = "decimal"
        elif dt == "date":
            col["kind"] = "date"
        elif dt in ("datetime", "timestamp"):
            col["kind"] = "datetime"
        elif dt in ("text", "mediumtext", "longtext") or (col["maxlen"] or 0) > 200:
            col["kind"] = "textarea"
        else:
            col["kind"] = "text"
        table = tables.setdefault(r["t"], {"columns": [], "pk": []})
        table["columns"].append(col)
        if r["k"] == "PRI":
            table["pk"].append(r["c"])
    _cache.update(at=time.time(), tables=tables)
    return tables


def table_info(table):
    return metadata().get(table) if table in TABLE_SEGMENT else None


def editable(table, col, adding):
    if col["generated"] or col["db_time"] or col["auto"]:
        return False
    return adding or col["name"] not in table_info(table)["pk"]


def required(col, adding):
    if col["kind"] == "bool" or col["nullable"]:
        return False
    return col["default"] is None if adding else True


def form_fields(table, adding):
    """The table's columns with editable and required worked out for an add or edit form."""
    return [dict(col, editable=editable(table, col, adding),
                 required=editable(table, col, adding) and required(col, adding))
            for col in table_info(table)["columns"]]


def key_of(table, row):
    return ",".join(str(row[k]) for k in table_info(table)["pk"])


def parse_key(table, text):
    pk = table_info(table)["pk"]
    parts = text.split(",")
    return parts if len(parts) == len(pk) and all(parts) else None


def where_pk(table):
    return " AND ".join(f"{q(k)} = %s" for k in table_info(table)["pk"])


def list_rows(table):
    """Every row, with a readable label next to each foreign key."""
    info = table_info(table)
    labels = []
    for col in info["columns"]:
        if col["fk"]:
            parent, parent_key = col["fk"]
            labels.append(f"(SELECT {LABEL_SQL.get(parent, q(parent_key))} FROM {q(parent)} p "
                          f"WHERE p.{q(parent_key)} = t.{q(col['name'])}) AS {q(col['name'] + '__label')}")
    order = ", ".join(f"t.{q(k)}" for k in info["pk"])
    return rows(f"SELECT t.*{''.join(', ' + x for x in labels)} FROM {q(table)} t ORDER BY {order} LIMIT 1000")


def get_row(table, key):
    found = rows(f"SELECT * FROM {q(table)} WHERE {where_pk(table)}", tuple(key))
    return found[0] if found else None


def options(table):
    """{fk column: [(id, label), ...]} for the dropdowns of a form."""
    queries = {}
    for col in table_info(table)["columns"]:
        if col["fk"]:
            parent, parent_key = col["fk"]
            queries[col["name"]] = (f"SELECT {q(parent_key)} AS id, {LABEL_SQL.get(parent, q(parent_key))} AS label "
                                    f"FROM {q(parent)} ORDER BY label")
    return {name: [(r["id"], r["label"]) for r in result] for name, result in fetch(**queries).items()} if queries else {}


def input_value(col, value):
    """A database value as the text an HTML input expects."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def read_form(table, form, adding):
    """Column values from a submitted form, and the problems found before asking MySQL."""
    values, problems = {}, []
    for col in table_info(table)["columns"]:
        if not editable(table, col, adding):
            continue
        name = col["name"]
        if col["kind"] == "bool":
            values[name] = 1 if form.get(name) else 0
            continue
        raw = (form.get(name) or "").strip()
        if raw == "":
            if required(col, adding):
                problems.append(f"{col['label']} is required.")
            elif col["nullable"]:
                values[name] = None
            continue                      # left out, so MySQL uses the column default
        if col["kind"] == "datetime":
            raw = raw.replace("T", " ") + (":00" if len(raw) == 16 else "")
        values[name] = raw
    return values, problems


def insert(cur, table, values):
    columns = list(values)
    cur.execute(f"INSERT INTO {q(table)} ({', '.join(map(q, columns))}) VALUES ({', '.join(['%s'] * len(columns))})",
                [values[c] for c in columns])
    return cur.lastrowid


def update(cur, table, values, key):
    if values:
        cur.execute(f"UPDATE {q(table)} SET {', '.join(f'{q(c)} = %s' for c in values)} WHERE {where_pk(table)}",
                    [*values.values(), *key])


def delete(cur, table, key):
    cur.execute(f"DELETE FROM {q(table)} WHERE {where_pk(table)}", tuple(key))
    return cur.rowcount


EXPLAIN = {
    1062: "Another record already has this value, and it must be unique.",
    1451: "Other records still refer to this one, so MySQL refuses to delete or change it.",
    1452: "The related record you chose does not exist.",
    3819: "The value breaks one of the database's CHECK rules.",
    1048: "A required value is missing.",
    1406: "A value is too long for its column.",
    1366: "A value has the wrong type for its column.",
    1292: "A date, time or number is not valid.",
    1264: "A number is outside the range its column allows.",
    1265: "A value is not allowed for its column.",
}


def explain(error):
    """A user-facing message for a MySQL error, keeping MySQL's own code and text."""
    code = error.args[0] if error.args else "?"
    text = error.args[1] if len(error.args) > 1 else str(error)
    if code == 1644:                      # raised by SIGNAL in a stored procedure
        return f"{text} (MySQL error 1644 from the stored procedure)"
    lead = EXPLAIN.get(code, "MySQL refused the change.")
    return f"{lead} MySQL error {code}: {text}"
