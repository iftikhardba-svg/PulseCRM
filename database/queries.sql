-- =====================================================================
--  PulseCRM - Demonstration and Report Queries
--  Run database/pulse_crm.sql first. Sections 6 and 7 change data
--  (lead conversion, closing a deal, a payment), so rebuild the database
--  with pulse_crm.sql before running this file a second time.
--  Statements marked 'Expected: ERROR' are integrity tests that must fail.
-- =====================================================================

USE pulse_crm;


-- =====================================================================
-- 1. Basic Retrieval and Filtering
-- =====================================================================

-- Q01: Staff Directory with Role and Manager
-- List all active staff with their role and line manager (self join on users).
-- Q01: active staff, role and manager
SELECT u.user_id,
       u.full_name,
       r.role_name,
       COALESCE(m.full_name, '-') AS manager
FROM users u
JOIN roles r       ON u.role_id = r.role_id
LEFT JOIN users m  ON u.manager_id = m.user_id
WHERE u.is_active = TRUE
ORDER BY r.role_id, u.full_name;

-- Q02: Customer Accounts in Karachi or Islamabad
-- Show customer accounts located in Karachi or Islamabad, largest annual revenue first.
-- Q02: customers in two cities
SELECT account_id,
       account_name,
       city,
       annual_revenue,
       employee_count
FROM accounts
WHERE account_type = 'Customer'
  AND city IN ('Karachi', 'Islamabad')
ORDER BY annual_revenue DESC;

-- Q03: Hot Leads
-- Find open leads (New, Contacted or Qualified) with a lead score of 60 or more.
-- Q03: open leads with a high score
SELECT lead_id,
       CONCAT(first_name, ' ', last_name) AS lead_name,
       company_name,
       city,
       status,
       lead_score
FROM leads
WHERE status IN ('New', 'Contacted', 'Qualified')
  AND lead_score >= 60
ORDER BY lead_score DESC;


-- =====================================================================
-- 2. Aggregate Functions, GROUP BY and HAVING
-- =====================================================================

-- Q04: Pipeline Summary by Stage
-- Count deals and total their value and weighted value for every pipeline stage.
-- Q04: pipeline by stage
SELECT s.stage_name,
       s.win_probability,
       COUNT(o.opportunity_id)                              AS deals,
       COALESCE(SUM(o.amount), 0)                           AS total_value,
       ROUND(COALESCE(SUM(o.amount), 0) * s.win_probability / 100, 2) AS weighted_value
FROM pipeline_stages s
LEFT JOIN opportunities o ON o.stage_id = s.stage_id
GROUP BY s.stage_id, s.stage_name, s.win_probability, s.stage_order
ORDER BY s.stage_order;

-- Q05: Busy Lead Sources
-- Show lead sources that produced at least 4 leads, with their average lead score.
-- Q05: lead sources with 4 or more leads (HAVING)
SELECT ls.source_name,
       COUNT(*)                     AS total_leads,
       ROUND(AVG(l.lead_score), 1)  AS avg_score
FROM leads l
JOIN lead_sources ls ON l.source_id = ls.source_id
GROUP BY ls.source_id, ls.source_name
HAVING COUNT(*) >= 4
ORDER BY total_leads DESC, avg_score DESC;

-- Q06: Monthly Won Revenue in 2026
-- Total the value of deals won in each month of 2026.
-- Q06: won revenue per month
SELECT DATE_FORMAT(o.actual_close_date, '%Y-%m') AS close_month,
       COUNT(*)                                  AS deals_won,
       SUM(o.amount)                             AS won_revenue
FROM opportunities o
JOIN pipeline_stages s ON o.stage_id = s.stage_id
WHERE s.is_won = TRUE
  AND YEAR(o.actual_close_date) = 2026
GROUP BY close_month
ORDER BY close_month;


-- =====================================================================
-- 3. JOINs Across Related Tables
-- =====================================================================

-- Q07: Open Deals with Account, Contact and Owner
-- Join opportunities, accounts, contacts, users and stages to list every open deal.
-- Q07: open pipeline (five-table join)
SELECT o.opportunity_id,
       o.opportunity_name,
       a.account_name,
       CONCAT(c.first_name, ' ', c.last_name) AS primary_contact,
       u.full_name                            AS owner,
       s.stage_name,
       o.amount,
       o.expected_close_date
FROM opportunities o
JOIN accounts a         ON o.account_id = a.account_id
LEFT JOIN contacts c    ON o.primary_contact_id = c.contact_id
JOIN users u            ON o.owner_user_id = u.user_id
JOIN pipeline_stages s  ON o.stage_id = s.stage_id
WHERE s.is_closed = FALSE
ORDER BY o.expected_close_date;

