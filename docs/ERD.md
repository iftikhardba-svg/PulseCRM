# Entity Relationship Diagram

PulseCRM has **18 tables** connected by **31 foreign keys**. The diagram is shown twice:

1. **Image** (`erd.png` / `erd.svg`), drawn for presentations. To keep it readable, the seven owner and assignee links to `users` are not drawn as lines.
2. **Mermaid** (below). GitHub renders it automatically, and it includes **every** relationship and column.

![PulseCRM ERD](erd.png)

## Crow's foot notation

| Symbol | Meaning |
|---|---|
| `\|\|` | exactly one (mandatory parent) |
| `\|o` | zero or one (optional parent, the FK column allows NULL) |
| `o{` | zero or many children |
| `o\|` | zero or one child (one-to-one, the FK column is UNIQUE) |

## Full diagram (Mermaid)

```mermaid
erDiagram
    industries |o--o{ accounts : "classifies"
    users ||--o{ accounts : "owns"
    contacts |o--o{ activities : "involves"
    leads |o--o{ activities : "follows up"
    opportunities |o--o{ activities : "progresses"
    users ||--o{ activities : "performs"
    campaigns ||--o{ campaign_leads : "targets"
    leads ||--o{ campaign_leads : "joins"
    users ||--o{ campaigns : "runs"
    accounts ||--o{ contacts : "employs"
    opportunities ||--o| invoices : "billed by"
    accounts |o--o{ leads : "converted from"
    users ||--o{ leads : "works"
    lead_sources ||--o{ leads : "generates"
    accounts ||--o{ opportunities : "has"
    contacts |o--o{ opportunities : "decides"
    leads |o--o{ opportunities : "becomes"
    users ||--o{ opportunities : "sells"
    pipeline_stages ||--o{ opportunities : "stage of"
    opportunities ||--o{ opportunity_products : "contains"
    products ||--o{ opportunity_products : "sold in"
    pipeline_stages |o--o{ opportunity_stage_history : "from"
    opportunities ||--o{ opportunity_stage_history : "tracked in"
    pipeline_stages ||--o{ opportunity_stage_history : "to"
    users |o--o{ opportunity_stage_history : "changes"
    invoices ||--o{ payments : "paid by"
    accounts ||--o{ tickets : "raises"
    users |o--o{ tickets : "resolves"
    contacts |o--o{ tickets : "reports"
    users |o--o{ users : "manages"
    roles ||--o{ users : "has"
    roles {
        int role_id PK
        varchar role_name UK
        varchar description
    }
    users {
        int user_id PK
        varchar full_name
        varchar email UK
        varchar phone
        int role_id FK
        int manager_id FK
        date hire_date
        boolean is_active
        datetime created_at
    }
    industries {
        int industry_id PK
        varchar industry_name UK
    }
    accounts {
        int account_id PK
        varchar account_name UK
        int industry_id FK
        varchar account_type
        varchar website
        varchar phone
        varchar city
        varchar country
        decimal annual_revenue
        int employee_count
        int owner_user_id FK
        datetime created_at
    }
    contacts {
        int contact_id PK
        int account_id FK
        varchar first_name
        varchar last_name
        varchar job_title
        varchar email UK
        varchar phone
        boolean is_primary
        datetime created_at
    }
    lead_sources {
        int source_id PK
        varchar source_name UK
    }
    leads {
        int lead_id PK
        varchar first_name
        varchar last_name
        varchar company_name
        varchar job_title
        varchar email UK
        varchar phone
        varchar city
        int source_id FK
        varchar status
        tinyint lead_score
        int owner_user_id FK
        int converted_account_id FK
        datetime converted_at
        datetime created_at
    }
    pipeline_stages {
        int stage_id PK
        varchar stage_name UK
        tinyint stage_order UK
        tinyint win_probability
        boolean is_closed
        boolean is_won
    }
    opportunities {
        int opportunity_id PK
        varchar opportunity_name
        int account_id FK
        int primary_contact_id FK
        int lead_id FK
        int owner_user_id FK
        int stage_id FK
        decimal amount
        date expected_close_date
        date actual_close_date
        varchar loss_reason
        datetime created_at
    }
    products {
        int product_id PK
        varchar product_code UK
        varchar product_name
        varchar category
        decimal unit_price
        boolean is_active
    }
    opportunity_products {
        int opportunity_id PK, FK
        int product_id PK, FK
        int quantity
        decimal unit_price
        decimal discount_pct
        decimal line_total
    }
    activities {
        int activity_id PK
        varchar activity_type
        varchar subject
        datetime activity_date
        smallint duration_minutes
        varchar status
        int owner_user_id FK
        int contact_id FK
        int lead_id FK
        int opportunity_id FK
        varchar notes
    }
    campaigns {
        int campaign_id PK
        varchar campaign_name UK
        varchar channel
        date start_date
        date end_date
        decimal budget
        int owner_user_id FK
    }
    campaign_leads {
        int campaign_id PK, FK
        int lead_id PK, FK
        date added_on
        varchar response
    }
    tickets {
        int ticket_id PK
        int account_id FK
        int contact_id FK
        int assigned_user_id FK
        varchar subject
        varchar priority
        varchar status
        datetime opened_at
        datetime resolved_at
        tinyint satisfaction_score
    }
    invoices {
        int invoice_id PK
        varchar invoice_number UK
        int opportunity_id FK, UK
        date invoice_date
        date due_date
        decimal total_amount
        varchar status
    }
    payments {
        int payment_id PK
        int invoice_id FK
        date payment_date
        decimal amount
        varchar payment_method
        varchar reference_no UK
    }
    opportunity_stage_history {
        int history_id PK
        int opportunity_id FK
        int from_stage_id FK
        int to_stage_id FK
        int changed_by FK
        datetime changed_at
    }
```

