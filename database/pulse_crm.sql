-- =====================================================================
--  PulseCRM - Customer Relationship Management Database
--  Final Project | Relational Database Management Systems (RDBMS)
--  Student: Iftikhar Ahmed | Postgraduate Diploma in Generative AI | NED University of Engineering & Technology, Karachi
--  DBMS: MySQL 8.0+  (InnoDB, utf8mb4)
--
--  This single script builds the complete database:
--    1. Database
--    2. Tables with PK, FK, UNIQUE, CHECK, DEFAULT constraints
--    3. Secondary indexes
--    4. Sample data (fictional companies and people)
--    5. Views for reporting
--    6. Trigger (opportunity stage history)
--    7. Stored procedures with transactions
--    8. Verification queries
--
--  Run it top to bottom in MySQL Workbench or:
--    mysql -u root -p < database/pulse_crm.sql
--  Running it again rebuilds the database from scratch.
-- =====================================================================

DROP DATABASE IF EXISTS pulse_crm;
CREATE DATABASE pulse_crm
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
USE pulse_crm;


-- =====================================================================
-- 2. TABLES
-- =====================================================================

-- ---------- 2.1 roles ------------------------------------------------
CREATE TABLE roles (
    role_id     INT          NOT NULL AUTO_INCREMENT COMMENT 'Role identifier',
    role_name   VARCHAR(50)  NOT NULL                COMMENT 'Job role name',
    description VARCHAR(255) NULL                    COMMENT 'What the role is responsible for',
    PRIMARY KEY (role_id),
    UNIQUE KEY uq_roles_name (role_name)
) ENGINE = InnoDB COMMENT = 'Staff roles that control what users do in the CRM';

-- ---------- 2.2 users (CRM staff) ------------------------------------
CREATE TABLE users (
    user_id    INT          NOT NULL AUTO_INCREMENT COMMENT 'User identifier',
    full_name  VARCHAR(100) NOT NULL                COMMENT 'Staff member full name',
    email      VARCHAR(120) NOT NULL                COMMENT 'Login and contact email',
    phone      VARCHAR(20)  NULL                    COMMENT 'Office mobile number',
    role_id    INT          NOT NULL                COMMENT 'Role of the user (FK roles)',
    manager_id INT          NULL                    COMMENT 'Line manager (FK users, self reference)',
    hire_date  DATE         NOT NULL                COMMENT 'Date the user joined',
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE   COMMENT 'FALSE when the user has left',
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email),
    CONSTRAINT fk_users_role    FOREIGN KEY (role_id)    REFERENCES roles (role_id),
    CONSTRAINT fk_users_manager FOREIGN KEY (manager_id) REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT chk_users_email  CHECK (email LIKE '%_@_%._%')
) ENGINE = InnoDB COMMENT = 'Sales, marketing and support staff who use the CRM';

-- ---------- 2.3 industries -------------------------------------------
CREATE TABLE industries (
    industry_id   INT         NOT NULL AUTO_INCREMENT COMMENT 'Industry identifier',
    industry_name VARCHAR(60) NOT NULL                COMMENT 'Industry sector name',
    PRIMARY KEY (industry_id),
    UNIQUE KEY uq_industries_name (industry_name)
) ENGINE = InnoDB COMMENT = 'Lookup list of business sectors';

-- ---------- 2.4 accounts (companies) ---------------------------------
CREATE TABLE accounts (
    account_id     INT           NOT NULL AUTO_INCREMENT COMMENT 'Account identifier',
    account_name   VARCHAR(150)  NOT NULL                COMMENT 'Company name',
    industry_id    INT           NULL                    COMMENT 'Business sector (FK industries)',
    account_type   VARCHAR(20)   NOT NULL DEFAULT 'Prospect' COMMENT 'Prospect, Customer, Partner or Churned',
    website        VARCHAR(150)  NULL                    COMMENT 'Company website',
    phone          VARCHAR(20)   NULL                    COMMENT 'Main office phone',
    city           VARCHAR(60)   NOT NULL                COMMENT 'Head office city',
    country        VARCHAR(60)   NOT NULL DEFAULT 'Pakistan' COMMENT 'Head office country',
    annual_revenue DECIMAL(15,2) NULL                    COMMENT 'Company yearly revenue (PKR)',
    employee_count INT           NULL                    COMMENT 'Number of employees',
    owner_user_id  INT           NOT NULL                COMMENT 'Account manager (FK users)',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_accounts_name (account_name),
    CONSTRAINT fk_accounts_industry FOREIGN KEY (industry_id)   REFERENCES industries (industry_id),
    CONSTRAINT fk_accounts_owner    FOREIGN KEY (owner_user_id) REFERENCES users (user_id),
    CONSTRAINT chk_accounts_type      CHECK (account_type IN ('Prospect', 'Customer', 'Partner', 'Churned')),
    CONSTRAINT chk_accounts_revenue   CHECK (annual_revenue IS NULL OR annual_revenue >= 0),
    CONSTRAINT chk_accounts_employees CHECK (employee_count IS NULL OR employee_count >= 0)
) ENGINE = InnoDB COMMENT = 'Organisations we sell to or work with';

-- ---------- 2.5 contacts (people at accounts) ------------------------
CREATE TABLE contacts (
    contact_id INT          NOT NULL AUTO_INCREMENT COMMENT 'Contact identifier',
    account_id INT          NOT NULL                COMMENT 'Company the person works for (FK accounts)',
    first_name VARCHAR(50)  NOT NULL                COMMENT 'First name',
    last_name  VARCHAR(50)  NOT NULL                COMMENT 'Last name',
    job_title  VARCHAR(100) NULL                    COMMENT 'Job title',
    email      VARCHAR(120) NOT NULL                COMMENT 'Business email',
    phone      VARCHAR(20)  NULL                    COMMENT 'Phone number',
    is_primary BOOLEAN      NOT NULL DEFAULT FALSE  COMMENT 'TRUE for the main contact of the account',
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (contact_id),
    UNIQUE KEY uq_contacts_email (email),
    CONSTRAINT fk_contacts_account FOREIGN KEY (account_id) REFERENCES accounts (account_id) ON DELETE CASCADE,
    CONSTRAINT chk_contacts_email  CHECK (email LIKE '%_@_%._%')
) ENGINE = InnoDB COMMENT = 'Individual people who work at an account';

-- ---------- 2.6 lead_sources -----------------------------------------
CREATE TABLE lead_sources (
    source_id   INT         NOT NULL AUTO_INCREMENT COMMENT 'Lead source identifier',
    source_name VARCHAR(50) NOT NULL                COMMENT 'Where the lead came from',
    PRIMARY KEY (source_id),
    UNIQUE KEY uq_lead_sources_name (source_name)
) ENGINE = InnoDB COMMENT = 'Lookup list of lead channels';

-- ---------- 2.7 leads (prospects not yet qualified) ------------------
CREATE TABLE leads (
    lead_id              INT              NOT NULL AUTO_INCREMENT COMMENT 'Lead identifier',
    first_name           VARCHAR(50)      NOT NULL                COMMENT 'First name',
    last_name            VARCHAR(50)      NOT NULL                COMMENT 'Last name',
    company_name         VARCHAR(150)     NOT NULL                COMMENT 'Company the lead belongs to',
    job_title            VARCHAR(100)     NULL                    COMMENT 'Job title',
    email                VARCHAR(120)     NOT NULL                COMMENT 'Email address',
    phone                VARCHAR(20)      NULL                    COMMENT 'Phone number',
    city                 VARCHAR(60)      NULL                    COMMENT 'City',
    source_id            INT              NOT NULL                COMMENT 'Lead channel (FK lead_sources)',
    status               VARCHAR(20)      NOT NULL DEFAULT 'New'  COMMENT 'New, Contacted, Qualified, Unqualified or Converted',
    lead_score           TINYINT UNSIGNED NOT NULL DEFAULT 0      COMMENT 'Sales readiness score 0-100',
    owner_user_id        INT              NOT NULL                COMMENT 'Sales owner (FK users)',
    converted_account_id INT              NULL                    COMMENT 'Account created on conversion (FK accounts)',
    converted_at         DATETIME         NULL                    COMMENT 'When the lead was converted',
    created_at           DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (lead_id),
    UNIQUE KEY uq_leads_email (email),
    CONSTRAINT fk_leads_source            FOREIGN KEY (source_id)            REFERENCES lead_sources (source_id),
    CONSTRAINT fk_leads_owner             FOREIGN KEY (owner_user_id)        REFERENCES users (user_id),
    CONSTRAINT fk_leads_converted_account FOREIGN KEY (converted_account_id) REFERENCES accounts (account_id),
    CONSTRAINT chk_leads_status    CHECK (status IN ('New', 'Contacted', 'Qualified', 'Unqualified', 'Converted')),
    CONSTRAINT chk_leads_score     CHECK (lead_score BETWEEN 0 AND 100),
    CONSTRAINT chk_leads_converted CHECK (status <> 'Converted'
                                          OR (converted_account_id IS NOT NULL AND converted_at IS NOT NULL))
) ENGINE = InnoDB COMMENT = 'Potential customers captured by marketing and sales';

-- ---------- 2.8 pipeline_stages --------------------------------------
CREATE TABLE pipeline_stages (
    stage_id        INT              NOT NULL AUTO_INCREMENT COMMENT 'Stage identifier',
    stage_name      VARCHAR(50)      NOT NULL                COMMENT 'Stage name',
    stage_order     TINYINT UNSIGNED NOT NULL                COMMENT 'Position of the stage in the pipeline',
    win_probability TINYINT UNSIGNED NOT NULL                COMMENT 'Chance of winning at this stage (%)',
    is_closed       BOOLEAN          NOT NULL DEFAULT FALSE  COMMENT 'TRUE for Closed Won and Closed Lost',
    is_won          BOOLEAN          NOT NULL DEFAULT FALSE  COMMENT 'TRUE only for Closed Won',
    PRIMARY KEY (stage_id),
    UNIQUE KEY uq_stages_name  (stage_name),
    UNIQUE KEY uq_stages_order (stage_order),
    CONSTRAINT chk_stages_probability CHECK (win_probability BETWEEN 0 AND 100),
    CONSTRAINT chk_stages_won_closed  CHECK (is_won = FALSE OR is_closed = TRUE)
) ENGINE = InnoDB COMMENT = 'Sales pipeline stages with win probability';

