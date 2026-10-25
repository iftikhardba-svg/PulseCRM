# Project Generation Prompt

This file contains the complete prompt used with a generative AI assistant to plan and build the PulseCRM project. It is included for transparency, as part of the Postgraduate Diploma in Generative AI. Every output was then run and checked on a real MySQL 8.0 server.

---

## Prompt

```text
ROLE
You are an expert database architect and MySQL 8.0 developer. You are helping a postgraduate
student of the Postgraduate Diploma in Generative AI prepare the final project for the course
"Relational Database Management Systems (RDBMS)" at NED University of Engineering & Technology,
Karachi.
Student: Iftikhar Ahmed. The project will be presented to the university and published on GitHub.

PROJECT
Build "PulseCRM", a Customer Relationship Management database for a B2B technology
services company. It must cover the full customer life cycle: leads -> accounts and contacts ->
opportunities (sales pipeline) -> activities -> marketing campaigns -> support tickets ->
invoices -> payments.

DELIVERABLES (GitHub repository layout)
PulseCRM/
  README.md               GitHub landing page
  REQUIREMENTS.md         software, functional and non-functional requirements, business rules
  PROMPT.md               this prompt
  LICENSE                 MIT, copyright 2026 Iftikhar Ahmed
  .gitignore
  database/pulse_crm.sql   ONE script that builds everything
  database/queries.sql       report and demonstration queries
  docs/PROJECT_REPORT.md     university-style project report
  docs/ERD.md                Mermaid ERD + notation + relationship list
  docs/erd.png, docs/erd.svg ERD image with crow's foot notation
  docs/DATA_DICTIONARY.md    every table, column, key and constraint
  docs/QUERY_RESULTS.md      each query with its real output
  docs/screenshots/          result-grid images of every query

DATABASE REQUIREMENTS (database/pulse_crm.sql)
- MySQL 8.0.16+, InnoDB, utf8mb4 / utf8mb4_0900_ai_ci, schema name pulse_crm.
- Start with DROP DATABASE IF EXISTS / CREATE DATABASE / USE so the script can be re-run.
- Script order: tables -> secondary indexes -> sample data -> views -> trigger -> stored
  procedures -> verification query that lists the row count of every table.
- Normalize to 3NF. Use INT AUTO_INCREMENT surrogate keys, DECIMAL for money (PKR),
  BOOLEAN flags, VARCHAR + CHECK (... IN (...)) for status lists, and a COMMENT on every
  table and column (the data dictionary is generated from them).
- Name constraints consistently: pk implicit, uq_<table>_<col>, fk_<table>_<parent>,
  chk_<table>_<rule>, idx_<table>_<cols>.
- Create these 18 tables:
  1  roles (role_name UNIQUE)
  2  users (email UNIQUE + format CHECK, role_id FK, manager_id self FK ON DELETE SET NULL,
     hire_date, is_active)
  3  industries (lookup)
  4  accounts (industry_id FK, account_type CHECK Prospect/Customer/Partner/Churned,
     city, country default Pakistan, annual_revenue >= 0, employee_count >= 0,
     owner_user_id FK)
  5  contacts (account_id FK ON DELETE CASCADE, email UNIQUE, is_primary)
  6  lead_sources (lookup: Website, Referral, LinkedIn, Trade Show, Cold Call, Email Campaign)
  7  leads (source_id FK, status CHECK New/Contacted/Qualified/Unqualified/Converted,
     lead_score 0-100, owner FK, converted_account_id FK, converted_at,
     CHECK: a Converted lead must have converted_account_id and converted_at)
  8  pipeline_stages (stage_order UNIQUE, win_probability 0-100, is_closed, is_won,
     CHECK is_won implies is_closed)
  9  opportunities (account, primary contact, source lead, owner, stage FKs, amount >= 0,
     expected/actual close date, loss_reason)
  10 products (product_code UNIQUE, category CHECK Software/Service/Support/Training,
     unit_price > 0)
  11 opportunity_products (bridge, composite PK, quantity > 0, discount 0-100,
     line_total as a STORED GENERATED column)
  12 activities (type CHECK Call/Email/Meeting/Demo/Task, status, owner FK, optional
     contact/lead/opportunity FKs, CHECK at least one of them is set)
  13 campaigns (channel CHECK, budget >= 0, CHECK end_date >= start_date)
  14 campaign_leads (bridge, composite PK, response CHECK Sent/Opened/Clicked/Responded)
  15 tickets (priority and status CHECKs, resolved_at >= opened_at, Resolved/Closed must have
     resolved_at, satisfaction 1-5)
  16 invoices (invoice_number UNIQUE, opportunity_id UNIQUE = one invoice per won deal,
     due_date >= invoice_date, status CHECK)
  17 payments (amount > 0, method CHECK, reference_no UNIQUE)
  18 opportunity_stage_history (from_stage, to_stage, changed_by, changed_at)
- Remember the MySQL rule: a column used in a CHECK constraint cannot also have an
  ON DELETE/ON UPDATE action on its foreign key.
- Secondary indexes on frequent filters: leads(status, lead_score), opportunities
  (expected_close_date), activities(activity_date, status), tickets(status, priority),
  invoices(status, due_date), accounts(account_type, city), history(changed_at).

SAMPLE DATA (fictional, consistent, Pakistani context, dates January-October 2026)
- 5 roles, 10 users (one inactive), 11 industries, 12 accounts, 24 contacts (2 per account),
  6 lead sources, 24 leads (6 Converted, 5 Qualified, 5 Contacted, 5 New, 3 Unqualified),
  6 stages, 8 products, 20 opportunities (6 won, 3 lost with reasons, the rest open),
  ~30 line items, 30 activities (some planned in the future), 4 campaigns with 20 campaign
  leads, 12 tickets, an invoice for every won deal, payments that leave invoices Paid,
  Partially Paid and Overdue.
- Use example.com-style fictional domains (e.g. @pulsecrm.example) - no real companies or people.
- Compute opportunities.amount from the line items, invoice totals from the deal amounts,
  invoice status from the payments, and the stage history from each deal's dates using
  INSERT ... SELECT, so the data is always internally consistent.

VIEWS
vw_sales_pipeline (weighted amount), vw_account_360 (contacts, open deals, open pipeline,
won revenue, open tickets - pre-aggregate each child table to avoid join fan-out),
vw_sales_rep_performance (leads, won/lost, revenue, win rate), vw_lead_conversion_by_source,
vw_ticket_resolution (hours to resolve), vw_invoice_balance (paid and balance due).

TRIGGER
trg_opportunities_stage_history: AFTER UPDATE on opportunities, insert a history row when
stage_id changes; changed_by comes from the session variable @crm_user_id.

STORED PROCEDURES (data-changing ones use START TRANSACTION, SELECT ... FOR UPDATE,
SIGNAL for business errors, and DECLARE EXIT HANDLER FOR SQLEXCEPTION -> ROLLBACK; RESIGNAL)
- sp_convert_lead(IN lead, IN deal name, IN amount, IN expected close, OUT new opportunity id):
  reject Converted/Unqualified leads, reuse or create the account, create the contact and the
  opportunity (Qualification stage), log history, mark the lead Converted.
- sp_update_opportunity_stage(IN opportunity, IN stage name, IN user, IN loss reason):
  reject unknown stages, closed deals and Closed Lost without a reason; set @crm_user_id for
  the trigger; when Closed Won, create the invoice in the same transaction.
- sp_record_payment(IN invoice, IN amount, IN method, IN reference): reject paid/cancelled
  invoices and overpayment, insert the payment, set status Paid or Partially Paid.
- sp_account_summary(IN account): two result sets (Account 360 row + open deals).
- sp_sales_rep_pipeline(IN user, OUT open pipeline, OUT weighted pipeline).

QUERIES (database/queries.sql) - 32 queries grouped by course topic, each with a comment header
1 Basic retrieval (self join staff directory, filtered accounts, hot leads)
2 Aggregates, GROUP BY, HAVING (pipeline by stage, lead sources, monthly won revenue)
3 JOINs (five-table open pipeline, LEFT JOIN ... IS NULL, product revenue, campaign results)
4 Subqueries, CTEs, window functions (above-average accounts, NOT EXISTS, RANK(), sales cycle)
5 Views (Account 360, scorecard, conversion, support time, outstanding invoices)
6 Procedures, trigger, transactions (call every procedure, convert a lead, close a deal and
  show the trigger history and auto invoice, record a payment, SAVEPOINT what-if with
  ROLLBACK TO SAVEPOINT and a final ROLLBACK)
7 Integrity tests that must fail, each marked "Expected: ERROR": CHECK violation, duplicate
  UNIQUE value, missing FK parent, deleting a referenced parent, overpayment, Closed Lost
  without a reason, converting an unqualified lead.

DOCUMENTATION
- README.md: badges, project information table (student, course, programme, institute,
  instructor, term), problem statement, features, "database at a glance" counts, ERD image +
  compact Mermaid diagram, table list by business area, repository tree, getting started
  (Workbench and CLI), views/procedures/trigger table, sample result screenshots, integrity
  test table with the real MySQL errors, course-topic mapping, future work, author, licence.
- REQUIREMENTS.md: purpose, scope, software/hardware requirements (MySQL 8.0.16+ because CHECK
  is enforced from that version), roles, functional requirements FR-xx with priority (MoSCoW)
  and the object that implements each, non-functional requirements, business rules BR-xx
  traced to constraint names, data requirements, assumptions, acceptance criteria.
- docs/PROJECT_REPORT.md: abstract, introduction (background, problem, objectives, scope),
  methodology (database design life cycle), conceptual design (entities, cardinality table,
  ERD), logical design with a worked normalization example (flat spreadsheet -> 1NF -> 2NF ->
  3NF and the anomalies removed), physical design decisions, implementation (views,
  transaction pattern, trigger, ACID table), testing and results with real numbers,
  discussion (what worked, challenges), conclusion, future work, references, how to
  reproduce, and a 10-slide presentation outline.
- docs/ERD.md: crow's foot notation table, full Mermaid erDiagram generated from the live
  schema (every column with PK/FK/UK), relationship list with cardinality and ON DELETE rule.
- docs/DATA_DICTIONARY.md: generated from information_schema - per table: column, type,
  null, key, default, description, CHECK constraints, foreign keys, indexes.

QUALITY RULES
- Run every script on MySQL and fix every error before finishing. Report the real outputs,
  never invented ones.
- Integrity tests must actually fail with the expected MySQL error codes
  (3819, 1062, 1452, 1451, 1644).
- Keep the writing clear and student-friendly. Use short sentences, explain every design
  decision, and do not overclaim.
- All sample data must be fictional.
```

---

## How the prompt was used

1. The prompt produced the first version of the schema, data, queries and documents.
2. Each SQL file was run on MySQL 8.0.46. The trial runs exposed real behaviour that was then documented:
   - Deleting account 101 is blocked by `fk_activities_contact`: the delete first cascades to the account's contacts, and activities still reference them.
3. The query outputs, the data dictionary and the Mermaid ERD were generated from the live database, so the documentation always matches the implemented schema.
