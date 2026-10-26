-- =====================================================================
--  PulseCRM - MySQL account used by the web dashboard
--
--  Least privilege: the website can read every table and view, and it can
--  change only its own sign-in tables (database/web_access.sql). It cannot
--  INSERT, UPDATE or DELETE CRM data, run procedures or change the schema.
--  Run this as an administrator after database/pulse_crm.sql and
--  database/web_access.sql, with a strong password of your own. Never
--  commit the real password. (web/setup_cloud_db.py runs these statements
--  with a random password.)
-- =====================================================================

CREATE USER IF NOT EXISTS 'pulse_web'@'%' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT SELECT ON pulse_crm.* TO 'pulse_web'@'%';

-- the sign-in tables, and nothing else
GRANT INSERT, UPDATE, DELETE ON pulse_crm.web_accounts TO 'pulse_web'@'%';
GRANT INSERT, DELETE ON pulse_crm.web_account_privileges TO 'pulse_web'@'%';
GRANT INSERT ON pulse_crm.web_audit_log TO 'pulse_web'@'%';

-- Check: USAGE, SELECT on pulse_crm.* and the three table grants above
SHOW GRANTS FOR 'pulse_web'@'%';