-- ---------- 2.9 opportunities (deals) --------------------------------
CREATE TABLE opportunities (
    opportunity_id      INT           NOT NULL AUTO_INCREMENT COMMENT 'Opportunity identifier',
    opportunity_name    VARCHAR(150)  NOT NULL                COMMENT 'Short deal name',
    account_id          INT           NOT NULL                COMMENT 'Customer company (FK accounts)',
    primary_contact_id  INT           NULL                    COMMENT 'Main decision maker (FK contacts)',
    lead_id             INT           NULL                    COMMENT 'Lead the deal came from (FK leads)',
    owner_user_id       INT           NOT NULL                COMMENT 'Sales owner (FK users)',
    stage_id            INT           NOT NULL                COMMENT 'Current pipeline stage (FK pipeline_stages)',
    amount              DECIMAL(14,2) NOT NULL DEFAULT 0      COMMENT 'Deal value (PKR), sum of line items',
    expected_close_date DATE          NOT NULL                COMMENT 'Forecast close date',
    actual_close_date   DATE          NULL                    COMMENT 'Date the deal was won or lost',
    loss_reason         VARCHAR(255)  NULL                    COMMENT 'Why the deal was lost',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    PRIMARY KEY (opportunity_id),
    CONSTRAINT fk_opportunities_account FOREIGN KEY (account_id)         REFERENCES accounts (account_id),
    CONSTRAINT fk_opportunities_contact FOREIGN KEY (primary_contact_id) REFERENCES contacts (contact_id),
    CONSTRAINT fk_opportunities_lead    FOREIGN KEY (lead_id)            REFERENCES leads (lead_id),
    CONSTRAINT fk_opportunities_owner   FOREIGN KEY (owner_user_id)      REFERENCES users (user_id),
    CONSTRAINT fk_opportunities_stage   FOREIGN KEY (stage_id)           REFERENCES pipeline_stages (stage_id),
    CONSTRAINT chk_opportunities_amount CHECK (amount >= 0)
) ENGINE = InnoDB COMMENT = 'Sales deals moving through the pipeline';

-- ---------- 2.10 products --------------------------------------------
CREATE TABLE products (
    product_id   INT           NOT NULL AUTO_INCREMENT COMMENT 'Product identifier',
    product_code VARCHAR(20)   NOT NULL                COMMENT 'Unique catalogue code',
    product_name VARCHAR(120)  NOT NULL                COMMENT 'Product or service name',
    category     VARCHAR(20)   NOT NULL                COMMENT 'Software, Service, Support or Training',
    unit_price   DECIMAL(12,2) NOT NULL                COMMENT 'List price (PKR)',
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE   COMMENT 'FALSE when no longer sold',
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_code (product_code),
    CONSTRAINT chk_products_category CHECK (category IN ('Software', 'Service', 'Support', 'Training')),
    CONSTRAINT chk_products_price    CHECK (unit_price > 0)
) ENGINE = InnoDB COMMENT = 'Products and services offered to customers';

-- ---------- 2.11 opportunity_products (deal line items, M:N) ---------
CREATE TABLE opportunity_products (
    opportunity_id INT           NOT NULL COMMENT 'Deal (FK opportunities)',
    product_id     INT           NOT NULL COMMENT 'Product on the deal (FK products)',
    quantity       INT           NOT NULL DEFAULT 1 COMMENT 'Units or days',
    unit_price     DECIMAL(12,2) NOT NULL COMMENT 'Agreed unit price (PKR)',
    discount_pct   DECIMAL(5,2)  NOT NULL DEFAULT 0 COMMENT 'Discount percentage',
    line_total     DECIMAL(14,2) GENERATED ALWAYS AS
                   (ROUND(quantity * unit_price * (1 - discount_pct / 100), 2)) STORED
                   COMMENT 'Calculated line value after discount',
    PRIMARY KEY (opportunity_id, product_id),
    CONSTRAINT fk_oppprod_opportunity FOREIGN KEY (opportunity_id) REFERENCES opportunities (opportunity_id) ON DELETE CASCADE,
    CONSTRAINT fk_oppprod_product     FOREIGN KEY (product_id)     REFERENCES products (product_id),
    CONSTRAINT chk_oppprod_quantity CHECK (quantity > 0),
    CONSTRAINT chk_oppprod_price    CHECK (unit_price >= 0),
    CONSTRAINT chk_oppprod_discount CHECK (discount_pct BETWEEN 0 AND 100)
) ENGINE = InnoDB COMMENT = 'Products included in each opportunity (bridge table)';

-- ---------- 2.12 activities (calls, meetings, emails, tasks) ---------
CREATE TABLE activities (
    activity_id      INT          NOT NULL AUTO_INCREMENT COMMENT 'Activity identifier',
    activity_type    VARCHAR(20)  NOT NULL                COMMENT 'Call, Email, Meeting, Demo or Task',
    subject          VARCHAR(150) NOT NULL                COMMENT 'Short description',
    activity_date    DATETIME     NOT NULL                COMMENT 'When it happened or is planned',
    duration_minutes SMALLINT     NOT NULL DEFAULT 0      COMMENT 'Length in minutes',
    status           VARCHAR(20)  NOT NULL DEFAULT 'Planned' COMMENT 'Planned, Completed or Cancelled',
    owner_user_id    INT          NOT NULL                COMMENT 'Staff member responsible (FK users)',
    contact_id       INT          NULL                    COMMENT 'Related contact (FK contacts)',
    lead_id          INT          NULL                    COMMENT 'Related lead (FK leads)',
    opportunity_id   INT          NULL                    COMMENT 'Related deal (FK opportunities)',
    notes            VARCHAR(500) NULL                    COMMENT 'Outcome or notes',
    PRIMARY KEY (activity_id),
    CONSTRAINT fk_activities_owner       FOREIGN KEY (owner_user_id)  REFERENCES users (user_id),
    CONSTRAINT fk_activities_contact     FOREIGN KEY (contact_id)     REFERENCES contacts (contact_id),
    CONSTRAINT fk_activities_lead        FOREIGN KEY (lead_id)        REFERENCES leads (lead_id),
    CONSTRAINT fk_activities_opportunity FOREIGN KEY (opportunity_id) REFERENCES opportunities (opportunity_id),
    CONSTRAINT chk_activities_type     CHECK (activity_type IN ('Call', 'Email', 'Meeting', 'Demo', 'Task')),
    CONSTRAINT chk_activities_status   CHECK (status IN ('Planned', 'Completed', 'Cancelled')),
    CONSTRAINT chk_activities_duration CHECK (duration_minutes >= 0),
    CONSTRAINT chk_activities_link     CHECK (contact_id IS NOT NULL OR lead_id IS NOT NULL
                                              OR opportunity_id IS NOT NULL)
) ENGINE = InnoDB COMMENT = 'Every interaction with a lead, contact or deal';

-- ---------- 2.13 campaigns -------------------------------------------
CREATE TABLE campaigns (
    campaign_id   INT           NOT NULL AUTO_INCREMENT COMMENT 'Campaign identifier',
    campaign_name VARCHAR(120)  NOT NULL                COMMENT 'Campaign name',
    channel       VARCHAR(20)   NOT NULL                COMMENT 'Email, Social Media, Event, Webinar or Paid Ads',
    start_date    DATE          NOT NULL                COMMENT 'First day of the campaign',
    end_date      DATE          NOT NULL                COMMENT 'Last day of the campaign',
    budget        DECIMAL(12,2) NOT NULL DEFAULT 0      COMMENT 'Approved budget (PKR)',
    owner_user_id INT           NOT NULL                COMMENT 'Marketing owner (FK users)',
    PRIMARY KEY (campaign_id),
    UNIQUE KEY uq_campaigns_name (campaign_name),
    CONSTRAINT fk_campaigns_owner FOREIGN KEY (owner_user_id) REFERENCES users (user_id),
    CONSTRAINT chk_campaigns_channel CHECK (channel IN ('Email', 'Social Media', 'Event', 'Webinar', 'Paid Ads')),
    CONSTRAINT chk_campaigns_budget  CHECK (budget >= 0),
    CONSTRAINT chk_campaigns_dates   CHECK (end_date >= start_date)
) ENGINE = InnoDB COMMENT = 'Marketing campaigns that generate leads';

-- ---------- 2.14 campaign_leads (M:N) --------------------------------
CREATE TABLE campaign_leads (
    campaign_id INT         NOT NULL COMMENT 'Campaign (FK campaigns)',
    lead_id     INT         NOT NULL COMMENT 'Targeted lead (FK leads)',
    added_on    DATE        NOT NULL COMMENT 'Date the lead joined the campaign',
    response    VARCHAR(20) NOT NULL DEFAULT 'Sent' COMMENT 'Sent, Opened, Clicked or Responded',
    PRIMARY KEY (campaign_id, lead_id),
    CONSTRAINT fk_campaignleads_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns (campaign_id) ON DELETE CASCADE,
    CONSTRAINT fk_campaignleads_lead     FOREIGN KEY (lead_id)     REFERENCES leads (lead_id) ON DELETE CASCADE,
    CONSTRAINT chk_campaignleads_response CHECK (response IN ('Sent', 'Opened', 'Clicked', 'Responded'))
) ENGINE = InnoDB COMMENT = 'Leads targeted by each campaign (bridge table)';

