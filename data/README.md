# Data

Dataset for the Vipps Data Analyst interview case. The machine-readable model
used for SQL analysis is [`semantic/model.yml`](../semantic/model.yml).

## Global rules

- CSV files are UTF-8 with headers.
- Identifiers and MCC codes are strings.
- Timestamps use `YYYY-MM-DD HH:MM:SS` on a common fictional clock; no timezone conversion is needed.
- The cutoff is `2026-01-01 00:00:00`, exclusive.
- Empty fields mean missing, not zero.
- `transactions.csv` contains only completed purchases with a positive transaction value.
- The data is synthetic; fee percentages and NOK values do not represent actual Vipps economics.

## Layout

| Path | Purpose | Committed |
|---|---|---|
| `data/raw/` | Original case files; immutable | Yes, if publication is permitted |
| `data/processed/` | Generated intermediate files, including the local DuckDB database | No |
| `notebooks/public/` | Analysis-ready CSV(s) used by the notebook and WASM export | Yes |

## Analytical marts

`notebooks/case_analysis.py` builds three derived marts in memory with DuckDB
and writes them to `data/processed/`:

| Mart | Grain | Rows | Source tables |
|---|---|---:|---|
| `df_user_spine` | One row per user | 419 | `users`, `transactions`, `experiment_exposure` |
| `df_exp_eval` | One row per experiment user | 269 | `experiment_exposure`, `users`, `transactions` |
| `df_weekly_panel` | One row per user-week | 20,725 | `df_user_spine`, `transactions`, `merchants`, `mcc` |

Column-level definitions, calculations and caveats are in
[`semantic/marts.yml`](../semantic/marts.yml); the relationship diagram is in
[`semantic/marts_erd.md`](../semantic/marts_erd.md). The notebook also renders
the dictionary in its appendix.

## Provenance

- **Source:** Vipps MobilePay case pack
- **Dictionary:** [`raw/Data_Dictionary.pdf`](raw/Data_Dictionary.pdf), dated 2026-10-12
- **Data period:** 2025 purchases, with a cutoff of 2026-01-01 00:00:00 exclusive
- **Owner:** Vipps / case provider
- **Publication permission:** Confirm before publishing raw files

## Files

| File | Grain | Rows | Primary key | Notes |
|---|---|---:|---|---|
| `raw/transactions.csv` | One completed positive purchase | 350,567 | `transaction_id` | Transaction-level fact table |
| `raw/users.csv` | One user | 419 | `user_id` | User attributes and cutoff membership status |
| `raw/merchants.csv` | One merchant | 30 | `merchant_id` | One merchant has no MCC |
| `raw/mcc.csv` | One MCC category | 6 | `merchant_mcc_code` | MCC, not NACE |
| `raw/cards.csv` | One card/payment source | 1,203 | `payment_source_id` | Optional table |
| `raw/experiment_exposure.csv` | One allocation per user | 269 | `user_id` | VIP invitation experiment |
| `raw/Data_Dictionary.pdf` | Source dictionary | 3 pages | - | Original Vipps document |

Row counts exclude the header and reflect the current raw files.

## Data dictionary

### `transactions.csv`

One completed purchase with a positive transaction value.

| Column | Type | Meaning |
|---|---|---|
| `transaction_id` | String | Unique purchase identifier. |
| `user_id` | String | Purchaser; joins to `users.user_id`. |
| `merchant_id` | String | Merchant receiving payment; joins to `merchants.merchant_id`. |
| `payment_source_id` | String | Card used; joins to `cards.payment_source_id`. |
| `transaction_timestamp` | Timestamp | Purchase completion time. |
| `volume_nok` | Decimal | Purchase value expressed in NOK. |
| `revenue_nok` | Decimal | NOK amount the fictional payment service retains: a merchant-specific percentage of `volume_nok`, rounded to two decimals. Before costs; not profit. |
| `currency` | String | `NOK`, regardless of user or merchant country. |
| `user_country` | String | `Norway` or `Denmark`, repeated from `users.csv` for convenience. Not physical location at payment time. |
| `payment_channel` | String | `online` or `in_person`; a broad channel rather than device or product feature. |

Notes:

- Fee percentages are synthetic, fixed per merchant during the year, and do not represent actual Vipps fees.
- NOK values are synthetically rescaled, not converted at a historical exchange rate.
- International purchases are already in NOK.
- Failed payments, refunds, and transfers are excluded.
- Use `transactions.user_country` for transaction-level country rather than joining users for country.

### `users.csv`

One user.

| Column | Type | Meaning |
|---|---|---|
| `user_id` | String | Unique user identifier. |
| `observation_start_date` | Timestamp | Start of complete purchase coverage, not signup or first use. |
| `vip_enrolled` | Boolean | True if enrolled in VIP by the dataset cutoff; false otherwise. Not membership status at every historical purchase. |
| `vip_enrolled_at` | Timestamp, nullable | VIP signup time; null for non-members at cutoff. No membership cancellations are modelled. |
| `user_country` | String | Synthetic residence: `Norway` or `Denmark`. Authoritative country attribute. |
| `age_bucket` | String | Synthetic age as of 1 January 2025: four-year buckets `18-21`, `22-25`, through `78-81`. |

Notes:

- All users share the cutoff.
- Behaviour before `observation_start_date` is unknown.
- The selected population is not representative of actual customers.
- Country and age are generated for the exercise.
- `vip_enrolled` is status at cutoff, not historical membership.