-- Q08: Accounts without Support Tickets
-- Find accounts that have never raised a support ticket (LEFT JOIN ... IS NULL).
-- Q08: accounts with no tickets
SELECT a.account_id,
       a.account_name,
       a.account_type
FROM accounts a
LEFT JOIN tickets t ON a.account_id = t.account_id
WHERE t.ticket_id IS NULL
ORDER BY a.account_name;

-- Q09: Product Revenue from Won Deals
-- Rank products by the revenue they brought in from won deals.
-- Q09: revenue per product (won deals only)
SELECT p.product_code,
       p.product_name,
       p.category,
       SUM(op.quantity)   AS units_sold,
       SUM(op.line_total) AS won_revenue
FROM opportunity_products op
JOIN products p         ON op.product_id = p.product_id
JOIN opportunities o    ON op.opportunity_id = o.opportunity_id
JOIN pipeline_stages s  ON o.stage_id = s.stage_id
WHERE s.is_won = TRUE
GROUP BY p.product_id, p.product_code, p.product_name, p.category
ORDER BY won_revenue DESC;

-- Q10: Campaign Effectiveness
-- For each campaign show leads reached, leads that responded, leads converted and cost per lead.
-- Q10: campaign results
SELECT c.campaign_name,
       c.channel,
       c.budget,
       COUNT(cl.lead_id)                                         AS leads_reached,
       SUM(CASE WHEN cl.response = 'Responded' THEN 1 ELSE 0 END) AS responded,
       SUM(CASE WHEN l.status = 'Converted' THEN 1 ELSE 0 END)    AS converted,
       ROUND(c.budget / NULLIF(COUNT(cl.lead_id), 0), 2)          AS cost_per_lead
FROM campaigns c
LEFT JOIN campaign_leads cl ON c.campaign_id = cl.campaign_id
LEFT JOIN leads l           ON cl.lead_id = l.lead_id
GROUP BY c.campaign_id, c.campaign_name, c.channel, c.budget
ORDER BY converted DESC, responded DESC;


-- =====================================================================
-- 4. Subqueries, CTEs and Window Functions
-- =====================================================================

-- Q11: Accounts above Average Won Revenue
-- Find accounts whose won revenue is greater than the average won revenue of accounts that have won deals.
-- Q11: subquery against an average
SELECT account_name,
       won_revenue
FROM vw_account_360
WHERE won_revenue > (SELECT AVG(won_revenue)
                     FROM vw_account_360
                     WHERE won_revenue > 0)
ORDER BY won_revenue DESC;

-- Q12: Open Leads Never Contacted
-- List open leads that have no activity logged against them (NOT EXISTS).
-- Q12: open leads with no activity
SELECT l.lead_id,
       CONCAT(l.first_name, ' ', l.last_name) AS lead_name,
       l.company_name,
       l.status,
       l.lead_score
FROM leads l
WHERE l.status IN ('New', 'Contacted', 'Qualified')
  AND NOT EXISTS (SELECT 1
                  FROM activities a
                  WHERE a.lead_id = l.lead_id)
ORDER BY l.lead_score DESC;

-- Q13: Sales Rep Ranking
-- Use a CTE and RANK() to rank sales staff by won revenue.
-- Q13: CTE + window function
WITH rep_revenue AS (
    SELECT u.full_name AS sales_rep,
           SUM(CASE WHEN s.is_won = TRUE THEN o.amount ELSE 0 END) AS won_revenue,
           COUNT(o.opportunity_id)                                 AS deals
    FROM users u
    JOIN opportunities o   ON o.owner_user_id = u.user_id
    JOIN pipeline_stages s ON o.stage_id = s.stage_id
    GROUP BY u.user_id, u.full_name
)
SELECT RANK() OVER (ORDER BY won_revenue DESC) AS revenue_rank,
       sales_rep,
       deals,
       won_revenue
FROM rep_revenue
ORDER BY revenue_rank;

-- Q14: Average Sales Cycle
-- Using a CTE, compare the average number of days from creation to close for won and lost deals.
-- Q14: sales cycle in days
WITH closed_deals AS (
    SELECT s.stage_name,
           DATEDIFF(o.actual_close_date, DATE(o.created_at)) AS cycle_days,
           o.amount
    FROM opportunities o
    JOIN pipeline_stages s ON o.stage_id = s.stage_id
    WHERE s.is_closed = TRUE
)
SELECT stage_name,
       COUNT(*)                 AS deals,
       ROUND(AVG(cycle_days), 1) AS avg_cycle_days,
       MIN(cycle_days)          AS shortest,
       MAX(cycle_days)          AS longest