-- ---------- 2.15 tickets (customer support cases) --------------------
CREATE TABLE tickets (
    ticket_id          INT          NOT NULL AUTO_INCREMENT COMMENT 'Ticket identifier',
    account_id         INT          NOT NULL                COMMENT 'Customer company (FK accounts)',
    contact_id         INT          NULL                    COMMENT 'Person who raised it (FK contacts)',
    assigned_user_id   INT          NULL                    COMMENT 'Support agent (FK users)',
    subject            VARCHAR(150) NOT NULL                COMMENT 'Problem summary',
    priority           VARCHAR(10)  NOT NULL DEFAULT 'Medium' COMMENT 'Low, Medium, High or Critical',
    status             VARCHAR(20)  NOT NULL DEFAULT 'Open'   COMMENT 'Open, In Progress, Resolved or Closed',
    opened_at          DATETIME     NOT NULL                COMMENT 'When the ticket was raised',
    resolved_at        DATETIME     NULL                    COMMENT 'When the ticket was resolved',
    satisfaction_score TINYINT      NULL                    COMMENT 'Customer rating 1-5 after resolution',
    PRIMARY KEY (ticket_id),
    CONSTRAINT fk_tickets_account  FOREIGN KEY (account_id)       REFERENCES accounts (account_id),
    CONSTRAINT fk_tickets_contact  FOREIGN KEY (contact_id)       REFERENCES contacts (contact_id),
    CONSTRAINT fk_tickets_assignee FOREIGN KEY (assigned_user_id) REFERENCES users (user_id),
    CONSTRAINT chk_tickets_priority     CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),
    CONSTRAINT chk_tickets_status       CHECK (status IN ('Open', 'In Progress', 'Resolved', 'Closed')),
    CONSTRAINT chk_tickets_resolved     CHECK (resolved_at IS NULL OR resolved_at >= opened_at),
    CONSTRAINT chk_tickets_resolved_set CHECK (status NOT IN ('Resolved', 'Closed') OR resolved_at IS NOT NULL),
    CONSTRAINT chk_tickets_satisfaction CHECK (satisfaction_score IS NULL OR satisfaction_score BETWEEN 1 AND 5)
) ENGINE = InnoDB COMMENT = 'Customer support requests';

-- ---------- 2.16 invoices (one per won opportunity, 1:1) -------------
CREATE TABLE invoices (
    invoice_id     INT           NOT NULL AUTO_INCREMENT COMMENT 'Invoice identifier',
    invoice_number VARCHAR(20)   NOT NULL                COMMENT 'Printed invoice number',
    opportunity_id INT           NOT NULL                COMMENT 'Won deal being billed (FK opportunities, unique)',
    invoice_date   DATE          NOT NULL                COMMENT 'Issue date',
    due_date       DATE          NOT NULL                COMMENT 'Payment due date',
    total_amount   DECIMAL(14,2) NOT NULL                COMMENT 'Invoice total (PKR)',
    status         VARCHAR(20)   NOT NULL DEFAULT 'Unpaid' COMMENT 'Unpaid, Partially Paid, Paid, Overdue or Cancelled',
    PRIMARY KEY (invoice_id),
    UNIQUE KEY uq_invoices_number      (invoice_number),
    UNIQUE KEY uq_invoices_opportunity (opportunity_id),
    CONSTRAINT fk_invoices_opportunity FOREIGN KEY (opportunity_id) REFERENCES opportunities (opportunity_id),
    CONSTRAINT chk_invoices_amount CHECK (total_amount >= 0),
    CONSTRAINT chk_invoices_dates  CHECK (due_date >= invoice_date),
    CONSTRAINT chk_invoices_status CHECK (status IN ('Unpaid', 'Partially Paid', 'Paid', 'Overdue', 'Cancelled'))
) ENGINE = InnoDB COMMENT = 'Bills raised for won deals';

-- ---------- 2.17 payments --------------------------------------------
CREATE TABLE payments (
    payment_id     INT           NOT NULL AUTO_INCREMENT COMMENT 'Payment identifier',
    invoice_id     INT           NOT NULL                COMMENT 'Invoice being paid (FK invoices)',
    payment_date   DATE          NOT NULL                COMMENT 'Date the money was received',
    amount         DECIMAL(14,2) NOT NULL                COMMENT 'Amount received (PKR)',
    payment_method VARCHAR(20)   NOT NULL                COMMENT 'Bank Transfer, Card, Cash or Cheque',
    reference_no   VARCHAR(50)   NULL                    COMMENT 'Bank or cheque reference',
    PRIMARY KEY (payment_id),
    UNIQUE KEY uq_payments_reference (reference_no),
    CONSTRAINT fk_payments_invoice FOREIGN KEY (invoice_id) REFERENCES invoices (invoice_id),
    CONSTRAINT chk_payments_amount CHECK (amount > 0),
    CONSTRAINT chk_payments_method CHECK (payment_method IN ('Bank Transfer', 'Card', 'Cash', 'Cheque'))
) ENGINE = InnoDB COMMENT = 'Money received against invoices';

