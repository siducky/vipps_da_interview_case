# Plot exports

Generated from `notebooks/vip_presentation.py` with
`uv run --with vl-convert-python python scripts/export_plots.py`.

Each folder groups the charts for one business question.

## `01_context`
Product and data context: channel mix and the churn cliff.

- `01_channel_mix_shares.png` - Channel mix by selected population
- `02_churn_cliff.png` - The churn cliff
  Share of inter-purchase silences reaching a threshold that never return before the 2026-01-01 cutoff, as the threshold grows.

## `02_q1_vip_selection`
Question 1: do VIP joiners buy more? The within-user event study around VIP enrollment.

- `01_event_study_weekly_purchases.png` - Weekly purchases around enrollment
  Lines show only the VIP members with a complete +/-8 week window; no synthetic comparison group is plotted.
- `02_event_study_weekly_gmv.png` - Weekly GMV around enrollment
  Lines show only the VIP members with a complete +/-8 week window; no synthetic comparison group is plotted.

## `03_q2_invitation_experiment`
Question 2: does inviting people help them keep using us? Take-up, cumulative enrollment and ITT effect estimates.

- `01_enrollment_rate_by_arm.png` - Enrollment rate by experiment arm
- `02_cumulative_enrollment.png` - Cumulative enrollment over time
- `03_effect_forest_itt.png` - Invitation vs. control · 16-week window
  Points are % lift versus the control mean; horizontal bars are 95% confidence intervals; the dashed line is zero.

## `04_q3_next_steps`
Question 3: what should the team do next? Channel economics and where the revenue opportunity sits.

- `01_gmv_share_by_sector.png` - GMV share by sector

## `05_summary_statistics`
Descriptive summary statistics from the analysis notebook: transaction trend, active users, purchase values and age mix.

- `01_monthly_gmv_and_aov.png` - Monthly GMV and average order value
- `02_monthly_active_users.png` - Monthly active users (MAU)
- `03_purchase_value_distribution.png` - Purchase value distribution
- `04_users_by_age_bucket.png` - Users by age bucket
