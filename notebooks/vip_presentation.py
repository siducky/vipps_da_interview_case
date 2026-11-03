import marimo

__generated_with = "0.25.2"
app = marimo.App(
    width="medium",
    layout_file="layouts/vip_presentation.slides.json",
)

with app.setup(hide_code=True):
    import math
    import warnings

    import altair as alt
    import duckdb
    import marimo as mo
    import numpy as np
    import pandas as pd
    from scipy import stats

    _ROOT = (mo.notebook_location() / "..").resolve()
    RAW_DIR = _ROOT / "data" / "raw"
    PROCESSED_DIR = _ROOT / "data" / "processed"

    ORANGE = "#FF5B24"
    NAVY = "#0B1F3A"
    BLUE = "#2F6DB3"
    GREY = "#8C8C8C"

    # Single source of truth for the deck's repository link.
    REPO_URL = "https://github.com/siducky/vipps_da_interview_case"

    VIPPS_CSS = """
    <style>
    .reveal-viewport {
        background-color: #FFFAF7;
    }

    .reveal h1,
    .reveal h2,
    .reveal h3 {
        color: #0B1F3A;
        font-weight: 700;
    }

    .reveal strong {
        color: #FF5B24;
    }

    .reveal a {
        color: #FF5B24;
    }

    .reveal .progress {
        color: #FF5B24;
    }

    </style>
    """

    mo.Html(VIPPS_CSS)

    def orange(value):
        return f'<span style="color: {ORANGE}; font-weight: 700;">{value}</span>'

    def vipps_slide(content):
        return mo.vstack(
            [
                mo.md(
                    f"""
                    <div style="
                        background-color: {ORANGE};
                        height: 8px;
                        width: 100%;
                        border-radius: 4px;
                    "></div>
                    """
                ),
                content,
            ],
            gap=1,
            align="stretch",
        )

    _SPECS = {
        "transactions": {
            "dtype": {
                "transaction_id": "string",
                "user_id": "string",
                "merchant_id": "string",
                "payment_source_id": "string",
                "currency": "string",
                "user_country": "string",
                "payment_channel": "string",
            },
            "parse_dates": ["transaction_timestamp"],
        },
        "users": {
            "dtype": {
                "user_id": "string",
                "vip_enrolled": "boolean",
                "user_country": "string",
                "age_bucket": "string",
            },
            "parse_dates": ["observation_start_date", "vip_enrolled_at"],
        },
        "merchants": {
            "dtype": {
                "merchant_id": "string",
                "merchant_name": "string",
                "merchant_country": "string",
                "merchant_mcc_code": "string",
            },
        },
        "mcc": {
            "dtype": {
                "merchant_mcc_code": "string",
                "category_name": "string",
            },
        },
        "experiment_exposure": {
            "dtype": {
                "user_id": "string",
                "experiment_id": "string",
                "variant": "string",
            },
            "parse_dates": ["exposure_timestamp"],
        },
    }

    def _read(_table):
        return pd.read_csv(RAW_DIR / f"{_table}.csv", **_SPECS[_table])

    transactions = _read("transactions")
    users = _read("users")
    merchants = _read("merchants")
    mcc = _read("mcc")
    experiment_exposure = _read("experiment_exposure")

    def _build_marts(transactions, users, merchants, mcc, experiment_exposure):
        _processed_dir = (
            mo.notebook_location() / ".." / "data" / "processed"
        ).resolve()
        _processed_dir.mkdir(parents=True, exist_ok=True)

        _con = duckdb.connect(":memory:")
        _con.register("transactions", transactions)
        _con.register("users", users)
        _con.register("merchants", merchants)
        _con.register("mcc", mcc)
        _con.register("experiment_exposure", experiment_exposure)

        _USER_SPINE_SQL = """
        WITH exp AS (
            SELECT
                user_id,
                variant,
                exposure_timestamp,
                CASE
                    WHEN exposure_timestamp < TIMESTAMP '2025-09-01' THEN 'summer'
                    WHEN exposure_timestamp >= TIMESTAMP '2025-11-01' THEN 'december'
                    ELSE 'unassigned'
                END AS experiment_wave
            FROM experiment_exposure
        ),
        tx AS (
            SELECT
                user_id,
                COUNT(*) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2025-05-01'
                ) AS pre_may_tx,
                SUM(volume_nok) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2025-05-01'
                ) AS pre_may_gmv,
                COUNT(*) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-06-01'
                      AND transaction_timestamp < TIMESTAMP '2025-07-01'
                ) AS june_tx,
                SUM(volume_nok) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-06-01'
                      AND transaction_timestamp < TIMESTAMP '2025-07-01'
                ) AS june_gmv,
                COUNT(*) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2025-07-01'
                ) AS h1_tx
            FROM transactions
            GROUP BY user_id
        )
        SELECT
            u.user_id,
            u.user_country,
            u.age_bucket,
            CAST(u.observation_start_date AS DATE) AS observation_start_date,
            (u.observation_start_date <= TIMESTAMP '2025-01-01') AS is_full_year_obs,
            date_diff(
                'day',
                CAST(u.observation_start_date AS DATE),
                DATE '2026-01-01'
            ) AS observable_days,
            u.vip_enrolled,
            u.vip_enrolled_at,
            CASE
                WHEN NOT u.vip_enrolled THEN 'never_vip'
                WHEN u.vip_enrolled_at < TIMESTAMP '2025-07-01' THEN 'pre_exp_organic'
                WHEN e.variant = 'invitation'
                 AND u.vip_enrolled_at >= e.exposure_timestamp
                    THEN 'exp_invitation_joiner'
                WHEN e.variant = 'control'
                 AND u.vip_enrolled_at >= e.exposure_timestamp
                    THEN 'exp_control_joiner'
                WHEN e.user_id IS NULL
                 AND u.vip_enrolled_at >= TIMESTAMP '2025-07-01'
                    THEN 'non_exp_late_organic'
                ELSE 'non_exp_late_organic'
            END AS vip_cohort,
            COALESCE(e.variant, 'unassigned') AS experiment_variant,
            e.exposure_timestamp,
            COALESCE(e.experiment_wave, 'unassigned') AS experiment_wave,
            COALESCE(t.pre_may_tx, 0) / (120.0 / 7.0) AS pre_may_tx_per_week,
            COALESCE(t.pre_may_gmv, 0) / (120.0 / 7.0) AS pre_may_gmv_per_week,
            COALESCE(t.june_tx, 0) AS june_tx_count,
            COALESCE(t.june_gmv, 0) AS june_gmv_nok,
            COALESCE(t.h1_tx, 0) / (181.0 / 7.0) AS h1_tx_per_week
        FROM users u
        LEFT JOIN exp e USING (user_id)
        LEFT JOIN tx t USING (user_id)
        ORDER BY u.user_id
        """
        df_user_spine = _con.execute(_USER_SPINE_SQL).df()
        _con.register("user_spine", df_user_spine)

        _EXP_EVAL_SQL = """
        WITH base AS (
            SELECT
                e.user_id,
                e.variant,
                e.exposure_timestamp,
                CAST(e.exposure_timestamp AS DATE) AS exposure_date,
                CAST(u.observation_start_date AS DATE) AS observation_start_date,
                u.vip_enrolled,
                u.vip_enrolled_at
            FROM experiment_exposure e
            JOIN users u USING (user_id)
        ),
        pre AS (
            SELECT
                b.user_id,
                COUNT(t.transaction_id) AS pre_tx_count,
                COALESCE(SUM(t.volume_nok), 0) AS pre_gmv,
                COALESCE(SUM(t.revenue_nok), 0) AS pre_rev,
                COUNT(t.transaction_id) FILTER (
                    WHERE t.payment_channel = 'online'
                ) AS pre_online_tx
            FROM base b
            LEFT JOIN transactions t
              ON t.user_id = b.user_id
             AND t.transaction_timestamp < b.exposure_timestamp
            GROUP BY b.user_id
        ),
        june AS (
            SELECT
                b.user_id,
                COUNT(t.transaction_id) AS june_tx_count
            FROM base b
            LEFT JOIN transactions t
              ON t.user_id = b.user_id
             AND t.transaction_timestamp >= TIMESTAMP '2025-06-01'
             AND t.transaction_timestamp < TIMESTAMP '2025-07-01'
            GROUP BY b.user_id
        ),
        post16 AS (
            SELECT
                b.user_id,
                COUNT(*) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                ) AS post_tx_16w,
                COALESCE(SUM(t.volume_nok) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                ), 0) AS post_gmv_16w,
                COALESCE(SUM(t.revenue_nok) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                ), 0) AS post_rev_16w,
                COUNT(*) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                      AND t.payment_channel = 'in_person'
                ) AS post_in_person_tx_16w,
                COUNT(*) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                      AND t.payment_channel = 'online'
                ) AS post_online_tx_16w,
                COUNT(DISTINCT floor(
                    date_diff(
                        'day',
                        b.exposure_date,
                        CAST(t.transaction_timestamp AS DATE)
                    ) / 7
                )) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                ) AS active_weeks_16w,
                COUNT(DISTINCT floor(
                    date_diff(
                        'day',
                        b.exposure_date,
                        CAST(t.transaction_timestamp AS DATE)
                    ) / 7
                )) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                      AND t.payment_channel = 'in_person'
                ) AS in_person_active_weeks_16w,
                COUNT(DISTINCT floor(
                    date_diff(
                        'day',
                        b.exposure_date,
                        CAST(t.transaction_timestamp AS DATE)
                    ) / 28
                )) FILTER (
                    WHERE t.transaction_timestamp >= b.exposure_timestamp
                      AND t.transaction_timestamp < b.exposure_timestamp + INTERVAL 112 DAY
                      AND t.payment_channel = 'online'
                ) AS online_active_months_16w
            FROM base b
            LEFT JOIN transactions t ON t.user_id = b.user_id
            GROUP BY b.user_id
        ),
        post_all AS (
            SELECT b.user_id, t.transaction_timestamp
            FROM base b
            JOIN transactions t ON t.user_id = b.user_id
            WHERE t.transaction_timestamp >= b.exposure_timestamp
        ),
        gaps AS (
            SELECT
                user_id,
                date_diff(
                    'day',
                    lag(transaction_timestamp) OVER (
                        PARTITION BY user_id ORDER BY transaction_timestamp
                    ),
                    transaction_timestamp
                ) AS gap_days
            FROM post_all
        ),
        gap_stats AS (
            SELECT user_id, median(gap_days) AS post_median_gap_days
            FROM gaps
            WHERE gap_days IS NOT NULL
            GROUP BY user_id
        ),
        last28 AS (
            SELECT
                b.user_id,
                COUNT(*) FILTER (
                    WHERE t.transaction_timestamp >= TIMESTAMP '2025-12-04'
                      AND t.transaction_timestamp < TIMESTAMP '2026-01-01'
                ) > 0 AS retained_last_28d
            FROM base b
            LEFT JOIN transactions t ON t.user_id = b.user_id
            GROUP BY b.user_id
        )
        SELECT
            b.user_id,
            b.variant,
            b.exposure_timestamp,
            COALESCE(j.june_tx_count, 0) AS june_tx_count,
            COALESCE(p.pre_tx_count, 0) / (
                date_diff('day', b.observation_start_date, b.exposure_date) / 7.0
            ) AS pre_tx_per_week,
            COALESCE(p.pre_gmv, 0) / (
                date_diff('day', b.observation_start_date, b.exposure_date) / 7.0
            ) AS pre_gmv_per_week,
            COALESCE(p.pre_rev, 0) / (
                date_diff('day', b.observation_start_date, b.exposure_date) / 7.0
            ) AS pre_rev_per_week,
            CASE
                WHEN COALESCE(p.pre_tx_count, 0) > 0
                THEN p.pre_online_tx::DOUBLE / p.pre_tx_count
                ELSE 0
            END AS pre_online_tx_share,
            (b.vip_enrolled AND b.vip_enrolled_at >= b.exposure_timestamp) AS enrolled_post_exposure,
            (
                b.vip_enrolled
                AND b.vip_enrolled_at >= b.exposure_timestamp
                AND b.vip_enrolled_at < b.exposure_timestamp + INTERVAL 14 DAY
            ) AS enrolled_within_14d,
            CASE
                WHEN b.vip_enrolled_at IS NOT NULL
                THEN date_diff('day', b.exposure_timestamp, b.vip_enrolled_at)
            END AS days_to_enroll,
            COALESCE(p16.post_tx_16w, 0) / 16.0 AS post_tx_per_week_16w,
            COALESCE(p16.post_gmv_16w, 0) / 16.0 AS post_gmv_per_week_16w,
            COALESCE(p16.post_rev_16w, 0) / 16.0 AS post_rev_per_week_16w,
            COALESCE(p16.post_in_person_tx_16w, 0) / 16.0
                AS post_in_person_tx_per_week_16w,
            COALESCE(p16.post_online_tx_16w, 0) / 16.0
                AS post_online_tx_per_week_16w,
            COALESCE(p16.active_weeks_16w, 0) / 16.0
                AS post_active_week_share_16w,
            COALESCE(p16.in_person_active_weeks_16w, 0) / 16.0
                AS in_person_active_week_share_16w,
            COALESCE(p16.online_active_months_16w, 0) / 4.0
                AS online_active_month_share_16w,
            gs.post_median_gap_days,
            COALESCE(l.retained_last_28d, FALSE) AS retained_last_28d,
            (
                COALESCE(p16.post_in_person_tx_16w, 0) > 0
                AND COALESCE(p16.post_online_tx_16w, 0) > 0
            ) AS is_dual_channel_16w
        FROM base b
        LEFT JOIN pre p USING (user_id)
        LEFT JOIN june j USING (user_id)
        LEFT JOIN post16 p16 USING (user_id)
        LEFT JOIN gap_stats gs USING (user_id)
        LEFT JOIN last28 l USING (user_id)
        ORDER BY b.user_id
        """
        df_exp_eval = _con.execute(_EXP_EVAL_SQL).df()

        _WEEKLY_PANEL_SQL = """
        WITH weeks AS (
            SELECT CAST(week_start AS DATE) AS week_start
            FROM (
                SELECT unnest(
                    generate_series(
                        DATE '2024-12-30',
                        DATE '2025-12-29',
                        INTERVAL 7 DAY
                    )
                ) AS week_start
            )
        ),
        user_weeks AS (
            SELECT
                s.user_id,
                w.week_start,
                s.is_full_year_obs,
                s.vip_cohort,
                s.vip_enrolled_at
            FROM user_spine s
            CROSS JOIN weeks w
            WHERE w.week_start >= date_trunc('week', s.observation_start_date)::DATE
        ),
        tx AS (
            SELECT
                t.user_id,
                date_trunc('week', t.transaction_timestamp)::DATE AS week_start,
                COUNT(*) AS tx_count,
                COUNT(*) FILTER (
                    WHERE t.payment_channel = 'in_person'
                ) AS in_person_tx_count,
                COUNT(*) FILTER (
                    WHERE t.payment_channel = 'online'
                ) AS online_tx_count,
                SUM(t.volume_nok) AS gmv_nok,
                SUM(t.volume_nok) FILTER (
                    WHERE t.payment_channel = 'in_person'
                ) AS in_person_gmv_nok,
                SUM(t.volume_nok) FILTER (
                    WHERE t.payment_channel = 'online'
                ) AS online_gmv_nok,
                SUM(t.revenue_nok) AS revenue_nok
            FROM transactions t
            JOIN merchants m USING (merchant_id)
            LEFT JOIN mcc c USING (merchant_mcc_code)
            GROUP BY 1, 2
        )
        SELECT
            uw.user_id,
            uw.week_start,
            uw.is_full_year_obs,
            uw.vip_cohort,
            COALESCE(tx.tx_count, 0) AS tx_count,
            COALESCE(tx.in_person_tx_count, 0) AS in_person_tx_count,
            COALESCE(tx.online_tx_count, 0) AS online_tx_count,
            COALESCE(tx.gmv_nok, 0) AS gmv_nok,
            COALESCE(tx.in_person_gmv_nok, 0) AS in_person_gmv_nok,
            COALESCE(tx.online_gmv_nok, 0) AS online_gmv_nok,
            COALESCE(tx.revenue_nok, 0) AS revenue_nok,
            (COALESCE(tx.tx_count, 0) > 0) AS is_active_week,
            (
                uw.vip_enrolled_at IS NOT NULL
                AND uw.week_start >= date_trunc('week', uw.vip_enrolled_at)::DATE
            ) AS is_vip_now,
            CASE
                WHEN uw.vip_enrolled_at IS NOT NULL
                THEN CAST(floor(
                    date_diff(
                        'day',
                        date_trunc('week', uw.vip_enrolled_at)::DATE,
                        uw.week_start
                    ) / 7.0
                ) AS INTEGER)
            END AS rel_week_to_vip
        FROM user_weeks uw
        LEFT JOIN tx
          ON uw.user_id = tx.user_id
         AND uw.week_start = tx.week_start
        ORDER BY uw.user_id, uw.week_start
        """
        df_weekly_panel = _con.execute(_WEEKLY_PANEL_SQL).df()
        _con.close()

        df_user_spine.to_csv(_processed_dir / "df_user_spine.csv", index=False)
        df_exp_eval.to_csv(_processed_dir / "df_exp_eval.csv", index=False)
        df_weekly_panel.to_csv(_processed_dir / "df_weekly_panel.csv", index=False)

        return df_exp_eval, df_user_spine, df_weekly_panel

    _paths = [
        PROCESSED_DIR / "df_user_spine.csv",
        PROCESSED_DIR / "df_exp_eval.csv",
        PROCESSED_DIR / "df_weekly_panel.csv",
    ]
    if all(_p.exists() for _p in _paths):
        df_user_spine = pd.read_csv(
            _paths[0],
            parse_dates=[
                "observation_start_date",
                "vip_enrolled_at",
                "exposure_timestamp",
            ],
        )
        df_exp_eval = pd.read_csv(_paths[1], parse_dates=["exposure_timestamp"])
        df_weekly_panel = pd.read_csv(_paths[2], parse_dates=["week_start"])
    else:
        df_exp_eval, df_user_spine, df_weekly_panel = _build_marts(
            transactions, users, merchants, mcc, experiment_exposure
        )

    # ---- enriched transactions ----
    _spine_cols = [
        "user_id",
        "is_full_year_obs",
        "vip_cohort",
        "vip_enrolled",
        "age_bucket",
        "user_country",
        "observation_start_date",
    ]
    _cat_map = {
        "5411": "Grocery/Food",
        "5499": "Grocery/Food",
        "5651": "Clothing",
        "5732": "Electronics",
        "5712": "Furniture",
        "5942": "Books",
    }
    # Both `transactions` and the user spine carry `user_country` (identical
    # row-for-row in this dataset); drop the per-transaction copy so the merge
    # yields one column for the country filter on slide 3.
    df_tx = (
        transactions.drop(columns=["user_country"])
        .merge(df_user_spine[_spine_cols], on="user_id", how="left")
        .merge(
            merchants[["merchant_id", "merchant_mcc_code"]],
            on="merchant_id",
            how="left",
        )
        .merge(mcc, on="merchant_mcc_code", how="left")
    )
    df_tx["category"] = df_tx["merchant_mcc_code"].map(_cat_map).fillna("Unclassified")
    df_tx["year"] = df_tx["transaction_timestamp"].dt.year

    # ---- silence spells ----
    _cutoff = pd.Timestamp("2026-01-01")
    _spell_rows = []
    for _uid, _grp in transactions.sort_values("transaction_timestamp").groupby(
        "user_id", sort=False
    ):
        _ts = _grp["transaction_timestamp"].tolist()
        for _i in range(len(_ts) - 1):
            _spell_rows.append((_uid, (_ts[_i + 1] - _ts[_i]).days, True))
        if _ts:
            _spell_rows.append((_uid, (_cutoff - _ts[-1]).days, False))
    df_silence_spells = pd.DataFrame(
        _spell_rows, columns=["user_id", "silence_days", "returned"]
    )
    _curve_rows = []
    for _x in range(1, 36):
        _m = df_silence_spells[df_silence_spells["silence_days"] >= _x]
        _curve_rows.append(
            {
                "threshold": _x,
                "spells": len(_m),
                "returned_share": float(_m["returned"].mean()) if len(_m) else np.nan,
                "churn_share": float((~_m["returned"]).mean()) if len(_m) else np.nan,
            }
        )
    df_silence_curve = pd.DataFrame(_curve_rows)

    # ---- multi-window post-exposure outcomes ----
    _con = duckdb.connect(":memory:")
    _con.register("transactions", transactions)
    _con.register("experiment_exposure", experiment_exposure)
    _window_sql = """
    WITH windows AS (SELECT unnest([4, 8, 12, 16]) AS weeks),
    base AS (
        SELECT
            user_id,
            exposure_timestamp,
            CAST(exposure_timestamp AS DATE) AS exposure_date
        FROM experiment_exposure
    )
    SELECT
        b.user_id,
        w.weeks,
        COUNT(t.transaction_id) AS tx_count,
        COALESCE(SUM(t.volume_nok), 0) AS gmv,
        COALESCE(SUM(t.revenue_nok), 0) AS revenue,
        COUNT(DISTINCT CASE
            WHEN t.transaction_id IS NOT NULL
            THEN floor(date_diff('day', b.exposure_date,
                CAST(t.transaction_timestamp AS DATE)) / 7)
        END) AS active_weeks,
        COUNT(DISTINCT CASE
            WHEN t.payment_channel = 'in_person'
            THEN floor(date_diff('day', b.exposure_date,
                CAST(t.transaction_timestamp AS DATE)) / 7)
        END) AS in_person_weeks,
        COUNT(DISTINCT CASE
            WHEN t.payment_channel = 'online'
            THEN floor(date_diff('day', b.exposure_date,
                CAST(t.transaction_timestamp AS DATE)) / 28)
        END) AS online_months
    FROM base b
    CROSS JOIN windows w
    LEFT JOIN transactions t
      ON t.user_id = b.user_id
     AND t.transaction_timestamp >= b.exposure_timestamp
     AND t.transaction_timestamp <
         b.exposure_timestamp + INTERVAL (w.weeks * 7) DAY
    GROUP BY b.user_id, w.weeks
    """
    _win = _con.execute(_window_sql).df()
    _con.close()

    def _expand_windows(_frame):
        _out = {}
        for _weeks in (4, 8, 12, 16):
            _sub = _frame[_frame["weeks"].eq(_weeks)].set_index("user_id")
            _months = _weeks / 4
            _out[f"post_tx_per_week_{_weeks}w"] = _sub["tx_count"] / _weeks
            _out[f"post_gmv_per_week_{_weeks}w"] = _sub["gmv"] / _weeks
            _out[f"post_rev_per_week_{_weeks}w"] = _sub["revenue"] / _weeks
            _out[f"post_active_week_share_{_weeks}w"] = _sub["active_weeks"] / _weeks
            _out[f"in_person_active_week_share_{_weeks}w"] = (
                _sub["in_person_weeks"] / _weeks
            )
            _out[f"online_active_month_share_{_weeks}w"] = (
                _sub["online_months"] / _months
            )
        return pd.DataFrame(_out).reindex(_frame["user_id"].unique())

    # df_exp_eval already carries 16w post outcomes; drop them so the
    # `_expand_windows` merge below does not produce _x/_y column collisions.
    _recompute_16w = [
        "post_tx_per_week_16w",
        "post_gmv_per_week_16w",
        "post_rev_per_week_16w",
        "post_active_week_share_16w",
        "in_person_active_week_share_16w",
        "online_active_month_share_16w",
    ]
    df_exp = df_exp_eval.drop(
        columns=[_c for _c in _recompute_16w if _c in df_exp_eval.columns]
    ).merge(
        df_user_spine[["user_id", "experiment_wave"]],
        on="user_id",
        how="left",
    )
    df_exp = df_exp.merge(
        _expand_windows(_win), left_on="user_id", right_index=True, how="left"
    )

    _summer = df_exp[df_exp["experiment_wave"].eq("summer")]
    df_exp["june_freq_tier"] = "All"
    _tiers = pd.qcut(_summer["june_tx_count"], 3, labels=["Low", "Medium", "High"])
    df_exp.loc[_summer.index, "june_freq_tier"] = _tiers.astype(str)

    # ---- per-user selection (slide 5) ----
    _tx25 = transactions[transactions["transaction_timestamp"].dt.year.eq(2025)]
    _fy_agg = _tx25.groupby("user_id").agg(
        fy_tx=("transaction_id", "size"),
        fy_gmv=("volume_nok", "sum"),
    )
    _pre_agg = (
        _tx25[_tx25["transaction_timestamp"] < pd.Timestamp("2025-05-01")]
        .groupby("user_id")
        .agg(
            pre_tx=("transaction_id", "size"),
            pre_gmv=("volume_nok", "sum"),
        )
    )
    _sel = (
        df_user_spine[df_user_spine["is_full_year_obs"]][
            ["user_id", "vip_enrolled", "vip_cohort"]
        ]
        .merge(_fy_agg, on="user_id", how="left")
        .merge(_pre_agg, on="user_id", how="left")
        .fillna(0)
    )
    _sel["fy_weekly_gmv"] = _sel["fy_gmv"] / (365 / 7)
    _sel["fy_weekly_tx"] = _sel["fy_tx"] / (365 / 7)
    _sel["pre_weekly_gmv"] = _sel["pre_gmv"] / (120 / 7)
    _sel["pre_weekly_tx"] = _sel["pre_tx"] / (120 / 7)

    # ---- channel economics (slide 9) ----
    _full_ids = set(df_user_spine.loc[df_user_spine["is_full_year_obs"], "user_id"])
    _tc = df_tx[df_tx["year"].eq(2025) & df_tx["user_id"].isin(_full_ids)]
    df_categories = _tc.groupby(["category", "payment_channel"], as_index=False).agg(
        purchases=("transaction_id", "size"),
        gmv=("volume_nok", "sum"),
        revenue=("revenue_nok", "sum"),
    )
    df_categories["take_rate"] = df_categories["revenue"] / df_categories["gmv"] * 100
    df_categories["gmv_share"] = df_categories["gmv"] / df_categories["gmv"].sum() * 100
    df_categories["channel"] = df_categories["payment_channel"].map(
        {"in_person": "In person", "online": "Online"}
    )
    df_categories["label"] = (
        df_categories["category"] + " (" + df_categories["channel"] + ")"
    )
    df_categories = df_categories.sort_values("gmv_share", ascending=False).reset_index(
        drop=True
    )

    # ---- headline constants ----
    _online = df_tx[df_tx["payment_channel"].eq("online")]
    _inperson = df_tx[df_tx["payment_channel"].eq("in_person")]
    CONSTANTS = {
        "n_users": int(users["user_id"].nunique()),
        "n_purchases": len(transactions),
        "n_merchants": int(merchants["merchant_id"].nunique()),
        "n_exp_users": int(experiment_exposure["user_id"].nunique()),
        "n_full_year": int(df_user_spine["is_full_year_obs"].sum()),
        "n_late": int((~df_user_spine["is_full_year_obs"]).sum()),
        "n_vip": int(df_user_spine["vip_enrolled"].sum()),
        "avg_online_ticket": float(_online["volume_nok"].mean()),
        "online_take": float(
            _online["revenue_nok"].sum() / _online["volume_nok"].sum()
        ),
        "inperson_take": float(
            _inperson["revenue_nok"].sum() / _inperson["volume_nok"].sum()
        ),
        "avg_online_rev_per_tx": float(_online["revenue_nok"].sum() / len(_online)),
    }

    D = {
        "df_tx": df_tx,
        "df_exp": df_exp,
        "df_silence_spells": df_silence_spells,
        "df_silence_curve": df_silence_curve,
        "df_sel": _sel,
        "df_categories": df_categories,
        "df_weekly_panel": df_weekly_panel,
        "constants": CONSTANTS,
    }

    # ---- widgets ----
    ui_s3_country = mo.ui.radio(
        options=["All countries", "Norway", "Denmark"],
        value="All countries",
        inline=True,
        label="Country",
    )
    ui_s3_full_only = mo.ui.switch(
        value=True,
        label="Filter to 373 full-year users (obs start <= Jan 1)",
    )
    ui_s4_silence_days = mo.ui.slider(
        start=1,
        stop=35,
        step=1,
        value=14,
        label="Silence threshold X (days without purchase)",
        show_value=True,
    )
    ui_s4_survival_days = mo.ui.radio(
        options=["7", "14", "28", "60"],
        value="28",
        inline=True,
        label="Year-end survival window (last N days)",
    )
    ui_s5_cohort = mo.ui.radio(
        options=[
            "Full year: VIP vs. non-VIP",
            "Jan–Apr: future VIPs vs. never-VIPs",
        ],
        value="Jan–Apr: future VIPs vs. never-VIPs",
        label="Comparison period",
    )
    ui_s6_window = mo.ui.slider(
        start=4,
        stop=12,
        step=2,
        value=8,
        label="Balanced window (+/- W weeks around signup)",
        show_value=True,
    )
    ui_s6_cohort = mo.ui.radio(
        options=[
            "All VIP members",
            "Joined organically",
            "Joined through invitation",
        ],
        value="All VIP members",
        inline=True,
        label="VIP group",
    )
    ui_s7_wave = mo.ui.radio(
        options=[
            "Summer wave (N=226, 16w obs)",
            "December wave (N=43, 5-17d obs)",
            "Both waves",
        ],
        value="Summer wave (N=226, 16w obs)",
        inline=True,
        label="Wave",
    )
    ui_s7_week = mo.ui.slider(
        start=1,
        stop=16,
        step=1,
        value=4,
        label="Inspect cumulative signup at Week W",
        show_value=True,
    )
    ui_s8_window = mo.ui.radio(
        options=["4", "8", "12", "16"],
        value="16",
        inline=True,
        label="Post-exposure window (weeks)",
    )
    ui_s8_june_tier = mo.ui.dropdown(
        options=[
            "All Summer users (N=226)",
            "Low June frequency",
            "Medium June frequency",
            "High June frequency",
        ],
        value="All Summer users (N=226)",
        label="June frequency block",
    )
    ui_s8_scale_late = mo.ui.switch(
        value=False,
        label="Scale for actual joiners (divide diff by net signup lift)",
    )
    ui_s9_extra_online_tx = mo.ui.slider(
        start=0.5,
        stop=4.0,
        step=0.5,
        value=1.0,
        label="Incremental online purchases / VIP / month",
        show_value=True,
    )
    ui_s9_point_cost_bps = mo.ui.slider(
        start=0,
        stop=150,
        step=10,
        value=50,
        label="Assumed point cost (bps of incremental GMV)",
        show_value=True,
    )


