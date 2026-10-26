-- =====================================================================
--  PulseCRM - read-only account for the web dashboard
--
--  Least privilege: the website can read every table and view but cannot
--  INSERT, UPDATE, DELETE, run procedures or change the schema.
--  Run the part for your database system as an administrator, after the
--  build script, with a strong password of your own. Never commit the
--  real password. (web/setup_supabase.py does the PostgreSQL part with a
--  random password.)
-- =====================================================================

-- ---------- MySQL (after database/pulse_crm.sql) ---------------------
CREATE USER IF NOT EXISTS 'pulse_web'@'%' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT SELECT ON pulse_crm.* TO 'pulse_web'@'%';

-- Check: only USAGE and SELECT should be listed
SHOW GRANTS FOR 'pulse_web'@'%';


-- ---------- PostgreSQL / Supabase (after database/pulse_crm_postgres.sql)
-- CREATE ROLE pulse_web WITH LOGIN PASSWORD 'replace-with-a-strong-password';
-- GRANT USAGE ON SCHEMA pulse_crm TO pulse_web;
-- GRANT SELECT ON ALL TABLES IN SCHEMA pulse_crm TO pulse_web;
-- ALTER ROLE pulse_web SET search_path = pulse_crm;
-- ALTER ROLE pulse_web SET default_transaction_read_only = on;
