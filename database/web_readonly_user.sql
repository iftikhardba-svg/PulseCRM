-- =====================================================================
--  PulseCRM - read-only account for the web dashboard
--
--  Least privilege: the website can read every table and view but cannot
--  INSERT, UPDATE, DELETE, run procedures or change the schema.
--  Run this as an administrator after database/pulse_crm.sql, with a
--  strong password of your own. Never commit the real password.
--  (web/setup_cloud_db.py runs these statements with a random password.)
-- =====================================================================

CREATE USER IF NOT EXISTS 'pulse_web'@'%' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT SELECT ON pulse_crm.* TO 'pulse_web'@'%';

-- Check: only USAGE and SELECT should be listed
SHOW GRANTS FOR 'pulse_web'@'%';