@app.cell(hide_code=True)
def slide_1():
    _c = D["constants"]

    vipps_slide_html = f"""
    <style>
    .vipps-slide {{
        box-sizing: border-box;
        width: 100%;
        min-height: 540px;
        padding:clamp(20.4px, 2.528cqw, 34px) clamp(25.2px, 3.123cqw, 42px);
        background: #FFFAF7;
        color: #0B1F3A;
        border-radius:clamp(10.8px, 1.338cqw, 18px);
        font-family: Inter, Arial, sans-serif;
        position: relative;
    }}
    .vipps-slide *,
    .vipps-slide h1,
    .vipps-slide h3,
    .vipps-slide strong,
    .vipps-slide .number {{
        box-sizing: border-box;
        font-family: Inter, Arial, sans-serif;
    }}
    .vipps-accent {{
        height:clamp(6px, 0.520cqw, 7px);
        width: 100%;
        margin-bottom:clamp(15px, 1.859cqw, 25px);
        background: #FF5B24;
        border-radius:clamp(6px, 0.595cqw, 8px);
    }}
    .vipps-kicker {{
        margin-bottom:clamp(7.2px, 0.892cqw, 12px);
        color: #FF5B24;
        font-size:clamp(7.2px, 0.892cqw, 12px);
        font-weight: 700;
        letter-spacing: 1.4px;
    }}
    .vipps-slide h1 {{
        margin: 0 0 12px;
        color: #0B1F3A;
        font-size:clamp(21px, 2.602cqw, 35px);
        font-weight: 700;
        line-height: 1.15;
        letter-spacing: -0.7px;
    }}
    .vipps-subtitle {{
        max-width: 760px;
        margin: 0 0 24px;
        color: #536174;
        font-size:clamp(9.6px, 1.190cqw, 16px);
        line-height: 1.5;
    }}
    .vipps-metrics {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap:clamp(7.2px, 0.892cqw, 12px);
        margin-bottom:clamp(15.6px, 1.933cqw, 26px);
    }}
    .vipps-metric {{
        padding:clamp(9px, 1.115cqw, 15px) clamp(10.2px, 1.264cqw, 17px);
        background: #FFFFFF;
        border: 1px solid #E8E1DC;
        border-top: 3px solid #FF5B24;
        border-radius:clamp(7.2px, 0.892cqw, 12px);
    }}
    .vipps-metric strong {{
        display: block;
        margin-bottom:clamp(6px, 0.446cqw, 6px);
        color: #0B1F3A;
        font-size:clamp(15.6px, 1.933cqw, 26px);
        font-weight: 700;
        line-height: 1.2;
    }}
    .vipps-metric span {{
        color: #687487;
        font-size:clamp(7.2px, 0.892cqw, 12px);
        line-height: 1.35;
    }}
    .vipps-roadmap {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap:clamp(8.4px, 1.041cqw, 14px);
    }}
    .vipps-card {{
        min-height: 145px;
        padding:clamp(10.2px, 1.264cqw, 17px) clamp(10.8px, 1.338cqw, 18px);
        background: #FFFFFF;
        border: 1px solid #E8E1DC;
        border-radius:clamp(7.2px, 0.892cqw, 12px);
    }}
    .vipps-card .number {{
        color: #FF5B24;
        font-size:clamp(6.6px, 0.818cqw, 11px);
        font-weight: 700;
        letter-spacing: 1px;
    }}
    .vipps-card h3 {{
        margin: 10px 0 8px;
        color: #0B1F3A;
        font-size:clamp(10.8px, 1.338cqw, 18px);
        font-weight: 700;
        line-height: 1.25;
    }}
    .vipps-card p {{
        margin: 0;
        color: #536174;
        font-size:clamp(7.8px, 0.967cqw, 13px);
        line-height: 1.5;
    }}
    .vipps-footer {{
        display: flex;
        align-items: center;
        gap:clamp(6px, 0.743cqw, 10px);
        margin-top:clamp(12px, 1.487cqw, 20px);
        color: #536174;
        font-size:clamp(7.2px, 0.892cqw, 12px);
    }}
    /* Responsive layer -------------------------------------------------------
       Slide type and spacing are expressed in clamp(px, cqw, px): the value is
       the design size at the 1345px canvas and shrinks in step with the reveal
       stage, which marimo sizes from the window width. Charts live in a shadow
       host, so they are scaled by media query instead. */
    .reveal .slides section [data-testid="slide-scroll-container"] {{
        container-type: inline-size;
    }}
    @media (max-width: 1432px) {{
        .mo-slide-content marimo-mime-renderer {{ zoom: 0.94; }}
    }}
    @media (max-width: 1359px) {{
        .mo-slide-content marimo-mime-renderer {{ zoom: 0.87; }}
    }}
    @media (max-width: 1269px) {{
        .mo-slide-content marimo-mime-renderer {{ zoom: 0.8; }}
    }}
    @media (max-width: 1179px) {{
        .mo-slide-content marimo-mime-renderer {{ zoom: 0.74; }}
    }}
    @media (max-width: 1089px) {{
        .mo-slide-content marimo-mime-renderer {{ zoom: 0.68; }}
    }}

    .vipps-footer-mark {{
        flex: 0 0 auto;
        width: 6px;
        height:clamp(6px, 0.446cqw, 6px);
        background: #FF5B24;
        border-radius: 50%;
    }}
    </style>

    <div class="vipps-slide">
    <div style="position:absolute;top:16px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">01<span style="color:#8C8C8C;"> / 11</span></div>
      <div class="vipps-accent"></div>
      <div class="vipps-kicker">VIPPS · CASE INTERVIEW</div>

      <h1>Does VIP create customer loyalty?</h1>
      <p class="vipps-subtitle">
        Assessing VIP’s impact on spending, retention, and engagement.
      </p>

      <div class="vipps-metrics">
        <div class="vipps-metric">
          <strong>{orange(f"{_c['n_users']:,}")}</strong>
          <span>Users in the dataset</span>
        </div>
        <div class="vipps-metric">
          <strong>{orange(f"{_c['n_purchases']:,}")}</strong>
          <span>Purchases</span>
        </div>
        <div class="vipps-metric">
          <strong>{orange(f"{_c['n_merchants']:,}")}</strong>
          <span>Merchants</span>
        </div>
        <div class="vipps-metric">
          <strong>{orange(f"{_c['n_exp_users']:,}")}</strong>
          <span>Experiment users</span>
        </div>
      </div>

      <div class="vipps-roadmap">
        <div class="vipps-card">
          <div class="number">01 · DEFINE</div>
          <h3>How do we measure loyalty?</h3>
          <p>Define “Keep coming back” in a way that reflects how customers use the service.</p>
        </div>
        <div class="vipps-card">
          <div class="number">02 · EVALUATE</div>
          <h3>Does VIP change behaviour?</h3>
          <p>Compare spending, retention, and engagement across VIP and non VIP users, experiment & control groups.</p>
        </div>
        <div class="vipps-card">
          <div class="number">03 · RECOMMEND</div>
          <h3>What should happen next?</h3>
          <p>Turn the findings into a decision, follow-up analysis, and success measures.</p>
        </div>
      </div>

      <div class="vipps-footer">
        <span class="vipps-footer-mark"></span>
        <span>From defining loyalty to evaluating impact and recommending action</span>
        <a href="{REPO_URL}" target="_blank" rel="noopener"
           style="color:#FF5B24;font-weight:700;text-decoration:none;border-bottom:1px solid #FF5B24;margin-left:auto;">Repository ↗</a>
      </div>
    </div>
    """

    mo.Html(vipps_slide_html)
    return


