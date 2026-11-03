# Understanding Inactivity, Churn, and Retention

## 1. What the Data Actually Shows About Silence Gaps

Across all 350,567 purchases in 2025:

- **50% (Median):** Repeat purchases happen within 0.17 days (~4 hours).
- **95%:** Repeat purchases happen within 1.0 day.
- **99%:** Repeat purchases happen within 2.0 days.
- **99.9%:** Normal repeat purchases happen within 4.2 days.

### What Happens When a User Goes Silent?

The following table shows what happens when a user goes silent for 3, 5, 7, 14, or 28+ days.

| Days of Silence | How Many Times This Happens in 2025 | % Where User Eventually Comes Back | % Where User Never Returns (Permanent Churn) | What Is Happening Behaviorally |
|---|---:|---:|---:|---|
| $\geq 3$ days | 1,197 times | 89.6% (1,073) | 10.4% (124) | **False alarm:** Mostly normal long-weekend gaps; 9 out of 10 come right back on Day 3 or 4. |
| $\geq 5$ days | 356 times | 65.7% (234) | 34.3% (122) | **The cliff starts:** Normal daily habit is broken; 1 in 3 never return. |
| $\geq 7$ days | 287 times | 57.5% (165) | 42.5% (122) | **Missed a full weekly grocery cycle:** Almost half of these silences are permanent churn. |
| $\geq 14$ days | 271 times | 55.0% (149) | 45.0% (122) | **Confirmed lapse:** Only 16 users returned between Day 7 and Day 14! Everyone else is either in a 2–3 month hiatus or gone forever. |
| $\geq 28$ days | 264 times | 54.5% (144) | 45.5% (120) | Almost identical to 14 days (only 7 users came back between Day 14 and Day 28). |

## 2. Why Not 5 Days or 30 Days for an Anti-Churn Trigger?

If the interviewer asks, "Why did you say 7–14 days for an inactivity nudge instead of 3 days or 30 days?", you now have a textbook data-backed answer.

### Why Not 3 Days?

At 3 days of silence, 90% of users come back on their own within the next day or two. Nudging at 3 days would spam loyal users and waste money on people who aren't churning.

### Why 5 to 14 Days Is the "Sweet Spot"

Because 99.9% of normal repeat purchases happen within 4.2 days.

Once a user hits 7 to 14 days without a purchase, they have missed 1–2 full weekly grocery cycles, and their chance of never coming back jumps to ~45%.

### Why 30 Days Is Too Late

Look at the table above: between Day 14 (271 silences) and Day 28 (264 silences), almost nobody returns (7 people).

If a user hasn't bought by Day 14, waiting until Day 30 just lets the habit go cold.

## 3. Why Did We Use "Active in Last 28 Days" for Year-End Survival?

There are two reasons: one product convention and one empirical check.

### 3.1 Product Analytics Convention (28 Days = 4 Full Weeks)

In consumer fintech, 28 days (Monthly Active User / MAU) is the standard retention window because it contains exactly 4 Mondays, 4 Fridays, 4 Saturdays, and 4 Sundays (unlike 30 or 31 days), and it aligns with monthly paydays and monthly online shopping cycles.

### 3.2 Empirical Sensitivity Check (7d vs. 14d vs. 28d Gives the Exact Same Answer!)

Look at how many of our 419 users were active at the end of 2025 under different windows:

| Activity Window | Active Users | Percentage |
|---|---:|---:|
| Active in last 7 days of the year | 297 / 419 | 70.9% |
| Active in last 14 days of the year | 297 / 419 | 70.9% |
| Active in last 28 days of the year | 299 / 419 | 71.4% |

Because active users buy almost every day, only 2 users in the entire dataset bought something in early December (last 28 days) and then stopped before the last 7 days!

### What to Tell the Interviewer

> "We chose 28 days because it is the standard 4-week MAU definition and captures monthly online shoppers—and we checked sensitivity at 7 days and 14 days, which give the exact same result (297 vs. 299 active users)."

That one sentence will immediately impress a senior analytics interviewer.
