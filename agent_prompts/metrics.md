
### Part 1: The 3 Definitions of "Keep Coming Back" (In Plain English)

Why do we need 3 definitions instead of 1? Because in our dataset, people use the payment service in two totally different ways:

- **In-person (~86% of transactions):** Mostly grocery stores and food shops. People buy groceries **every week**.
- **Online (~14% of transactions):** Clothing, electronics, books, and furniture. People do **not** buy a sofa or a laptop every week. They buy online **once every few weeks or months**, but those purchases bring in higher fee percentages (`revenue_nok`) for us.

If we only measure "Did the user buy something every week?", online shoppers will look "inactive" even when they are loyal.

Here are the 3 ways to define "keep coming back," each capturing a different behavior.

---

#### Definition 1: Consistency ("How regularly do they show up?")

- **The Metric:** **Active Period Share** — out of the 16 weeks after the experiment started, in what percentage of weeks (or months) did the user make at least 1 payment?

- **Concrete Example:**
  - User A buys one huge 10,000 NOK TV in July and never uses the app again (active in **1 out of 16 weeks = 6%**).
  - User B buys groceries every single week (active in **16 out of 16 weeks = 100%**).

- **Online vs. In-Person:**
  - **In-Person:** Check whether users are active every week, because people buy groceries weekly.
  - **Online:** Check whether users are active every month (e.g., active in 4 out of 4 months after July), because buying online once a month is already great habit consistency.

- **Why the PM Cares:** It tells us if VIP turns our app into a **routine habit** rather than a one-off tool.

---

#### Definition 2: Speed & Survival ("Are they coming back faster, and are they still alive at year-end?")

- **The Metric:** **Days Between Purchases** + **Still Active in December (Last 28 Days)**

- **Concrete Example:**
  - Since nobody formally "cancels" a free payment app, users churn **silently**. Their gap between purchases gets longer and longer until they stop.
  - If a user normally pays with us every 6 days, and after joining VIP they pay every 4 days, they are coming back faster.
  - If they made a purchase in the last 28 days of the year (December), we know they haven't silently quit.

- **Online vs. In-Person:**
  - **In-Person:** Drives the short day-to-day gap (3–5 days).
  - **Online:** Gaps are naturally longer (15–30 days), so we look at whether VIP shrinks the gap between online orders.

- **Why the PM Cares:** This is the truest measure of **preventing silent churn**.

---

#### Definition 3: Cross-Channel Expansion ("Do in-store shoppers start using us online?")

- **The Metric:** **Dual-Channel Usage Rate** (% of users who use us *both* in-person and online) & **Weekly Revenue (`revenue_nok`)**

- **Concrete Example:**
  - Suppose a user already uses our app at the grocery store (`in_person`).
  - When they join VIP and start earning points in-store, do they start picking our payment button when shopping for clothes or electronics online?

- **Online vs. In-Person:**
  - **In-Person:** Grocery stores build the daily habit.
  - **Online:** Non-food retailers typically have higher merchant fee percentages (`revenue_nok / volume_nok`).

- **Why the PM Cares:** It connects "keep coming back" directly to **how the business makes money (`revenue_nok`)**.

---

> **What to recommend in your presentation:**
>
> Use **Definition 1 (Weekly/Monthly Consistency)** as the headline retention metric, supported by:
>
> 1. **Definition 2 (Active in Last 28 Days):** To check for silent churn.
> 2. **Definition 3 (In-Person vs. Online Split):** To see where the revenue comes from.

---

### Part 2: How to Answer the PM's 3 Questions

Here is the exact blueprint for how we answer each of the PM's three questions in your 20-minute presentation.

---

#### Question 1: "Do people who join VIP buy more, the same, or less?"

**The Trap to Avoid:**

You **cannot** simply compare average 2025 spend of VIP members (`vip_enrolled = True`) vs. non-members (`vip_enrolled = False`).

Why?

- Frequent shoppers naturally see the VIP prompt more often and sign up more (**selection bias**).
- `vip_enrolled` is recorded at the end of the year, so comparing full-year totals mixes together purchases made *before* and *after* they joined.

**How We Answer It (2-Step Proof):**

1. **First, show the "Naive vs. Real" contrast:**
   - Show that VIP members *are* heavier shoppers overall. They were already buying more **before** they ever joined VIP.

