# PulseCRM Web Dashboard

A CRM website for the `pulse_crm` database, written in Python with Flask and hosted on Vercel. Users sign in. Each page shows reports from the views in `database/pulse_crm.sql`, and links to its tables, where users with the right privileges add, edit and delete records.

| Page | Report source | Tables (add, edit, delete) |
|---|---|---|
| Dashboard | KPI cards, pipeline by stage, sales funnel, top accounts | none |
| Pipeline | `vw_sales_pipeline` | deals, deal line items, activities, products, pipeline stages; stage history read-only |
| Accounts | `vw_account_360` | accounts, contacts, industries |
| Sales Team | `vw_sales_rep_performance` | CRM staff (`users`), roles |
| Leads | `vw_lead_conversion_by_source`, `leads` | leads |
| Marketing | campaigns with reach, responses, conversions and cost per lead; campaign members; lead sources | campaigns, campaign members, lead sources |
| Support | `vw_ticket_resolution` | tickets |
| Invoices | `vw_invoice_balance` | invoices, payments |
| Database | Row counts of all 18 tables, ER diagram, integrity rules | none |
| Users | Accounts, privileges and the activity log | web accounts |

Every signed-in user also has **My account**, where they change their password. `/health` is public and returns the database name, MySQL version and account count as JSON.

**Sidebar:** the pages are listed in a sidebar on the left, grouped under Sales, Marketing, Service, Finance and Admin, showing only the pages the account may open. The menu button at the top left hides the sidebar down to its icons (page names become tooltips) and shows it again; the choice is remembered in the browser. On a phone the sidebar is a drawer that the same button slides over the page.

**Light and dark mode:** the moon/sun button at the top right of every page switches the theme. The choice is remembered in the browser; until someone chooses, the site follows the system setting. All colours are CSS variables in `templates/base.html`, with a second set for `[data-theme="dark"]`.

## Records

- **Forms follow the database.** `web/crud.py` reads the columns, types, NOT NULL rules, defaults, primary keys, foreign keys and `CHECK (... IN (...))` lists from `information_schema`. Foreign keys become dropdowns with readable names, CHECK lists become choices, and AUTO_INCREMENT keys, generated columns (`line_total`) and timestamps set by MySQL are read-only.
- **MySQL has the last word.** Every value is sent as a query parameter, and when a change breaks a rule the page shows MySQL's own error. Examples: 3819 for a CHECK, 1062 for a duplicate, 1452 for a missing parent, 1451 for a row that others still use.
- **Business operations call the stored procedures**, so their transactions and checks apply:

| Operation | Procedure | Privilege |
|---|---|---|
| Convert a qualified lead into account, contact and deal | `sp_convert_lead` | Leads: edit |
| Move a deal to another stage; a won deal gets its invoice | `sp_update_opportunity_stage` | Pipeline: edit |
| Record a payment, refusing more than the balance due | `sp_record_payment` | Invoices: add |

- **Every change is recorded.** Before each change the app sets `@crm_user_id` to the CRM staff member linked to the account, so `trg_opportunities_stage_history` records who moved a deal. Each add, edit, delete and procedure call is written to `web_audit_log`.

## Sign-in and privileges

Accounts live in six extra tables, created by [database/web_access.sql](../database/web_access.sql) next to the 18 CRM tables:

| Table | Holds |
|---|---|
| `web_privileges` | 31 privileges: `view_`, `add_`, `edit_` and `delete_` for each page, and `manage_users` |
| `web_accounts` | User name, name, optional link to a CRM staff member (`users`), password hash, status |
| `web_account_privileges` | Which privileges each account has |
| `web_role_privileges` | Default privileges for each CRM role, filled in when an account is linked to staff |
| `web_audit_log` | Sign-ins, account changes and record changes |
| `web_login_failures` | Wrong passwords: network address, account tried and time (kept for one day) |

On the Users page, privileges are a grid: one row per page, with View, Add, Edit and Delete columns. The CRM role defaults are:

