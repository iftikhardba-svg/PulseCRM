# PulseCRM Web Dashboard

A read-only reporting website for the `pulse_crm` database, written in Python with Flask and hosted on Vercel. Every page runs `SELECT` queries against the reporting views in `database/pulse_crm.sql`:

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

`/health` returns the database name, MySQL version and account count as JSON.

## Read-only by design

The site connects as `pulse_web`, a MySQL account with `SELECT` privilege only ([database/web_readonly_user.sql](../database/web_readonly_user.sql)). Every session is also set to `READ ONLY`, so nothing on the website can change data.

## Settings

| Variable | Value |
|---|---|
| `DATABASE_URL` | `mysql://pulse_web:<password>@<host>:<port>/pulse_crm` |
| `DATABASE_CA_CERT` | The server's CA certificate (PEM text). Turns on verified TLS. |

## Run locally

```bash
pip install -r web/requirements.txt
```

Set `DATABASE_URL` to any MySQL 8 server that has `pulse_crm` (for example the Docker setup in the main README: `mysql://root:pulsecrm@127.0.0.1:3307/pulse_crm`), then:

```bash
flask --app web/app.py run
```

## Deploy

1. **Database:** create a free MySQL 8 service (this project uses [Aiven](https://aiven.io/mysql)). Put its admin URI in `web/.env` as `AIVEN_ADMIN_URL=...` and its CA certificate in `web/ca.pem`. Both are git-ignored. Then run:

   ```bash
   python web/setup_cloud_db.py
   ```

   It builds `pulse_crm` with the unchanged build script, creates `pulse_web` and checks that the account can read but not write. It also writes the two settings to `web/.env.vercel`, which is git-ignored.
2. **Website:** in Vercel, import this GitHub repository, set **Root Directory** to `web` and add the two settings as environment variables. Vercel detects Flask on its own, and every push to `main` redeploys the site.

Aiven powers off a free MySQL service that goes unused. When that happens, the site shows a "database is offline" page with links to the repository, until you switch the service back on in the Aiven console.
