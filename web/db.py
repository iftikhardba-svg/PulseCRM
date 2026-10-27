"""Database helpers for the PulseCRM web dashboard (PyMySQL).

Reads run in READ ONLY sessions; changes run in transaction(), which commits at the end
and rolls back on any error.

Environment variables:
  DATABASE_URL      mysql://user:password@host:port/pulse_crm
  DATABASE_CA_CERT  PEM text of the server's CA certificate (turns on verified TLS)
"""
import os
import ssl
from contextlib import contextmanager
from urllib.parse import parse_qs, unquote, urlparse

import pymysql


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
    """A writable connection: commits at the end, rolls back on any error."""
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