@app.cell(hide_code=True)
def slide_2():
    _c = D["constants"]

    summary_html = f"""
    <style>
    .vipps-summary {{
        box-sizing: border-box;
        width: 100%;
        padding:clamp(18px, 2.230cqw, 30px) clamp(21.6px, 2.677cqw, 36px);
        background: #FFFAF7;
        color: #0B1F3A;
        border-radius:clamp(10.8px, 1.338cqw, 18px);
        font-family: Inter, Arial, sans-serif;
        position: relative;
    }}
    .vipps-summary *,
    .vipps-summary h1,
    .vipps-summary h2,
    .vipps-summary strong {{
        box-sizing: border-box;
        font-family: Inter, Arial, sans-serif;
    }}
    .vipps-summary-accent {{
        height:clamp(6px, 0.520cqw, 7px);
        margin-bottom:clamp(14.4px, 1.784cqw, 24px);
        background: #FF5B24;
        border-radius:clamp(6px, 0.595cqw, 8px);
    }}
    .vipps-summary-kicker {{
        margin-bottom:clamp(6px, 0.743cqw, 10px);
        color: #FF5B24;
        font-size:clamp(7.2px, 0.892cqw, 12px);
        font-weight: 700;
        letter-spacing: 1.4px;
        text-transform: uppercase;
    }}
    .vipps-summary h1 {{
        max-width: 850px;
        margin: 0 0 12px;
        color: #0B1F3A;
        font-size:clamp(18px, 2.230cqw, 30px);
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: -0.7px;
    }}
    .vipps-summary-lede {{
        max-width: 850px;
        margin: 0 0 24px;
        color: #536174;
        font-size:clamp(9px, 1.115cqw, 15px);
        line-height: 1.5;
    }}
    .vipps-summary-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap:clamp(8.4px, 1.041cqw, 14px);
    }}
    .vipps-summary-card {{
        min-width: 0;
        padding:clamp(11.4px, 1.413cqw, 19px) clamp(12px, 1.487cqw, 20px);
        background: #FFFFFF;
        border: 1px solid #E8E1DC;
        border-radius:clamp(7.2px, 0.892cqw, 12px);
    }}
    .vipps-summary-card-label {{
        margin-bottom:clamp(6px, 0.743cqw, 10px);
        color: #FF5B24;
        font-size:clamp(6.6px, 0.818cqw, 11px);
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    .vipps-summary-card h2 {{
        margin: 0 0 8px;
        color: #0B1F3A;
        font-size:clamp(10.2px, 1.264cqw, 17px);
        font-weight: 700;
        line-height: 1.3;
    }}
    .vipps-summary-card p {{
        margin: 0;
        color: #536174;
        font-size:clamp(7.8px, 0.967cqw, 13px);
        font-weight: 400;
        line-height: 1.55;
    }}
    .vipps-summary-card ul {{
        margin: 7px 0 10px;
        padding-left:clamp(10.8px, 1.338cqw, 18px);
        color: #536174;
        font-family: Inter, Arial, sans-serif;
        font-size:clamp(7.8px, 0.967cqw, 13px);
        font-weight: 400;
        line-height: 1.55;
    }}
    .vipps-summary-card li {{
        margin-bottom:clamp(6px, 0.297cqw, 4px);
        font: inherit;
    }}
    .vipps-summary-card li:last-child {{
        margin-bottom: 0;
    }}
    .vipps-summary-card li strong {{
        color: #0B1F3A;
        font: inherit;
        font-weight: 700;
    }}
    .vipps-orange {{
        color: #FF5B24;
        font-weight: 700;
    }}
    .vipps-summary-bottomline {{
        margin-top:clamp(10.8px, 1.338cqw, 18px);
        padding:clamp(7.8px, 0.967cqw, 13px) clamp(9.6px, 1.190cqw, 16px);
        background: #0B1F3A;
        color: #FFFFFF;
        border-radius:clamp(7.2px, 0.892cqw, 12px);
        font-size:clamp(7.8px, 0.967cqw, 13px);
        line-height: 1.5;
    }}
    .vipps-summary-bottomline strong {{
        color: #FF8A62;
        font-weight: 700;
    }}
    </style>

    <div class="vipps-summary">
    <div style="position:absolute;top:16px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">02<span style="color:#8C8C8C;"> / 11</span></div>
        <div class="vipps-summary-accent"></div>
        <div class="vipps-summary-kicker">Executive summary</div>

        <h1>
            Invites drive signups,<br>
            <span class="vipps-orange">not retention.</span>
        </h1>

        <p class="vipps-summary-lede">
           Customers don't gradually slow down: They either use us multiple times a day or stop completely (~29% churn before year-end).
        </p>

        <div class="vipps-summary-grid">
            <div class="vipps-summary-card">
                <div class="vipps-summary-card-label">01 · Define success</div>
                <h2>Keep coming back</h2>
                <p>We define repeat engagement through three metrics:</p>
                <ul>
                    <li><strong>Survival:</strong> The user made a purchase in the last <span class="vipps-orange">28</span> days.</li>
                    <li><strong>Cadence:</strong> The user maintains the expected purchase frequency.</li>
                    <li><strong>Spend:</strong> The user continues to make purchases and generate GMV.</li>
                </ul>
                <p>
                    Together, these metrics capture whether users remain active,
                    return regularly, and continue spending on the platform.
                </p>
            </div>

            <div class="vipps-summary-card">
                <div class="vipps-summary-card-label">02 · Early VIP adopters</div>
                <h2>Customers who adopted VIP were already more active</h2>
                <p>
                    Future VIP customers spent <span class="vipps-orange">1.09×</span>
                    more per week before launch. After enrollment, purchases rose
                    <span class="vipps-orange">8.4%</span> and GMV
                    <span class="vipps-orange">5.5%</span> within user, driven by
                    in-person activity.
                </p>
            </div>

            <div class="vipps-summary-card">
                <div class="vipps-summary-card-label">03 · Invitation experiment</div>
                <h2>Experiment boosts signup, not retention</h2>
                <p>
                    Signup increased from <strong>8.0%</strong> to
                    <strong>68.1%</strong>
                    <span class="vipps-orange">(+60.2 pp)</span>
                    (<strong>p &lt; 0.001</strong>).  However,
                    it produced no statistically significant lift in retention or spend 
                    (<span class="vipps-orange">4.7%</span> purchases , <span class="vipps-orange">-0.5%</span> GMV).
                </p>
            </div>

            <div class="vipps-summary-card">
                <div class="vipps-summary-card-label">04 · What to do next</div>
                <h2>Passive signup nudges aren't enough</h2>
                <p>
                    Test 14-day inactivity reminders. Online checkout point multipliers
                    (Online take rate is
                    <span class="vipps-orange">{_c["online_take"]:.2%}</span>
                    versus
                    <span class="vipps-orange">{_c["inperson_take"]:.2%}</span>
                    for in-person).
                </p>
            </div>
        </div>

        <div class="vipps-summary-bottomline">
            <strong>BOTTOM LINE</strong>
            &nbsp; Invitations are effective at converting users into VIPs;
            retention impact remains unproven.
        </div>
    </div>
    """

    mo.Html(summary_html)
    return


