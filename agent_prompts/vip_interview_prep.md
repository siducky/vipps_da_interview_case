
# VIP Experiment Analysis — Interview Preparation

## 1. Exact Formulas Behind Each Slide

Use this section to explain how each metric, chart, and statistical test was calculated.

### Slide 3: Channel Shares and Take Rate

**Dataset:** Full-year observations only, filtered to `is_full_year_obs == True`.

- Observation start date: `2025-01-01` or earlier
- Users: 373
- Purchases: 344,318

#### Purchases Share

$$
\text{Purchases Share}_c =
\frac{\text{Count of transactions in channel }c}
{\text{Total transaction count}}
$$

- In-person: 85.8%
- Online: 14.2%

#### GMV Share

$$
\text{GMV Share}_c =
\frac{\sum \text{volume\_nok}_c}
{\sum \text{volume\_nok}}
$$

- In-person: 69.3%
- Online: 30.7%

#### Revenue Share

$$
\text{Revenue Share}_c =
\frac{\sum \text{revenue\_nok}_c}
{\sum \text{revenue\_nok}}
$$

- In-person: 59.9%
- Online: 40.1%

#### Take Rate

$$
\text{Take Rate}_c =
\frac{\sum \text{revenue\_nok}_c}
{\sum \text{volume\_nok}_c}
$$

- In-person: 1.29%
- Online: 1.95%

**Interpretation:** Online transactions represent a smaller share of purchases but generate a disproportionately large share of GMV and revenue. The higher online take rate indicates that online transactions generate more revenue per NOK of transaction volume.

---

### Slide 4: Churn Cliff Curve

**Dataset:** `df_silence_curve`

For each user, sort all 2025 transaction timestamps:

$$
t_1 < t_2 < \dots < t_k
$$

#### Step 1: Calculate Silence Spells

**Completed spells:** The user returned after the silence period.

$$
\text{silence\_days}_i =
(t_{i+1} - t_i).\text{days}
$$

These spells have `returned = True`.

**Right-censored spells:** The user did not return before the end of 2025.

$$
\text{silence\_days} =
(\text{2026-01-01} - t_k).\text{days}
$$

These spells have `returned = False`.

#### Step 2: Calculate the No-Return Share

For every threshold \(X\) from 1 to 35 days, filter to spells with at least \(X\) days of silence.

$$
\text{No-Return Share}(X) =
\frac{
\text{Count of spells with returned = False and silence\_days} \geq X
}{
\text{Count of all spells with silence\_days} \geq X
}
$$

**Interpretation:** The curve estimates the share of observed silence spells that had not ended in a return by the end of the observation period.

---

### Slide 5: Weekly Pre-Launch vs. Full-Year Rates

**Dataset:** 373 full-year users.

- VIPs: 189
- Never-VIPs: 184

#### Jan–Apr Weekly Rate

For each user:

$$
\text{Weekly Rate}_{Jan-Apr} =
\frac{
\text{Total purchases from Jan 1 to Apr 30}
}{
120/7
}
$$

The observation period contains 120 days, or approximately 17.143 weeks.

The same calculation is applied to NOK volume.

#### Full-Year Weekly Rate

$$
\text{Weekly Rate}_{2025} =
\frac{
\text{Total purchases during 2025}
}{
365/7
}
$$

The observation period contains 365 days, or approximately 52.143 weeks.

The same calculation is applied to NOK volume.

#### Statistical Test

A two-sample Welch's t-test is used:

```python
scipy.stats.ttest_ind(group_vip, group_never_vip, equal_var=False)
```

**Why Welch's t-test?**

It compares the means of two independent groups without assuming equal population variances.

---

### Slide 6: Within-User Event Study

**Dataset:** `df_weekly_panel`

The analysis compares users' purchasing behavior before and after VIP enrollment.

#### Step 1: Construct the Weekly Panel

- Anchor weeks on Monday using `date_trunc('week', timestamp)`.
- Create a balanced user-week grid.
- Fill weeks with no purchases using `COALESCE(..., 0)`.

#### Step 2: Calculate Relative Week

$$
\text{rel\_week\_to\_vip} =
\left\lfloor
\frac{
\text{week\_start} -
\text{week\_start}(\text{vip\_enrolled\_at})
}{
7
}
\right\rfloor
$$

#### Step 3: Select Users

Include only full-year VIPs with all \(2W+1\) weeks observed inside the event window:

$$
[-W, +W]
$$

At \(W=8\), the sample contains 177 users.

#### Step 4: Calculate Pre- and Post-Enrollment Averages

