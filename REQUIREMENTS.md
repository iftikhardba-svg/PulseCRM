# PulseCRM: Requirements Specification

| | |
|---|---|
| **Project** | PulseCRM: Customer Relationship Management Database |
| **Course** | Relational Database Management Systems (RDBMS) |
| **Programme** | Postgraduate Diploma in Generative AI, NED University of Engineering & Technology, Karachi |
| **Author** | Iftikhar Ahmed |
| **Version** | 1.0 |

---

## 1. Purpose

This document lists what the PulseCRM database must do (functional requirements), how well it must do it (non-functional requirements), the business rules it enforces, and the software needed to run it. Each requirement is traced to the table, constraint, view or procedure that implements it.

## 2. Scope

**In scope**
- The relational database: schema, constraints, sample data, views, procedures and trigger.
- Report and demonstration queries.
- Documentation: ERD, data dictionary and report.

**Out of scope**
- A graphical front end.
- E-mail sending and online payment processing.

---

## 3. Software and Hardware Requirements

| Item | Requirement | Notes |
|---|---|---|
| Database server | **MySQL Community Server 8.0.16+** | CHECK constraints are enforced from 8.0.16; tested on 8.0.46 |
| Storage engine | InnoDB | Needed for foreign keys and transactions |
| Character set | utf8mb4 / utf8mb4_0900_ai_ci | Full Unicode support for names |
| Client | MySQL Workbench 8.0, or the `mysql` CLI | Workbench is used for screenshots |
| Version control | Git 2.x and a GitHub account | To publish the repository |
| Operating system | Windows 10/11, macOS or Linux | Any OS supported by MySQL 8 |
| Hardware | 2 CPU cores, 4 GB RAM, 1 GB free disk | The sample database is under 5 MB |
| Privileges | A user with `CREATE`, `DROP`, `CREATE ROUTINE` and `TRIGGER` | `root` is fine for local development |

---

## 4. Users and Roles

| Role | Main tasks in the CRM |
|---|---|
| Administrator | Manages users and roles, and has full access |
| Sales Manager | Monitors the pipeline, closes deals and reviews the team scorecard |
| Sales Representative | Works leads, accounts, contacts, opportunities and activities |
| Marketing | Runs campaigns and adds leads |
| Support Agent | Handles customer tickets |

These are stored in the `roles` table and linked to `users.role_id`.

---

## 5. Functional Requirements

Priority: **M** = Must have, **S** = Should have, **C** = Could have.

### 5.1 Users

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-01 | Store staff with name, unique e-mail, phone, role and hire date | M | `users`, `uq_users_email` |
| FR-02 | Record each user's line manager | S | `users.manager_id` (self FK) |
| FR-03 | Deactivate a user who leaves without deleting their history | M | `users.is_active` |

### 5.2 Accounts and contacts

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-04 | Store companies with industry, type, city, revenue and an owner | M | `accounts`, `industries` |
| FR-05 | Allow only the types Prospect, Customer, Partner and Churned | M | `chk_accounts_type` |
| FR-06 | Store many contacts per account, one of them marked primary | M | `contacts`, `is_primary` |
| FR-07 | Contact e-mails must be unique | M | `uq_contacts_email` |

### 5.3 Leads and marketing

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-08 | Capture leads with source, status, score and owner | M | `leads`, `lead_sources` |
| FR-09 | Keep the lead score between 0 and 100 | M | `chk_leads_score` |
| FR-10 | Convert a qualified lead into account + contact + opportunity in one step | M | `sp_convert_lead` |
| FR-11 | A converted lead must point to the account it became | M | `chk_leads_converted`, `fk_leads_converted_account` |
| FR-12 | Plan campaigns with channel, dates and budget | S | `campaigns`, `chk_campaigns_dates` |
| FR-13 | Record which leads each campaign reached and how they responded | S | `campaign_leads` |
| FR-14 | Report conversion rate by lead source | S | `vw_lead_conversion_by_source` |

### 5.4 Sales pipeline

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-15 | Track deals with account, contact, owner, stage, value and close dates | M | `opportunities` |
| FR-16 | Use fixed pipeline stages with a win probability | M | `pipeline_stages` |
| FR-17 | Calculate deal value from product line items with discounts | M | `opportunity_products.line_total` (generated column) |
| FR-18 | Log every stage change with the user and time | M | `opportunity_stage_history`, `trg_opportunities_stage_history` |
| FR-19 | Require a reason when a deal is lost | M | `sp_update_opportunity_stage` |
| FR-20 | Show open and weighted pipeline per stage and per representative | M | `vw_sales_pipeline`, `sp_sales_rep_pipeline` |
| FR-21 | Score each representative (won, lost, revenue, win rate) | S | `vw_sales_rep_performance` |

### 5.5 Activities

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-22 | Log calls, e-mails, meetings, demos and tasks with status and duration | M | `activities` |
| FR-23 | Every activity must relate to a lead, a contact or a deal | M | `chk_activities_link` |

### 5.6 Customer support

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-24 | Record tickets with priority, status, agent and timestamps | M | `tickets` |
| FR-25 | A resolved or closed ticket must have a resolved time after the opened time | M | `chk_tickets_resolved`, `chk_tickets_resolved_set` |
| FR-26 | Capture a satisfaction score from 1 to 5 | C | `chk_tickets_satisfaction` |
| FR-27 | Report resolution time by priority | S | `vw_ticket_resolution` |