@app.cell(hide_code=True)
def slide_3():
    _c = D["constants"]
    _tx = D["df_tx"]
    if ui_s3_country.value != "All countries":
        _tx = _tx[_tx["user_country"].eq(ui_s3_country.value)]
    if ui_s3_full_only.value:
        _tx = _tx[_tx["is_full_year_obs"]]
    _ch = _tx.groupby("payment_channel", as_index=False).agg(
        purchases=("transaction_id", "size"),
        gmv=("volume_nok", "sum"),
        revenue=("revenue_nok", "sum"),
        users=("user_id", "nunique"),
        ticket=("volume_nok", "mean"),
        ticket_median=("volume_nok", "median"),
    )
    _ch["purchases_share"] = _ch["purchases"] / _ch["purchases"].sum() * 100
    _ch["gmv_share"] = _ch["gmv"] / _ch["gmv"].sum() * 100
    _ch["revenue_share"] = _ch["revenue"] / _ch["revenue"].sum() * 100
    _ch["take_rate"] = _ch["revenue"] / _ch["gmv"] * 100

    _rows = []
    for _metric, _col in (
        ("Purchases", "purchases_share"),
        ("GMV", "gmv_share"),
        ("Revenue", "revenue_share"),
    ):
        for _channel, _label in (
            ("online", "Online"),
            ("in_person", "In person"),
        ):
            _rows.append(
                {
                    "metric": _metric,
                    "channel": _label,
                    "share": float(
                        _ch.set_index("payment_channel").loc[_channel, _col]
                    ),
                }
            )
    _mix = pd.DataFrame(_rows)
    _mix["label"] = [f"{v:.1f}%" for v in _mix["share"]]
    _mix_base = alt.Chart(_mix).encode(
        x=alt.X(
            "metric:N",
            title=None,
            sort=["Purchases", "GMV", "Revenue"],
            axis=alt.Axis(labelAngle=0),
        ),
        xOffset=alt.XOffset("channel:N", title=None),
        y=alt.Y(
            "share:Q",
            title="Share (%)",
            scale=alt.Scale(domain=[0, 100]),
            axis=alt.Axis(format=".0f"),
        ),
        color=alt.Color(
            "channel:N",
            title=None,
            scale=alt.Scale(
                domain=["In person", "Online"], range=["#FF5B24", "#2F6DB3"]
            ),
        ),
    )

    _chart = (
        alt.layer(
            _mix_base.mark_bar(),
            _mix_base.mark_text(
                dy=-8,
                fontSize=11,
                fontWeight=700,
                color="#0B1F3A",
            ).encode(text="label:N"),
        )
        .properties(
            height=250, width="container", title="Channel mix by selected population"
        )
        .configure(background="#FFFFFF")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor="#526176",
            titleColor="#0B1F3A",
            domainColor="#D8DEE7",
            tickColor="#D8DEE7",
            gridColor="#F0E5DF",
            labelFont="Inter, Arial, sans-serif",
            titleFont="Inter, Arial, sans-serif",
            titleFontWeight=700,
        )
        .configure_legend(
            labelColor="#526176",
            titleColor="#0B1F3A",
            labelFont="Inter, Arial, sans-serif",
            titleFont="Inter, Arial, sans-serif",
        )
    )

    _on = _ch.set_index("payment_channel").loc["online"]
    _in = _ch.set_index("payment_channel").loc["in_person"]

    _summary_html = f"""
    <div style="
        background: #FFFFFF;
        border: 1px solid #F0E5DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(12px, 1.487cqw, 20px);
        color: #0B1F3A;
        font-family: Inter, Arial, sans-serif;
    ">
        <div style="
            color: #FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight: 800;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom:clamp(6px, 0.595cqw, 8px);
        ">Channel comparison</div>

        <div style="
            font-size:clamp(10.8px, 1.338cqw, 18px);
            font-weight: 750;
            margin-bottom:clamp(8.4px, 1.041cqw, 14px);
        ">Two distinct spending patterns</div>

        <table style="
            width: 100%;
            border-collapse: collapse;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            line-height: 1.5;
        ">
            <thead>
                <tr style="border-bottom: 1px solid #F0E5DF;">
                    <th style="text-align: left; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #526176;">Metric</th>
                    <th style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #FF5B24;">In person</th>
                    <th style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #2F6DB3;">Online</th>
                </tr>
            </thead>
            <tbody>
                <tr style="border-bottom: 1px solid #F5EDE8;">
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #526176;">Active users</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{int(_in["users"]):,}</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{int(_on["users"]):,}</td>
                </tr>
                <tr style="border-bottom: 1px solid #F5EDE8;">
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #526176;">Mean ticket</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{_in["ticket"]:,.0f} NOK</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{_on["ticket"]:,.0f} NOK</td>
                </tr>
                <tr style="border-bottom: 1px solid #F5EDE8;">
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #526176;">Median ticket</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{_in["ticket_median"]:,.0f} NOK</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{_on["ticket_median"]:,.0f} NOK</td>
                </tr>
                <tr>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #526176;">Take rate</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px);">{_in["take_rate"]:.2f}%</td>
                    <td style="text-align: right; padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.297cqw, 4px); color: #FF5B24; font-weight: 800;">{_on["take_rate"]:.2f}%</td>
                </tr>
            </tbody>
        </table>

        <div style="
            margin-top:clamp(9.6px, 1.190cqw, 16px);
            padding:clamp(8.4px, 1.041cqw, 14px);
            background: #FFFAF7;
            border-radius:clamp(6px, 0.743cqw, 10px);
            font-size:clamp(7.8px, 0.967cqw, 13px);
            line-height: 1.55;
            color: #526176;
        ">
            Online represents {orange(f"{_on['purchases_share']:.1f}%")} of purchases,
            but {orange(f"{_on['gmv_share']:.1f}%")} of GMV and
            {orange(f"{_on['revenue_share']:.1f}%")} of service revenue.
            Its take rate is {orange(f"{_on['take_rate']:.2f}%")}, compared with
            {orange(f"{_in['take_rate']:.2f}%")} in person.
        </div>
    </div>
    """

    mo.vstack(
        [
            mo.hstack(
                [ui_s3_country, ui_s3_full_only],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    background: #FFFAF7;position:relative;
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    font-family: Inter, Arial, sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">03<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background: #FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color: #FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight: 800;
                        letter-spacing: 1.5px;
                        text-transform: uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Channel economics</div>
                    <div style="
                        color: #0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height: 1.2;
                        font-weight: 800;
                        letter-spacing: -0.5px;
                    ">
                        Two distinct products in one:<br>
                        <span style="color: #FF5B24;">daily habit</span> and
                        <span style="color: #2F6DB3;">high-value retail</span>
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    _chart,
                    mo.Html(_summary_html),
                ],
                widths=[1.05, 1],
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_4():
    _curve = D["df_silence_curve"].copy()
    _spells = D["df_silence_spells"].copy()

    _x = int(ui_s4_silence_days.value)
    _win = int(ui_s4_survival_days.value)

    # -----------------------------
    # Churn / return curve
    # -----------------------------
    _at_x = _curve.loc[_curve["threshold"].eq(_x)]

    # Fall back to the nearest available threshold if the selected value is absent
    if _at_x.empty:
        _idx = (_curve["threshold"] - _x).abs().idxmin()
        _at_x = _curve.loc[[_idx]]
        _x = int(_at_x["threshold"].iloc[0])

    _n_spells = int(_at_x["spells"].iloc[0])
    _ret_pct = float(_at_x["returned_share"].iloc[0])
    _churn_pct = float(_at_x["churn_share"].iloc[0])

    _line = (
        alt.Chart(_curve)
        .mark_line(
            interpolate="step-after",
            point=alt.OverlayMarkDef(size=35, filled=True),
            strokeWidth=3,
            color="#2F6DB3",
        )
        .encode(
            x=alt.X(
                "threshold:Q",
                title="Days without a purchase",
                axis=alt.Axis(tickMinStep=7),
            ),
            y=alt.Y(
                "churn_share:Q",
                title="Share of spells with no observed return",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            tooltip=[
                alt.Tooltip("threshold:Q", title="Silence threshold (days)"),
                alt.Tooltip("spells:Q", title="Purchase spells", format=","),
                alt.Tooltip("returned_share:Q", title="Returned", format=".1%"),
                alt.Tooltip("churn_share:Q", title="No observed return", format=".1%"),
            ],
        )
    )

    _rule = (
        alt.Chart(alt.Data(values=[{"threshold": _x}]))
        .mark_rule(
            strokeDash=[5, 4],
            color="#FF5B24",
            strokeWidth=2,
        )
        .encode(x="threshold:Q")
    )

    _point = (
        alt.Chart(_at_x)
        .mark_point(
            size=110,
            color="#FF5B24",
            filled=True,
            stroke="white",
            strokeWidth=1.5,
        )
        .encode(
            x="threshold:Q",
            y="churn_share:Q",
            tooltip=[
                alt.Tooltip("threshold:Q", title="Selected threshold (days)"),
                alt.Tooltip("spells:Q", title="Purchase spells", format=","),
                alt.Tooltip("returned_share:Q", title="Returned", format=".1%"),
                alt.Tooltip("churn_share:Q", title="No observed return", format=".1%"),
            ],
        )
    )

    _cliff = (
        alt.layer(_line, _rule, _point)
        .properties(height=250, width="container", title="The churn cliff")
        .configure(background="#FFFFFF")
        .configure_view(stroke=None)
        .configure_axis(
            labelFont="Inter, Arial, sans-serif",
            titleFont="Inter, Arial, sans-serif",
            labelColor="#526176",
            titleColor="#0B1F3A",
            domainColor="#D8DEE7",
            tickColor="#D8DEE7",
            gridColor="#E9E3DF",
            titleFontWeight=700,
        )
        .configure_title(
            font="Inter, Arial, sans-serif",
            color="#0B1F3A",
            fontSize=14,
            fontWeight=700,
            anchor="start",
        )
    )

    # -----------------------------
    # Active-user KPI
    # -----------------------------
    _last = (
        D["df_tx"][D["df_tx"]["year"].eq(2025)]
        .groupby("user_id")["transaction_timestamp"]
        .max()
    )

    _active_cutoff = pd.Timestamp("2026-01-01") - pd.Timedelta(days=_win)
    _active_last = int((_last >= _active_cutoff).sum())

    # -----------------------------
    # Supporting cards
    # -----------------------------
    _kpi_html = f"""
    <div style="
        background:#FFFFFF;
        border:1px solid #E9E3DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(10.8px, 1.338cqw, 18px) clamp(12px, 1.487cqw, 20px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#526176;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            font-weight:600;
            margin-bottom:clamp(6px, 0.520cqw, 7px);
        ">No observed return by {_x} days</div>

        <div style="
            color:#FF5B24;
            font-size:clamp(20.4px, 2.528cqw, 34px);
            line-height:1;
            font-weight:750;
        ">{_churn_pct:.0%}</div>

        <div style="
            color:#526176;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            margin-top:clamp(6px, 0.595cqw, 8px);
        ">Across {_n_spells:,} purchase spells</div>

        <div style="
            border-top:1px solid #E9E3DF;
            margin:16px 0;
        "></div>

        <div style="
            color:#526176;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            font-weight:600;
            margin-bottom:clamp(6px, 0.520cqw, 7px);
        ">Users active within the {_win}-day window</div>

        <div style="
            color:#0B1F3A;
            font-size:clamp(20.4px, 2.528cqw, 34px);
            line-height:1;
            font-weight:750;
        ">{_active_last:,}</div>

        <div style="
            color:#526176;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            margin-top:clamp(6px, 0.595cqw, 8px);
        ">Last purchase within {_win} days of year-end</div>
    </div>
    """

    _framework_html = """
    <div style="
        background:#FFFFFF;
        border:1px solid #E9E3DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(9.6px, 1.190cqw, 16px) clamp(10.8px, 1.338cqw, 18px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight:800;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:clamp(6px, 0.446cqw, 6px);
        ">Retention framework</div>

        <div style="
            font-size:clamp(9.6px, 1.190cqw, 16px);
            font-weight:750;
            margin-bottom:clamp(7.2px, 0.892cqw, 12px);
        ">Three layers of “keep coming back”</div>

        <div style="
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:clamp(8.4px, 1.041cqw, 14px);
        ">
            <div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);font-weight:750;color:#FF5B24;margin-bottom:clamp(6px, 0.372cqw, 5px);">
                    01 / SURVIVAL
                </div>
                <div style="font-size:clamp(7.8px, 0.967cqw, 13px);font-weight:700;margin-bottom:clamp(6px, 0.297cqw, 4px);">
                    Recent activity
                </div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                    Purchased within the selected survival window.
                </div>
            </div>

            <div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);font-weight:750;color:#FF5B24;margin-bottom:clamp(6px, 0.372cqw, 5px);">
                    02 / CADENCE
                </div>
                <div style="font-size:clamp(7.8px, 0.967cqw, 13px);font-weight:700;margin-bottom:clamp(6px, 0.297cqw, 4px);">
                    Expected frequency
                </div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                    Weekly in-person and monthly online activity.
                </div>
            </div>

            <div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);font-weight:750;color:#FF5B24;margin-bottom:clamp(6px, 0.372cqw, 5px);">
                    03 / SPEND
                </div>
                <div style="font-size:clamp(7.8px, 0.967cqw, 13px);font-weight:700;margin-bottom:clamp(6px, 0.297cqw, 4px);">
                    Customer value
                </div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                    Purchase frequency and GMV.
                </div>
            </div>
        </div>

        <div style="
            margin-top:clamp(7.2px, 0.892cqw, 12px);
            padding-top:clamp(6px, 0.743cqw, 10px);
            border-top:1px solid #E9E3DF;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            line-height:1.45;
            color:#526176;
        ">
            Based on the
            <a href="https://en.wikipedia.org/wiki/RFM_(market_research)"
               target="_blank" rel="noopener"
               style="color:#FF5B24;font-weight:700;text-decoration:none;border-bottom:1px solid #FF5B24;">RFM framework</a>
        </div>
    </div>
    """

    # -----------------------------
    # Slide
    # -----------------------------
    mo.vstack(
        [
            mo.hstack(
                [ui_s4_silence_days, ui_s4_survival_days],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    background:#FFFAF7;position:relative;
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">04<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Defining retention</div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        What does it mean to<br>
                        <span style="color:#FF5B24;">keep coming back?</span>
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    mo.vstack(
                        [
                            _cliff,
                            mo.Html(_framework_html),
                        ],
                        gap=1,
                    ),
                    mo.Html(_kpi_html),
                ],
                widths=[1.55, 0.8],
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_5():
    _sel = D["df_sel"]
    _choice = ui_s5_cohort.value

    # Same groups in both views; only the measurement period changes.
    _vip = _sel[_sel["vip_enrolled"]]
    _never = _sel[_sel["vip_cohort"].eq("never_vip")]

    if _choice == "Full year: VIP vs. non-VIP":
        _gmv_col = "fy_weekly_gmv"
        _tx_col = "fy_weekly_tx"
        _period_label = "Full year"
        _vip_label = "VIP"
        _comparison_label = "VIP average vs. Never-VIP"
        _headline = "VIP members spent and purchased more"
        _description = (
            "Across the full year, VIP members had higher average weekly "
            "spend and purchase frequency than users who never enrolled."
        )
        _interpretation = (
            "This is a descriptive full-year comparison, not a causal estimate "
            "of the effect of VIP membership. Members may already have been "
            "more engaged before joining."
        )
    else:
        _gmv_col = "pre_weekly_gmv"
        _tx_col = "pre_weekly_tx"
        _period_label = "Jan–Apr · Before VIP launch"
        _vip_label = "Future VIPs"
        _comparison_label = "Future VIP average vs. Never-VIP"
        _headline = "Future VIPs were already more engaged"
        _description = (
            "Before VIP launched, users who later enrolled were already spending "
            "more and purchasing more often than users who never enrolled."
        )
        _interpretation = (
            "This pre-existing difference is evidence of selection bias: the "
            "full-year gap cannot be interpreted as the effect of VIP membership alone."
        )

    _gmv_vip = _vip[_gmv_col].mean()
    _gmv_never = _never[_gmv_col].mean()
    _tx_vip = _vip[_tx_col].mean()
    _tx_never = _never[_tx_col].mean()

    _ratio_gmv = _gmv_vip / _gmv_never
    _ratio_tx = _tx_vip / _tx_never

    # Two-sample Welch t-tests on the shown averages.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        _, _p_gmv = stats.ttest_ind(
            _vip[_gmv_col].astype(float),
            _never[_gmv_col].astype(float),
            equal_var=False,
        )
        _, _p_tx = stats.ttest_ind(
            _vip[_tx_col].astype(float),
            _never[_tx_col].astype(float),
            equal_var=False,
        )

    def _comparison_card(
        title,
        vip_value,
        never_value,
        ratio,
        unit,
        fmt,
        n_vip,
        n_never,
        p_value,
    ):
        _max_ratio = max(ratio, 1.0)
        _never_width = 100 / _max_ratio
        _vip_width = ratio / _max_ratio * 100

        return f"""
        <div style="
            background:#FFFFFF; border:1px solid #F0E5DF; border-radius:clamp(8.4px, 1.041cqw, 14px);
            padding:clamp(12px, 1.487cqw, 20px); color:#0B1F3A; font-family:Inter,Arial,sans-serif;
        ">
            <div style="
                color:#526176; font-size:clamp(6.6px, 0.818cqw, 11px); font-weight:800;
                letter-spacing:1px; text-transform:uppercase; margin-bottom:clamp(6px, 0.595cqw, 8px);
            ">{title}</div>

            <div style="
                font-size:clamp(18px, 2.230cqw, 30px); line-height:1.1; font-weight:800;
                color:#FF5B24; margin-bottom:clamp(6px, 0.297cqw, 4px);
            ">{ratio:.2f}×</div>

            <div style="font-size:clamp(7.2px, 0.892cqw, 12px); color:#526176; margin-bottom:clamp(6px, 0.297cqw, 4px);">
                {_comparison_label}
            </div>

            <div style="font-size:clamp(6.6px, 0.818cqw, 11px); color:#526176; margin-bottom:clamp(9.6px, 1.190cqw, 16px);">
                N={n_vip} vs. N={n_never} ·
                Welch t-test p = {p_value:.3f}
            </div>

            <div style="font-size:clamp(7.2px, 0.892cqw, 12px); color:#526176; margin-bottom:clamp(6px, 0.372cqw, 5px);">
                Never-VIP
                <span style="float:right; color:#0B1F3A; font-weight:700;">
                    {fmt.format(never_value)} {unit}
                </span>
            </div>
            <div style="
                height:clamp(6px, 0.743cqw, 10px); background:#E8EDF3; border-radius:clamp(599.4px, 74.275cqw, 999px);
                margin-bottom:clamp(8.4px, 1.041cqw, 14px);
            ">
                <div style="
                    width:{_never_width:.1f}%; height:clamp(6px, 0.743cqw, 10px);
                    background:#2F6DB3; border-radius:clamp(599.4px, 74.275cqw, 999px);
                "></div>
            </div>

            <div style="font-size:clamp(7.2px, 0.892cqw, 12px); color:#526176; margin-bottom:clamp(6px, 0.372cqw, 5px);">
                {_vip_label}
                <span style="float:right; color:#FF5B24; font-weight:700;">
                    {fmt.format(vip_value)} {unit}
                </span>
            </div>
            <div style="height:clamp(6px, 0.743cqw, 10px); background:#F0E5DF; border-radius:clamp(599.4px, 74.275cqw, 999px);">
                <div style="
                    width:{_vip_width:.1f}%; height:clamp(6px, 0.743cqw, 10px);
                    background:#FF5B24; border-radius:clamp(599.4px, 74.275cqw, 999px);
                "></div>
            </div>
        </div>
        """

    _gmv_card = _comparison_card(
        f"Average weekly GMV · {_period_label}",
        _gmv_vip,
        _gmv_never,
        _ratio_gmv,
        "NOK",
        "{:,.0f}",
        len(_vip),
        len(_never),
        float(_p_gmv),
    )

    _tx_card = _comparison_card(
        f"Average weekly purchases · {_period_label}",
        _tx_vip,
        _tx_never,
        _ratio_tx,
        "purchases",
        "{:.2f}",
        len(_vip),
        len(_never),
        float(_p_tx),
    )

    mo.vstack(
        [
            mo.hstack([ui_s5_cohort], gap=1.5, align="center"),
            mo.Html(f"""
                <div style="
                    background:#FFFAF7;position:relative; padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    border-radius:clamp(9.6px, 1.190cqw, 16px); font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">05<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px); background:#FF5B24; border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24; font-size:clamp(6.6px, 0.818cqw, 11px); font-weight:800;
                        letter-spacing:1.5px; text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">{_period_label}</div>
                    <div style="
                        color:#0B1F3A; font-size:clamp(15.6px, 1.933cqw, 26px); line-height:1.2;
                        font-weight:800; letter-spacing:-0.5px;
                    ">{_headline}</div>
                    <div style="
                        color:#526176; font-size:clamp(8.4px, 1.041cqw, 14px); line-height:1.5;
                        margin-top:clamp(6px, 0.743cqw, 10px);
                    ">{_description}</div>
                </div>
            """),
            mo.hstack(
                [mo.Html(_gmv_card), mo.Html(_tx_card)],
                widths="equal",
                gap=1.5,
            ),
            mo.Html(f"""
                <div style="
                    background:#FFFFFF; border:1px solid #F0E5DF;
                    border-radius:clamp(8.4px, 1.041cqw, 14px); padding:clamp(10.8px, 1.338cqw, 18px) clamp(12px, 1.487cqw, 20px);
                    color:#526176; font-family:Inter,Arial,sans-serif;
                    font-size:clamp(7.8px, 0.967cqw, 13px); line-height:1.6;
                ">
                    <strong style="color:#0B1F3A;">How to interpret this:</strong>
                    {_interpretation}
                </div>
            """),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_6():
    _panel = D["df_weekly_panel"]
    _w = ui_s6_window.value
    _choice = ui_s6_cohort.value

    # Preserve the existing cohort selection logic.
    if _choice == "All VIP members":
        _mask = _panel["vip_cohort"].ne("never_vip")
    elif _choice == "Joined organically":
        _mask = _panel["vip_cohort"].eq("pre_exp_organic")
    else:
        _mask = _panel["vip_cohort"].eq("exp_invitation_joiner")

    _sub = _panel[
        _mask & _panel["is_full_year_obs"] & _panel["rel_week_to_vip"].between(-_w, _w)
    ]

    _complete = _sub.groupby("user_id")["rel_week_to_vip"].nunique()
    _event = _sub[_sub["user_id"].isin(_complete[_complete.eq(2 * _w + 1)].index)]
    _n = int(_event["user_id"].nunique())

    _measures = {
        "Purchases / week": ("tx_count", "count"),
        "In-person GMV / week": ("in_person_gmv_nok", "money"),
        "Online GMV / week": ("online_gmv_nok", "money"),
        "Total GMV / week": ("gmv_nok", "money"),
    }

    _pre = _event[_event["rel_week_to_vip"].between(-_w, -1)]
    _post = _event[_event["rel_week_to_vip"].between(1, _w)]

    _rows = []
    for _label, (_col, _unit) in _measures.items():
        _p0 = _pre.groupby("user_id")[_col].mean()
        _p1 = _post.groupby("user_id")[_col].mean()
        _, _p_val = stats.ttest_rel(_p1, _p0)

        _rows.append(
            {
                "metric": _label,
                "pre": _p0.mean(),
                "post": _p1.mean(),
                "change": (_p1.mean() / _p0.mean() - 1) * 100,
                "p": _p_val,
            }
        )

    _table = pd.DataFrame(_rows)

    def _fmt(_v, _unit):
        if _unit == "count":
            return f"{_v:.1f}"
        return f"{_v:,.0f} NOK"

    # Styled, readable summary table.
    _html = (
        """
    <div style="
        background:#FFFFFF;
        border:1px solid #F0E5DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight:800;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:clamp(6px, 0.595cqw, 8px);
        ">Before vs. after enrollment</div>
        <table style="
            width:100%;
            border-collapse:collapse;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            line-height:1.4;
        ">
            <thead>
                <tr style="text-align:left;background:#FFFAF7;">
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">Metric</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">Before</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">After</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">Change</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">p-value</th>
                </tr>
            </thead>
            <tbody>
    """
        + "".join(
            f"""
                <tr style="border-top:1px solid #F0E5DF;">
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);font-weight:700;">{_r["metric"]}</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">{_fmt(_r["pre"], _measures[_r["metric"]][1])}</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">{_fmt(_r["post"], _measures[_r["metric"]][1])}</td>
                    <td style="
                        padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);
                        color:{"#FF5B24" if _r["change"] >= 0 else "#2F6DB3"};
                        font-weight:700;
                    ">{_r["change"]:+.1f}%</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">{_r["p"]:.3f}</td>
                </tr>
        """
            for _r in _table.to_dict(orient="records")
        )
        + """
            </tbody>
        </table>
    </div>
    """
    )

    # Prepare weekly channel-level trends.
    _long = _event.melt(
        id_vars=["user_id", "rel_week_to_vip"],
        value_vars=[
            "in_person_tx_count",
            "online_tx_count",
            "in_person_gmv_nok",
            "online_gmv_nok",
        ],
        var_name="measure",
        value_name="value",
    )

    _long["channel"] = np.where(
        _long["measure"].str.startswith("in_person"), "In person", "Online"
    )
    _long["metric"] = np.where(
        _long["measure"].str.endswith("gmv_nok"), "GMV", "Purchases"
    )

    _means = (
        _long.groupby(["rel_week_to_vip", "metric", "channel"])["value"]
        .mean()
        .reset_index()
    )

    _base = alt.Chart(_means).encode(
        x=alt.X(
            "rel_week_to_vip:Q",
            title="Weeks relative to VIP enrollment",
            axis=alt.Axis(values=list(range(-_w, _w + 1, 2)), grid=False),
        ),
        color=alt.Color(
            "channel:N",
            title="Channel",
            scale=alt.Scale(
                domain=["In person", "Online"],
                range=["#FF5B24", "#2F6DB3"],
            ),
            legend=alt.Legend(orient="top", labelFontSize=10, symbolSize=70),
        ),
    )

    def _lines(_metric, _title, _fmt):
        _line = (
            _base.transform_filter(alt.datum.metric == _metric)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                y=alt.Y(
                    "value:Q",
                    title=_title,
                    axis=alt.Axis(format=_fmt, gridColor="#F0E5DF", titleFontSize=11),
                ),
                tooltip=[
                    alt.Tooltip("rel_week_to_vip:Q", title="Week"),
                    alt.Tooltip("channel:N", title="Channel"),
                    alt.Tooltip("value:Q", title=_title, format=_fmt),
                ],
            )
            .properties(height=210, width=210)
        )

        _enrollment_line = (
            alt.Chart(alt.Data(values=[{"x": 0}]))
            .mark_rule(strokeDash=[4, 4], color="#8C8C8C", strokeWidth=1.5)
            .encode(x="x:Q")
        )

        return (
            alt.layer(_line, _enrollment_line)
            .properties(title=alt.Title(_title, fontSize=12, anchor="start"))
            .configure(background="#FFFFFF")
            .configure_view(stroke=None)
            .configure_axis(
                labelFont="Inter, Arial, sans-serif",
                titleFont="Inter, Arial, sans-serif",
                labelColor="#526176",
                titleColor="#0B1F3A",
                domainColor="#D8DEE7",
                tickColor="#D8DEE7",
            )
            .configure_legend(
                labelColor="#526176",
                titleColor="#0B1F3A",
                labelFont="Inter, Arial, sans-serif",
                orient="top",
            )
            .configure_title(
                font="Inter, Arial, sans-serif",
                color="#0B1F3A",
                fontSize=12,
                anchor="start",
            )
        )

    mo.vstack(
        [
            mo.hstack(
                [ui_s6_window, ui_s6_cohort],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    background:#FFFAF7;position:relative;
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">06<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Q1 · Do people who join VIP buy more?</div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        VIP enrollment coincides with<br>
                        <span style="color:#FF5B24;">higher in-person activity</span>
                    </div>
                    <div style="
                        color:#526176;
                        font-size:clamp(7.8px, 0.967cqw, 13px);
                        line-height:1.5;
                        margin-top:clamp(6px, 0.595cqw, 8px);
                    ">
                        Activity for the selected cohort before and after enrollment.
                        The dashed vertical line marks the enrollment week.
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    mo.hstack(
                        [
                            _lines(
                                "Purchases",
                                "Weekly purchases around enrollment",
                                ".1f",
                            ),
                            _lines(
                                "GMV",
                                "Weekly GMV around enrollment",
                                "~s",
                            ),
                        ],
                        gap=1,
                    ),
                    mo.vstack(
                        [
                            mo.Html(_html),
                            mo.Html(f"""
                                <div style="
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-radius:clamp(8.4px, 1.041cqw, 14px);
                                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                                    color:#526176;
                                    font-family:Inter,Arial,sans-serif;
                                    font-size:clamp(7.2px, 0.892cqw, 12px);
                                    line-height:1.5;
                                ">
                                    <strong style="color:#0B1F3A;">How to read this (N={_n}):</strong>
                                    Each user’s average weekly activity before enrollment
                                    is compared with their average after enrollment.
                                    The change is an association, not proof that VIP
                                    caused it, because users choose when to join.
                                </div>
                            """),
                        ],
                        gap=1,
                    ),
                ],
                widths=[1.15, 1],
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_7():
    _exp = D["df_exp"]
    _choice = ui_s7_wave.value

    if _choice.startswith("Summer"):
        _wave = _exp[_exp["experiment_wave"].eq("summer")]
    elif _choice.startswith("December"):
        _wave = _exp[_exp["experiment_wave"].eq("december")]
    else:
        _wave = _exp

    # Enrollment rates by experiment arm
    _rates = _wave.groupby("variant", as_index=False).agg(
        n=("user_id", "size"),
        ever=("enrolled_post_exposure", "sum"),
        within14=("enrolled_within_14d", "sum"),
    )
    _rates["ever_rate"] = _rates["ever"] / _rates["n"]
    _rates["within14_rate"] = _rates["within14"] / _rates["n"]

    _inv = _rates.set_index("variant").loc["invitation"]
    _ctl = _rates.set_index("variant").loc["control"]

    # Pooled two-proportion z-test for ever-enrollment
    _pool = (_inv["ever"] + _ctl["ever"]) / (_inv["n"] + _ctl["n"])
    _se = math.sqrt(_pool * (1 - _pool) * (1 / _inv["n"] + 1 / _ctl["n"]))
    _z = (_inv["ever_rate"] - _ctl["ever_rate"]) / _se if _se > 0 else 0
    _p_ever = float(2 * (1 - stats.norm.cdf(abs(_z))))
    _p_ever_txt = "p < 0.001" if _p_ever < 0.001 else f"p = {_p_ever:.3f}"

    # Display labels: experiment arms are capitalized in every chart and legend.
    _ARM_LABELS = {"invitation": "Invitation", "control": "Control"}

    # Bar chart: shorter labels prevent axis-label overlap
    _rate_long = _rates.melt(
        id_vars=["variant", "n"],
        value_vars=["ever_rate", "within14_rate"],
        var_name="measure",
        value_name="rate",
    )
    _rate_long["metric"] = np.where(
        _rate_long["measure"].eq("ever_rate"),
        "By end of observation",
        "Within 14 days",
    )
    _rate_long["variant"] = _rate_long["variant"].map(_ARM_LABELS)

    _chart_colors = alt.Scale(
        domain=["Invitation", "Control"],
        range=["#FF5B24", "#2F6DB3"],
    )

    _legend = alt.Legend(
        orient="top",
        direction="horizontal",
        columns=2,
        labelFontSize=11,
        symbolSize=80,
        padding=4,
    )

    _bars_base = alt.Chart(_rate_long).encode(
        x=alt.X(
            "metric:N",
            title=None,
            sort=["Within 14 days", "By end of observation"],
            axis=alt.Axis(labelAngle=0, labelLimit=150, labelFontSize=11),
        ),
        xOffset=alt.XOffset("variant:N", title=None),
        color=alt.Color(
            "variant:N",
            title=None,
            scale=_chart_colors,
            legend=_legend,
        ),
    )

    _signup_chart = alt.layer(
        _bars_base.mark_bar(
            cornerRadiusTopLeft=4,
            cornerRadiusTopRight=4,
        ).encode(
            y=alt.Y(
                "rate:Q",
                title="Share of assigned users",
                axis=alt.Axis(format="%", gridColor="#F0E5DF"),
            )
        ),
        _bars_base.mark_text(
            dy=-7,
            fontSize=11,
            fontWeight=700,
            color="#0B1F3A",
        ).encode(
            y=alt.Y("rate:Q"),
            text=alt.Text("rate:Q", format=".0%"),
        ),
    ).properties(
        height=210,
        width=340,
        title="Enrollment rate by experiment arm",
    )

    # Baseline characteristics
    _bal_rows = []
    for _col, _label in (
        ("june_tx_count", "June transactions (selection variable)"),
        ("pre_tx_per_week", "Pre-exposure purchases / week"),
    ):
        _iv = _wave.loc[_wave["variant"].eq("invitation"), _col].dropna()
        _ct = _wave.loc[_wave["variant"].eq("control"), _col].dropna()

        if len(_iv) > 1 and len(_ct) > 1:
            _, _p_balance = stats.ttest_ind(_iv, _ct, equal_var=False)
        else:
            _p_balance = float("nan")

        _bal_rows.append(
            {
                "metric": _label,
                "invitation": _iv.mean(),
                "control": _ct.mean(),
                "p": _p_balance,
            }
        )

    _bal = pd.DataFrame(_bal_rows)

    _bal_html = (
        """
    <div style="
        background:#FFFFFF;
        border:1px solid #F0E5DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight:800;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:clamp(6px, 0.743cqw, 10px);
        ">Baseline characteristics</div>
        <table style="
            width:100%;
            border-collapse:collapse;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            line-height:1.45;
        ">
            <thead>
                <tr style="text-align:left;background:#FFFAF7;">
                    <th style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">Baseline</th>
                    <th style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">Invitation</th>
                    <th style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">Control</th>
                    <th style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">p-value</th>
                </tr>
            </thead>
            <tbody>
    """
        + "".join(
            f"""
                <tr style="border-top:1px solid #F0E5DF;">
                    <td style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);font-weight:700;">{_r["metric"]}</td>
                    <td style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">{_r["invitation"]:.2f}</td>
                    <td style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">{_r["control"]:.2f}</td>
                    <td style="padding:clamp(6px, 0.669cqw, 9px) clamp(6px, 0.520cqw, 7px);">{_r["p"]:.3f}</td>
                </tr>
        """
            for _r in _bal.to_dict(orient="records")
        )
        + """
            </tbody>
        </table>
    </div>
    """
    )

    # Cumulative enrollment curve
    _curve_rows = []
    for _variant, _arm_label in _ARM_LABELS.items():
        _g = _wave[_wave["variant"].eq(_variant)]
        _weeks = _g["days_to_enroll"] / 7

        for _week in range(17):
            _curve_rows.append(
                {
                    "variant": _arm_label,
                    "week": _week,
                    "rate": float((_weeks <= _week).sum()) / len(_g),
                }
            )

    _curve = pd.DataFrame(_curve_rows)

    _curve_chart = (
        alt.Chart(_curve)
        .mark_line(
            interpolate="step-after",
            point=True,
            strokeWidth=2.5,
        )
        .encode(
            x=alt.X(
                "week:Q",
                title="Weeks since exposure",
                axis=alt.Axis(values=list(range(0, 17, 2)), grid=False),
            ),
            y=alt.Y(
                "rate:Q",
                title="Cumulative share enrolled",
                axis=alt.Axis(format="%", gridColor="#F0E5DF"),
            ),
            color=alt.Color(
                "variant:N",
                title=None,
                scale=_chart_colors,
                legend=_legend,
            ),
            tooltip=[
                alt.Tooltip("week:Q", title="Week"),
                alt.Tooltip("variant:N", title="Experiment arm"),
                alt.Tooltip("rate:Q", title="Cumulative enrollment", format=".1%"),
            ],
        )
    )

    _wk = ui_s7_week.value

    _rule = (
        alt.Chart(alt.Data(values=[{"x": _wk}]))
        .mark_rule(
            strokeDash=[4, 4],
            color="#FF5B24",
            strokeWidth=1.5,
        )
        .encode(x="x:Q")
    )

    _curve_chart = alt.layer(_curve_chart, _rule).properties(
        height=190,
        title="Cumulative enrollment over time",
    )

    _cum_inv = _curve[(_curve["variant"].eq("Invitation")) & (_curve["week"].eq(_wk))][
        "rate"
    ].iloc[0]

    _cum_ctl = _curve[(_curve["variant"].eq("Control")) & (_curve["week"].eq(_wk))][
        "rate"
    ].iloc[0]

    _week_lift_pp = (_cum_inv - _cum_ctl) * 100
    _ever_lift_pp = (_inv["ever_rate"] - _ctl["ever_rate"]) * 100

    # Shared chart styling
    _chart_theme = {
        "background": "#FFFFFF",
        "view": {"stroke": None},
        "axis": {
            "labelColor": "#526176",
            "titleColor": "#0B1F3A",
            "domainColor": "#D8DEE7",
            "tickColor": "#D8DEE7",
            "gridColor": "#F0E5DF",
            "labelFont": "Inter, Arial, sans-serif",
            "titleFont": "Inter, Arial, sans-serif",
            "titleFontWeight": 700,
        },
        "legend": {
            "labelColor": "#526176",
            "titleColor": "#0B1F3A",
            "labelFont": "Inter, Arial, sans-serif",
            "titleFont": "Inter, Arial, sans-serif",
        },
        "title": {
            "color": "#0B1F3A",
            "font": "Inter, Arial, sans-serif",
            "fontSize": 13,
            "fontWeight": 700,
            "anchor": "start",
        },
    }

    _signup_chart = _signup_chart.configure(**_chart_theme)
    _curve_chart = _curve_chart.configure(**_chart_theme)

    mo.vstack(
        [
            mo.hstack(
                [ui_s7_wave, ui_s7_week],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    background:#FFFAF7;position:relative;
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">07<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Q2 · Does inviting people to join VIP help in making them come back? </div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        The invitation increased<br>
                        <span style="color:#FF5B24;">VIP enrollment</span>
                    </div>
                    <div style="
                        color:#526176;
                        font-size:clamp(7.8px, 0.967cqw, 13px);
                        line-height:1.5;
                        margin-top:clamp(6px, 0.595cqw, 8px);
                    ">
                        Compare enrollment between assigned experiment arms,
                        then follow how the gap develops over time.
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    mo.vstack(
                        [
                            _signup_chart,
                            mo.Html(_bal_html),
                            mo.Html("""
                                <div style="
                                    color:#526176;
                                    font-family:Inter,Arial,sans-serif;
                                    font-size:clamp(7.2px, 0.892cqw, 12px);
                                    line-height:1.5;
                                    padding:clamp(6px, 0.149cqw, 2px) clamp(6px, 0.149cqw, 2px)0;
                                ">
                                    Invited and Control arms had near-identical June
                                    purchase frequency prior to assignment
                                    (p = 0.903), confirming balanced randomization.
                                </div>
                            """),
                        ],
                        gap=1,
                    ),
                    mo.vstack(
                        [
                            _curve_chart,
                            mo.Html(f"""
                                <div style="
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-left:5px solid #FF5B24;
                                    border-radius:clamp(8.4px, 1.041cqw, 14px);
                                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                                    color:#0B1F3A;
                                    font-family:Inter,Arial,sans-serif;
                                ">
                                    <div style="
                                        color:#FF5B24;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        font-weight:800;
                                        letter-spacing:1px;
                                        text-transform:uppercase;
                                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                                    ">Cumulative enrollment · Week {_wk}</div>
                                    <div style="
                                        font-size:clamp(12px, 1.487cqw, 20px);
                                        line-height:1.3;
                                        font-weight:800;
                                        margin-bottom:clamp(6px, 0.446cqw, 6px);
                                    ">
                                        {_cum_inv:.1%} invitation
                                        <span style="color:#526176;font-weight:500;">vs.</span>
                                        {_cum_ctl:.1%} control
                                    </div>
                                    <div style="
                                        color:#FF5B24;
                                        font-size:clamp(9px, 1.115cqw, 15px);
                                        font-weight:800;
                                    ">
                                        Difference: {_week_lift_pp:+.1f} percentage points
                                    </div>
                                    <div style="
                                        color:#526176;
                                        font-size:clamp(7.2px, 0.892cqw, 12px);
                                        line-height:1.5;
                                        margin-top:clamp(6px, 0.595cqw, 8px);
                                    ">
                                        Ever-enrollment difference across the observation
                                        period: {_ever_lift_pp:+.1f} pp
                                        ({_p_ever_txt}).
                                    </div>
                                </div>
                            """),
                        ],
                        gap=1,
                    ),
                ],
                widths="equal",
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_8():
    _exp = D["df_exp"]
    _w = int(ui_s8_window.value)
    _tier = ui_s8_june_tier.value
    _scale_late = bool(ui_s8_scale_late.value)

    _summer = _exp[_exp["experiment_wave"].eq("summer")]

    if _tier == "Low June frequency":
        _group = _summer[_summer["june_freq_tier"].eq("Low")]
    elif _tier == "Medium June frequency":
        _group = _summer[_summer["june_freq_tier"].eq("Medium")]
    elif _tier == "High June frequency":
        _group = _summer[_summer["june_freq_tier"].eq("High")]
    else:
        _group = _summer

    _metrics = [
        ("Retained in last 28 days", "retained_last_28d", "share"),
        ("Active week share", f"post_active_week_share_{_w}w", "share"),
        ("Purchases per week", f"post_tx_per_week_{_w}w", "count"),
        ("GMV per week", f"post_gmv_per_week_{_w}w", "money"),
    ]

    _treat = _group["variant"].eq("invitation").to_numpy()

    # Net enrollment lift inside the selected group: the ITT -> complier scaling factor.
    _net_compliance = float(
        _group.loc[_treat, "enrolled_post_exposure"].mean()
        - _group.loc[~_treat, "enrolled_post_exposure"].mean()
    )
    _scale = _scale_late and _net_compliance > 0
    _divisor = _net_compliance if _scale else 1.0

    _rows = []
    for _label, _col, _unit in _metrics:
        _y = _group[_col].astype(float).to_numpy()
        _y_inv = _y[_treat]
        _y_ctl = _y[~_treat]

        _inv_mean = float(_y_inv.mean())
        _ctl_mean = float(_y_ctl.mean())
        _diff = _inv_mean - _ctl_mean

        _se = math.sqrt(
            float(_y_inv.var(ddof=1)) / len(_y_inv)
            + float(_y_ctl.var(ddof=1)) / len(_y_ctl)
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            _, _p = stats.ttest_ind(_y_inv, _y_ctl, equal_var=False)

        _lo = _diff - 1.96 * _se
        _hi = _diff + 1.96 * _se

        # Express difference and confidence interval relative to control average,
        # then divide by the net signup lift when complier scaling is on.
        if _ctl_mean != 0:
            _diff_pct = _diff / _ctl_mean * 100 / _divisor
            _lo_pct = _lo / _ctl_mean * 100 / _divisor
            _hi_pct = _hi / _ctl_mean * 100 / _divisor
        else:
            _diff_pct = _lo_pct = _hi_pct = float("nan")

        _rows.append(
            {
                "metric": _label,
                "unit": _unit,
                "control": _ctl_mean,
                "invitation": _inv_mean,
                "diff_pct": _diff_pct,
                "lo_pct": _lo_pct,
                "hi_pct": _hi_pct,
                "p": float(_p),
            }
        )

    _df = pd.DataFrame(_rows)

    def _fmt(_value, _unit):
        if _unit == "share":
            return f"{_value:.1%}"
        if _unit == "count":
            return f"{_value:.1f}"
        return f"{_value:,.0f} NOK"

    _estimates_html = (
        """
    <div style="
        box-sizing:border-box;
        width:100%;
        background:#FFFFFF;
        border:1px solid #F0E5DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight:800;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:clamp(6px, 0.743cqw, 10px);
        ">Outcome estimates</div>
        <table style="
            border-collapse:collapse;
            table-layout:auto;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            line-height:1.4;
            width:100%;
        ">
            <thead>
                <tr style="text-align:left;background:#FFFAF7;">
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);">Metric</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;">Control</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;">Invitation</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;">Diff. [95% CI]</th>
                    <th style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;">p</th>
                </tr>
            </thead>
            <tbody>
    """
        + "".join(
            f"""
                <tr style="border-top:1px solid #F0E5DF;">
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);font-weight:700;">{_r["metric"]}</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;white-space:nowrap;">{_fmt(_r["control"], _r["unit"])}</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;white-space:nowrap;">{_fmt(_r["invitation"], _r["unit"])}</td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;white-space:nowrap;">
                        {_r["diff_pct"]:+.1f}% [{_r["lo_pct"]:+.1f}, {_r["hi_pct"]:+.1f}]
                    </td>
                    <td style="padding:clamp(6px, 0.595cqw, 8px) clamp(6px, 0.446cqw, 6px);text-align:right;">{_r["p"]:.3f}</td>
                </tr>
        """
            for _r in _df.to_dict(orient="records")
        )
        + """
            </tbody>
        </table>
    </div>
    """
    )

    # Forest plot
    _base = alt.Chart(_df).encode(
        y=alt.Y(
            "metric:N",
            sort=_df["metric"].tolist(),
            title=None,
            axis=alt.Axis(labelFontSize=11, labelLimit=190),
        ),
        x=alt.X(
            "diff_pct:Q",
            title="Difference vs. control average (%)",
            axis=alt.Axis(labelFontSize=10, gridColor="#F0E5DF", titleFontSize=11),
        ),
    )

    _forest = alt.layer(
        alt.Chart(alt.Data(values=[{"x": 0}]))
        .mark_rule(
            strokeDash=[4, 4],
            color="#0B1F3A",
            strokeWidth=1.5,
        )
        .encode(x="x:Q"),
        _base.mark_rule(
            strokeWidth=2,
            color="#FF5B24",
        ).encode(
            x="lo_pct:Q",
            x2="hi_pct:Q",
        ),
        _base.mark_point(
            filled=True,
            size=80,
            color="#2F6DB3",
        ).encode(
            tooltip=[
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("diff_pct:Q", title="Difference (%)", format="+.1f"),
                alt.Tooltip("lo_pct:Q", title="95% CI low", format="+.1f"),
                alt.Tooltip("hi_pct:Q", title="95% CI high", format="+.1f"),
            ]
        ),
    ).properties(
        height=250,
        width="container",
        title=f"Invitation vs. control · {_w}-week window",
    )

    # Shared chart styling
    _chart_theme = {
        "background": "#FFFFFF",
        "view": {"stroke": None},
        "axis": {
            "labelColor": "#526176",
            "titleColor": "#0B1F3A",
            "domainColor": "#D8DEE7",
            "tickColor": "#D8DEE7",
            "gridColor": "#F0E5DF",
            "labelFont": "Inter, Arial, sans-serif",
            "titleFont": "Inter, Arial, sans-serif",
            "titleFontWeight": 700,
        },
        "title": {
            "color": "#0B1F3A",
            "font": "Inter, Arial, sans-serif",
            "fontSize": 13,
            "fontWeight": 700,
            "anchor": "start",
        },
    }

    _forest = _forest.configure(**_chart_theme)

    _all_include_zero = bool(((_df["lo_pct"] <= 0) & (_df["hi_pct"] >= 0)).all())

    if _all_include_zero:
        _takeaway = (
            "All 95% confidence intervals include zero, so we cannot conclude the "
            "invitation changed retention or spending."
        )
    else:
        _takeaway = (
            "At least one 95% confidence interval excludes zero. Review that "
            "outcome before drawing a conclusion."
        )

    _scale_note = (
        f" Estimates are complier-scaled by the net enrollment lift "
        f"(×{1 / _net_compliance:.2f})."
        if _scale
        else ""
    )

    mo.vstack(
        [
            mo.hstack(
                [ui_s8_window, ui_s8_june_tier, ui_s8_scale_late],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    box-sizing:border-box;
                    width:100%;
                    background:#FFFAF7;position:relative;
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">08<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Q2 · Does inviting people to join VIP help in making them come back?</div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        The invitation did not show a clear change<br>
                        <span style="color:#FF5B24;">in retention or spend</span>
                    </div>
                    <div style="
                        color:#526176;
                        font-size:clamp(7.8px, 0.967cqw, 13px);
                        line-height:1.5;
                        margin-top:clamp(6px, 0.595cqw, 8px);
                    ">
                        Compare post-exposure activity and spending between
                        invitation and control users.
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    mo.vstack(
                        [
                            _forest,
                            mo.Html(f"""
                                <div style="
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-left:5px solid #FF5B24;
                                    border-radius:clamp(8.4px, 1.041cqw, 14px);
                                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                                    color:#0B1F3A;
                                    font-family:Inter,Arial,sans-serif;
                                ">
                                    <div style="
                                        color:#FF5B24;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        font-weight:800;
                                        letter-spacing:1px;
                                        text-transform:uppercase;
                                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                                    ">Interpretation</div>
                                    <div style="font-size:clamp(7.8px, 0.967cqw, 13px);line-height:1.5;font-weight:700;">
                                        {_takeaway}
                                    </div>
                                    <div style="
                                        color:#526176;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        line-height:1.5;
                                        margin-top:clamp(6px, 0.446cqw, 6px);
                                    ">
                                        Points show estimated differences; lines show
                                        95% confidence intervals.{_scale_note}
                                        June-frequency groups use pre-experiment activity.
                                    </div>
                                </div>
                            """),
                        ],
                        gap=1,
                    ),
                    mo.Html(_estimates_html),
                ],
                widths=[1, 1.15],
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_9():
    _c = D["constants"]
    _cat = D["df_categories"]
    # Readable labels: online sectors drop the "(Online)" suffix;
    # the in-person row keeps "(In person)" so both Grocery/Food
    # rows stay distinct.
    _cat = _cat.assign(label=_cat["label"].str.replace(" (Online)", "", regex=False))
    _order = _cat["label"].tolist()

    # Keep the channel suffix on the axis so Grocery/Food (In person) and
    # Grocery/Food (Online) stay distinguishable.
    _label_axis = alt.Axis(
        labelFontSize=11,
        labelLimit=180,
    )

    _bars = (
        alt.Chart(_cat)
        .mark_bar()
        .encode(
            y=alt.Y(
                "label:N",
                sort=_order,
                title=None,
                axis=_label_axis,
            ),
            x=alt.X(
                "gmv_share:Q",
                title="GMV share (%)",
                axis=alt.Axis(
                    labelFontSize=10,
                    gridColor="#F0E5DF",
                ),
            ),
            color=alt.Color(
                "channel:N",
                title=None,
                scale=alt.Scale(
                    domain=["In person", "Online"],
                    range=["#FF5B24", "#2F6DB3"],
                ),
                legend=alt.Legend(
                    orient="top",
                    labelFontSize=11,
                ),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Sector"),
                alt.Tooltip("channel:N", title="Channel"),
                alt.Tooltip("gmv_share:Q", title="GMV share (%)", format=".1f"),
                alt.Tooltip("take_rate:Q", title="Take rate (%)", format=".2f"),
            ],
        )
        .properties(width=330, height=240)
    )

    # Separate take-rate column, aligned to the same sector rows
    _take_rate = (
        alt.Chart(_cat)
        .mark_text(
            align="right",
            baseline="middle",
            fontSize=11,
            fontWeight=600,
            color="#0B1F3A",
        )
        .encode(
            y=alt.Y(
                "label:N",
                sort=_order,
                title=None,
                axis=None,
            ),
            x=alt.value(88),
            text=alt.Text("take_rate:Q", format=".2f"),
            tooltip=[
                alt.Tooltip("label:N", title="Sector"),
                alt.Tooltip("take_rate:Q", title="Take rate (%)", format=".2f"),
            ],
        )
        .properties(
            width=96,
            height=290,
            title=alt.Title(
                "Take rate (%)",
                font="Inter, Arial, sans-serif",
                fontSize=11,
                color="#526176",
                anchor="end",
            ),
        )
    )

    _chart = (
        alt.hconcat(
            _bars,
            _take_rate,
            spacing=12,
        )
        .resolve_scale(y="shared")
        .properties(
            title=alt.Title(
                "GMV share by sector",
                subtitle="Bar length shows GMV share; the right column shows take rate",
                font="Inter, Arial, sans-serif",
                fontSize=14,
                color="#0B1F3A",
                subtitleFont="Inter, Arial, sans-serif",
                subtitleFontSize=11,
                subtitleColor="#526176",
                anchor="start",
            ),
        )
        .configure(
            background="#FFFFFF",
        )
        .configure_view(
            stroke=None,
        )
        .configure_axis(
            labelColor="#526176",
            titleColor="#0B1F3A",
            domainColor="#D8DEE7",
            tickColor="#D8DEE7",
            gridColor="#F0E5DF",
            labelFont="Inter, Arial, sans-serif",
            titleFont="Inter, Arial, sans-serif",
            titleFontWeight=700,
        )
        .configure_legend(
            labelColor="#526176",
            titleColor="#0B1F3A",
            labelFont="Inter, Arial, sans-serif",
            titleFont="Inter, Arial, sans-serif",
        )
    )

    _extra = ui_s9_extra_online_tx.value
    _bps = ui_s9_point_cost_bps.value

    # Assumption: extra online purchases per VIP per month
    _tx_year = _c["n_vip"] * 12 * _extra
    _gmv = _tx_year * _c["avg_online_ticket"]
    _fee = _gmv * _c["online_take"]
    _cost = _gmv * _bps / 10000
    _net = _fee - _cost

    _scenario = mo.Html(f"""
    <div style="
        box-sizing:border-box;
        width:100%;
        background:#FFFFFF;
        border:1px solid #F0E5DF;
        border-radius:clamp(8.4px, 1.041cqw, 14px);
        padding:clamp(9.6px, 1.190cqw, 16px);
        color:#0B1F3A;
        font-family:Inter,Arial,sans-serif;
    ">
        <div style="
            color:#FF5B24;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            font-weight:800;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:clamp(6px, 0.446cqw, 6px);
        ">Illustrative online cross-sell scenario</div>

        <div style="
            color:#526176;
            font-size:clamp(7.2px, 0.892cqw, 12px);
            line-height:1.45;
            margin-bottom:clamp(8.4px, 1.041cqw, 14px);
        ">
            What if each VIP made <b>{_extra:.1f} extra online purchases per month?</b>
        </div>

        <div style="
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(145px,1fr));
            gap:clamp(6px, 0.595cqw, 8px);
            align-items:stretch;
        ">
            <div style="background:#FFFAF7;border:1px solid #F0E5DF;border-radius:clamp(6px, 0.743cqw, 10px);padding:clamp(7.2px, 0.892cqw, 12px);">
                <div style="font-size:clamp(6px, 0.743cqw, 10px);color:#526176;margin-bottom:clamp(6px, 0.446cqw, 6px);">1 · Extra purchases / year</div>
                <div style="font-size:clamp(12px, 1.487cqw, 20px);font-weight:800;color:#0B1F3A;">{_tx_year:,.0f}</div>
                <div style="font-size:clamp(6.6px, 0.818cqw, 11px);color:#526176;margin-top:clamp(6px, 0.372cqw, 5px);">VIPs × 12 × {_extra:.1f}</div>
            </div>

            <div style="background:#FFFAF7;border:1px solid #F0E5DF;border-radius:clamp(6px, 0.743cqw, 10px);padding:clamp(7.2px, 0.892cqw, 12px);">
                <div style="font-size:clamp(6px, 0.743cqw, 10px);color:#526176;margin-bottom:clamp(6px, 0.446cqw, 6px);">2 · Incremental online GMV</div>
                <div style="font-size:clamp(12px, 1.487cqw, 20px);font-weight:800;color:#0B1F3A;">NOK {_gmv:,.0f}</div>
                <div style="font-size:clamp(6.6px, 0.818cqw, 11px);color:#526176;margin-top:clamp(6px, 0.372cqw, 5px);">Purchases × {_c["avg_online_ticket"]:,.0f} NOK average ticket</div>
            </div>

            <div style="background:#FFFAF7;border:1px solid #F0E5DF;border-radius:clamp(6px, 0.743cqw, 10px);padding:clamp(7.2px, 0.892cqw, 12px);">
                <div style="font-size:clamp(6px, 0.743cqw, 10px);color:#526176;margin-bottom:clamp(6px, 0.446cqw, 6px);">3 · Estimated fee revenue</div>
                <div style="font-size:clamp(12px, 1.487cqw, 20px);font-weight:800;color:#0B1F3A;">NOK {_fee:,.0f}</div>
                <div style="font-size:clamp(6.6px, 0.818cqw, 11px);color:#526176;margin-top:clamp(6px, 0.372cqw, 5px);">GMV × {_c["online_take"]:.2%} take rate</div>
            </div>

            <div style="background:#FFFAF7;border:1px solid #F0E5DF;border-radius:clamp(6px, 0.743cqw, 10px);padding:clamp(7.2px, 0.892cqw, 12px);">
                <div style="font-size:clamp(6px, 0.743cqw, 10px);color:#526176;margin-bottom:clamp(6px, 0.446cqw, 6px);">4 · Point cost</div>
                <div style="font-size:clamp(12px, 1.487cqw, 20px);font-weight:800;color:#0B1F3A;">− NOK {_cost:,.0f}</div>
                <div style="font-size:clamp(6.6px, 0.818cqw, 11px);color:#526176;margin-top:clamp(6px, 0.372cqw, 5px);">GMV × {_bps} bps assumed cost</div>
            </div>
        </div>

        <div style="
            margin-top:clamp(6px, 0.743cqw, 10px);
            padding:clamp(8.4px, 1.041cqw, 14px);
            background:#0B1F3A;
            border-radius:clamp(6px, 0.743cqw, 10px);
            color:#FFFFFF;
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:clamp(7.2px, 0.892cqw, 12px);
            flex-wrap:wrap;
        ">
            <div>
                <div style="font-size:clamp(6px, 0.743cqw, 10px);color:#D8DEE7;text-transform:uppercase;letter-spacing:1px;">
                    Estimated fee revenue less point cost
                </div>
                <div style="font-size:clamp(7.2px, 0.892cqw, 12px);color:#FFFFFF;margin-top:clamp(6px, 0.297cqw, 4px);">
                    Fee revenue − point cost
                </div>
            </div>
            <div style="font-size:clamp(13.2px, 1.636cqw, 22px);font-weight:800;color:#FF8A63;">
                NOK {_net:,.0f}
            </div>
        </div>

        <div style="
            color:#526176;
            font-size:clamp(6.6px, 0.818cqw, 11px);
            line-height:1.45;
            margin-top:clamp(6px, 0.743cqw, 10px);
        ">
            Illustrative only. Assumes 195 VIP users (2025 total).
            Take rate is average of all online take rates.
        </div>
    </div>
    """)

    _ideas = mo.Html("""
        <div style="
            box-sizing:border-box;
            width:100%;
            background:#FFFFFF;
            border:1px solid #F0E5DF;
            border-left:5px solid #2F6DB3;
            border-radius:clamp(8.4px, 1.041cqw, 14px);
            padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
            color:#0B1F3A;
            font-family:Inter,Arial,sans-serif;
        ">
            <div style="
                color:#2F6DB3;
                font-size:clamp(6.6px, 0.818cqw, 11px);
                font-weight:800;
                letter-spacing:1px;
                text-transform:uppercase;
                margin-bottom:clamp(6px, 0.595cqw, 8px);
            ">Ideas to test</div>
            <div style="font-size:clamp(8.4px, 1.041cqw, 14px);line-height:1.65;">
                <b>1.</b> Replace batch signup invites with a 14-day inactivity trigger <br>
                <b>2.</b> Test online checkout point multipliers to encourage online purchases.<br>
            </div>
        </div>
    """)

    mo.vstack(
        [
            mo.hstack(
                [ui_s9_extra_online_tx, ui_s9_point_cost_bps],
                gap=1.5,
                align="center",
            ),
            mo.Html("""
                <div style="
                    box-sizing:border-box;
                    width:100%;
                    background:#FFFAF7;position:relative;
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">09<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Q3 · Recommendations &amp; next steps</div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        Turn VIP membership into an active habit
                    </div>
                    <div style="
                        color:#526176;
                        font-size:clamp(7.8px, 0.967cqw, 13px);
                        line-height:1.5;
                        margin-top:clamp(6px, 0.595cqw, 8px);
                    ">
                        Sector GMV and take rates can help identify where online
                        cross-sell may be worth testing.
                    </div>
                </div>
            """),
            mo.hstack(
                [
                    mo.vstack(
                        [
                            _chart,
                            mo.Html("""
                                <div style="
                                    color:#526176;
                                    font-family:Inter,Arial,sans-serif;
                                    font-size:clamp(6.6px, 0.818cqw, 11px);
                                    line-height:1.45;
                                ">
                                    GMV share describes transaction value mix; take rate
                                    is shown as a label and is not encoded by bar length.
                                </div>
                            """),
                            _ideas,
                        ],
                        gap=1,
                    ),
                    _scenario,
                ],
                widths=[1.05, 1],
                gap=1.5,
                align="start",
            ),
        ],
        gap=1,
    )
    return


@app.cell(hide_code=True)
def slide_10():
    mo.vstack(
        [
            mo.Html("""
                <div style="
                    box-sizing:border-box;
                    width:100%;
                    background:#FFFAF7;position:relative;
                    border-radius:clamp(9.6px, 1.190cqw, 16px);
                    padding:clamp(13.2px, 1.636cqw, 22px) clamp(14.4px, 1.784cqw, 24px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">10<span style="color:#8C8C8C;"> / 11</span></div>
                    <div style="
                        height:clamp(6px, 0.372cqw, 5px);
                        background:#FF5B24;
                        border-radius:clamp(6px, 0.595cqw, 8px);
                        margin-bottom:clamp(9.6px, 1.190cqw, 16px);
                    "></div>
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6.6px, 0.818cqw, 11px);
                        font-weight:800;
                        letter-spacing:1.5px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">Q3 · Recommendations &amp; next steps</div>
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(15.6px, 1.933cqw, 26px);
                        line-height:1.2;
                        font-weight:800;
                        letter-spacing:-0.5px;
                    ">
                        What we left for later
                    </div>
                    <div style="
                        color:#526176;
                        font-size:clamp(8.4px, 1.041cqw, 14px);
                        line-height:1.5;
                        margin-top:clamp(6px, 0.743cqw, 10px);
                    ">
                        Focus the analysis on reliable, decision-ready evidence.
                        Revisit these areas when the data can support stronger conclusions.
                    </div>
                </div>
            """),
            mo.vstack(
                [
                    mo.Html("""
                        <div style="
                            color:#526176;
                            font-family:Inter,Arial,sans-serif;
                            font-size:clamp(6.6px, 0.818cqw, 11px);
                            font-weight:800;
                            letter-spacing:1px;
                            text-transform:uppercase;
                            margin:4px 0 2px;
                        ">Deferred analyses</div>
                    """),
                    mo.hstack(
                        [
                            mo.Html("""
                                <div style="
                                    box-sizing:border-box;
                                    width:100%;
                                    height:100%;
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-top:4px solid #FF5B24;
                                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                                    padding:clamp(9.6px, 1.190cqw, 16px);
                                    color:#0B1F3A;
                                    font-family:Inter,Arial,sans-serif;
                                ">
                                    <div style="
                                        color:#FF5B24;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        font-weight:800;
                                        letter-spacing:0.8px;
                                        text-transform:uppercase;
                                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                                    ">01 · Card-level analysis</div>
                                    <div style="font-size:clamp(9.6px, 1.190cqw, 16px);font-weight:800;margin-bottom:clamp(6px, 0.595cqw, 8px);">
                                        cards.csv
                                    </div>
                                    <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                                        <b style="color:#0B1F3A;">Why deferred</b><br>
                                        Card status is only known at the 2026-01-01 cutoff, not historical
                                        purchase time. Optional table, so not investigated further.
                                    </div>
                                    <div style="
                                        margin-top:clamp(8.4px, 1.041cqw, 14px);
                                        padding-top:clamp(6px, 0.743cqw, 10px);
                                        border-top:1px solid #F0E5DF;
                                        font-size:clamp(7.2px, 0.892cqw, 12px);
                                        line-height:1.45;
                                    ">
                                        <b>Revisit when:</b> card history (issued, blocked, cancelled) exists.
                                    </div>
                                </div>
                            """),
                            mo.Html("""
                                <div style="
                                    box-sizing:border-box;
                                    width:100%;
                                    height:100%;
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-top:4px solid #2F6DB3;
                                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                                    padding:clamp(9.6px, 1.190cqw, 16px);
                                    color:#0B1F3A;
                                    font-family:Inter,Arial,sans-serif;
                                ">
                                    <div style="
                                        color:#2F6DB3;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        font-weight:800;
                                        letter-spacing:0.8px;
                                        text-transform:uppercase;
                                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                                    ">02 · Age segmentation</div>
                                    <div style="font-size:clamp(9.6px, 1.190cqw, 16px);font-weight:800;margin-bottom:clamp(6px, 0.595cqw, 8px);">
                                        16 age buckets
                                    </div>
                                    <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                                        <b style="color:#0B1F3A;">Why deferred</b><br>
                                        Splitting 419 users into 16 four-year bands leaves about 26 per
                                        band, and only ~7 per experiment arm — too few to compare
                                        reliably.
                                    </div>
                                    <div style="
                                        margin-top:clamp(8.4px, 1.041cqw, 14px);
                                        padding-top:clamp(6px, 0.743cqw, 10px);
                                        border-top:1px solid #F0E5DF;
                                        font-size:clamp(7.2px, 0.892cqw, 12px);
                                        line-height:1.45;
                                    ">
                                        <b>Revisit with:</b> pooled years or wider age bands.
                                    </div>
                                </div>
                            """),
                            mo.Html("""
                                <div style="
                                    box-sizing:border-box;
                                    width:100%;
                                    height:100%;
                                    background:#FFFFFF;
                                    border:1px solid #F0E5DF;
                                    border-top:4px solid #8C8C8C;
                                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                                    padding:clamp(9.6px, 1.190cqw, 16px);
                                    color:#0B1F3A;
                                    font-family:Inter,Arial,sans-serif;
                                ">
                                    <div style="
                                        color:#8C8C8C;
                                        font-size:clamp(6.6px, 0.818cqw, 11px);
                                        font-weight:800;
                                        letter-spacing:0.8px;
                                        text-transform:uppercase;
                                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                                    ">03 · December retention</div>
                                    <div style="font-size:clamp(9.6px, 1.190cqw, 16px);font-weight:800;margin-bottom:clamp(6px, 0.595cqw, 8px);">
                                        December wave
                                    </div>
                                    <div style="font-size:clamp(7.2px, 0.892cqw, 12px);line-height:1.5;color:#526176;">
                                        <b style="color:#0B1F3A;">Why deferred</b><br>
                                        Limited days of observation were available
                                        before the 2026-01-01 cutoff.
                                    </div>
                                    <div style="
                                        margin-top:clamp(8.4px, 1.041cqw, 14px);
                                        padding-top:clamp(6px, 0.743cqw, 10px);
                                        border-top:1px solid #F0E5DF;
                                        font-size:clamp(7.2px, 0.892cqw, 12px);
                                        line-height:1.45;
                                    ">
                                        <b>Revisit in:</b> Q1 2026, once 16 weeks elapse.
                                    </div>
                                </div>
                            """),
                        ],
                        widths=[1, 1, 1],
                        gap=1,
                        align="stretch",
                    ),
                ],
                gap=0.75,
            ),
            mo.Html("""
                <div style="
                    box-sizing:border-box;
                    width:100%;
                    background:#0B1F3A;
                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(10.8px, 1.338cqw, 18px);
                    color:#FFFFFF;
                    font-family:Inter,Arial,sans-serif;
                    font-size:clamp(7.8px, 0.967cqw, 13px);
                    line-height:1.5;
                ">
                    <span style="color:#FF8A63;font-weight:800;">Principle:</span>
                    Prioritize analyses that are interpretable now; revisit deferred questions
                    when the data can support them.
                </div>
            """),
        ],
        gap=1.5,
    )
    return


@app.cell(hide_code=True)
def slide_11():
    # Appendix: sources, data lineage, and the AI-assisted workflow.
    mo.Html(f"""
        <div style="
            box-sizing:border-box;
            width:100%;
            background:#FFFAF7;
            position:relative;
            border-radius:clamp(9.6px, 1.190cqw, 16px);
            padding:clamp(12px, 1.487cqw, 20px) clamp(14.4px, 1.784cqw, 24px) clamp(9.6px, 1.190cqw, 16px);
            color:#0B1F3A;
            font-family:Inter,Arial,sans-serif;
        ">
            <div style="position:absolute;top:6px;right:22px;font-family:Inter,Arial,sans-serif;font-size:clamp(6.6px, 0.818cqw, 11px);font-weight:800;letter-spacing:1.2px;color:#0B1F3A;">11<span style="color:#8C8C8C;"> / 11</span></div>
            <div style="
                height:clamp(6px, 0.372cqw, 5px);
                background:#FF5B24;
                border-radius:clamp(6px, 0.595cqw, 8px);
                margin-bottom:clamp(9.6px, 1.190cqw, 16px);
            "></div>
            <div style="
                color:#FF5B24;
                font-size:clamp(6.6px, 0.818cqw, 11px);
                font-weight:800;
                letter-spacing:1.5px;
                text-transform:uppercase;
                margin-bottom:clamp(6px, 0.595cqw, 8px);
            ">Appendix · Sources, lineage &amp; AI workflow</div>
            <div style="
                color:#0B1F3A;
                font-size:clamp(15.6px, 1.933cqw, 26px);
                line-height:1.2;
                font-weight:800;
                letter-spacing:-0.5px;
            ">
                Reproducible pipeline &amp; human-in-the-loop AI workflow
            </div>
            <div style="
                color:#526176;
                font-size:clamp(7.8px, 0.967cqw, 13px);
                line-height:1.5;
                margin-top:clamp(6px, 0.595cqw, 8px);
            ">
                All metrics, marts, and interactive visuals are generated reproducibly
                from immutable raw CSVs.
            </div>

            <div style="
                display:grid;
                grid-template-columns:repeat(2, minmax(0, 1fr));
                gap:clamp(8.4px, 1.041cqw, 14px);
                margin-top:clamp(8.4px, 1.041cqw, 14px);
            ">
                <div style="
                    background:#FFFFFF;
                    border:1px solid #F0E5DF;
                    border-top:4px solid #FF5B24;
                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6px, 0.743cqw, 10px);
                        font-weight:800;
                        letter-spacing:0.9px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">01 · Code, notebooks &amp; plot archive</div>
                    <div style="font-size:clamp(6.9px, 0.855cqw, 11.5px);line-height:1.5;color:#526176;">
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">GitHub Repository</b> —
                            <a href="{REPO_URL}" target="_blank" rel="noopener"
                               style="color:#FF5B24;font-weight:700;text-decoration:none;border-bottom:1px solid #FF5B24;">vipps_da_interview_case</a>
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Full Analysis Workbook</b> —
                            notebooks/case_analysis.py
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Interactive Slide Deck</b> —
                            notebooks/vip_presentation.py
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Static Plot Gallery</b> —
                            plots/
                        </div>
                    </div>
                </div>

                <div style="
                    background:#FFFFFF;
                    border:1px solid #F0E5DF;
                    border-top:4px solid #2F6DB3;
                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="
                        color:#2F6DB3;
                        font-size:clamp(6px, 0.743cqw, 10px);
                        font-weight:800;
                        letter-spacing:0.9px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">02 · Data lineage &amp; semantic model</div>
                    <div style="font-size:clamp(6.9px, 0.855cqw, 11.5px);line-height:1.5;color:#526176;">
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Raw Case Data</b>
                            <code style="font-size:clamp(6.3px, 0.781cqw, 10.5px);color:#0B1F3A;">data/raw/</code> —
                            transactions.csv, users.csv, merchants.csv, mcc.csv,
                            experiment_exposure.csv, cards.csv (deferred)
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Derived Marts</b>
                            <code style="font-size:clamp(6.3px, 0.781cqw, 10.5px);color:#0B1F3A;">data/processed/</code> —
                            df_user_spine.csv, df_exp_eval.csv, df_weekly_panel.csv
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Semantic Layer</b>
                            <code style="font-size:clamp(6.3px, 0.781cqw, 10.5px);color:#0B1F3A;">semantic/</code> —
                            model.yml, marts.yml, erd.md
                        </div>
                    </div>
                </div>

                <div style="
                    background:#FFFFFF;
                    border:1px solid #F0E5DF;
                    border-top:4px solid #0B1F3A;
                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="
                        color:#0B1F3A;
                        font-size:clamp(6px, 0.743cqw, 10px);
                        font-weight:800;
                        letter-spacing:0.9px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">03 · Tech stack &amp; statistical methods</div>
                    <div style="font-size:clamp(6.9px, 0.855cqw, 11.5px);line-height:1.5;color:#526176;">
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Compute &amp; QA</b> —
                            Python, DuckDB, Pandas, NumPy, ruff, pytest
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Visualization</b> —
                            Marimo + Altair (Vega-Lite)
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Statistical Inference</b>
                            <code style="font-size:clamp(6.3px, 0.781cqw, 10.5px);color:#0B1F3A;">scipy.stats</code> —
                            Welch t-test, paired t-test, two-proportion z-test,
                            complier-scaled ITT
                        </div>
                    </div>
                </div>

                <div style="
                    background:#FFFFFF;
                    border:1px solid #F0E5DF;
                    border-top:4px solid #FF5B24;
                    border-radius:clamp(7.2px, 0.892cqw, 12px);
                    padding:clamp(8.4px, 1.041cqw, 14px) clamp(9.6px, 1.190cqw, 16px);
                    font-family:Inter,Arial,sans-serif;
                ">
                    <div style="
                        color:#FF5B24;
                        font-size:clamp(6px, 0.743cqw, 10px);
                        font-weight:800;
                        letter-spacing:0.9px;
                        text-transform:uppercase;
                        margin-bottom:clamp(6px, 0.595cqw, 8px);
                    ">04 · AI models &amp; human verification</div>
                    <div style="font-size:clamp(6.9px, 0.855cqw, 11.5px);line-height:1.5;color:#526176;">
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Planning &amp; Analytical Partner</b> —
                            Gemini 4 Argon
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Coding &amp; Implementation Model</b> —
                            DeepSeek V4.1
                        </div>
                        <div style="margin-top:clamp(6px, 0.446cqw, 6px);">
                            <b style="color:#0B1F3A;font-weight:750;">Human-in-the-Loop Governance</b> —
                            every metric, cohort filter, and conclusion verified against raw data
                        </div>
                    </div>
                </div>
            </div>

            <div style="
                margin-top:clamp(7.2px, 0.892cqw, 12px);
                padding:clamp(7.8px, 0.967cqw, 13px) clamp(9.6px, 1.190cqw, 16px);
                background:#0B1F3A;
                border-radius:clamp(7.2px, 0.892cqw, 12px);
                display:flex;
                align-items:center;
                justify-content:center;
                gap:clamp(6px, 0.743cqw, 10px);
                font-family:Inter,Arial,sans-serif;
            ">
                <div style="
                    width:7px;
                    height:clamp(6px, 0.520cqw, 7px);
                    background:#FF5B24;
                    border-radius:50%;
                    flex:0 0 auto;
                "></div>
                <div style="
                    font-size:clamp(9px, 1.115cqw, 15px);
                    font-weight:700;
                    letter-spacing:0.2px;
                    color:#FFFFFF;
                ">
                    Thanks for your time &amp; questions are welcome!
                </div>
            </div>
        </div>
    """)
    return


if __name__ == "__main__":
    app.run()