### `merchants.csv`

One merchant.

| Column | Type | Meaning |
|---|---|---|
| `merchant_id` | String | Unique merchant identifier. |
| `merchant_name` | String | Fictional grocery, specialist-food or online retailer. |
| `merchant_country` | String | `Norway`, `Denmark`, `Sweden`, `Germany`, or `Netherlands`. |
| `merchant_mcc_code` | String, nullable | MCC category; joins to `mcc.merchant_mcc_code` when known. Missing means unclassified, not "other". |

Notes:

- Users can purchase from international merchants.
- Grocers support online and in-person payments; non-food retailers accept online payments.
- Merchant country is not the transaction currency.
- Resemblance of fictional names to actual businesses is incidental.

### `mcc.csv`

One category.

| Column | Type | Meaning |
|---|---|---|
| `merchant_mcc_code` | String | Unique Merchant Category Code (MCC). |
| `category_name` | String | Category description. |

Notes:

- This is MCC, not NACE.
- Several merchants share a category.
- Join `transactions` to `merchants`, then `merchants` to `mcc`; preserve transaction grain in both joins.

### `cards.csv`

One card/payment source. This table is optional.

| Column | Type | Meaning |
|---|---|---|
| `payment_source_id` | String | Unique card identifier used in transactions. |
| `user_id` | String | Card owner. A user can have several cards. |
| `card_type` | String | Synthetic `debit` or `credit`. |
| `card_status` | String | `Active` or `Inactive` as of 1 January 2026. |
| `card_scheme` | String | `visa` or `mastercard`, the network/scheme. Issuing bank is not supplied. |

Notes:

- Use this optional table only if it supports your chosen question.
- No card numbers, expiry dates, or security codes are included.
- Cutoff status does not describe status at the historical purchase time; an inactive card can have valid earlier purchases.
- Check purchase-card ownership using `payment_source_id` and `user_id`; joining transactions to all of a user's cards would multiply purchases.

### `experiment_exposure.csv`

One allocation per user.

| Column | Type | Meaning |
|---|---|---|
| `user_id` | String | Eligible non-member allocated to the invitation experiment. |
| `experiment_id` | String | `vip_invitation_v1`, the only experiment. |
| `variant` | String | `control` (no invitation) or `invitation` (assigned a VIP invitation). Not actual membership. |
| `exposure_timestamp` | Timestamp | Randomised assignment/start time for either group; not observed interaction or VIP signup. |

Notes:

- The brief describes eligibility, randomisation, and waves.
- Allocation applies across all cards and merchants.
- Control users can join organically; invited users can decline.
- Use `vip_enrolled_at` when assessing behaviour before and after membership.
- Users outside the trial can also be VIP members.
- Purchases or signups after cutoff are unobserved.
- No invitation interaction events or block identifiers are supplied.

## Join map

```text
transactions.user_id           -> users.user_id
transactions.merchant_id       -> merchants.merchant_id
transactions.payment_source_id -> cards.payment_source_id
merchants.merchant_mcc_code    -> mcc.merchant_mcc_code
cards.user_id                  -> users.user_id
experiment_exposure.user_id    -> users.user_id
```

- Preserve transaction grain (`transaction_id`) when joining.
- Join transactions to cards on `payment_source_id`, not `user_id`; the latter fans out rows.
- `merchants.merchant_mcc_code` can be null; missing means unclassified.

## Observed profile

- **Transactions:** 350,567 rows from `2025-01-01 00:15:00` to `2025-12-31 23:58:00`; zero critical nulls; all values in NOK; 301,044 `in_person` and 49,523 `online`.
- **Users:** 419 unique users; `observation_start_date` from `2025-01-01` to `2025-11-26`; 195 VIP and 224 non-VIP; 224 null `vip_enrolled_at`; 266 Norway and 153 Denmark.
- **Merchants:** 30 unique merchants; one missing MCC.
- **Cards:** 1,203 unique payment sources; no missing `card_status`.
- **Experiment:** 269 unique users; 134 control and 135 invitation; exposure from `2025-07-01` to `2025-12-27`.
- **MCC:** 6 categories.

Critical nulls for transactions are nulls in `transaction_id`, `user_id`, `merchant_id`, `payment_source_id`, `transaction_timestamp`, `volume_nok`, or `revenue_nok`.

## Machine-readable model

[`semantic/model.yml`](../semantic/model.yml) defines table grain, keys, joins, column metadata, enums, metrics, and caveats for SQL analysis.

The rendered entity-relationship diagram is in
[`semantic/erd.md`](../semantic/erd.md). Open the local viewer with `make model`.

```bash
make semantic-check  # validate the model against the raw CSVs
make db              # build data/processed/vipps.duckdb with one view per table
make model           # open the data model viewer
```

## Processing

1. Keep `data/raw/` unchanged.
2. Clean and transform in `notebooks/case_analysis.py` or `notebooks/utils/`.
3. Write the analysis-ready CSV(s) the notebook needs to `notebooks/public/`.
4. Load each file with `mo.notebook_location() / "public" / "<file>.csv"` so it works locally and in WebAssembly.

## Privacy

The dataset is synthetic and uses fictional merchants. No card numbers, expiry
dates, or security codes are included. Confirm permission with the case provider
before publishing raw files. Do not add real customer data, PII, credentials, or
confidential fields.
