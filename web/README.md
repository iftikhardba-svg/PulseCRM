# PulseCRM Web Dashboard

A reporting website for the `pulse_crm` database, written in Python with Flask and hosted on Vercel. Users sign in, and each CRM page runs `SELECT` queries against the reporting views in `database/pulse_crm.sql`:

| Page | Privilege | Source |
|---|---|---|
| Overview | `view_overview` | KPIs, pipeline by stage, leads by source, top accounts |
| Pipeline | `view_pipeline` | `vw_sales_pipeline` |
| Accounts | `view_accounts` | `vw_account_360` |
| Sales Team | `view_team` | `vw_sales_rep_performance` |
| Leads | `view_leads` | `vw_lead_conversion_by_source` and `leads` |
| Support | `view_support` | `vw_ticket_resolution` |
| Invoices | `view_invoices` | `vw_invoice_balance` |
| Database | `view_database` | Live row count of all 18 tables, ER diagram, integrity rules |
| Users | `manage_users` | Accounts, privileges and the activity log |

Every signed-in user also has **My account**, where they change their password. `/health` is public and returns the database name, MySQL version and account count as JSON.

## Sign-in and privileges

Accounts live in five extra tables, created by [database/web_access.sql](../database/web_access.sql) next to the 18 CRM tables:

| Table | Holds |
|---|---|
| `web_privileges` | The nine privileges above |
| `web_accounts` | User name, name, optional link to a CRM staff member (`users`), password hash, status |
| `web_account_privileges` | Which privileges each account has |
| `web_role_privileges` | Default privileges for each CRM role, filled in when an account is linked to staff |
| `web_audit_log` | Sign-ins, failed attempts and every change made on the Users page |

- **Passwords:** stored only as salted scrypt hashes. New accounts get a temporary password that must be changed at the first sign-in.
- **Lockout:** five wrong passwords lock an account for 15 minutes; an administrator can unlock it sooner.
- **Forms:** every form carries a CSRF token.
- **Sessions:** the session cookie is signed with `SECRET_KEY`, is HTTP-only and HTTPS-only, and expires after 8 hours.
- **Administrators:** they cannot deactivate themselves or remove their own **Manage users** privilege, and the last administrator cannot be removed.

## Database access

The site connects as `pulse_web` ([database/web_app_user.sql](../database/web_app_user.sql)). This MySQL account has two kinds of privilege:

- it can read every table and view;
- it can write only to `web_accounts`, `web_account_privileges` and `web_audit_log`.

CRM pages also run in `READ ONLY` sessions, so nothing on the website can change CRM data.

## Settings

| Variable | Value |
|---|---|
| `DATABASE_URL` | `mysql://pulse_web:<password>@<host>:<port>/pulse_crm` |
| `DATABASE_CA_CERT` | The server's CA certificate (PEM text). Turns on verified TLS. |
| `SECRET_KEY` | A long random string that signs the session cookie. Without it, nobody can sign in. |

## Run locally

```bash
pip install -r web/requirements.txt
```

Build the database with `database/pulse_crm.sql`, then `database/web_access.sql`, for example with the Docker setup in the main README. Then:

1. Set `DATABASE_URL` (for Docker: `mysql://root:pulsecrm@127.0.0.1:3307/pulse_crm`).
2. Set `SECRET_KEY` to any random string.
3. Create a first account. With `ADMIN_DATABASE_URL` set to the same address, `python web/setup_cloud_db.py --keep-data` does it, as described in the next section.
4. Start the site:

```bash
flask --app web/app.py run
```

## Deploy

1. **Database:** create a free MySQL 8 service (this project uses [Aiven](https://aiven.io/mysql)). Put its admin URI in `web/.env` as `AIVEN_ADMIN_URL=...` and its CA certificate in `web/ca.pem`. Both are git-ignored. Then run:

   ```bash
   python web/setup_cloud_db.py
   ```

   It does five things:
   - builds `pulse_crm` with the unchanged build script;
   - adds the sign-in tables;
   - creates `pulse_web` with its grants, and checks that it cannot change CRM data;
   - creates the first administrator, `admin`. Its temporary password goes to `web/.env.admin`, which is git-ignored;
   - writes the three settings to `web/.env.vercel`, which is git-ignored.

   On a database that is already running, `python web/setup_cloud_db.py --keep-data` adds or updates only the sign-in tables. It keeps the data and `pulse_web`'s password.
2. **Website:**
   - In Vercel, import this GitHub repository and set **Root Directory** to `web`.
   - Add the three settings as environment variables.
   - Vercel detects Flask on its own, and every push to `main` redeploys the site.
3. **First sign-in:** sign in as `admin` with the temporary password, choose a new password, and create accounts on the **Users** page.

Aiven powers off a free MySQL service that goes unused. When that happens, the site shows a "database is offline" page with links to the repository, until you switch the service back on in the Aiven console.