### 5.7 Billing

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-28 | Create exactly one invoice when a deal is won | M | `uq_invoices_opportunity`, `sp_update_opportunity_stage` |
| FR-29 | Record full or part payments against an invoice | M | `payments`, `sp_record_payment` |
| FR-30 | Never accept a payment larger than the balance due | M | `sp_record_payment` |
| FR-31 | Keep the invoice status in line with the payments received | M | `sp_record_payment` |
| FR-32 | Show amount paid and balance due per invoice | M | `vw_invoice_balance` |

### 5.8 Reporting

| ID | Requirement | Priority | Implemented by |
|---|---|---|---|
| FR-33 | Give a single view of each customer (contacts, deals, revenue, tickets) | M | `vw_account_360`, `sp_account_summary` |
| FR-34 | Provide monthly revenue, product revenue and campaign results | S | `database/queries.sql` (Q06, Q09, Q10) |

---

## 6. Non-Functional Requirements

| ID | Category | Requirement | How it is met |
|---|---|---|---|
| NFR-01 | Data integrity | Invalid, duplicate or orphan data must be rejected by the database, not only by an application | 31 foreign keys, 14 unique keys, 34 CHECK constraints, NOT NULL |
| NFR-02 | Reliability (ACID) | Multi-step changes must be all-or-nothing | Transactions with `EXIT HANDLER` → `ROLLBACK` in every data-changing procedure |
| NFR-03 | Auditability | Pipeline changes must be traceable | Stage history trigger, `created_at` columns |
| NFR-04 | Performance | Frequent filters must use indexes | FK indexes plus 7 secondary indexes (status, dates, city) |
| NFR-05 | Maintainability | Fixed lists must be editable in one place | Lookup tables for roles, industries, sources and stages |
| NFR-06 | Usability | Managers must get reports without writing JOINs | Six reporting views |
| NFR-07 | Portability | The whole database must build from one script | `database/pulse_crm.sql` |
| NFR-08 | Security | Staff data and customer data must be protected | Recommended: separate MySQL users per role with `GRANT` (see Future Work) |
| NFR-09 | Internationalization | Names in any language | utf8mb4 character set |
| NFR-10 | Recoverability | The database must be easy to back up and restore | Standard `mysqldump`; the build script recreates the schema |

---

## 7. Business Rules

| ID | Rule | Enforced by |
|---|---|---|
| BR-01 | E-mail addresses of users, contacts and leads are unique; user and contact e-mails must also contain `@` and a domain | `uq_users_email`, `uq_contacts_email`, `uq_leads_email`, `chk_users_email`, `chk_contacts_email` |
| BR-02 | Money values are never negative; unit prices and payments are above zero | `chk_accounts_revenue`, `chk_opportunities_amount`, `chk_products_price`, `chk_payments_amount` |
| BR-03 | Discounts are between 0 % and 100 % | `chk_oppprod_discount` |
| BR-04 | Win probability is between 0 % and 100 %, and only a closed stage can be "won" | `chk_stages_probability`, `chk_stages_won_closed` |
| BR-05 | Unqualified or already converted leads cannot be converted | `sp_convert_lead` |
| BR-06 | A closed deal cannot be moved again | `sp_update_opportunity_stage` |
| BR-07 | A campaign cannot end before it starts; an invoice cannot be due before it is issued | `chk_campaigns_dates`, `chk_invoices_dates` |
| BR-08 | An account cannot be deleted while deals, activities or tickets still reference it | Foreign keys (`ON DELETE` default RESTRICT) |
| BR-09 | Deleting a deal removes its line items and stage history | `ON DELETE CASCADE` on the child tables |
| BR-10 | When a manager leaves, their team's `manager_id` becomes NULL | `fk_users_manager ON DELETE SET NULL` |

---

## 8. Data Requirements

- **Sample data** (fictional): 10 users, 12 accounts, 24 contacts, 24 leads, 20 opportunities, 30 line items, 30 activities, 4 campaigns, 12 tickets, 6 invoices, 6 payments and 71 stage-history rows. That is 305 rows in total.
- **Currency:** all amounts are in Pakistani Rupees (PKR), stored as `DECIMAL` to avoid rounding errors.
- **Dates:** the sample data covers January–October 2026.

---

## 9. Assumptions and Constraints

- One company uses the CRM, so there is no multi-tenant design.
- One invoice per won deal; instalments are recorded as multiple payments.
- A deal has one primary contact; other people involved are linked through activities.
- Each lead has one owner; a team can share leads by reassigning the owner.

---

## 10. Acceptance Criteria

The project is accepted when:

1. `database/pulse_crm.sql` runs without errors on MySQL 8.0.16+ and reports 18 tables with 305 rows.
2. All 25 report and procedure queries in `database/queries.sql` (Q01–Q25) return results.
3. All 7 integrity tests (Q26–Q32) are **rejected** with the expected error codes (3819, 1062, 1452, 1451, 1644).
4. The ERD, data dictionary and report match the implemented schema.

All four criteria were met during testing. See [docs/QUERY_RESULTS.md](docs/QUERY_RESULTS.md).