2. **Second, run a "Before vs. After" (Event Study) on the same users:**
   - Line up every VIP member at the exact week they signed up (`vip_enrolled_at` = Week 0).
   - Compare their average weekly purchases, spend (`volume_nok`), and revenue (`revenue_nok`) in the **12 weeks BEFORE joining** vs. the **12 weeks AFTER joining**.
   - Compare that trend against non-members over the same calendar period, filtering to users observed since January 1 so data coverage is fair.
   - Break that "Before vs. After" change down into **In-Person** vs. **Online** to show *where* any change in buying happens.

---

#### Question 2: "Does inviting people to join help them keep using us?"

**The Setup:**

Use `experiment_exposure.csv` (269 users who were non-members in June and randomly split 50/50 into `invitation` vs. `control`).

- **Crucial Adjustment:** Separate the experiment into two waves:
  - **Summer Wave:** July exposure — plenty of time to observe whether they "keep using us" through December.
  - **December Wave:** Exposed right before year-end — too little time left in the year to measure retention.

**How We Answer It (3-Step Funnel):**

1. **Step A — Did the invitation actually get people to join VIP? (First Stage)**
   - Compare what percentage of the `invitation` group joined VIP after being assigned vs. what percentage of the `control` group joined on their own organically.
   - Also check if invited users joined *sooner* (fewer days to sign up) than control users.

2. **Step B — Did the Invited Group Keep Using Us More Than Control? (Intent-to-Treat / ITT)**
   - Compare the entire `invitation` group vs. the entire `control` group (Summer Wave) over the post-exposure months using the 3 retention definitions:
     - Active Weeks
     - Active in Last 28 Days
     - Weekly Spend/Revenue
   - **Senior Analyst Touch:** Control for each user's **June purchase frequency**, since the experiment was randomized within blocks of June frequency. This removes baseline noise and makes your statistical test much sharper.

3. **Step C — Why Did (or Didn't) the Invitation Move the Needle? (Dilution / LATE)**
   - Explain to the PM that an invitation only changes behavior *if* it causes someone to join VIP who wouldn't have joined otherwise.
   - If many `invitation` users ignored the invite, and many `control` users signed up organically anyway, the difference between the two groups gets diluted.
   - Scaling the effect by the net signup difference (the **Wald / LATE estimate**) tells us the impact on the subset of users who actually joined *because* of the invite.

---

#### Question 3: "What should we do next?"

Because we are missing **3 critical pieces of data** (invitation open/click tracking, points redemption, and loyalty cost per point), your recommendation should combine **immediate product actions** with **what to measure next before scaling spend**.

1. **Fix & Instrument the Invitation Funnel (Acquisition)**
   - **Current Limitation:** Right now, we only know someone was *assigned* an invitation (`exposure_timestamp`), not whether they received, opened, or clicked it.
   - **Action:** Log invitation delivery/open/click events, and test **in-flow checkout nudges** (prompting users right after a payment, when engagement is 100%) instead of a one-time batch invite.

2. **Use VIP to Bridge In-Person Users to Online Checkout (Engagement & Margin)**
   - **Current Insight:** In-person grocery transactions are 86% of volume, while online transactions drive retail expansion and distinct merchant fee rates (`revenue_nok`).
   - **Action:** Test targeted VIP point bonuses (e.g., *"2x points on your first online purchase"*) to convert habitual in-store grocery users into higher-margin online shoppers.

3. **Establish a Unit Economics Gate Before Scaling (Profitability)**
   - **Current Limitation:** Currently we observe gross fee revenue (`revenue_nok`), not net profit after point costs.
   - **Action:** Partner with Finance/PM to plug in the **cost per point issued and expected redemption rate**.
   - **Break-Even Threshold:**

     \[
     \text{Incremental Revenue per VIP} > \text{Points Liability Cost per VIP}
     \]

     Only roll out aggressive signup incentives once this threshold is met.

4. **Re-evaluate the December Wave in Q1 2026**
   - **Current Limitation:** Since our data cuts off on `2026-01-01`, the December experiment wave is censored.
   - **Action:** Schedule a follow-up pull in March 2026, once those users have 12+ weeks of post-invitation history.

