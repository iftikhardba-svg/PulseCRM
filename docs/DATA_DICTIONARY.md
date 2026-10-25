# Data Dictionary

Generated from the live MySQL `information_schema` after running `database/pulse_crm.sql`.

**Key:** PK = primary key, FK = foreign key, UK = unique key, MUL = indexed column.

| # | Table | Purpose | Columns |
|---|---|---|---|
| 1 | [`roles`](#roles) | Staff roles that control what users do in the CRM | 3 |
| 2 | [`users`](#users) | Sales, marketing and support staff who use the CRM | 9 |
| 3 | [`industries`](#industries) | Lookup list of business sectors | 2 |
| 4 | [`accounts`](#accounts) | Organisations we sell to or work with | 12 |
| 5 | [`contacts`](#contacts) | Individual people who work at an account | 9 |
| 6 | [`lead_sources`](#lead_sources) | Lookup list of lead channels | 2 |
| 7 | [`leads`](#leads) | Potential customers captured by marketing and sales | 15 |
| 8 | [`pipeline_stages`](#pipeline_stages) | Sales pipeline stages with win probability | 6 |
| 9 | [`opportunities`](#opportunities) | Sales deals moving through the pipeline | 12 |
| 10 | [`products`](#products) | Products and services offered to customers | 6 |
| 11 | [`opportunity_products`](#opportunity_products) | Products included in each opportunity (bridge table) | 6 |
| 12 | [`activities`](#activities) | Every interaction with a lead, contact or deal | 11 |
| 13 | [`campaigns`](#campaigns) | Marketing campaigns that generate leads | 7 |
| 14 | [`campaign_leads`](#campaign_leads) | Leads targeted by each campaign (bridge table) | 4 |
| 15 | [`tickets`](#tickets) | Customer support requests | 10 |
| 16 | [`invoices`](#invoices) | Bills raised for won deals | 7 |
| 17 | [`payments`](#payments) | Money received against invoices | 6 |
| 18 | [`opportunity_stage_history`](#opportunity_stage_history) | Audit trail of pipeline stage changes | 6 |

## roles

Staff roles that control what users do in the CRM

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `role_id` | int | NO | PK | AUTO_INCREMENT | Role identifier |
| `role_name` | varchar(50) | NO | UK |  | Job role name |
| `description` | varchar(255) | YES |  |  | What the role is responsible for |

**Indexes**

- `uq_roles_name` (unique): role_name

## users

Sales, marketing and support staff who use the CRM

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `user_id` | int | NO | PK | AUTO_INCREMENT | User identifier |
| `full_name` | varchar(100) | NO |  |  | Staff member full name |
| `email` | varchar(120) | NO | UK |  | Login and contact email |
| `phone` | varchar(20) | YES |  |  | Office mobile number |
| `role_id` | int | NO | FK → roles.role_id |  | Role of the user (FK roles) |
| `manager_id` | int | YES | FK → users.user_id |  | Line manager (FK users, self reference) |
| `hire_date` | date | NO |  |  | Date the user joined |
| `is_active` | tinyint(1) | NO |  | 1 | FALSE when the user has left |
| `created_at` | datetime | NO |  | generated (stored) | Record creation time |

**CHECK constraints**

- `chk_users_email`: `(email like '%_@_%._%')`

**Foreign keys**

- `fk_users_manager`: `manager_id` → `users.user_id` (ON DELETE SET NULL)
- `fk_users_role`: `role_id` → `roles.role_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_users_manager` (non-unique): manager_id
- `fk_users_role` (non-unique): role_id
- `uq_users_email` (unique): email

## industries

Lookup list of business sectors

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `industry_id` | int | NO | PK | AUTO_INCREMENT | Industry identifier |
| `industry_name` | varchar(60) | NO | UK |  | Industry sector name |

**Indexes**

- `uq_industries_name` (unique): industry_name

## accounts

Organisations we sell to or work with

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `account_id` | int | NO | PK | AUTO_INCREMENT | Account identifier |
| `account_name` | varchar(150) | NO | UK |  | Company name |
| `industry_id` | int | YES | FK → industries.industry_id |  | Business sector (FK industries) |
| `account_type` | varchar(20) | NO | MUL | Prospect | Prospect, Customer, Partner or Churned |
| `website` | varchar(150) | YES |  |  | Company website |
| `phone` | varchar(20) | YES |  |  | Main office phone |
| `city` | varchar(60) | NO |  |  | Head office city |
| `country` | varchar(60) | NO |  | Pakistan | Head office country |
| `annual_revenue` | decimal(15,2) | YES |  |  | Company yearly revenue (PKR) |
| `employee_count` | int | YES |  |  | Number of employees |
| `owner_user_id` | int | NO | FK → users.user_id |  | Account manager (FK users) |
| `created_at` | datetime | NO |  | generated (stored) | Record creation time |

**CHECK constraints**

- `chk_accounts_employees`: `((employee_count is null) or (employee_count >= 0))`
- `chk_accounts_revenue`: `((annual_revenue is null) or (annual_revenue >= 0))`
- `chk_accounts_type`: `(account_type in ('Prospect','Customer','Partner','Churned'))`

**Foreign keys**

- `fk_accounts_industry`: `industry_id` → `industries.industry_id` (ON DELETE NO ACTION)
- `fk_accounts_owner`: `owner_user_id` → `users.user_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_accounts_industry` (non-unique): industry_id
- `fk_accounts_owner` (non-unique): owner_user_id
- `idx_accounts_type_city` (non-unique): account_type, city
- `uq_accounts_name` (unique): account_name

## contacts

Individual people who work at an account

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `contact_id` | int | NO | PK | AUTO_INCREMENT | Contact identifier |
| `account_id` | int | NO | FK → accounts.account_id |  | Company the person works for (FK accounts) |
| `first_name` | varchar(50) | NO |  |  | First name |
| `last_name` | varchar(50) | NO |  |  | Last name |
| `job_title` | varchar(100) | YES |  |  | Job title |
| `email` | varchar(120) | NO | UK |  | Business email |
| `phone` | varchar(20) | YES |  |  | Phone number |
| `is_primary` | tinyint(1) | NO |  | 0 | TRUE for the main contact of the account |
| `created_at` | datetime | NO |  | generated (stored) | Record creation time |

**CHECK constraints**

- `chk_contacts_email`: `(email like '%_@_%._%')`

**Foreign keys**

- `fk_contacts_account`: `account_id` → `accounts.account_id` (ON DELETE CASCADE)

**Indexes**

- `fk_contacts_account` (non-unique): account_id
- `uq_contacts_email` (unique): email

## lead_sources

Lookup list of lead channels

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `source_id` | int | NO | PK | AUTO_INCREMENT | Lead source identifier |
| `source_name` | varchar(50) | NO | UK |  | Where the lead came from |

**Indexes**

- `uq_lead_sources_name` (unique): source_name

## leads

Potential customers captured by marketing and sales

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `lead_id` | int | NO | PK | AUTO_INCREMENT | Lead identifier |
| `first_name` | varchar(50) | NO |  |  | First name |
| `last_name` | varchar(50) | NO |  |  | Last name |
| `company_name` | varchar(150) | NO |  |  | Company the lead belongs to |
| `job_title` | varchar(100) | YES |  |  | Job title |
| `email` | varchar(120) | NO | UK |  | Email address |
| `phone` | varchar(20) | YES |  |  | Phone number |
| `city` | varchar(60) | YES |  |  | City |
| `source_id` | int | NO | FK → lead_sources.source_id |  | Lead channel (FK lead_sources) |
| `status` | varchar(20) | NO | MUL | New | New, Contacted, Qualified, Unqualified or Converted |
| `lead_score` | tinyint unsigned | NO |  | 0 | Sales readiness score 0-100 |
| `owner_user_id` | int | NO | FK → users.user_id |  | Sales owner (FK users) |
| `converted_account_id` | int | YES | FK → accounts.account_id |  | Account created on conversion (FK accounts) |
| `converted_at` | datetime | YES |  |  | When the lead was converted |
| `created_at` | datetime | NO |  | generated (stored) | Record creation time |

**CHECK constraints**

- `chk_leads_converted`: `((status <> 'Converted') or ((converted_account_id is not null) and (converted_at is not null)))`
- `chk_leads_score`: `(lead_score between 0 and 100)`
- `chk_leads_status`: `(status in ('New','Contacted','Qualified','Unqualified','Converted'))`

**Foreign keys**

- `fk_leads_converted_account`: `converted_account_id` → `accounts.account_id` (ON DELETE NO ACTION)
- `fk_leads_owner`: `owner_user_id` → `users.user_id` (ON DELETE NO ACTION)
- `fk_leads_source`: `source_id` → `lead_sources.source_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_leads_converted_account` (non-unique): converted_account_id
- `fk_leads_owner` (non-unique): owner_user_id
- `fk_leads_source` (non-unique): source_id
- `idx_leads_status_score` (non-unique): status, lead_score
- `uq_leads_email` (unique): email

## pipeline_stages

Sales pipeline stages with win probability

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `stage_id` | int | NO | PK | AUTO_INCREMENT | Stage identifier |
| `stage_name` | varchar(50) | NO | UK |  | Stage name |
| `stage_order` | tinyint unsigned | NO | UK |  | Position of the stage in the pipeline |
| `win_probability` | tinyint unsigned | NO |  |  | Chance of winning at this stage (%) |
| `is_closed` | tinyint(1) | NO |  | 0 | TRUE for Closed Won and Closed Lost |
| `is_won` | tinyint(1) | NO |  | 0 | TRUE only for Closed Won |

**CHECK constraints**

- `chk_stages_probability`: `(win_probability between 0 and 100)`
- `chk_stages_won_closed`: `((is_won = false) or (is_closed = true))`

**Indexes**

- `uq_stages_name` (unique): stage_name
- `uq_stages_order` (unique): stage_order

## opportunities

Sales deals moving through the pipeline

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `opportunity_id` | int | NO | PK | AUTO_INCREMENT | Opportunity identifier |
| `opportunity_name` | varchar(150) | NO |  |  | Short deal name |
| `account_id` | int | NO | FK → accounts.account_id |  | Customer company (FK accounts) |
| `primary_contact_id` | int | YES | FK → contacts.contact_id |  | Main decision maker (FK contacts) |
| `lead_id` | int | YES | FK → leads.lead_id |  | Lead the deal came from (FK leads) |
| `owner_user_id` | int | NO | FK → users.user_id |  | Sales owner (FK users) |
| `stage_id` | int | NO | FK → pipeline_stages.stage_id |  | Current pipeline stage (FK pipeline_stages) |
| `amount` | decimal(14,2) | NO |  | 0.00 | Deal value (PKR), sum of line items |
| `expected_close_date` | date | NO | MUL |  | Forecast close date |
| `actual_close_date` | date | YES |  |  | Date the deal was won or lost |
| `loss_reason` | varchar(255) | YES |  |  | Why the deal was lost |
| `created_at` | datetime | NO |  | generated (stored) | Record creation time |

**CHECK constraints**

- `chk_opportunities_amount`: `(amount >= 0)`

**Foreign keys**

- `fk_opportunities_account`: `account_id` → `accounts.account_id` (ON DELETE NO ACTION)
- `fk_opportunities_contact`: `primary_contact_id` → `contacts.contact_id` (ON DELETE NO ACTION)
- `fk_opportunities_lead`: `lead_id` → `leads.lead_id` (ON DELETE NO ACTION)
- `fk_opportunities_owner`: `owner_user_id` → `users.user_id` (ON DELETE NO ACTION)
- `fk_opportunities_stage`: `stage_id` → `pipeline_stages.stage_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_opportunities_account` (non-unique): account_id
- `fk_opportunities_contact` (non-unique): primary_contact_id
- `fk_opportunities_lead` (non-unique): lead_id
- `fk_opportunities_owner` (non-unique): owner_user_id
- `fk_opportunities_stage` (non-unique): stage_id
- `idx_opportunities_close` (non-unique): expected_close_date

## products

Products and services offered to customers

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `product_id` | int | NO | PK | AUTO_INCREMENT | Product identifier |
| `product_code` | varchar(20) | NO | UK |  | Unique catalogue code |
| `product_name` | varchar(120) | NO |  |  | Product or service name |
| `category` | varchar(20) | NO |  |  | Software, Service, Support or Training |
| `unit_price` | decimal(12,2) | NO |  |  | List price (PKR) |
| `is_active` | tinyint(1) | NO |  | 1 | FALSE when no longer sold |

**CHECK constraints**

- `chk_products_category`: `(category in ('Software','Service','Support','Training'))`
- `chk_products_price`: `(unit_price > 0)`

**Indexes**

- `uq_products_code` (unique): product_code

## opportunity_products

Products included in each opportunity (bridge table)

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `opportunity_id` | int | NO | PK, FK → opportunities.opportunity_id |  | Deal (FK opportunities) |
| `product_id` | int | NO | PK, FK → products.product_id |  | Product on the deal (FK products) |
| `quantity` | int | NO |  | 1 | Units or days |
| `unit_price` | decimal(12,2) | NO |  |  | Agreed unit price (PKR) |
| `discount_pct` | decimal(5,2) | NO |  | 0.00 | Discount percentage |
| `line_total` | decimal(14,2) | YES |  | generated (stored) | Calculated line value after discount |

**CHECK constraints**

- `chk_oppprod_discount`: `(discount_pct between 0 and 100)`
- `chk_oppprod_price`: `(unit_price >= 0)`
- `chk_oppprod_quantity`: `(quantity > 0)`

**Foreign keys**

- `fk_oppprod_opportunity`: `opportunity_id` → `opportunities.opportunity_id` (ON DELETE CASCADE)
- `fk_oppprod_product`: `product_id` → `products.product_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_oppprod_product` (non-unique): product_id

## activities

Every interaction with a lead, contact or deal

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `activity_id` | int | NO | PK | AUTO_INCREMENT | Activity identifier |
| `activity_type` | varchar(20) | NO |  |  | Call, Email, Meeting, Demo or Task |
| `subject` | varchar(150) | NO |  |  | Short description |
| `activity_date` | datetime | NO | MUL |  | When it happened or is planned |
| `duration_minutes` | smallint | NO |  | 0 | Length in minutes |
| `status` | varchar(20) | NO |  | Planned | Planned, Completed or Cancelled |
| `owner_user_id` | int | NO | FK → users.user_id |  | Staff member responsible (FK users) |
| `contact_id` | int | YES | FK → contacts.contact_id |  | Related contact (FK contacts) |
| `lead_id` | int | YES | FK → leads.lead_id |  | Related lead (FK leads) |
| `opportunity_id` | int | YES | FK → opportunities.opportunity_id |  | Related deal (FK opportunities) |
| `notes` | varchar(500) | YES |  |  | Outcome or notes |

**CHECK constraints**

- `chk_activities_duration`: `(duration_minutes >= 0)`
- `chk_activities_link`: `((contact_id is not null) or (lead_id is not null) or (opportunity_id is not null))`
- `chk_activities_status`: `(status in ('Planned','Completed','Cancelled'))`
- `chk_activities_type`: `(activity_type in ('Call','Email','Meeting','Demo','Task'))`

**Foreign keys**

- `fk_activities_contact`: `contact_id` → `contacts.contact_id` (ON DELETE NO ACTION)
- `fk_activities_lead`: `lead_id` → `leads.lead_id` (ON DELETE NO ACTION)
- `fk_activities_opportunity`: `opportunity_id` → `opportunities.opportunity_id` (ON DELETE NO ACTION)
- `fk_activities_owner`: `owner_user_id` → `users.user_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_activities_contact` (non-unique): contact_id
- `fk_activities_lead` (non-unique): lead_id
- `fk_activities_opportunity` (non-unique): opportunity_id
- `fk_activities_owner` (non-unique): owner_user_id
- `idx_activities_date_status` (non-unique): activity_date, status

## campaigns

Marketing campaigns that generate leads

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `campaign_id` | int | NO | PK | AUTO_INCREMENT | Campaign identifier |
| `campaign_name` | varchar(120) | NO | UK |  | Campaign name |
| `channel` | varchar(20) | NO |  |  | Email, Social Media, Event, Webinar or Paid Ads |
| `start_date` | date | NO |  |  | First day of the campaign |
| `end_date` | date | NO |  |  | Last day of the campaign |
| `budget` | decimal(12,2) | NO |  | 0.00 | Approved budget (PKR) |
| `owner_user_id` | int | NO | FK → users.user_id |  | Marketing owner (FK users) |

**CHECK constraints**

- `chk_campaigns_budget`: `(budget >= 0)`
- `chk_campaigns_channel`: `(channel in ('Email','Social Media','Event','Webinar','Paid Ads'))`
- `chk_campaigns_dates`: `(end_date >= start_date)`

**Foreign keys**

- `fk_campaigns_owner`: `owner_user_id` → `users.user_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_campaigns_owner` (non-unique): owner_user_id
- `uq_campaigns_name` (unique): campaign_name

## campaign_leads

Leads targeted by each campaign (bridge table)

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `campaign_id` | int | NO | PK, FK → campaigns.campaign_id |  | Campaign (FK campaigns) |
| `lead_id` | int | NO | PK, FK → leads.lead_id |  | Targeted lead (FK leads) |
| `added_on` | date | NO |  |  | Date the lead joined the campaign |
| `response` | varchar(20) | NO |  | Sent | Sent, Opened, Clicked or Responded |

**CHECK constraints**

- `chk_campaignleads_response`: `(response in ('Sent','Opened','Clicked','Responded'))`

**Foreign keys**

- `fk_campaignleads_campaign`: `campaign_id` → `campaigns.campaign_id` (ON DELETE CASCADE)
- `fk_campaignleads_lead`: `lead_id` → `leads.lead_id` (ON DELETE CASCADE)

**Indexes**

- `fk_campaignleads_lead` (non-unique): lead_id

## tickets

Customer support requests

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `ticket_id` | int | NO | PK | AUTO_INCREMENT | Ticket identifier |
| `account_id` | int | NO | FK → accounts.account_id |  | Customer company (FK accounts) |
| `contact_id` | int | YES | FK → contacts.contact_id |  | Person who raised it (FK contacts) |
| `assigned_user_id` | int | YES | FK → users.user_id |  | Support agent (FK users) |
| `subject` | varchar(150) | NO |  |  | Problem summary |
| `priority` | varchar(10) | NO |  | Medium | Low, Medium, High or Critical |
| `status` | varchar(20) | NO | MUL | Open | Open, In Progress, Resolved or Closed |
| `opened_at` | datetime | NO |  |  | When the ticket was raised |
| `resolved_at` | datetime | YES |  |  | When the ticket was resolved |
| `satisfaction_score` | tinyint | YES |  |  | Customer rating 1-5 after resolution |

**CHECK constraints**

- `chk_tickets_priority`: `(priority in ('Low','Medium','High','Critical'))`
- `chk_tickets_resolved`: `((resolved_at is null) or (resolved_at >= opened_at))`
- `chk_tickets_resolved_set`: `((status not in ('Resolved','Closed')) or (resolved_at is not null))`
- `chk_tickets_satisfaction`: `((satisfaction_score is null) or (satisfaction_score between 1 and 5))`
- `chk_tickets_status`: `(status in ('Open','In Progress','Resolved','Closed'))`

**Foreign keys**

- `fk_tickets_account`: `account_id` → `accounts.account_id` (ON DELETE NO ACTION)
- `fk_tickets_assignee`: `assigned_user_id` → `users.user_id` (ON DELETE NO ACTION)
- `fk_tickets_contact`: `contact_id` → `contacts.contact_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_tickets_account` (non-unique): account_id
- `fk_tickets_assignee` (non-unique): assigned_user_id
- `fk_tickets_contact` (non-unique): contact_id
- `idx_tickets_status_priority` (non-unique): status, priority

## invoices

Bills raised for won deals

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `invoice_id` | int | NO | PK | AUTO_INCREMENT | Invoice identifier |
| `invoice_number` | varchar(20) | NO | UK |  | Printed invoice number |
| `opportunity_id` | int | NO | UK, FK → opportunities.opportunity_id |  | Won deal being billed (FK opportunities, unique) |
| `invoice_date` | date | NO |  |  | Issue date |
| `due_date` | date | NO |  |  | Payment due date |
| `total_amount` | decimal(14,2) | NO |  |  | Invoice total (PKR) |
| `status` | varchar(20) | NO | MUL | Unpaid | Unpaid, Partially Paid, Paid, Overdue or Cancelled |

**CHECK constraints**

- `chk_invoices_amount`: `(total_amount >= 0)`
- `chk_invoices_dates`: `(due_date >= invoice_date)`
- `chk_invoices_status`: `(status in ('Unpaid','Partially Paid','Paid','Overdue','Cancelled'))`

**Foreign keys**

- `fk_invoices_opportunity`: `opportunity_id` → `opportunities.opportunity_id` (ON DELETE NO ACTION)

**Indexes**

- `idx_invoices_status_due` (non-unique): status, due_date
- `uq_invoices_number` (unique): invoice_number
- `uq_invoices_opportunity` (unique): opportunity_id

## payments

Money received against invoices

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `payment_id` | int | NO | PK | AUTO_INCREMENT | Payment identifier |
| `invoice_id` | int | NO | FK → invoices.invoice_id |  | Invoice being paid (FK invoices) |
| `payment_date` | date | NO |  |  | Date the money was received |
| `amount` | decimal(14,2) | NO |  |  | Amount received (PKR) |
| `payment_method` | varchar(20) | NO |  |  | Bank Transfer, Card, Cash or Cheque |
| `reference_no` | varchar(50) | YES | UK |  | Bank or cheque reference |

**CHECK constraints**

- `chk_payments_amount`: `(amount > 0)`
- `chk_payments_method`: `(payment_method in ('Bank Transfer','Card','Cash','Cheque'))`

**Foreign keys**

- `fk_payments_invoice`: `invoice_id` → `invoices.invoice_id` (ON DELETE NO ACTION)

**Indexes**

- `fk_payments_invoice` (non-unique): invoice_id
- `uq_payments_reference` (unique): reference_no

## opportunity_stage_history

Audit trail of pipeline stage changes

| Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|
| `history_id` | int | NO | PK | AUTO_INCREMENT | History row identifier |
| `opportunity_id` | int | NO | FK → opportunities.opportunity_id |  | Deal that moved (FK opportunities) |
| `from_stage_id` | int | YES | FK → pipeline_stages.stage_id |  | Previous stage, NULL when created (FK pipeline_stages) |
| `to_stage_id` | int | NO | FK → pipeline_stages.stage_id |  | New stage (FK pipeline_stages) |
| `changed_by` | int | YES | FK → users.user_id |  | User who moved the deal (FK users) |
| `changed_at` | datetime | NO | MUL | generated (stored) | Time of the change |

**Foreign keys**

- `fk_history_from_stage`: `from_stage_id` → `pipeline_stages.stage_id` (ON DELETE NO ACTION)
- `fk_history_opportunity`: `opportunity_id` → `opportunities.opportunity_id` (ON DELETE CASCADE)
- `fk_history_to_stage`: `to_stage_id` → `pipeline_stages.stage_id` (ON DELETE NO ACTION)
- `fk_history_user`: `changed_by` → `users.user_id` (ON DELETE SET NULL)

**Indexes**

- `fk_history_from_stage` (non-unique): from_stage_id
- `fk_history_opportunity` (non-unique): opportunity_id
- `fk_history_to_stage` (non-unique): to_stage_id
- `fk_history_user` (non-unique): changed_by
- `idx_history_changed_at` (non-unique): changed_at
