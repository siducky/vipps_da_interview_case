# Vipps Case Data Model

Entity-relationship diagram for the Vipps Data Analyst interview case. The
machine-readable definitions are in [`model.yml`](model.yml); full column
descriptions are in [`data/README.md`](../data/README.md).

```mermaid
erDiagram
    USERS {
        string user_id PK
        timestamp observation_start_date
        boolean vip_enrolled
        timestamp vip_enrolled_at "nullable"
        string user_country
        string age_bucket
    }
    CARDS {
        string payment_source_id PK
        string user_id FK
        string card_type
        string card_status
        string card_scheme
    }
    TRANSACTIONS {
        string transaction_id PK
        string user_id FK
        string merchant_id FK
        string payment_source_id FK
        timestamp transaction_timestamp
        decimal volume_nok
        decimal revenue_nok
        string currency
        string user_country
        string payment_channel
    }
    MERCHANTS {
        string merchant_id PK
        string merchant_name
        string merchant_country
        string merchant_mcc_code FK "nullable"
    }
    MCC {
        string merchant_mcc_code PK
        string category_name
    }
    EXPERIMENT_EXPOSURE {
        string user_id PK, FK
        string experiment_id
        string variant
        timestamp exposure_timestamp
    }

    USERS ||--o{ TRANSACTIONS : "user_id"
    MERCHANTS ||--o{ TRANSACTIONS : "merchant_id"
    TRANSACTIONS }o--|| CARDS : "payment_source_id"
    USERS ||--o| EXPERIMENT_EXPOSURE : "user_id"
    USERS ||--o{ CARDS : "user_id"
    MERCHANTS }o--o| MCC : "merchant_mcc_code"
```

## Legend

- `||--o{` — one to zero-or-more
- `||--o|` — one to zero-or-one
- `}o--||` — zero-or-more to one
- `}o--o|` — zero-or-more to zero-or-one
- `PK` — primary key
- `FK` — foreign key

## Notes

- `transactions` is the fact table; it has one row per completed purchase.
- `users`, `merchants`, `cards`, and `mcc` are dimension tables.
- `experiment_exposure` is a subset of users in the VIP invitation experiment.
- `merchants.merchant_mcc_code` is nullable; missing MCC means unclassified.
- `users.vip_enrolled_at` is nullable; missing means not enrolled at cutoff.
- `cards` is optional for analysis.
- `experiment_exposure.user_id` is both a primary key and a foreign key to
  `users.user_id`.
- Relationships are oriented from whichever side keeps the fact table central;
  the crow's-foot markers preserve the original cardinality.