-- ---------- 2.18 opportunity_stage_history (audit) -------------------
CREATE TABLE opportunity_stage_history (
    history_id     INT      NOT NULL AUTO_INCREMENT COMMENT 'History row identifier',
    opportunity_id INT      NOT NULL                COMMENT 'Deal that moved (FK opportunities)',
    from_stage_id  INT      NULL                    COMMENT 'Previous stage, NULL when created (FK pipeline_stages)',
    to_stage_id    INT      NOT NULL                COMMENT 'New stage (FK pipeline_stages)',
    changed_by     INT      NULL                    COMMENT 'User who moved the deal (FK users)',
    changed_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Time of the change',
    PRIMARY KEY (history_id),
    CONSTRAINT fk_history_opportunity FOREIGN KEY (opportunity_id) REFERENCES opportunities (opportunity_id) ON DELETE CASCADE,
    CONSTRAINT fk_history_from_stage  FOREIGN KEY (from_stage_id)  REFERENCES pipeline_stages (stage_id),
    CONSTRAINT fk_history_to_stage    FOREIGN KEY (to_stage_id)    REFERENCES pipeline_stages (stage_id),
    CONSTRAINT fk_history_user        FOREIGN KEY (changed_by)     REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE = InnoDB COMMENT = 'Audit trail of pipeline stage changes';


-- =====================================================================
-- 3. SECONDARY INDEXES (foreign keys are indexed automatically)
-- =====================================================================
CREATE INDEX idx_accounts_type_city      ON accounts (account_type, city);
CREATE INDEX idx_leads_status_score      ON leads (status, lead_score);
CREATE INDEX idx_opportunities_close     ON opportunities (expected_close_date);
CREATE INDEX idx_activities_date_status  ON activities (activity_date, status);
CREATE INDEX idx_tickets_status_priority ON tickets (status, priority);
CREATE INDEX idx_invoices_status_due     ON invoices (status, due_date);
CREATE INDEX idx_history_changed_at      ON opportunity_stage_history (changed_at);


-- =====================================================================
-- 4. SAMPLE DATA (all companies, people and numbers are fictional)
-- =====================================================================

INSERT INTO roles (role_id, role_name, description) VALUES
(1, 'Administrator',        'Full access to CRM data, users and settings'),
(2, 'Sales Manager',        'Manages the sales team, pipeline and targets'),
(3, 'Sales Representative', 'Works leads, accounts and opportunities'),
(4, 'Marketing',            'Plans campaigns and generates leads'),
(5, 'Support Agent',        'Handles customer support tickets');

INSERT INTO users (user_id, full_name, email, phone, role_id, manager_id, hire_date, is_active, created_at) VALUES
(1,  'Ayesha Malik',   'ayesha.malik@pulsecrm.example',   '0300-5550101', 1, NULL, '2024-01-15', TRUE,  '2026-01-02 09:00:00'),
(2,  'Bilal Hassan',   'bilal.hassan@pulsecrm.example',   '0300-5550102', 2, 1,    '2024-03-01', TRUE,  '2026-01-02 09:05:00'),
(6,  'Faisal Qureshi', 'faisal.qureshi@pulsecrm.example', '0300-5550106', 4, 1,    '2024-08-12', TRUE,  '2026-01-02 09:10:00'),
(8,  'Kamran Ali',     'kamran.ali@pulsecrm.example',     '0300-5550108', 5, 1,    '2024-02-05', TRUE,  '2026-01-02 09:15:00'),
(3,  'Sana Javed',     'sana.javed@pulsecrm.example',     '0300-5550103', 3, 2,    '2024-06-10', TRUE,  '2026-01-02 09:20:00'),
(4,  'Usman Tariq',    'usman.tariq@pulsecrm.example',    '0300-5550104', 3, 2,    '2025-01-20', TRUE,  '2026-01-02 09:25:00'),
(5,  'Hira Nadeem',    'hira.nadeem@pulsecrm.example',    '0300-5550105', 3, 2,    '2025-04-07', TRUE,  '2026-01-02 09:30:00'),
(7,  'Zainab Raza',    'zainab.raza@pulsecrm.example',    '0300-5550107', 4, 6,    '2025-07-01', TRUE,  '2026-01-02 09:35:00'),
(9,  'Mehak Shah',     'mehak.shah@pulsecrm.example',     '0300-5550109', 5, 8,    '2025-02-14', TRUE,  '2026-01-02 09:40:00'),
(10, 'Danish Iqbal',   'danish.iqbal@pulsecrm.example',   '0300-5550110', 5, 8,    '2025-09-01', FALSE, '2026-01-02 09:45:00');

INSERT INTO industries (industry_id, industry_name) VALUES
(1, 'Manufacturing'), (2, 'Healthcare'), (3, 'Logistics'), (4, 'FMCG'), (5, 'Construction'), (6, 'Hospitality'),
(7, 'Education'), (8, 'Agriculture'), (9, 'Energy'), (10, 'Retail'), (11, 'Finance');

INSERT INTO accounts (account_id, account_name, industry_id, account_type, website, phone, city, annual_revenue, employee_count, owner_user_id, created_at) VALUES
(101, 'Indus Weave Textiles',  1,  'Customer', 'www.indusweave.example',     '041-5550201', 'Faisalabad', 850000000.00,  1200, 3, '2026-01-12 10:15:00'),
(102, 'Crescent Health Labs',  2,  'Customer', 'www.crescenthealth.example', '021-5550202', 'Karachi',    420000000.00,  380,  4, '2026-01-20 11:00:00'),
(103, 'Margalla Freight Co',   3,  'Customer', 'www.margallafreight.example','051-5550203', 'Islamabad',  610000000.00,  540,  5, '2026-02-03 09:30:00'),
(104, 'Ravi Fresh Foods',      4,  'Customer', 'www.ravifresh.example',      '042-5550204', 'Lahore',     950000000.00,  900,  3, '2026-02-18 14:20:00'),
(105, 'Bolan Stone Builders',  5,  'Prospect', 'www.bolanstone.example',     '081-5550205', 'Quetta',     300000000.00,  260,  4, '2026-03-05 10:00:00'),
(106, 'Seaview Hotels Group',  6,  'Customer', 'www.seaviewhotels.example',  '021-5550206', 'Karachi',    720000000.00,  650,  5, '2026-03-11 12:45:00'),
(107, 'Kohsar Academy',        7,  'Prospect', 'www.kohsar.example',         '0992-555207', 'Abbottabad', 85000000.00,   140,  3, '2026-04-02 09:10:00'),
(108, 'Chenab Agro Traders',   8,  'Prospect', 'www.chenabagro.example',     '061-5550208', 'Multan',     260000000.00,  210,  4, '2026-04-15 16:00:00'),
(109, 'Thar Solar Energy',     9,  'Customer', 'www.tharsolar.example',      '022-5550209', 'Hyderabad',  1250000000.00, 480,  5, '2026-05-06 10:40:00'),
(110, 'Pak Lane Retail',       10, 'Churned',  'www.paklane.example',        '042-5550210', 'Lahore',     390000000.00,  320,  3, '2026-01-08 15:00:00'),
(111, 'Karakoram Fintech',     11, 'Customer', 'www.karakoram.example',      '051-5550211', 'Islamabad',  540000000.00,  170,  4, '2026-05-21 11:30:00'),
(112, 'Sindh Care Clinics',    2,  'Partner',  'www.sindhcare.example',      '022-5550212', 'Hyderabad',  150000000.00,  120,  2, '2026-06-09 13:15:00');

INSERT INTO contacts (contact_id, account_id, first_name, last_name, job_title, email, phone, is_primary, created_at) VALUES
(201, 101, 'Asif',    'Mahmood',  'Chief Information Officer', 'asif.mahmood@indusweave.example',      '0321-5550201', TRUE,  '2026-01-12 10:20:00'),
(202, 101, 'Rabia',   'Anwar',    'Procurement Manager',       'rabia.anwar@indusweave.example',       '0321-5550202', FALSE, '2026-01-15 09:00:00'),
(203, 102, 'Saima',   'Khalid',   'Operations Director',       'saima.khalid@crescenthealth.example',  '0321-5550203', TRUE,  '2026-01-20 11:05:00'),
(204, 102, 'Adeel',   'Shaikh',   'IT Manager',                'adeel.shaikh@crescenthealth.example',  '0321-5550204', FALSE, '2026-01-22 10:00:00'),
(205, 103, 'Imran',   'Yousaf',   'Chief Executive Officer',   'imran.yousaf@margallafreight.example', '0321-5550205', TRUE,  '2026-02-03 09:35:00'),
(206, 103, 'Nadia',   'Pervez',   'Finance Manager',           'nadia.pervez@margallafreight.example', '0321-5550206', FALSE, '2026-02-05 12:00:00'),
(207, 104, 'Tariq',   'Javed',    'Head of IT',                'tariq.javed@ravifresh.example',        '0321-5550207', TRUE,  '2026-02-18 14:25:00'),
(208, 104, 'Fariha',  'Noor',     'Supply Chain Lead',         'fariha.noor@ravifresh.example',        '0321-5550208', FALSE, '2026-02-20 10:30:00'),
(209, 105, 'Shahid',  'Baloch',   'Managing Director',         'shahid.baloch@bolanstone.example',     '0321-5550209', TRUE,  '2026-03-05 10:05:00'),
(210, 105, 'Amna',    'Kakar',    'Project Coordinator',       'amna.kakar@bolanstone.example',        '0321-5550210', FALSE, '2026-03-06 11:00:00'),
(211, 106, 'Omar',    'Farooq',   'General Manager',           'omar.farooq@seaviewhotels.example',    '0321-5550211', TRUE,  '2026-03-11 12:50:00'),
(212, 106, 'Sadia',   'Rehman',   'Guest Experience Manager',  'sadia.rehman@seaviewhotels.example',   '0321-5550212', FALSE, '2026-03-14 09:40:00'),
(213, 107, 'Naveed',  'Abbasi',   'Principal',                 'naveed.abbasi@kohsar.example',         '0321-5550213', TRUE,  '2026-04-02 09:15:00'),
(214, 107, 'Kiran',   'Hayat',    'Admin Officer',             'kiran.hayat@kohsar.example',           '0321-5550214', FALSE, '2026-04-03 10:00:00'),
(215, 108, 'Ghulam',  'Mustafa',  'Owner',                     'ghulam.mustafa@chenabagro.example',    '0321-5550215', TRUE,  '2026-04-15 16:05:00'),
(216, 108, 'Saba',    'Iqbal',    'Accounts Officer',          'saba.iqbal@chenabagro.example',        '0321-5550216', FALSE, '2026-04-16 11:20:00'),
(217, 109, 'Zeeshan', 'Memon',    'Chief Technology Officer',  'zeeshan.memon@tharsolar.example',      '0321-5550217', TRUE,  '2026-05-06 10:45:00'),
(218, 109, 'Ayesha',  'Soomro',   'Procurement Head',          'ayesha.soomro@tharsolar.example',      '0321-5550218', FALSE, '2026-05-08 09:30:00'),
(219, 110, 'Hamid',   'Raza',     'IT Director',               'hamid.raza@paklane.example',           '0321-5550219', TRUE,  '2026-01-08 15:05:00'),
(220, 110, 'Lubna',   'Aziz',     'Store Operations Manager',  'lubna.aziz@paklane.example',           '0321-5550220', FALSE, '2026-01-09 10:00:00'),
(221, 111, 'Fahad',   'Mirza',    'Head of Engineering',       'fahad.mirza@karakoram.example',        '0321-5550221', TRUE,  '2026-05-21 11:35:00'),
(222, 111, 'Maria',   'Haider',   'Compliance Officer',        'maria.haider@karakoram.example',       '0321-5550222', FALSE, '2026-05-23 14:00:00'),
(223, 112, 'Ali',     'Hassan',   'Partnerships Manager',      'ali.hassan@sindhcare.example',         '0321-5550223', TRUE,  '2026-06-09 13:20:00'),
(224, 112, 'Nimra',   'Sheikh',   'Clinic Administrator',      'nimra.sheikh@sindhcare.example',       '0321-5550224', FALSE, '2026-06-10 10:10:00');

INSERT INTO lead_sources (source_id, source_name) VALUES
(1, 'Website'), (2, 'Referral'), (3, 'LinkedIn'), (4, 'Trade Show'), (5, 'Cold Call'), (6, 'Email Campaign');

INSERT INTO leads (lead_id, first_name, last_name, company_name, job_title, email, phone, city, source_id, status, lead_score, owner_user_id, converted_account_id, converted_at, created_at) VALUES
(301, 'Asif',     'Mahmood',  'Indus Weave Textiles',      'Chief Information Officer', 'asif.mahmood@lead.indusweave.example',   '0321-5550201', 'Faisalabad', 2, 'Converted',   90, 3, 101,  '2026-01-12 10:00:00', '2025-12-20 11:00:00'),
(302, 'Imran',    'Yousaf',   'Margalla Freight Co',       'Chief Executive Officer',   'imran.yousaf@lead.margalla.example',     '0321-5550205', 'Islamabad',  3, 'Converted',   85, 5, 103,  '2026-02-03 09:15:00', '2026-01-15 10:30:00'),
(303, 'Tariq',    'Javed',    'Ravi Fresh Foods',          'Head of IT',                'tariq.javed@lead.ravifresh.example',     '0321-5550207', 'Lahore',     4, 'Converted',   80, 3, 104,  '2026-02-18 14:00:00', '2026-01-28 12:00:00'),
(304, 'Omar',     'Farooq',   'Seaview Hotels Group',      'General Manager',           'omar.farooq@lead.seaview.example',       '0321-5550211', 'Karachi',    1, 'Converted',   88, 5, 106,  '2026-03-11 12:30:00', '2026-02-20 09:45:00'),
(305, 'Zeeshan',  'Memon',    'Thar Solar Energy',         'Chief Technology Officer',  'zeeshan.memon@lead.tharsolar.example',   '0321-5550217', 'Hyderabad',  6, 'Converted',   92, 5, 109,  '2026-05-06 10:30:00', '2026-04-10 15:10:00'),
(306, 'Fahad',    'Mirza',    'Karakoram Fintech',         'Head of Engineering',       'fahad.mirza@lead.karakoram.example',     '0321-5550221', 'Islamabad',  3, 'Converted',   87, 4, 111,  '2026-05-21 11:20:00', '2026-04-28 10:00:00'),
(307, 'Hassan',   'Nawaz',    'Gwadar Port Services',      'Operations Manager',        'hassan.nawaz@gwadarport.example',        '0333-5550307', 'Gwadar',     4, 'Qualified',   72, 4, NULL, NULL, '2026-07-03 11:00:00'),
(308, 'Mahnoor',  'Saleem',   'Lyallpur Garments',         'Owner',                     'mahnoor.saleem@lyallpur.example',        '0333-5550308', 'Faisalabad', 2, 'Qualified',   70, 3, NULL, NULL, '2026-07-14 09:30:00'),
(309, 'Waqas',    'Ahmed',    'Swat Valley Resorts',       'Director',                  'waqas.ahmed@swatresorts.example',        '0333-5550309', 'Swat',       1, 'Qualified',   66, 5, NULL, NULL, '2026-08-02 14:15:00'),
(310, 'Sobia',    'Khan',     'Mehran Auto Parts',         'Plant Manager',             'sobia.khan@mehranauto.example',          '0333-5550310', 'Karachi',    5, 'Qualified',   68, 4, NULL, NULL, '2026-08-19 10:45:00'),
(311, 'Junaid',   'Akhtar',   'Potohar Dairy',             'Chief Executive Officer',   'junaid.akhtar@potohardairy.example',     '0333-5550311', 'Rawalpindi', 6, 'Qualified',   75, 3, NULL, NULL, '2026-09-05 12:00:00'),
(312, 'Rida',     'Fatima',   'Lahore Grammar Network',    'IT Coordinator',            'rida.fatima@lgnschools.example',         '0333-5550312', 'Lahore',     1, 'Contacted',   55, 5, NULL, NULL, '2026-08-25 09:00:00'),
(313, 'Kashif',   'Bashir',   'Sialkot Sports Works',      'Export Manager',            'kashif.bashir@sialkotsports.example',    '0333-5550313', 'Sialkot',    4, 'Contacted',   50, 4, NULL, NULL, '2026-09-02 11:30:00'),
(314, 'Areeba',   'Tahir',    'Hunza Organic Foods',       'Founder',                   'areeba.tahir@hunzaorganic.example',      '0333-5550314', 'Hunza',      3, 'Contacted',   48, 3, NULL, NULL, '2026-09-10 10:15:00'),
(315, 'Salman',   'Qadir',    'Kharian Cement Co',         'Finance Director',          'salman.qadir@khariancement.example',     '0333-5550315', 'Kharian',    5, 'Contacted',   45, 4, NULL, NULL, '2026-09-18 15:00:00'),
(316, 'Mariam',   'Siddiqui', 'Clifton Dental Care',       'Practice Manager',          'mariam.siddiqui@cliftondental.example',  '0333-5550316', 'Karachi',    6, 'Contacted',   52, 5, NULL, NULL, '2026-09-22 13:20:00'),
(317, 'Usama',    'Rauf',     'Bahawalpur Cotton Ginners', 'Owner',                     'usama.rauf@bwpcotton.example',           '0333-5550317', 'Bahawalpur', 5, 'New',         20, 4, NULL, NULL, '2026-10-05 10:00:00'),
(318, 'Hina',     'Jamil',    'Peshawar Tiles House',      'Sales Head',                'hina.jamil@peshawartiles.example',       '0333-5550318', 'Peshawar',   1, 'New',         25, 3, NULL, NULL, '2026-10-08 11:40:00'),
(319, 'Adnan',    'Shah',     'Gilgit Trek Tours',         'Manager',                   'adnan.shah@gilgittrek.example',          '0333-5550319', 'Gilgit',     3, 'New',         30, 5, NULL, NULL, '2026-10-12 09:10:00'),
(320, 'Saima',    'Butt',     'Gujranwala Fans Ltd',       'Procurement Officer',       'saima.butt@gujranwalafans.example',      '0333-5550320', 'Gujranwala', 4, 'New',         35, 4, NULL, NULL, '2026-10-15 14:30:00'),
(321, 'Noman',    'Iqbal',    'Larkana Rice Mills',        'Director',                  'noman.iqbal@larkanarice.example',        '0333-5550321', 'Larkana',    2, 'New',         40, 3, NULL, NULL, '2026-10-20 16:00:00'),
(322, 'Bushra',   'Ali',      'Student Project',           'Student',                   'bushra.ali@mail.example',                '0333-5550322', 'Karachi',    1, 'Unqualified',  5, 5, NULL, NULL, '2026-06-30 10:00:00'),
(323, 'Tahir',    'Mehmood',  'Mardan Sweets',             'Owner',                     'tahir.mehmood@mardansweets.example',     '0333-5550323', 'Mardan',     5, 'Unqualified', 10, 4, NULL, NULL, '2026-07-21 12:00:00'),
(324, 'Komal',    'Riaz',     'Freelance Designer',        'Freelancer',                'komal.riaz@mail.example',                '0333-5550324', 'Lahore',     3, 'Unqualified', 12, 3, NULL, NULL, '2026-08-11 09:30:00');

INSERT INTO pipeline_stages (stage_id, stage_name, stage_order, win_probability, is_closed, is_won) VALUES
(1, 'Prospecting',   1, 10,  FALSE, FALSE),
(2, 'Qualification', 2, 25,  FALSE, FALSE),
(3, 'Proposal',      3, 50,  FALSE, FALSE),
(4, 'Negotiation',   4, 75,  FALSE, FALSE),
(5, 'Closed Won',    5, 100, TRUE,  TRUE),
(6, 'Closed Lost',   6, 0,   TRUE,  FALSE);

INSERT INTO products (product_id, product_code, product_name, category, unit_price, is_active) VALUES
(501, 'PC-ERP-CLD', 'Cloud ERP License (Annual)',        'Software', 1200000.00, TRUE),
(502, 'PC-CRM-IMP', 'CRM Implementation Package',        'Service',  850000.00,  TRUE),
(503, 'PC-BI-DASH', 'Analytics Dashboard Suite',         'Software', 450000.00,  TRUE),
(504, 'PC-SUP-247', 'Managed Support 24/7 (Annual)',     'Support',  600000.00,  TRUE),
(505, 'PC-SEC-AUD', 'Cybersecurity Audit',               'Service',  350000.00,  TRUE),
(506, 'PC-APP-MOB', 'Mobile App Development',            'Service',  1500000.00, TRUE),
(507, 'PC-TRN-WKS', 'Staff Training Workshop (per day)', 'Training', 75000.00,   TRUE),
(508, 'PC-WEB-CMS', 'Website and CMS Development',       'Service',  400000.00,  TRUE);

-- amount starts at 0 and is calculated from the line items below
INSERT INTO opportunities (opportunity_id, opportunity_name, account_id, primary_contact_id, lead_id, owner_user_id, stage_id, expected_close_date, actual_close_date, loss_reason, created_at) VALUES
(401, 'Indus Weave ERP Rollout',              101, 201, 301,  3, 5, '2026-03-31', '2026-03-25', NULL,                             '2026-01-12 10:30:00'),
(402, 'Margalla Fleet Tracking App',          103, 205, 302,  5, 5, '2026-04-30', '2026-04-22', NULL,                             '2026-02-03 10:00:00'),
(403, 'Ravi Foods Analytics Dashboard',       104, 207, 303,  3, 5, '2026-05-15', '2026-05-10', NULL,                             '2026-02-18 15:00:00'),
(404, 'Seaview Hotels Support Contract',      106, 211, 304,  5, 5, '2026-06-30', '2026-06-18', NULL,                             '2026-03-11 13:00:00'),
(405, 'Thar Solar Security Audit',            109, 217, 305,  5, 5, '2026-07-31', '2026-07-20', NULL,                             '2026-05-06 11:00:00'),
(406, 'Karakoram Fintech CRM Implementation', 111, 221, 306,  4, 5, '2026-08-31', '2026-08-26', NULL,                             '2026-05-21 12:00:00'),
(407, 'Crescent Health Mobile Portal',        102, 203, NULL, 4, 6, '2026-05-31', '2026-05-28', 'Chose a cheaper local vendor',   '2026-01-25 10:00:00'),
(408, 'Pak Lane POS Upgrade',                 110, 219, NULL, 3, 6, '2026-04-15', '2026-04-10', 'Budget frozen by the customer',  '2026-01-08 15:30:00'),
(409, 'Bolan Builders Website',               105, 209, NULL, 4, 6, '2026-07-15', '2026-07-12', 'Project postponed to next year', '2026-03-05 11:00:00'),
(410, 'Crescent Health ERP Phase 2',          102, 204, NULL, 4, 4, '2026-11-15', NULL,         NULL,                             '2026-07-01 10:00:00'),
(411, 'Indus Weave Staff Training',           101, 202, NULL, 3, 4, '2026-11-10', NULL,         NULL,                             '2026-08-05 09:30:00'),
(412, 'Thar Solar Mobile App',                109, 218, NULL, 5, 4, '2026-12-05', NULL,         NULL,                             '2026-08-20 14:00:00'),
(413, 'Seaview Hotels Website Revamp',        106, 212, NULL, 5, 3, '2026-12-15', NULL,         NULL,                             '2026-09-01 10:00:00'),
(414, 'Kohsar Academy Cloud ERP',             107, 213, NULL, 3, 3, '2026-12-20', NULL,         NULL,                             '2026-09-10 11:15:00'),
(415, 'Margalla Freight Security Audit',      103, 206, NULL, 5, 3, '2026-11-30', NULL,         NULL,                             '2026-09-15 12:00:00'),
(416, 'Chenab Agro Analytics',                108, 215, NULL, 4, 2, '2027-01-15', NULL,         NULL,                             '2026-09-25 10:30:00'),
(417, 'Karakoram Fintech Support 24/7',       111, 222, NULL, 4, 2, '2026-12-31', NULL,         NULL,                             '2026-10-01 09:00:00'),
(418, 'Sindh Care Clinic App',                112, 223, NULL, 2, 2, '2027-01-31', NULL,         NULL,                             '2026-10-05 15:45:00'),
(419, 'Ravi Foods Training Program',          104, 208, NULL, 3, 1, '2027-02-15', NULL,         NULL,                             '2026-10-12 10:00:00'),
(420, 'Bolan Builders ERP Pilot',             105, 210, NULL, 4, 1, '2027-02-28', NULL,         NULL,                             '2026-10-18 11:00:00');

INSERT INTO opportunity_products (opportunity_id, product_id, quantity, unit_price, discount_pct) VALUES
(401, 501, 1, 1200000.00, 5),  (401, 502, 1, 850000.00, 10), (401, 507, 4, 75000.00, 0),
(402, 506, 1, 1500000.00, 8),  (402, 504, 1, 600000.00, 0),
(403, 503, 2, 450000.00, 5),   (403, 507, 2, 75000.00, 0),
(404, 504, 2, 600000.00, 10),
(405, 505, 1, 350000.00, 0),   (405, 507, 1, 75000.00, 0),
(406, 502, 1, 850000.00, 0),   (406, 503, 1, 450000.00, 10), (406, 507, 3, 75000.00, 0),
(407, 506, 1, 1500000.00, 5),
(408, 501, 1, 1200000.00, 15),
(409, 508, 1, 400000.00, 0),
(410, 501, 2, 1200000.00, 10), (410, 504, 1, 600000.00, 5),
(411, 507, 6, 75000.00, 10),
(412, 506, 1, 1500000.00, 10),
(413, 508, 1, 400000.00, 0),   (413, 504, 1, 600000.00, 5),
(414, 501, 1, 1200000.00, 12), (414, 507, 2, 75000.00, 0),
(415, 505, 1, 350000.00, 0),
(416, 503, 1, 450000.00, 0),
(417, 504, 1, 600000.00, 0),
(418, 506, 1, 1500000.00, 15),
(419, 507, 5, 75000.00, 0),
(420, 501, 1, 1200000.00, 20);

-- deal value = sum of its line items
UPDATE opportunities o
JOIN (SELECT opportunity_id, SUM(line_total) AS total
      FROM opportunity_products
      GROUP BY opportunity_id) t
  ON o.opportunity_id = t.opportunity_id
SET o.amount = t.total;

-- stage history: every deal starts in Prospecting, then moves forward
INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at)
SELECT opportunity_id, NULL, 1, owner_user_id, created_at
FROM opportunities;

INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at)
SELECT opportunity_id, 1, 2, owner_user_id, DATE_ADD(created_at, INTERVAL 7 DAY)
FROM opportunities WHERE stage_id IN (2, 3, 4, 5, 6);

INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at)
SELECT opportunity_id, 2, 3, owner_user_id, DATE_ADD(created_at, INTERVAL 21 DAY)
FROM opportunities WHERE stage_id IN (3, 4, 5, 6);

INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at)
SELECT opportunity_id, 3, 4, owner_user_id, DATE_ADD(created_at, INTERVAL 35 DAY)
FROM opportunities WHERE stage_id IN (4, 5);

INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at)
SELECT opportunity_id, CASE WHEN stage_id = 5 THEN 4 ELSE 3 END, stage_id, owner_user_id,
       TIMESTAMP(actual_close_date, '16:00:00')
FROM opportunities WHERE stage_id IN (5, 6);

INSERT INTO activities (activity_id, activity_type, subject, activity_date, duration_minutes, status, owner_user_id, contact_id, lead_id, opportunity_id, notes) VALUES
(601, 'Call',    'Discovery call',                   '2026-01-05 11:00:00', 30,  'Completed', 3, NULL, 301,  NULL, 'Needs a cloud ERP for 3 mills'),
(602, 'Meeting', 'ERP requirements workshop',        '2026-01-20 10:00:00', 120, 'Completed', 3, 201,  NULL, 401,  'Finance and inventory modules required'),
(603, 'Demo',    'Cloud ERP demo',                   '2026-02-10 14:00:00', 90,  'Completed', 3, 201,  NULL, 401,  'Positive feedback from CIO'),
(604, 'Email',   'Proposal sent',                    '2026-02-25 09:30:00', 10,  'Completed', 3, 202,  NULL, 401,  'Proposal v2 with training days'),
(605, 'Call',    'Fleet tracking discovery',         '2026-01-22 12:00:00', 45,  'Completed', 5, NULL, 302,  NULL, '120 trucks to track'),
(606, 'Meeting', 'App scope meeting',                '2026-02-15 11:00:00', 90,  'Completed', 5, 205,  NULL, 402,  'Android and iOS driver app'),
(607, 'Demo',    'Dashboard prototype demo',         '2026-03-12 15:00:00', 60,  'Completed', 3, 207,  NULL, 403,  'Sales and stock KPIs approved'),
(608, 'Email',   'Support contract terms',           '2026-05-20 10:00:00', 15,  'Completed', 5, 211,  NULL, 404,  'Two-year contract requested'),
(609, 'Meeting', 'Security audit kickoff',           '2026-07-25 10:00:00', 60,  'Completed', 5, 217,  NULL, 405,  'Scope signed off'),
(610, 'Call',    'Implementation planning',          '2026-07-30 16:00:00', 40,  'Completed', 4, 221,  NULL, 406,  'Go-live target 1 September'),
(611, 'Meeting', 'Patient portal requirements',      '2026-03-05 11:30:00', 90,  'Completed', 4, 203,  NULL, 407,  NULL),
(612, 'Call',    'Budget follow-up',                 '2026-04-02 10:00:00', 20,  'Completed', 3, 219,  NULL, 408,  'Budget frozen for this year'),
(613, 'Email',   'Website quotation',                '2026-06-10 09:00:00', 10,  'Completed', 4, 209,  NULL, 409,  NULL),
(614, 'Meeting', 'ERP phase 2 negotiation',          '2026-10-14 11:00:00', 60,  'Completed', 4, 204,  NULL, 410,  'Asked for 10 percent discount'),
(615, 'Call',    'Discount discussion',              '2026-10-28 15:00:00', 30,  'Planned',   4, 204,  NULL, 410,  NULL),
(616, 'Demo',    'Training curriculum walkthrough',  '2026-10-20 10:30:00', 60,  'Completed', 3, 202,  NULL, 411,  'Six training days agreed'),
(617, 'Meeting', 'Mobile app pricing',               '2026-11-03 12:00:00', 60,  'Planned',   5, 218,  NULL, 412,  NULL),
(618, 'Email',   'Website proposal',                 '2026-10-02 09:00:00', 10,  'Completed', 5, 212,  NULL, 413,  NULL),
(619, 'Demo',    'Cloud ERP for schools demo',       '2026-10-22 11:00:00', 75,  'Completed', 3, 213,  NULL, 414,  'Fee collection module liked'),
(620, 'Call',    'Audit scope call',                 '2026-10-30 14:00:00', 30,  'Planned',   5, 206,  NULL, 415,  NULL),
(621, 'Call',    'Needs assessment',                 '2026-10-06 10:00:00', 25,  'Completed', 4, 215,  NULL, 416,  NULL),
(622, 'Email',   'Support plan brochure',            '2026-10-07 09:15:00', 5,   'Completed', 4, 222,  NULL, 417,  NULL),
(623, 'Meeting', 'Partnership app idea',             '2026-11-05 13:00:00', 60,  'Planned',   2, 223,  NULL, 418,  NULL),
(624, 'Call',    'Training needs call',              '2026-10-25 11:00:00', 20,  'Cancelled', 3, 208,  NULL, 419,  'Customer asked to reschedule'),
(625, 'Call',    'Intro call',                       '2026-07-08 10:00:00', 20,  'Completed', 4, NULL, 307,  NULL, 'Interested in port ERP'),
(626, 'Email',   'Product catalogue sent',           '2026-07-16 09:00:00', 5,   'Completed', 3, NULL, 308,  NULL, NULL),
(627, 'Call',    'Follow-up call',                   '2026-09-12 12:00:00', 15,  'Completed', 3, NULL, 314,  NULL, 'Call back in November'),
(628, 'Email',   'Webinar invitation',               '2026-10-09 09:00:00', 5,   'Completed', 7, NULL, 318,  NULL, NULL),
(629, 'Task',    'Prepare ERP pilot estimate',       '2026-10-29 17:00:00', 120, 'Planned',   4, 210,  NULL, 420,  NULL),
(630, 'Call',    'Qualify new lead',                 '2026-10-27 10:30:00', 15,  'Planned',   4, NULL, 320,  NULL, NULL);

