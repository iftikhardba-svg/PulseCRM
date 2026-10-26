# PulseCRM Web Dashboard

A read-only reporting website for the `pulse_crm` database, written in Python with Flask. It is hosted on Vercel, and its database runs on Supabase (PostgreSQL). Every page runs `SELECT` queries against the reporting views:

| Page | Source |
|---|---|
| Overview | KPIs, pipeline by stage, leads by source, top accounts |
| Pipeline | `vw_sales_pipeline` |
| Accounts | `vw_account_360` |
| Sales Team | `vw_sales_rep_performance` |
| Leads | `vw_lead_conversion_by_source` and `leads` |
| Support | `vw_ticket_resolution` |
| Invoices | `vw_invoice_balance` |
| Database | Live row count of all 18 tables, ER diagram, integrity rules |

`/health` returns the database system, version, schema and account count as JSON.

## MySQL or PostgreSQL

The same app runs on either system, and the scheme of `DATABASE_URL` decides which:

| Database | Build script | Used for |
|---|---|---|
| MySQL 8.0+ | [database/pulse_crm.sql](../database/pulse_crm.sql) | The course project, MySQL Workbench, Docker |
| PostgreSQL 15+ | [database/pulse_crm_postgres.sql](../database/pulse_crm_postgres.sql) | The live site on Supabase |

The PostgreSQL script is a translation of the MySQL one. On every push, the [PostgreSQL port](../.github/workflows/postgres.yml) workflow builds both and checks that they behave the same. It compares:

- every table and view;
- every dashboard page;
- the seven integrity tests;
- the stored procedures.

## Read-only by design

The site connects as `pulse_web`, an account with `SELECT` privilege only ([database/web_readonly_user.sql](../database/web_readonly_user.sql)). Every transaction is also `READ ONLY`, so nothing on the website can change data.

## Settings

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://pulse_web.<project-ref>:<password>@<region>.pooler.supabase.com:6543/postgres?sslmode=require`, or `mysql://pulse_web:<password>@<host>:<port>/pulse_crm` |
| `DATABASE_CA_CERT` | Optional. The server's CA certificate (PEM text), to verify the server as well as encrypt the connection. |

## Run locally

```bash
pip install -r web/requirements.txt
```

Set `DATABASE_URL` to any database built with one of the scripts. For example, with the Docker setup from the main README, use `mysql://root:pulsecrm@127.0.0.1:3307/pulse_crm`. Then run:

```bash
flask --app web/app.py run
```

## Deploy (Vercel + Supabase)

1. **Database:** create a free project at [supabase.com](https://supabase.com).
   - In the dashboard, open **Connect**, copy the **Session pooler** connection string and fill in your database password.
   - Save it in `web/.env`, which git ignores, as `SUPABASE_DB_URL=...`.
   - Then run:

   ```bash
   python web/setup_supabase.py
   ```

   The script builds the `pulse_crm` schema and creates `pulse_web`. It then checks that `pulse_web` can read but not write, and writes `DATABASE_URL` to `web/.env.vercel`, which git also ignores.
2. **Website:**
   - In Vercel, import this GitHub repository and set **Root Directory** to `web`.
   - Add `DATABASE_URL` as an environment variable, then redeploy.
   - Vercel detects Flask on its own, and every push to `main` redeploys the site.

Supabase pauses free projects after a week without activity. When that happens, the site shows a "database is offline" page with links to the repository, until you restore the project in the Supabase dashboard.