| Role | Pages | Can change |
|---|---|---|
| Administrator | all | everything |
| Sales Manager | Dashboard, Pipeline, Accounts, Sales Team, Leads, Marketing, Invoices | add, edit and delete Pipeline, Accounts and Leads; add and edit Invoices |
| Sales Representative | Dashboard, Pipeline, Accounts, Leads | add and edit Pipeline, Accounts and Leads |
| Marketing | Dashboard, Leads, Marketing | add and edit Leads; add, edit and delete Marketing |
| Support Agent | Dashboard, Accounts, Support | add and edit Support |

- **Passwords:** stored only as salted scrypt hashes. New accounts get a temporary password that must be changed at the first sign-in.
- **Throttling:** wrong passwords block the network address they came from, never the account. Five for one account, or twenty for any accounts, block that address for up to 15 minutes; people elsewhere can still sign in to the same account. A blocked address is refused without its password being checked, and the Users page shows blocked addresses so an administrator can clear them sooner. On Vercel the address comes from the `X-Real-IP` header that Vercel's proxy sets itself; anywhere else such headers are ignored, because a visitor could forge them.
- **Forms:** every form carries a CSRF token.
- **Content-Security-Policy:** scripts run only from `<script>` tags that carry the response's random nonce. There are no inline event handlers, and nothing is loaded from other sites except the ER diagram image from GitHub.
- **Sessions:** the session cookie is signed with `SECRET_KEY`, is HTTP-only and HTTPS-only, and expires after 8 hours.
- **Administrators:** they cannot deactivate themselves or remove their own **Manage users** privilege, and the last administrator cannot be removed.
- **Shared demo account:** an administrator can mark an account as a shared demo account (`password_locked`). Everyone signs in with the same password, so My account does not offer a password change, and a password reset does not ask for a new one; such an account cannot have **Manage users**. The live site's public demo login is `demo` / `PulseCRM-Tour-2026` (view only), shown on the sign-in page; it is set in `DEMO_LOGIN` in `app.py`, and the account's password on the Users page must match it.

## Database access

The site connects as `pulse_web` ([database/web_app_user.sql](../database/web_app_user.sql)). It is created with `REQUIRE SSL`, so MySQL refuses it without TLS, and it is granted table by table:

- `SELECT` on every table and view;
- `INSERT`, `UPDATE` and `DELETE` on the 17 CRM tables. The stage history is excluded: only the trigger and the procedures write to it;
- `EXECUTE` on `sp_convert_lead`, `sp_update_opportunity_stage` and `sp_record_payment`;
- writes on `web_accounts`, `web_account_privileges`, `web_audit_log` and `web_login_failures`.

It has no `CREATE`, `ALTER`, `DROP` or `GRANT` rights. Report pages run in `READ ONLY` sessions; changes run in one transaction each.

## Settings

| Variable | Value |
|---|---|
| `DATABASE_URL` | `mysql://pulse_web:<password>@<host>:<port>/pulse_crm`. Without `DATABASE_CA_CERT`, add `?ssl-mode=REQUIRED` for TLS without certificate checks. |
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
   - creates `pulse_web` with its grants, and checks that it is refused without TLS and cannot change the stage history or the schema;
   - creates the first administrator, `admin`. Its temporary password goes to `web/.env.admin`, which is git-ignored;
   - writes the three settings to `web/.env.vercel`, which is git-ignored.

   On a database that is already running, `python web/setup_cloud_db.py --keep-data` updates only the sign-in tables (it also removes the per-account lockout columns of older versions), the new privileges (granted to the active administrators) and `pulse_web`'s rules. It keeps the data and `pulse_web`'s password.
2. **Website:**
   - In Vercel, import this GitHub repository and set **Root Directory** to `web`.
   - Add the three settings as environment variables.
   - Vercel detects Flask on its own, and every push to `main` redeploys the site.
3. **First sign-in:** sign in as `admin` with the temporary password, choose a new password, and create accounts on the **Users** page.

Aiven powers off a free MySQL service that goes unused. The [keep-alive workflow](../.github/workflows/keep-alive.yml) opens `/health`, which runs a query, every hour so the service always shows activity. If it is powered off anyway, the site shows a "database is offline" page with links to the repository, the workflow run fails and GitHub e-mails you; switch the service back on in the Aiven console (Services → mysql-pulsecrm → Actions → Power on). A paid plan, such as Aiven's Developer tier, runs around the clock.