INSERT INTO campaigns (campaign_id, campaign_name, channel, start_date, end_date, budget, owner_user_id) VALUES
(701, 'Cloud ERP Webinar 2026',      'Webinar',      '2026-03-01', '2026-03-31', 150000.00, 6),
(702, 'LinkedIn Lead Generation Q2', 'Social Media', '2026-04-01', '2026-06-30', 300000.00, 7),
(703, 'Karachi Tech Expo 2026',      'Event',        '2026-07-10', '2026-07-12', 500000.00, 6),
(704, 'Autumn Email Nurture',        'Email',        '2026-09-01', '2026-11-30', 80000.00,  7);

INSERT INTO campaign_leads (campaign_id, lead_id, added_on, response) VALUES
(701, 303, '2026-03-02', 'Opened'),
(701, 304, '2026-03-02', 'Responded'),
(702, 305, '2026-04-12', 'Responded'),
(702, 306, '2026-04-30', 'Responded'),
(703, 307, '2026-07-11', 'Responded'),
(703, 308, '2026-07-14', 'Clicked'),
(703, 323, '2026-07-21', 'Opened'),
(704, 309, '2026-09-01', 'Opened'),
(704, 310, '2026-09-01', 'Clicked'),
(704, 311, '2026-09-05', 'Responded'),
(704, 312, '2026-09-01', 'Opened'),
(704, 313, '2026-09-02', 'Sent'),
(704, 314, '2026-09-10', 'Responded'),
(704, 315, '2026-09-18', 'Sent'),
(704, 316, '2026-09-22', 'Clicked'),
(704, 317, '2026-10-05', 'Sent'),
(704, 318, '2026-10-08', 'Opened'),
(704, 319, '2026-10-12', 'Sent'),
(704, 320, '2026-10-15', 'Sent'),
(704, 321, '2026-10-20', 'Sent');

INSERT INTO tickets (ticket_id, account_id, contact_id, assigned_user_id, subject, priority, status, opened_at, resolved_at, satisfaction_score) VALUES
(801, 101, 201, 9,    'ERP login issue after password reset',   'High',     'Closed',      '2026-04-05 09:10:00', '2026-04-05 13:40:00', 5),
(802, 101, 202, 10,   'Report export to Excel failing',         'Medium',   'Resolved',    '2026-05-12 11:00:00', '2026-05-14 16:30:00', 4),
(803, 103, 205, 9,    'Driver app GPS not updating',            'Critical', 'Closed',      '2026-05-20 08:00:00', '2026-05-20 12:15:00', 4),
(804, 104, 207, 8,    'Dashboard data refresh delay',           'Medium',   'Resolved',    '2026-06-02 10:30:00', '2026-06-04 09:00:00', 3),
(805, 106, 211, 9,    'Support portal access request',          'Low',      'Closed',      '2026-07-01 14:00:00', '2026-07-02 10:00:00', 5),
(806, 109, 217, 10,   'Audit report clarification',            'Low',      'Resolved',    '2026-08-05 09:45:00', '2026-08-06 15:20:00', 4),
(807, 111, 221, 9,    'CRM data import errors',                 'High',     'In Progress', '2026-10-15 10:00:00', NULL, NULL),
(808, 101, 201, 8,    'New users need ERP access',              'Medium',   'Open',        '2026-10-21 09:30:00', NULL, NULL),
(809, 103, 206, 9,    'Invoice PDF formatting',                 'Low',      'Open',        '2026-10-22 11:20:00', NULL, NULL),
(810, 104, 208, 9,    'Training session reschedule',            'Low',      'In Progress', '2026-10-23 15:10:00', NULL, NULL),
(811, 106, 212, 8,    'Payment gateway timeout on booking app', 'Critical', 'Open',        '2026-10-24 18:45:00', NULL, NULL),
(812, 110, 220, NULL, 'Account closure data export',            'Medium',   'Open',        '2026-10-25 12:00:00', NULL, NULL);