For each user \(i\):

$$
\bar{Y}_{i,\text{pre}} =
\frac{1}{W}
\sum_{w=-W}^{-1} Y_{i,w}
$$

$$
\bar{Y}_{i,\text{post}} =
\frac{1}{W}
\sum_{w=1}^{W} Y_{i,w}
$$

Week 0 is excluded because enrollment occurs during the week.

#### Step 5: Test the Difference

Use a paired t-test on the 177 user-level pre- and post-enrollment averages:

```python
scipy.stats.ttest_rel(post_user_means, pre_user_means)
```

**Interpretation:** This measures the average within-user change around enrollment. It does not, by itself, establish that VIP enrollment caused the change.

---

### Slide 7: Signup Lift and Pooled Z-Test

#### Signup Definitions

**Ever enrolled after exposure:**

```python
vip_enrolled == True
and vip_enrolled_at >= exposure_timestamp
```

**Enrolled within 14 days:**

```python
exposure_timestamp <= vip_enrolled_at
< exposure_timestamp + 14 days
```

#### Two-Proportion Pooled Z-Test

Let:

- \(x_{inv}\): Number of invited users who enrolled
- \(x_{ctl}\): Number of control users who enrolled
- \(n_{inv}\): Number of invited users
- \(n_{ctl}\): Number of control users

The pooled proportion is:

$$
\hat{p} =
\frac{x_{inv}+x_{ctl}}
{n_{inv}+n_{ctl}}
$$

The standard error is:

$$
SE =
\sqrt{
\hat{p}(1-\hat{p})
\left(
\frac{1}{n_{inv}}+\frac{1}{n_{ctl}}
\right)
}
$$

The z-statistic is:

$$
z =
\frac{
\hat{p}_{inv}-\hat{p}_{ctl}
}{
SE
}
$$

**Interpretation:** The test evaluates whether the invitation and control groups have statistically different signup rates.

---

### Slide 8: Experiment Forest Plot and Complier Scaling

**Dataset:** Summer experiment wave.

- Exposure date: Before September 1, 2025
- Total users: 226
- Invitation group: 113
- Control group: 113

Each user is measured over their exact individual observation window:

$$
[t_{\text{exposure}},
t_{\text{exposure}} + 7W\text{ days})
$$

Inactive weeks are counted as zero.

#### Intention-to-Treat (ITT) Difference

$$
\Delta\% =
\frac{
\bar{Y}_{inv}-\bar{Y}_{ctl}
}{
\bar{Y}_{ctl}
}
\times 100
$$

#### Standard Error

$$
SE =
\sqrt{
\frac{s^2_{inv}}{n_{inv}}
+
\frac{s^2_{ctl}}{n_{ctl}}
}
$$

#### 95% Confidence Interval

$$
CI_{95\%} =
\frac{
(\bar{Y}_{inv}-\bar{Y}_{ctl})
\pm 1.96 \cdot SE
}{
\bar{Y}_{ctl}
}
\times 100
$$

#### Complier Scaling

When the scaling option is enabled, divide the ITT estimate and confidence interval by the net first-stage signup lift.

$$
\text{First-stage lift} =
0.6814-0.0796=0.6018
$$

$$
\text{Scaling factor} =
\frac{1}{0.6018}
\approx 1.66
$$

**Interpretation:** The scaled estimate represents an approximate effect among users induced to enroll by the invitation, under the assumptions required for instrumental-variable interpretation.

---

### Slide 9: Cross-Sell Calculator

#### Extra Purchases per Year

$$
\text{Extra Purchases/year} =
195 \times 12 \times X
$$

Where \(X\) is the slider value.

At \(X=1.0\):

$$
195 \times 12 = 2,340
$$

#### Incremental GMV

$$
\text{Incremental GMV} =
\text{Extra Purchases/year}
\times 1,008\text{ NOK}
$$

At \(X=1.0\):

$$
2,340 \times 1,008 =
2,359,799\text{ NOK}
$$

#### Gross Fee Revenue

$$
\text{Gross Fee Revenue} =
\text{Incremental GMV}
\times 1.9504\%
$$

At the default setting:

$$
\text{Gross Fee Revenue}
=46,025\text{ NOK}
$$

#### Point Cost

$$
\text{Point Cost} =
\text{Incremental GMV}
\times
\frac{\text{bps}_{slider}}{10,000}
$$

At 50 basis points:

$$
\text{Point Cost}=11,799\text{ NOK}
$$

#### Net Revenue

$$
\text{Net Revenue} =
\text{Gross Fee Revenue}
-
\text{Point Cost}
$$