FROM closed_deals
GROUP BY stage_name;


-- =====================================================================
-- 5. Reporting Views
-- =====================================================================

-- Q15: Account 360 View
-- Show the top accounts from vw_account_360, ordered by won revenue.
-- Q15: account 360
SELECT account_name,
       industry_name,
       account_type,
       contacts,
       open_opportunities,
       open_pipeline_value,
       won_revenue,
       open_tickets
FROM vw_account_360
ORDER BY won_revenue DESC, open_pipeline_value DESC;

-- Q16: Sales Rep Scorecard
-- Show the sales team scorecard from vw_sales_rep_performance.
-- Q16: sales scorecard
SELECT sales_rep,
       leads_owned,
       leads_converted,
       opportunities,
       won_deals,
       lost_deals,
       won_revenue,
       open_pipeline,
       win_rate_pct
FROM vw_sales_rep_performance
ORDER BY won_revenue DESC;

-- Q17: Lead Conversion by Source
-- Show conversion rate by lead source from vw_lead_conversion_by_source.
-- Q17: lead conversion
SELECT *
FROM vw_lead_conversion_by_source
ORDER BY conversion_rate_pct DESC, total_leads DESC;

-- Q18: Support Resolution Time by Priority
-- Average resolution hours and customer satisfaction per ticket priority, from vw_ticket_resolution.
-- Q18: support performance
SELECT priority,
       COUNT(*)                           AS tickets,
       SUM(CASE WHEN resolved_at IS NULL THEN 1 ELSE 0 END) AS still_open,
       ROUND(AVG(resolution_hours), 1)    AS avg_resolution_hours,
       ROUND(AVG(satisfaction_score), 1)  AS avg_satisfaction
FROM vw_ticket_resolution
GROUP BY priority
ORDER BY FIELD(priority, 'Critical', 'High', 'Medium', 'Low');

-- Q19: Outstanding Invoices
-- List invoices that still have a balance due, from vw_invoice_balance.
-- Q19: money still to collect
SELECT invoice_number,
       account_name,
       due_date,
       total_amount,
       amount_paid,
       balance_due,
       status
FROM vw_invoice_balance
WHERE balance_due > 0
ORDER BY due_date;


-- =====================================================================
-- 6. Stored Procedures, Trigger and Transactions
-- =====================================================================

-- Q20: Account Summary Procedure
-- Call sp_account_summary for Indus Weave Textiles (account 101). It returns two result sets.
-- Q20: account 360 + open deals for account 101
CALL sp_account_summary(101);

-- Q21: Sales Rep Pipeline with OUT Parameters
-- Call sp_sales_rep_pipeline for Usman Tariq (user 4) and read the two OUT values.
-- Q21: OUT parameters
CALL sp_sales_rep_pipeline(4, @open_pipeline, @weighted_pipeline);

-- returned values
SELECT @open_pipeline AS open_pipeline,
       @weighted_pipeline AS weighted_pipeline;

-- Q22: Convert a Lead (Transaction)
-- Convert qualified lead 307 into an account, contact and opportunity in one transaction with sp_convert_lead.
-- Q22: convert lead 307
CALL sp_convert_lead(307, 'Gwadar Port ERP Implementation', 2400000.00, '2027-01-31', @new_opportunity);

-- lead is now Converted
SELECT lead_id, status, converted_account_id
FROM leads
WHERE lead_id = 307;

-- new account and contact
SELECT a.account_id, a.account_name, a.account_type, a.city,
       CONCAT(c.first_name, ' ', c.last_name) AS contact, c.is_primary
FROM accounts a
JOIN contacts c ON c.account_id = a.account_id
WHERE a.account_id = (SELECT converted_account_id FROM leads WHERE lead_id = 307);

-- new opportunity
SELECT opportunity_id, opportunity_name, account_name, owner_name, stage_name, amount
FROM vw_sales_pipeline
WHERE opportunity_id = @new_opportunity;

-- Q23: Close a Deal as Won (Trigger + Auto Invoice)
-- Move opportunity 410 to Closed Won with sp_update_opportunity_stage. The trigger logs the stage change and the procedure raises the invoice in the same transaction.
-- Q23: Bilal Hassan (user 2) closes deal 410
CALL sp_update_opportunity_stage(410, 'Closed Won', 2, NULL);

-- stage history written by the trigger
SELECT h.history_id, f.stage_name AS from_stage, t.stage_name AS to_stage,
       u.full_name AS changed_by
