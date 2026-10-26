-- =====================================================================
--  PulseCRM - sign-in and privileges for the web dashboard
--
--  Run after database/pulse_crm.sql, in the same database. It adds five
--  tables for the web application only; the 18 CRM tables are unchanged.
--    web_privileges          what can be granted (one per page, plus user management)
--    web_accounts            who may sign in (optionally linked to a CRM user)
--    web_account_privileges  which privileges each account has (bridge table)
--    web_role_privileges     default privileges for each CRM role (bridge table)
--    web_audit_log           sign-ins and user-management changes
--  Passwords are stored only as salted scrypt hashes.
--  Running it again keeps existing accounts.
-- =====================================================================

CREATE TABLE IF NOT EXISTS web_privileges (
    privilege_code VARCHAR(30)      NOT NULL COMMENT 'Privilege identifier used by the web application',
    privilege_name VARCHAR(60)      NOT NULL COMMENT 'Name shown on the Users page',
    description    VARCHAR(200)     NOT NULL COMMENT 'What the privilege allows',
    sort_order     TINYINT UNSIGNED NOT NULL COMMENT 'Display order',
    PRIMARY KEY (privilege_code),
    UNIQUE KEY uq_web_privileges_order (sort_order)
) ENGINE = InnoDB COMMENT = 'Privileges that can be granted to web accounts';

CREATE TABLE IF NOT EXISTS web_accounts (
    account_id           INT              NOT NULL AUTO_INCREMENT COMMENT 'Web account identifier',
    username             VARCHAR(40)      NOT NULL                COMMENT 'Sign-in name, lower case',
    display_name         VARCHAR(100)     NOT NULL                COMMENT 'Name shown in the application',
    user_id              INT              NULL                    COMMENT 'Linked CRM staff member (FK users), optional',
    password_hash        VARCHAR(255)     NOT NULL                COMMENT 'Salted scrypt hash; the password itself is never stored',
    is_active            BOOLEAN          NOT NULL DEFAULT TRUE   COMMENT 'FALSE blocks sign-in',
    must_change_password BOOLEAN          NOT NULL DEFAULT TRUE   COMMENT 'TRUE until the user replaces a temporary password',
    failed_logins        TINYINT UNSIGNED NOT NULL DEFAULT 0      COMMENT 'Wrong passwords in a row',
    locked_until         DATETIME         NULL                    COMMENT 'Sign-in blocked until this time after 5 wrong passwords',
    last_login_at        DATETIME         NULL                    COMMENT 'Last successful sign-in',
    created_at           DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_web_accounts_username (username),
    UNIQUE KEY uq_web_accounts_user (user_id),
    CONSTRAINT fk_web_accounts_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT chk_web_accounts_username CHECK (username REGEXP '^[a-z0-9._-]{3,40}$')
) ENGINE = InnoDB COMMENT = 'People who may sign in to the web dashboard';

CREATE TABLE IF NOT EXISTS web_account_privileges (
    account_id     INT         NOT NULL COMMENT 'Account (FK web_accounts)',
    privilege_code VARCHAR(30) NOT NULL COMMENT 'Granted privilege (FK web_privileges)',
    granted_by     INT         NULL     COMMENT 'Administrator who granted it (FK web_accounts)',
    granted_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When it was granted',
    PRIMARY KEY (account_id, privilege_code),
    CONSTRAINT fk_web_accpriv_account    FOREIGN KEY (account_id)     REFERENCES web_accounts (account_id) ON DELETE CASCADE,
    CONSTRAINT fk_web_accpriv_privilege  FOREIGN KEY (privilege_code) REFERENCES web_privileges (privilege_code),
    CONSTRAINT fk_web_accpriv_granted_by FOREIGN KEY (granted_by)     REFERENCES web_accounts (account_id) ON DELETE SET NULL
) ENGINE = InnoDB COMMENT = 'Privileges granted to each web account (bridge table)';

CREATE TABLE IF NOT EXISTS web_role_privileges (
    role_id        INT         NOT NULL COMMENT 'CRM role (FK roles)',
    privilege_code VARCHAR(30) NOT NULL COMMENT 'Default privilege for that role (FK web_privileges)',
    PRIMARY KEY (role_id, privilege_code),
    CONSTRAINT fk_web_rolepriv_role      FOREIGN KEY (role_id)        REFERENCES roles (role_id) ON DELETE CASCADE,
    CONSTRAINT fk_web_rolepriv_privilege FOREIGN KEY (privilege_code) REFERENCES web_privileges (privilege_code)
) ENGINE = InnoDB COMMENT = 'Default web privileges for each CRM role (bridge table)';

CREATE TABLE IF NOT EXISTS web_audit_log (
    log_id     INT          NOT NULL AUTO_INCREMENT COMMENT 'Log entry identifier',
    account_id INT          NULL     COMMENT 'Account that acted (FK web_accounts); NULL for an unknown user name',
    action     VARCHAR(30)  NOT NULL COMMENT 'What happened',
    detail     VARCHAR(255) NULL     COMMENT 'Details, such as which account was changed',
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When it happened',
    PRIMARY KEY (log_id),
    KEY idx_web_audit_created (created_at),
    CONSTRAINT fk_web_audit_account FOREIGN KEY (account_id) REFERENCES web_accounts (account_id) ON DELETE SET NULL,
    CONSTRAINT chk_web_audit_action CHECK (action IN ('login', 'login_failed', 'logout', 'password_changed',
                                                     'account_created', 'account_updated', 'password_reset',
                                                     'account_deleted'))
) ENGINE = InnoDB COMMENT = 'Sign-ins and user-management changes';


-- ---------- privileges -----------------------------------------------
INSERT IGNORE INTO web_privileges (privilege_code, privilege_name, description, sort_order) VALUES
('view_overview', 'Overview',     'KPIs, pipeline by stage, leads by source and top accounts', 1),
('view_pipeline', 'Pipeline',     'Open and closed deals with weighted values',                2),
('view_accounts', 'Accounts',     'Account 360 view of every company',                         3),
('view_team',     'Sales Team',   'Sales representative scorecard',                            4),
('view_leads',    'Leads',        'Lead status, hottest leads and conversion by source',       5),
('view_support',  'Support',      'Support tickets and resolution times',                      6),
('view_invoices', 'Invoices',     'Invoices, payments and balances due',                       7),
('view_database', 'Database',     'Table row counts, ER diagram and integrity rules',          8),
('manage_users',  'Manage users', 'Create web accounts, grant privileges, reset passwords',    9);

-- ---------- default privileges for each CRM role ---------------------
INSERT IGNORE INTO web_role_privileges (role_id, privilege_code)
SELECT r.role_id, p.privilege_code
FROM roles r
JOIN web_privileges p
  ON r.role_name = 'Administrator'
  OR (r.role_name = 'Sales Manager'
      AND p.privilege_code IN ('view_overview', 'view_pipeline', 'view_accounts', 'view_team', 'view_leads', 'view_invoices'))
  OR (r.role_name = 'Sales Representative'
      AND p.privilege_code IN ('view_overview', 'view_pipeline', 'view_accounts', 'view_leads'))
  OR (r.role_name = 'Marketing'
      AND p.privilege_code IN ('view_overview', 'view_leads'))
  OR (r.role_name = 'Support Agent'
      AND p.privilege_code IN ('view_overview', 'view_accounts', 'view_support'));