-- one invoice per won deal; the total comes from the deal amount
INSERT INTO invoices (invoice_id, invoice_number, opportunity_id, invoice_date, due_date, total_amount, status)
SELECT 500 + opportunity_id,
       CONCAT('INV-2026-', LPAD(opportunity_id, 4, '0')),
       opportunity_id,
       DATE_ADD(actual_close_date, INTERVAL 1 DAY),
       DATE_ADD(actual_close_date, INTERVAL 31 DAY),
       amount,
       'Unpaid'
FROM opportunities
WHERE stage_id = 5;

INSERT INTO payments (payment_id, invoice_id, payment_date, amount, payment_method, reference_no)
SELECT 951, 901, '2026-04-20', total_amount, 'Bank Transfer', 'BT-26-0401' FROM invoices WHERE invoice_id = 901
UNION ALL
SELECT 952, 902, '2026-05-05', ROUND(total_amount / 2, 2), 'Bank Transfer', 'BT-26-0402A' FROM invoices WHERE invoice_id = 902
UNION ALL
SELECT 953, 902, '2026-05-20', total_amount - ROUND(total_amount / 2, 2), 'Cheque', 'CHQ-26-0402B' FROM invoices WHERE invoice_id = 902
UNION ALL
SELECT 954, 903, '2026-06-08', ROUND(total_amount * 0.40, 2), 'Card', 'CARD-26-0403' FROM invoices WHERE invoice_id = 903
UNION ALL
SELECT 955, 904, '2026-07-15', total_amount, 'Bank Transfer', 'BT-26-0404' FROM invoices WHERE invoice_id = 904
UNION ALL
SELECT 956, 906, '2026-09-20', ROUND(total_amount * 0.70, 2), 'Bank Transfer', 'BT-26-0406' FROM invoices WHERE invoice_id = 906;

-- invoice status follows the payments (data as of 26 October 2026)
UPDATE invoices i
LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid
           FROM payments
           GROUP BY invoice_id) p
  ON i.invoice_id = p.invoice_id
SET i.status = CASE
                   WHEN COALESCE(p.paid, 0) >= i.total_amount THEN 'Paid'
                   WHEN COALESCE(p.paid, 0) > 0 THEN 'Partially Paid'
                   WHEN i.due_date < '2026-10-26' THEN 'Overdue'
                   ELSE 'Unpaid'
               END;


-- =====================================================================
-- 5. VIEWS
-- =====================================================================

-- 5.1 every deal with its account, owner, stage and weighted value
CREATE OR REPLACE VIEW vw_sales_pipeline AS
SELECT o.opportunity_id,
       o.opportunity_name,
       a.account_name,
       o.owner_user_id,
       u.full_name                                    AS owner_name,
       s.stage_name,
       s.stage_order,
       s.win_probability,
       o.amount,
       ROUND(o.amount * s.win_probability / 100, 2)   AS weighted_amount,
       o.expected_close_date,
       o.actual_close_date,
       s.is_closed,
       s.is_won
FROM opportunities o
JOIN accounts a        ON o.account_id = a.account_id
JOIN users u           ON o.owner_user_id = u.user_id
JOIN pipeline_stages s ON o.stage_id = s.stage_id;

-- 5.2 one row per account: contacts, pipeline, revenue and open tickets
--     (each child table is aggregated first so the totals are not multiplied)
CREATE OR REPLACE VIEW vw_account_360 AS
SELECT a.account_id,
       a.account_name,
       i.industry_name,
       a.account_type,
       a.city,
       u.full_name                       AS account_owner,
       COALESCE(c.contacts, 0)           AS contacts,
       COALESCE(op.open_opportunities, 0) AS open_opportunities,
       COALESCE(op.open_pipeline, 0)     AS open_pipeline_value,
       COALESCE(op.won_revenue, 0)       AS won_revenue,
       COALESCE(t.open_tickets, 0)       AS open_tickets
FROM accounts a
LEFT JOIN industries i ON a.industry_id = i.industry_id
JOIN users u           ON a.owner_user_id = u.user_id
LEFT JOIN (SELECT account_id, COUNT(*) AS contacts
           FROM contacts
           GROUP BY account_id) c
       ON c.account_id = a.account_id
LEFT JOIN (SELECT o.account_id,
                  SUM(CASE WHEN s.is_closed = FALSE THEN 1 ELSE 0 END)        AS open_opportunities,
                  SUM(CASE WHEN s.is_closed = FALSE THEN o.amount ELSE 0 END) AS open_pipeline,
                  SUM(CASE WHEN s.is_won = TRUE THEN o.amount ELSE 0 END)     AS won_revenue
           FROM opportunities o
           JOIN pipeline_stages s ON o.stage_id = s.stage_id
           GROUP BY o.account_id) op
       ON op.account_id = a.account_id
LEFT JOIN (SELECT account_id, COUNT(*) AS open_tickets
           FROM tickets
           WHERE status IN ('Open', 'In Progress')
           GROUP BY account_id) t
       ON t.account_id = a.account_id;

-- 5.3 sales team scorecard
CREATE OR REPLACE VIEW vw_sales_rep_performance AS
SELECT u.user_id,
       u.full_name                         AS sales_rep,
       r.role_name,
       COALESCE(l.leads_owned, 0)          AS leads_owned,
       COALESCE(l.leads_converted, 0)      AS leads_converted,
       COALESCE(o.opportunities, 0)        AS opportunities,
       COALESCE(o.won_deals, 0)            AS won_deals,
       COALESCE(o.lost_deals, 0)           AS lost_deals,
       COALESCE(o.won_revenue, 0)          AS won_revenue,
       COALESCE(o.open_pipeline, 0)        AS open_pipeline,
       CASE WHEN COALESCE(o.won_deals, 0) + COALESCE(o.lost_deals, 0) = 0 THEN NULL
            ELSE ROUND(o.won_deals * 100 / (o.won_deals + o.lost_deals), 1)
       END                                 AS win_rate_pct
FROM users u
JOIN roles r ON u.role_id = r.role_id
LEFT JOIN (SELECT owner_user_id,
                  COUNT(*) AS leads_owned,
                  SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) AS leads_converted
           FROM leads
           GROUP BY owner_user_id) l
       ON l.owner_user_id = u.user_id
LEFT JOIN (SELECT o.owner_user_id,
                  COUNT(*) AS opportunities,
                  SUM(CASE WHEN s.is_won = TRUE THEN 1 ELSE 0 END)                         AS won_deals,
                  SUM(CASE WHEN s.is_closed = TRUE AND s.is_won = FALSE THEN 1 ELSE 0 END) AS lost_deals,
                  SUM(CASE WHEN s.is_won = TRUE THEN o.amount ELSE 0 END)                  AS won_revenue,
                  SUM(CASE WHEN s.is_closed = FALSE THEN o.amount ELSE 0 END)              AS open_pipeline
           FROM opportunities o
           JOIN pipeline_stages s ON o.stage_id = s.stage_id
           GROUP BY o.owner_user_id) o
       ON o.owner_user_id = u.user_id
WHERE r.role_name IN ('Sales Manager', 'Sales Representative');

-- 5.4 which lead channels convert best
CREATE OR REPLACE VIEW vw_lead_conversion_by_source AS
SELECT ls.source_name,
       COUNT(l.lead_id)                                              AS total_leads,
       SUM(CASE WHEN l.status = 'Converted' THEN 1 ELSE 0 END)       AS converted_leads,
       ROUND(SUM(CASE WHEN l.status = 'Converted' THEN 1 ELSE 0 END) * 100
             / NULLIF(COUNT(l.lead_id), 0), 1)                       AS conversion_rate_pct,
       ROUND(AVG(l.lead_score), 1)                                   AS avg_lead_score
FROM lead_sources ls
LEFT JOIN leads l ON l.source_id = ls.source_id
GROUP BY ls.source_id, ls.source_name;

-- 5.5 support tickets with resolution time
CREATE OR REPLACE VIEW vw_ticket_resolution AS
SELECT t.ticket_id,
       a.account_name,
       t.subject,
       t.priority,
       t.status,
       COALESCE(u.full_name, 'Unassigned') AS assigned_to,
       t.opened_at,
       t.resolved_at,
       CASE WHEN t.resolved_at IS NULL THEN NULL
            ELSE ROUND(TIMESTAMPDIFF(MINUTE, t.opened_at, t.resolved_at) / 60, 1)
       END                                 AS resolution_hours,
       t.satisfaction_score
FROM tickets t
JOIN accounts a    ON t.account_id = a.account_id
LEFT JOIN users u  ON t.assigned_user_id = u.user_id;

-- 5.6 invoice balances
CREATE OR REPLACE VIEW vw_invoice_balance AS
SELECT i.invoice_id,
       i.invoice_number,
       a.account_name,
       o.opportunity_name,
       i.invoice_date,
       i.due_date,
       i.total_amount,
       COALESCE(p.amount_paid, 0)                  AS amount_paid,
       i.total_amount - COALESCE(p.amount_paid, 0) AS balance_due,
       i.status
FROM invoices i
JOIN opportunities o ON i.opportunity_id = o.opportunity_id
JOIN accounts a      ON o.account_id = a.account_id
LEFT JOIN (SELECT invoice_id, SUM(amount) AS amount_paid
           FROM payments
           GROUP BY invoice_id) p
       ON p.invoice_id = i.invoice_id;


-- =====================================================================
-- 6. TRIGGER - record every stage change automatically
--    Procedures set @crm_user_id so the trigger knows who made the change.
-- =====================================================================
DELIMITER //
CREATE TRIGGER trg_opportunities_stage_history
AFTER UPDATE ON opportunities
FOR EACH ROW
BEGIN
    IF NEW.stage_id <> OLD.stage_id THEN
        INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by)
        VALUES (NEW.opportunity_id, OLD.stage_id, NEW.stage_id, @crm_user_id);
    END IF;