## Relationship list

| Parent (one) | Child (many) | Foreign key | Cardinality | Parent link | ON DELETE |
|---|---|---|---|---|---|
| `industries` | `accounts` | `accounts.industry_id` → `industries.industry_id` | 1 : N | optional | NO ACTION |
| `users` | `accounts` | `accounts.owner_user_id` → `users.user_id` | 1 : N | required | NO ACTION |
| `contacts` | `activities` | `activities.contact_id` → `contacts.contact_id` | 1 : N | optional | NO ACTION |
| `leads` | `activities` | `activities.lead_id` → `leads.lead_id` | 1 : N | optional | NO ACTION |
| `opportunities` | `activities` | `activities.opportunity_id` → `opportunities.opportunity_id` | 1 : N | optional | NO ACTION |
| `users` | `activities` | `activities.owner_user_id` → `users.user_id` | 1 : N | required | NO ACTION |
| `campaigns` | `campaign_leads` | `campaign_leads.campaign_id` → `campaigns.campaign_id` | 1 : N | required | CASCADE |
| `leads` | `campaign_leads` | `campaign_leads.lead_id` → `leads.lead_id` | 1 : N | required | CASCADE |
| `users` | `campaigns` | `campaigns.owner_user_id` → `users.user_id` | 1 : N | required | NO ACTION |
| `accounts` | `contacts` | `contacts.account_id` → `accounts.account_id` | 1 : N | required | CASCADE |
| `opportunities` | `invoices` | `invoices.opportunity_id` → `opportunities.opportunity_id` | 1 : 0..1 | required | NO ACTION |
| `accounts` | `leads` | `leads.converted_account_id` → `accounts.account_id` | 1 : N | optional | NO ACTION |
| `users` | `leads` | `leads.owner_user_id` → `users.user_id` | 1 : N | required | NO ACTION |
| `lead_sources` | `leads` | `leads.source_id` → `lead_sources.source_id` | 1 : N | required | NO ACTION |
| `accounts` | `opportunities` | `opportunities.account_id` → `accounts.account_id` | 1 : N | required | NO ACTION |
| `contacts` | `opportunities` | `opportunities.primary_contact_id` → `contacts.contact_id` | 1 : N | optional | NO ACTION |
| `leads` | `opportunities` | `opportunities.lead_id` → `leads.lead_id` | 1 : N | optional | NO ACTION |
| `users` | `opportunities` | `opportunities.owner_user_id` → `users.user_id` | 1 : N | required | NO ACTION |
| `pipeline_stages` | `opportunities` | `opportunities.stage_id` → `pipeline_stages.stage_id` | 1 : N | required | NO ACTION |
| `opportunities` | `opportunity_products` | `opportunity_products.opportunity_id` → `opportunities.opportunity_id` | 1 : N | required | CASCADE |
| `products` | `opportunity_products` | `opportunity_products.product_id` → `products.product_id` | 1 : N | required | NO ACTION |
| `pipeline_stages` | `opportunity_stage_history` | `opportunity_stage_history.from_stage_id` → `pipeline_stages.stage_id` | 1 : N | optional | NO ACTION |
| `opportunities` | `opportunity_stage_history` | `opportunity_stage_history.opportunity_id` → `opportunities.opportunity_id` | 1 : N | required | CASCADE |
| `pipeline_stages` | `opportunity_stage_history` | `opportunity_stage_history.to_stage_id` → `pipeline_stages.stage_id` | 1 : N | required | NO ACTION |
| `users` | `opportunity_stage_history` | `opportunity_stage_history.changed_by` → `users.user_id` | 1 : N | optional | SET NULL |
| `invoices` | `payments` | `payments.invoice_id` → `invoices.invoice_id` | 1 : N | required | NO ACTION |
| `accounts` | `tickets` | `tickets.account_id` → `accounts.account_id` | 1 : N | required | NO ACTION |
| `users` | `tickets` | `tickets.assigned_user_id` → `users.user_id` | 1 : N | optional | NO ACTION |
| `contacts` | `tickets` | `tickets.contact_id` → `contacts.contact_id` | 1 : N | optional | NO ACTION |
| `users` | `users` | `users.manager_id` → `users.user_id` | 1 : N | optional | SET NULL |
| `roles` | `users` | `users.role_id` → `roles.role_id` | 1 : N | required | NO ACTION |

## Design notes

- **Many-to-many relationships** are resolved with bridge tables that use composite primary keys:
  - `opportunity_products`: deals ↔ products
  - `campaign_leads`: campaigns ↔ leads
- **One-to-one:** `invoices.opportunity_id` is `UNIQUE`, so a won deal is billed exactly once.
- **Self-reference:** `users.manager_id` → `users.user_id` stores the reporting line.
- **Two relationships between the same pair of tables:** `opportunity_stage_history` refers to `pipeline_stages` twice, once for the `from_stage_id` and once for the `to_stage_id` of a change.
- **Lookup tables** (`roles`, `industries`, `lead_sources`, `pipeline_stages`) keep repeated text out of the main tables and give one place to change a value.