FROM opportunity_stage_history h
LEFT JOIN pipeline_stages f ON h.from_stage_id = f.stage_id
JOIN pipeline_stages t      ON h.to_stage_id = t.stage_id
LEFT JOIN users u           ON h.changed_by = u.user_id
WHERE h.opportunity_id = 410
ORDER BY h.history_id;

-- invoice created automatically
SELECT invoice_number, account_name, total_amount, balance_due, status
FROM vw_invoice_balance
WHERE opportunity_name = 'Crescent Health ERP Phase 2';

-- Q24: Record a Payment (Transaction)
-- Record a part payment of PKR 1,000,000 against the new invoice with sp_record_payment.
-- Q24: part payment for the new invoice
SET @invoice_id = (SELECT invoice_id FROM invoices WHERE opportunity_id = 410);
CALL sp_record_payment(@invoice_id, 1000000.00, 'Bank Transfer', 'BT-26-0410A');

-- invoice is now Partially Paid
SELECT invoice_number, total_amount, amount_paid, balance_due, status
FROM vw_invoice_balance
WHERE invoice_id = @invoice_id;

-- Q25: Price What-If with SAVEPOINT
-- Test a price change inside a transaction: keep the training price rise, undo a mistaken software rise with ROLLBACK TO SAVEPOINT, then roll back the whole what-if.
-- Q25: prices before
SELECT product_code, category, unit_price
FROM products
WHERE category IN ('Training', 'Software')
ORDER BY product_code;

START TRANSACTION;

UPDATE products SET unit_price = unit_price * 1.05 WHERE category = 'Training';
SAVEPOINT training_price_updated;

UPDATE products SET unit_price = unit_price * 1.50 WHERE category = 'Software';

-- inside the transaction: both changes visible
SELECT product_code, category, unit_price
FROM products
WHERE category IN ('Training', 'Software')
ORDER BY product_code;

ROLLBACK TO SAVEPOINT training_price_updated;

-- after ROLLBACK TO SAVEPOINT: only the training rise remains
SELECT product_code, category, unit_price
FROM products
WHERE category IN ('Training', 'Software')
ORDER BY product_code;

-- it was only a what-if, so cancel everything
ROLLBACK;

-- after ROLLBACK: original prices
SELECT product_code, category, unit_price
FROM products
WHERE category IN ('Training', 'Software')
ORDER BY product_code;


-- =====================================================================
-- 7. Data Integrity Tests (expected to fail)
-- =====================================================================

-- Q26: Lead Score Above 100
-- Try to give a lead a score of 150. The CHECK constraint chk_leads_score must reject it.
-- Q26: lead score outside 0-100 (Expected: ERROR)
UPDATE leads SET lead_score = 150 WHERE lead_id = 317;

-- Q27: Duplicate Contact Email
-- Try to add a contact with an email that already exists. The UNIQUE key must reject it.
-- Q27: duplicate email (Expected: ERROR)
INSERT INTO contacts (account_id, first_name, last_name, email)
VALUES (102, 'Test', 'Duplicate', 'asif.mahmood@indusweave.example');

-- Q28: Deal for a Missing Account
-- Try to create an opportunity for account 999, which does not exist. The foreign key must reject it.
-- Q28: unknown account (Expected: ERROR)
INSERT INTO opportunities (opportunity_name, account_id, owner_user_id, stage_id, expected_close_date)
VALUES ('Ghost Deal', 999, 3, 1, '2027-01-01');

-- Q29: Delete an Account that Has Deals
-- Try to delete account 101. The delete would cascade to its contacts, but activities, deals and tickets still reference them, so a foreign key blocks the whole delete and nothing is removed.
-- Q29: parent row still referenced (Expected: ERROR)
DELETE FROM accounts WHERE account_id = 101;

-- Q30: Overpayment Rejected by Procedure
-- Try to record a payment larger than the balance due. The procedure raises its own error and rolls back.
-- Q30: payment larger than the balance (Expected: ERROR)
CALL sp_record_payment(903, 99999999.00, 'Card', 'CARD-TEST-01');

-- Q31: Closed Lost without a Reason
-- Try to mark a deal as Closed Lost without giving a loss reason.
-- Q31: missing loss reason (Expected: ERROR)
CALL sp_update_opportunity_stage(411, 'Closed Lost', 3, NULL);

-- Q32: Converting an Unqualified Lead
-- Try to convert lead 322, which is Unqualified.
-- Q32: unqualified lead (Expected: ERROR)
CALL sp_convert_lead(322, 'Test Deal', 1000.00, '2027-01-01', @x);