END //
DELIMITER ;


-- =====================================================================
-- 7. STORED PROCEDURES
-- =====================================================================

-- 7.1 Convert a lead into account + contact + opportunity (one transaction)
DROP PROCEDURE IF EXISTS sp_convert_lead;
DELIMITER //
CREATE PROCEDURE sp_convert_lead(
    IN  p_lead_id          INT,
    IN  p_opportunity_name VARCHAR(150),
    IN  p_amount           DECIMAL(14,2),
    IN  p_expected_close   DATE,
    OUT p_opportunity_id   INT
)
BEGIN
    DECLARE v_status     VARCHAR(20);
    DECLARE v_company    VARCHAR(150);
    DECLARE v_city       VARCHAR(60);
    DECLARE v_owner      INT;
    DECLARE v_account_id INT;
    DECLARE v_contact_id INT;
    DECLARE v_stage_id   INT;

    -- any error: undo everything, then report it
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT status, company_name, city, owner_user_id
      INTO v_status, v_company, v_city, v_owner
    FROM leads
    WHERE lead_id = p_lead_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lead not found';
    END IF;
    IF v_status = 'Converted' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lead is already converted';
    END IF;
    IF v_status = 'Unqualified' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unqualified leads cannot be converted';
    END IF;

    -- reuse the account if the company already exists
    SELECT account_id INTO v_account_id
    FROM accounts
    WHERE account_name = v_company;

    IF v_account_id IS NULL THEN
        INSERT INTO accounts (account_name, account_type, city, owner_user_id)
        VALUES (v_company, 'Prospect', COALESCE(v_city, 'Karachi'), v_owner);
        SET v_account_id = LAST_INSERT_ID();
    END IF;

    INSERT INTO contacts (account_id, first_name, last_name, job_title, email, phone, is_primary)
    SELECT v_account_id, first_name, last_name, job_title, email, phone, TRUE
    FROM leads
    WHERE lead_id = p_lead_id;
    SET v_contact_id = LAST_INSERT_ID();

    SELECT stage_id INTO v_stage_id
    FROM pipeline_stages
    WHERE stage_name = 'Qualification';

    INSERT INTO opportunities (opportunity_name, account_id, primary_contact_id, lead_id,
                               owner_user_id, stage_id, amount, expected_close_date)
    VALUES (p_opportunity_name, v_account_id, v_contact_id, p_lead_id,
            v_owner, v_stage_id, p_amount, p_expected_close);
    SET p_opportunity_id = LAST_INSERT_ID();

    INSERT INTO opportunity_stage_history (opportunity_id, from_stage_id, to_stage_id, changed_by)
    VALUES (p_opportunity_id, NULL, v_stage_id, v_owner);

    UPDATE leads
    SET status = 'Converted',
        converted_account_id = v_account_id,
        converted_at = NOW()
    WHERE lead_id = p_lead_id;

    COMMIT;
END //
DELIMITER ;

-- 7.2 Move a deal to another stage; a won deal gets its invoice in the same transaction
DROP PROCEDURE IF EXISTS sp_update_opportunity_stage;
DELIMITER //
CREATE PROCEDURE sp_update_opportunity_stage(
    IN p_opportunity_id INT,
    IN p_stage_name     VARCHAR(50),
    IN p_user_id        INT,
    IN p_loss_reason    VARCHAR(255)
)
BEGIN
    DECLARE v_stage_id       INT;
    DECLARE v_is_closed      BOOLEAN;
    DECLARE v_is_won         BOOLEAN;
    DECLARE v_current_stage  INT;
    DECLARE v_current_closed BOOLEAN;
    DECLARE v_amount         DECIMAL(14,2);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET @crm_user_id = NULL;
        RESIGNAL;
    END;

    SELECT stage_id, is_closed, is_won
      INTO v_stage_id, v_is_closed, v_is_won
    FROM pipeline_stages
    WHERE stage_name = p_stage_name;

    IF v_stage_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unknown pipeline stage';
    END IF;
    IF v_is_closed = TRUE AND v_is_won = FALSE AND p_loss_reason IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A loss reason is required for Closed Lost';
    END IF;

    START TRANSACTION;

    SELECT o.stage_id, s.is_closed, o.amount
      INTO v_current_stage, v_current_closed, v_amount
    FROM opportunities o
    JOIN pipeline_stages s ON o.stage_id = s.stage_id
    WHERE o.opportunity_id = p_opportunity_id
    FOR UPDATE;

    IF v_current_stage IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Opportunity not found';
    END IF;
    IF v_current_closed = TRUE THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Opportunity is already closed';
    END IF;

    SET @crm_user_id = p_user_id;          -- read by trg_opportunities_stage_history

    UPDATE opportunities
    SET stage_id          = v_stage_id,
        actual_close_date = IF(v_is_closed, CURDATE(), NULL),
        loss_reason       = IF(v_is_closed AND NOT v_is_won, p_loss_reason, NULL)
    WHERE opportunity_id = p_opportunity_id;

    IF v_is_won = TRUE THEN
        INSERT INTO invoices (invoice_number, opportunity_id, invoice_date, due_date, total_amount, status)
        VALUES (CONCAT('INV-', YEAR(CURDATE()), '-', LPAD(p_opportunity_id, 4, '0')),
                p_opportunity_id, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 30 DAY), v_amount, 'Unpaid');
    END IF;

    COMMIT;
    SET @crm_user_id = NULL;
END //
DELIMITER ;

-- 7.3 Record a payment and update the invoice status (one transaction)
DROP PROCEDURE IF EXISTS sp_record_payment;
DELIMITER //
CREATE PROCEDURE sp_record_payment(
    IN p_invoice_id INT,
    IN p_amount     DECIMAL(14,2),
    IN p_method     VARCHAR(20),
    IN p_reference  VARCHAR(50)
)
BEGIN
    DECLARE v_total  DECIMAL(14,2);
    DECLARE v_status VARCHAR(20);
    DECLARE v_paid   DECIMAL(14,2);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT total_amount, status
      INTO v_total, v_status
    FROM invoices
    WHERE invoice_id = p_invoice_id
    FOR UPDATE;

    IF v_total IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invoice not found';
    END IF;
    IF v_status IN ('Paid', 'Cancelled') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invoice is already paid or cancelled';
    END IF;

    SELECT COALESCE(SUM(amount), 0) INTO v_paid
    FROM payments
    WHERE invoice_id = p_invoice_id;

    IF p_amount <= 0 OR v_paid + p_amount > v_total THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment must be positive and cannot exceed the balance due';
    END IF;

    INSERT INTO payments (invoice_id, payment_date, amount, payment_method, reference_no)
    VALUES (p_invoice_id, CURDATE(), p_amount, p_method, p_reference);

    UPDATE invoices
    SET status = IF(v_paid + p_amount = v_total, 'Paid', 'Partially Paid')
    WHERE invoice_id = p_invoice_id;

    COMMIT;
END //
DELIMITER ;

-- 7.4 Account 360 summary and its open deals (two result sets)
DROP PROCEDURE IF EXISTS sp_account_summary;
DELIMITER //
CREATE PROCEDURE sp_account_summary(
    IN p_account_id INT
)
BEGIN
    SELECT *
    FROM vw_account_360
    WHERE account_id = p_account_id;

    SELECT opportunity_id, opportunity_name, stage_name, amount, weighted_amount, expected_close_date
    FROM vw_sales_pipeline
    WHERE account_name = (SELECT account_name FROM accounts WHERE account_id = p_account_id)
      AND is_closed = FALSE
    ORDER BY expected_close_date;
END //
DELIMITER ;

-- 7.5 Open and weighted pipeline of one sales rep (OUT parameters)
DROP PROCEDURE IF EXISTS sp_sales_rep_pipeline;
DELIMITER //
CREATE PROCEDURE sp_sales_rep_pipeline(
    IN  p_user_id           INT,
    OUT p_open_pipeline     DECIMAL(14,2),
    OUT p_weighted_pipeline DECIMAL(14,2)
)
BEGIN
    SELECT COALESCE(SUM(amount), 0),
           COALESCE(SUM(weighted_amount), 0)
      INTO p_open_pipeline, p_weighted_pipeline
    FROM vw_sales_pipeline
    WHERE owner_user_id = p_user_id
      AND is_closed = FALSE;
END //
DELIMITER ;


-- =====================================================================
-- 8. VERIFICATION
-- =====================================================================
SELECT 'roles' AS table_name, COUNT(*) AS row_count FROM roles
UNION ALL SELECT 'users',                     COUNT(*) FROM users
UNION ALL SELECT 'industries',                COUNT(*) FROM industries
UNION ALL SELECT 'accounts',                  COUNT(*) FROM accounts
UNION ALL SELECT 'contacts',                  COUNT(*) FROM contacts
UNION ALL SELECT 'lead_sources',              COUNT(*) FROM lead_sources
UNION ALL SELECT 'leads',                     COUNT(*) FROM leads
UNION ALL SELECT 'pipeline_stages',           COUNT(*) FROM pipeline_stages
UNION ALL SELECT 'opportunities',             COUNT(*) FROM opportunities
UNION ALL SELECT 'products',                  COUNT(*) FROM products
UNION ALL SELECT 'opportunity_products',      COUNT(*) FROM opportunity_products
UNION ALL SELECT 'activities',                COUNT(*) FROM activities
UNION ALL SELECT 'campaigns',                 COUNT(*) FROM campaigns
UNION ALL SELECT 'campaign_leads',            COUNT(*) FROM campaign_leads
UNION ALL SELECT 'tickets',                   COUNT(*) FROM tickets
UNION ALL SELECT 'invoices',                  COUNT(*) FROM invoices
UNION ALL SELECT 'payments',                  COUNT(*) FROM payments
UNION ALL SELECT 'opportunity_stage_history', COUNT(*) FROM opportunity_stage_history;

-- =====================================================================
-- END OF SCRIPT
-- =====================================================================