At the default setting:

$$
46,025-11,799=34,226\text{ NOK}
$$

---

## 2. Why We Chose Each Metric

If stakeholders ask why these metrics were chosen to measure "keep coming back," use the following structured explanation.

### 1. Why Retained in the Last 28 Days?

**Metric:** Survival / recent retention.

Approximately 29% of users experience hard churn: they stop buying completely and never return before December 31.

A user who averages 20 purchases per week in July and August but then churns in October could still look healthy on a 16-week average.

A year-end survival check is therefore necessary.

We chose 28 days because it represents a balanced four-week cycle.

We also verified that the result was insensitive to the retention window:

| Retention window | Retained users |
|---|---:|
| 7 days | 297 |
| 14 days | 297 |
| 28 days | 299 |

### 2. Why Separate In-Person and Online Activity?

**Metrics:**
- In-person Active Week Share
- Online Active Month Share (28-day)

Customer purchasing cadence differs by channel.

- In-person purchases account for 85.8% of transactions and are largely driven by weekly grocery shopping.
- Online purchases account for 14.2% and often involve less frequent purchases such as clothing, furniture, and electronics.

Measuring online activity at a weekly grain would artificially penalize normal monthly online shoppers.

### 3. Why Purchases per Week and GMV per Week?

We include inactive weeks as zero.

This captures total customer value over the entire 16-week observation window without conditioning on survival.

Calculating averages only over active weeks would create survivorship bias because it would exclude periods when users stopped purchasing.

### 4. Why Reject Median Inter-Purchase Gap and Dual-Channel Activity?

We tested both metrics and found ceiling effects.

**Median inter-purchase gap:**

Active users purchase multiple times per day, with a median gap of approximately 0.20 days in both experiment arms.

**Dual-channel activity:**

Over 16 weeks, 100% of active users made at least one in-person and one online purchase.

Both metrics have little or no variation, making them unable to detect meaningful treatment effects.

---

## 3. Top Stakeholder Questions and Answers

### Q1. "Slide 6 shows VIPs increased purchases by +8.4% after joining, but Slide 8 shows the experiment had no significant effect. Which one is true?"

**Answer:**

"Both are true, and Slide 6 actually helps explain why.

When I filter Slide 6 to organic joiners (N=90), their GMV increased by 8.0%, with a p-value of 0.006.

When I filter to invited experiment joiners (N=77), their GMV change was only +1.8%, with a p-value of 0.638.

People who seek out VIP themselves may enroll when their shopping needs are already increasing. This is self-selection in enrollment timing.

Passively inviting users through an experiment does not necessarily change their underlying shopping habits."

### Q2. "Why did you exclude the 43 December experiment users on Slide 8?"

**Answer:**

"Their exposure timestamps fall between December 14 and December 26, while our dataset ends at January 1, 2026.

They therefore have only 5–17 days of post-exposure data.

Every Summer wave user (N=226) has at least 16 full weeks, or 112 days, of post-exposure data.

Mixing five-day observation windows with 112-day windows would distort retention and purchasing comparisons.

We can still evaluate the December wave's 14-day signup lift on Slide 7, which was +54.1 percentage points."

### Q3. "Why did you exclude Week 0 from the Before/After table on Slide 6?"

**Answer:**

"Week 0 is the calendar week in which the user enrolled in VIP.

Part of that week occurs before enrollment and part after it. Users also often enroll during checkout.

Comparing Weeks -8 to -1 against Weeks +1 to +8 gives us a cleaner pre- versus post-enrollment comparison."

### Q4. "Could the experiment just be underpowered to detect a small effect?"

**Answer:**

"Yes. That is why we show the 95% confidence intervals on Slide 8.

With 113 users per arm in the Summer wave:

- Weekly purchases: -3.0% to +12.3%
- GMV: -8.7% to +7.8%

The experiment provides evidence against a large positive lift, but it cannot rule out smaller effects.

We would need a larger sample size to reliably detect a 2–4% lift."

### Q5. "Should we shut down VIP or stop sending invitations?"

**Answer:**

"I would not shut down invitations.

They cost very little and convert 68% of invited users into VIPs within two weeks.

However, we should stop expecting a one-time signup invitation to drive retention on its own.

Instead, I would combine VIP membership with:

1. 14-day inactivity triggers.
2. Online checkout point multipliers.
3. Logging point redemptions and reward costs so we can measure net margin.

This would allow us to move from simply increasing enrollment to actively driving repeat purchases and measuring the profitability of those interventions."

