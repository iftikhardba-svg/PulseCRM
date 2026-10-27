-- =====================================================================
--  PulseCRM - MySQL account used by the web dashboard
--
--  Least privilege, table by table:
--    * SELECT on every table and view
--    * INSERT, UPDATE, DELETE on the 17 CRM tables the dashboard edits
--      (never on opportunity_stage_history, the audit trail written by the
--      trigger and the procedures)
--    * EXECUTE on the three procedures that change data
--    * writes on the three sign-in tables of database/web_access.sql
--  It has no CREATE, ALTER, DROP or GRANT rights.
--  Run this as an administrator after database/pulse_crm.sql and
--  database/web_access.sql, with a strong password of your own. Never
--  commit the real password. (web/setup_cloud_db.py runs these statements
--  with a random password.)
-- =====================================================================

CREATE USER IF NOT EXISTS 'pulse_web'@'%' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT SELECT ON pulse_crm.* TO 'pulse_web'@'%';

-- CRM records: add, edit and delete from the dashboard
GRANT INSERT, UPDATE, DELETE ON pulse_crm.roles TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.users TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.industries TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.accounts TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.contacts TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.lead_sources TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.leads TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.pipeline_stages TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.opportunities TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.products TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.opportunity_products TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.activities TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.campaigns TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.campaign_leads TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.tickets TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.invoices TO 'pulse_web'@'%';
GRANT INSERT, UPDATE, DELETE ON pulse_crm.payments TO 'pulse_web'@'%';

-- business operations, each one transaction inside the procedure
GRANT EXECUTE ON PROCEDURE pulse_crm.sp_convert_lead TO 'pulse_web'@'%';
GRANT EXECUTE ON PROCEDURE pulse_crm.sp_update_opportunity_stage TO 'pulse_web'@'%';
GRANT EXECUTE ON PROCEDURE pulse_crm.sp_record_payment TO 'pulse_web'@'%';

-- the sign-in tables
GRANT INSERT, UPDATE, DELETE ON pulse_crm.web_accounts TO 'pulse_web'@'%';
GRANT INSERT, DELETE ON pulse_crm.web_account_privileges TO 'pulse_web'@'%';
GRANT INSERT ON pulse_crm.web_audit_log TO 'pulse_web'@'%';

-- Check the result
SHOW GRANTS FOR 'pulse_web'@'%';
