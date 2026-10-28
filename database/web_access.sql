-- =====================================================================
--  PulseCRM - sign-in and privileges for the web dashboard
--
--  Run after database/pulse_crm.sql, in the same database. It adds six
--  tables for the web application only; the 18 CRM tables are unchanged.
--    web_privileges          what can be granted: view, add, edit and delete per page,
--                            plus user management
--    web_accounts            who may sign in (optionally linked to a CRM user)
--    web_account_privileges  which privileges each account has (bridge table)
--    web_role_privileges     default privileges for each CRM role (bridge table)
--    web_audit_log           sign-ins and user-management changes
--    web_login_failures      wrong passwords per network address (sign-in throttling)
--  Passwords are stored only as salted scrypt hashes. Wrong passwords block the
--  network address they came from, never the account itself, so nobody can lock
--  other people out of a shared account.
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
    password_locked      BOOLEAN          NOT NULL DEFAULT FALSE  COMMENT 'TRUE for a shared demo account: its users cannot change the password',
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
                                                     'account_deleted', 'record_added', 'record_updated',
                                                     'record_deleted', 'procedure_called'))
) ENGINE = InnoDB COMMENT = 'Sign-ins and user-management changes';

-- 5 wrong passwords for one account from one address, or 20 from one address in
-- total, block that address for 15 minutes; rows older than a day are deleted
CREATE TABLE IF NOT EXISTS web_login_failures (
    failure_id BIGINT      NOT NULL AUTO_INCREMENT COMMENT 'Failed sign-in identifier',
    ip_address VARCHAR(45) NOT NULL COMMENT 'Network address of the attempt (IPv4 or IPv6)',
    account_id INT         NULL     COMMENT 'Account that was tried (FK web_accounts); NULL for an unknown user name',
    failed_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When it happened',
    PRIMARY KEY (failure_id),
    KEY idx_web_failures_address (ip_address, failed_at),
    CONSTRAINT fk_web_failures_account FOREIGN KEY (account_id) REFERENCES web_accounts (account_id) ON DELETE CASCADE
) ENGINE = InnoDB COMMENT = 'Wrong passwords per network address, for sign-in throttling';


-- ---------- privileges -----------------------------------------------
INSERT IGNORE INTO web_privileges (privilege_code, privilege_name, description, sort_order) VALUES
('view_overview', 'Dashboard',    'KPI cards, pipeline by stage, sales funnel and top accounts', 1),
('view_pipeline', 'Pipeline',     'Open and closed deals with weighted values',                2),
('view_accounts', 'Accounts',     'Account 360 view of every company',                         3),
('view_team',     'Sales Team',   'Sales representative scorecard',                            4),
('view_leads',    'Leads',        'Lead status, hottest leads and conversion by source',       5),
('view_support',  'Support',      'Support tickets and resolution times',                      6),
('view_invoices', 'Invoices',     'Invoices, payments and balances due',                       7),
('view_database', 'Database',     'Table row counts, ER diagram and integrity rules',          8),
('manage_users',  'Manage users', 'Create web accounts, grant privileges, reset passwords',    9);

-- add, edit and delete records on a page (codes are <action>_<page>)
INSERT IGNORE INTO web_privileges (privilege_code, privilege_name, description, sort_order) VALUES
('add_pipeline',    'Pipeline: add',      'Add deals, line items, activities, products and stages',      10),
('edit_pipeline',   'Pipeline: edit',     'Edit those records and move deals between stages',             11),
('delete_pipeline', 'Pipeline: delete',   'Delete deals, line items, activities, products and stages',   12),
('add_accounts',    'Accounts: add',      'Add accounts, contacts and industries',                        13),
('edit_accounts',   'Accounts: edit',     'Edit accounts, contacts and industries',                       14),
('delete_accounts', 'Accounts: delete',   'Delete accounts, contacts and industries',                     15),
('add_team',        'Sales Team: add',    'Add CRM staff and roles',                                      16),
('edit_team',       'Sales Team: edit',   'Edit CRM staff and roles',                                     17),
('delete_team',     'Sales Team: delete', 'Delete CRM staff and roles',                                   18),
('add_leads',       'Leads: add',         'Add leads, campaigns, campaign members and lead sources',      19),
('edit_leads',      'Leads: edit',        'Edit those records and convert qualified leads',               20),
('delete_leads',    'Leads: delete',      'Delete leads, campaigns, campaign members and lead sources',   21),
('add_support',     'Support: add',       'Add support tickets',                                          22),
('edit_support',    'Support: edit',      'Edit support tickets',                                         23),
('delete_support',  'Support: delete',    'Delete support tickets',                                       24),
('add_invoices',    'Invoices: add',      'Add invoices and payments, and record payments',               25),
('edit_invoices',   'Invoices: edit',     'Edit invoices and payments',                                   26),
('delete_invoices', 'Invoices: delete',   'Delete invoices and payments',                                 27);

-- the Marketing page: campaigns, campaign members and lead sources (until 2026-10 part of Leads)
INSERT IGNORE INTO web_privileges (privilege_code, privilege_name, description, sort_order) VALUES
('view_marketing',   'Marketing',          'Campaign results, audience and lead sources',                  28),
('add_marketing',    'Marketing: add',     'Add campaigns, campaign members and lead sources',             29),
('edit_marketing',   'Marketing: edit',    'Edit campaigns, campaign members and lead sources',            30),
('delete_marketing', 'Marketing: delete',  'Delete campaigns, campaign members and lead sources',          31);
UPDATE web_privileges SET description = 'Add leads'                          WHERE privilege_code = 'add_leads';
UPDATE web_privileges SET description = 'Edit leads and convert qualified leads' WHERE privilege_code = 'edit_leads';
UPDATE web_privileges SET description = 'Delete leads'                       WHERE privilege_code = 'delete_leads';
-- the Overview page is called Dashboard since 2026-10
UPDATE web_privileges SET privilege_name = 'Dashboard',
                          description = 'KPI cards, pipeline by stage, sales funnel and top accounts'
WHERE privilege_code = 'view_overview';

-- ---------- default privileges for each CRM role ---------------------
INSERT IGNORE INTO web_role_privileges (role_id, privilege_code)
SELECT r.role_id, p.privilege_code
FROM roles r
JOIN web_privileges p
  ON r.role_name = 'Administrator'
  OR (r.role_name = 'Sales Manager'
      AND p.privilege_code IN ('view_overview', 'view_pipeline', 'view_accounts', 'view_team', 'view_leads', 'view_invoices',
                               'add_pipeline', 'edit_pipeline', 'delete_pipeline', 'add_accounts', 'edit_accounts',
                               'delete_accounts', 'add_leads', 'edit_leads', 'delete_leads', 'add_invoices', 'edit_invoices',
                               'view_marketing'))
  OR (r.role_name = 'Sales Representative'
      AND p.privilege_code IN ('view_overview', 'view_pipeline', 'view_accounts', 'view_leads',
                               'add_pipeline', 'edit_pipeline', 'add_accounts', 'edit_accounts', 'add_leads', 'edit_leads'))
  OR (r.role_name = 'Marketing'
      AND p.privilege_code IN ('view_overview', 'view_leads', 'add_leads', 'edit_leads',
                               'view_marketing', 'add_marketing', 'edit_marketing', 'delete_marketing'))
  OR (r.role_name = 'Support Agent'
      AND p.privilege_code IN ('view_overview', 'view_accounts', 'view_support', 'add_support', 'edit_support'));
