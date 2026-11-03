import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def imports():
    """Shared imports and aliases for the Vipps case analysis."""

    from pathlib import Path

    import altair as alt
    import duckdb
    import marimo as mo
    import numpy as np
    import pandas as pd
    import yaml
    from scipy import stats

    return Path, alt, duckdb, mo, np, pd, stats, yaml


@app.cell(hide_code=True)
def load_raw_data(Path, mo, pd):
    RAW_DATA_DIR = (mo.notebook_location() / ".." / "data" / "raw").resolve()

    _TABLE_SPECS: dict[str, dict[str, object]] = {
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
            "dtype": {"merchant_mcc_code": "string", "category_name": "string"},
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

    def load_raw_datasets(data_dir: Path = RAW_DATA_DIR) -> dict[str, pd.DataFrame]:
        """Load every raw CSV table into its own DataFrame, keyed by table name."""
        return {
            table: pd.read_csv(data_dir / f"{table}.csv", **spec)
            for table, spec in _TABLE_SPECS.items()
        }

    _datasets = load_raw_datasets()
    transactions = _datasets["transactions"]
    users = _datasets["users"]
    merchants = _datasets["merchants"]
    mcc = _datasets["mcc"]
    experiment_exposure = _datasets["experiment_exposure"]
    return experiment_exposure, mcc, merchants, transactions, users


@app.cell(hide_code=True)
def eda_quality(merchants, mo, pd, transactions, users):
    _tx = transactions
    _users = users
    _merchants = merchants

    _quality = pd.DataFrame(
        [
            {
                "dataset": _name,
                "rows": len(_df),
                "columns": _df.shape[1],
                "grain": _grain,
                "key": _key,
                "duplicate key rows": int(_df[_key].duplicated().sum()),
                "rows with nulls": int(_df.isna().any(axis=1).sum()),
                "null cells": int(_df.isna().sum().sum()),
            }
            for _name, _df, _grain, _key in (
                ("transactions", _tx, "one completed purchase", "transaction_id"),
                ("users", _users, "one user", "user_id"),
                ("merchants", _merchants, "one merchant", "merchant_id"),
            )
        ]
    )

    _NULL_NOTES = {
        ("users", "vip_enrolled_at"): "expected: null for non-VIP at cutoff",
        ("merchants", "merchant_mcc_code"): "expected: unclassified merchant",
    }
    _missing = pd.concat(
        [
            _df.isna()
            .sum()
            .rename_axis("column")
            .reset_index(name="missing")
            .assign(dataset=_name)
            for _name, _df in (
                ("transactions", _tx),
                ("users", _users),
                ("merchants", _merchants),
            )
        ]
    ).query("missing > 0")[["dataset", "column", "missing"]]
    _missing["note"] = [
        _NULL_NOTES.get((_dataset, _column), "unexpected")
        for _dataset, _column in zip(_missing["dataset"], _missing["column"])
    ]
    _null_text = ", ".join(
        f"`{_row.dataset}.{_row.column}` ({_row.missing:,})"
        for _row in _missing.itertuples()
    )

    _country_check = (
        _tx[["user_id", "user_country"]]
        .drop_duplicates()
        .merge(
            _users[["user_id", "user_country"]],
            on="user_id",
            suffixes=("_tx", "_user"),
        )
    )
    _before_start = (
        _tx[["user_id", "transaction_timestamp"]]
        .merge(_users[["user_id", "observation_start_date"]], on="user_id")
        .query("transaction_timestamp < observation_start_date")
    )
    _unclassified_merchants = _merchants.loc[
        _merchants["merchant_mcc_code"].isna(), "merchant_id"
    ]

    mo.vstack(
        [
            mo.md("### 1. Data quality and grain"),
            mo.md(
                "**Grain** is the entity one row represents: one completed purchase "
                "in `transactions`, one user in `users`, and one merchant in "
                "`merchants`. The key column should be unique at that grain."
            ),
            _quality,
            mo.md(
                "**Missing values are column-level, not table-level.** The only "
                f"nulls are {_null_text}. Both are documented nullable fields: "
                "`vip_enrolled_at` is null for non-VIP users at cutoff, and "
                "`merchant_mcc_code` is null for unclassified merchants. "
                "`transactions` has no nulls."
            ),
            _missing,
            mo.md(
                f"**Integrity:** {int((~_tx['user_id'].isin(_users['user_id'])).sum())} "
                "orphan user ids and "
                f"{int((~_tx['merchant_id'].isin(_merchants['merchant_id'])).sum())} "
                "orphan merchant ids; "
                f"{len(_before_start):,} transactions before a user's observation "
                "start; "
                f"{int((_country_check['user_country_tx'] != _country_check['user_country_user']).sum())} "
                "user-country disagreements; "
                f"{len(_unclassified_merchants)} merchant "
                f"({int(_tx['merchant_id'].isin(_unclassified_merchants).sum()):,} "
                "purchases) without an MCC."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def eda_transactions_controls(mo):
    period_filter = mo.ui.dropdown(
        options=["Full year", "H1", "H2", "Q1", "Q2", "Q3", "Q4"],
        value="Full year",
        label="Period",
    )
    mo.vstack(
        [
            mo.md("### 2. Transactions overview"),
            mo.hstack([period_filter], justify="start", align="end"),
        ]
    )
    return (period_filter,)


@app.cell(hide_code=True)
def eda_transactions_overview(alt, mo, np, pd, period_filter, transactions):
    _tx_all = transactions
    _PERIODS = {
        "Full year": (1, 12),
        "H1": (1, 6),
        "H2": (7, 12),
        "Q1": (1, 3),
        "Q2": (4, 6),
        "Q3": (7, 9),
        "Q4": (10, 12),
    }
    _start_month, _end_month = _PERIODS[period_filter.value]
    _tx = _tx_all[
        _tx_all["transaction_timestamp"].dt.month.between(_start_month, _end_month)
    ]

    _monthly = (
        _tx.assign(
            month=_tx["transaction_timestamp"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby("month")
        .agg(
            gmv_nok=("volume_nok", "sum"),
            revenue_nok=("revenue_nok", "sum"),
            purchases=("transaction_id", "size"),
            active_users=("user_id", "nunique"),
        )
        .reset_index()
    )
    _monthly["avg_ticket"] = _monthly["gmv_nok"] / _monthly["purchases"]

    _active_sets = (
        _tx.assign(
            month=_tx["transaction_timestamp"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby("month")["user_id"]
        .apply(set)
    )
    _retention = []
    for _i, _month in enumerate(_monthly["month"]):
        if _i == len(_monthly) - 1:
            _retention.append(np.nan)
            continue
        _current = _active_sets.loc[_month]
        _next = _active_sets.loc[_monthly["month"].iloc[_i + 1]]
        _retention.append(len(_current & _next) / len(_current))
    _monthly["retention_next_month"] = _retention

    _total_gmv = float(_tx["volume_nok"].sum())
    _total_revenue = float(_tx["revenue_nok"].sum())
    _online = _tx["payment_channel"] == "online"
    _ticket_low = _monthly["avg_ticket"].min()
    _ticket_high = _monthly["avg_ticket"].max()
    _ticket_band = (
        f"NOK {_ticket_low:,.0f}"
        if abs(_ticket_high - _ticket_low) < 1
        else f"NOK {_ticket_low:,.0f}-{_ticket_high:,.0f}"
    )

    _ret_early = _monthly.loc[
        _monthly["month"] < pd.Timestamp("2025-09-01"), "retention_next_month"
    ].mean()
    _ret_low = _monthly["retention_next_month"].min()
    _ret_early_txt = f"{_ret_early:.0%}" if pd.notna(_ret_early) else "n/a"
    _ret_low_txt = f"{_ret_low:.0%}" if pd.notna(_ret_low) else "n/a"

    _gmv_chart = (
        alt.layer(
            alt.Chart(_monthly)
            .mark_line(point=True, color="#4c78a8")
            .encode(
                x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
                y=alt.Y(
                    "gmv_nok:Q",
                    title="GMV (NOK, left)",
                    axis=alt.Axis(format="~s", titleColor="#4c78a8"),
                ),
                tooltip=[
                    alt.Tooltip("month:T", title="Month", format="%b %Y"),
                    alt.Tooltip("gmv_nok:Q", title="GMV", format=",.0f"),
                    alt.Tooltip(
                        "avg_ticket:Q",
                        title="Avg order value",
                        format=",.0f",
                    ),
                    alt.Tooltip("purchases:Q", title="Purchases", format=","),
                ],
            ),
            alt.Chart(_monthly)
            .mark_line(point=True, color="#e45756", strokeDash=[4, 2])
            .encode(
                x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
                y=alt.Y(
                    "avg_ticket:Q",
                    title=None,
                    axis=alt.Axis(format=",.0f", titleColor="#e45756"),
                    scale=alt.Scale(domain=[400, 500]),
                ),
                tooltip=[
                    alt.Tooltip("month:T", title="Month", format="%b %Y"),
                    alt.Tooltip(
                        "avg_ticket:Q",
                        title="Avg order value",
                        format=",.0f",
                    ),
                ],
            ),
        )
        .resolve_scale(y="independent")
        .properties(
            title=alt.TitleParams(
                text="Monthly GMV and average order value",
                subtitle=(
                    "Left axis: GMV (NOK). Right axis: average order value (NOK)."
                ),
            ),
            height=240,
        )
    )

    _users_chart = (
        alt.Chart(_monthly)
        .mark_line(point=True, color="#e45756")
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
            y=alt.Y(
                "active_users:Q", title="Active users", scale=alt.Scale(zero=False)
            ),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("active_users:Q", title="Active users", format=","),
            ],
        )
        .properties(title="Monthly active users (MAU)", height=240)
    )

    _retention_chart = (
        alt.Chart(_monthly.dropna(subset=["retention_next_month"]))
        .mark_line(point=True, color="#54a24b")
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
            y=alt.Y(
                "retention_next_month:Q",
                title="Retained next month",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0.7, 1.0]),
            ),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("retention_next_month:Q", title="Retention", format=".1%"),
            ],
        )
        .properties(
            width=780,
            title="Month-over-month retention (axis starts at 70%)",
            height=180,
        )
    )

    mo.vstack(
        [
            mo.md(
                f"**{len(_tx):,} purchases** between "
                f"{_tx['transaction_timestamp'].min():%d %b %Y} and "
                f"{_tx['transaction_timestamp'].max():%d %b %Y}. Total **gross "
                f"merchandise value (GMV)** is **NOK {_total_gmv / 1e6:,.1f}m**, "
                "calculated as `sum(transactions.volume_nok)` across completed "
                "purchases. GMV is the value paid by customers, not service "
                f"revenue (NOK {_total_revenue / 1e6:,.2f}m). Only completed "
                "positive purchases are included; failed payments, refunds and "
                "transfers are excluded. The mean purchase is "
                f"NOK {_tx['volume_nok'].mean():,.0f} (median "
                f"NOK {_tx['volume_nok'].median():,.0f}). Online accounts for "
                f"{_online.mean():.1%} of purchases and "
                f"{_tx.loc[_online, 'volume_nok'].sum() / _total_gmv:.1%} of GMV."
            ),
            mo.hstack([_gmv_chart, _users_chart], widths="equal", gap=1.5),
            mo.hstack(
                [
                    mo.md(
                        "**GMV** = `sum(transactions.volume_nok)` per month; **average order value** = monthly GMV / `count(transactions.transaction_id)`. Both grouped by month of `transactions.transaction_timestamp`."
                    ),
                    mo.md(
                        "**MAU** = distinct `transactions.user_id` with at least one purchase in the month (`nunique`), grouped by month of `transactions.transaction_timestamp`. It counts purchasers, not app visitors."
                    ),
                ],
                widths="equal",
                gap=1.5,
            ),
            _retention_chart,
            mo.md(
                "**Month-over-month retention** = |users active in month m AND users active in month m+1| / |users active in month m|, from `transactions.user_id` and `transactions.transaction_timestamp`. Only consecutive months count; the last month has no next month, so its point is null."
            ),
            mo.md(
                f"Monthly GMV tracks active users: "
                f"MAU peaks at {_monthly['active_users'].max():,} "
                f"in {_monthly.loc[_monthly['active_users'].idxmax(), 'month']:%b} "
                f"and ends at {_monthly['active_users'].iloc[-1]:,} in "
                f"{_monthly['month'].iloc[-1]:%b}. Average ticket stays in a "
                f"{_ticket_band} band across the selected months, so changes are "
                "activity-driven rather than price-driven."
            ),
            mo.md(
                f"**Retention explains the MAU gap.** Month-to-month retention "
                f"averages {_ret_early_txt} through August and falls as low as "
                f"{_ret_low_txt} after it. Users who leave had typical spend "
                "while active but fewer active months, so headcount falls faster "
                "than GMV; spend per active user is stable."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def eda_transaction_values_controls(mo):
    value_channel_filter = mo.ui.dropdown(
        options=["All channels", "Online", "In person"],
        value="All channels",
        label="Channel",
    )
    value_axis_scale = mo.ui.radio(
        options=["Log", "Linear"],
        value="Log",
        label="Value axis",
        inline=True,
    )
    value_bin_count = mo.ui.slider(
        start=10,
        stop=60,
        step=5,
        value=40,
        label="Bins",
        show_value=True,
    )
    mix_metric_filter = mo.ui.dropdown(
        options=["GMV", "Purchases", "Revenue"],
        value="Revenue",
        label="Channel pie",
    )
    mo.vstack(
        [
            mo.md("### 3. Purchase values and channel mix"),
            mo.hstack(
                [
                    value_channel_filter,
                    value_axis_scale,
                    value_bin_count,
                    mix_metric_filter,
                ],
                justify="start",
                align="end",
                wrap=True,
            ),
        ]
    )
    return (
        mix_metric_filter,
        value_axis_scale,
        value_bin_count,
        value_channel_filter,
    )


@app.cell(hide_code=True)
def eda_transaction_values(
    alt,
    mix_metric_filter,
    mo,
    np,
    pd,
    transactions,
    value_axis_scale,
    value_bin_count,
    value_channel_filter,
):
    _tx_all = transactions
    _CHANNELS = {"All channels": None, "Online": "online", "In person": "in_person"}
    _CHANNEL_LABELS = {
        "All channels": "all channels",
        "Online": "online",
        "In person": "in-person",
    }
    _channel_value = _CHANNELS[value_channel_filter.value]
    _tx = (
        _tx_all
        if _channel_value is None
        else _tx_all[_tx_all["payment_channel"] == _channel_value]
    )

    _value_summary = pd.DataFrame(
        [
            {
                "purchases": len(_tx),
                "mean": _tx["volume_nok"].mean(),
                "median": _tx["volume_nok"].median(),
                "P90": _tx["volume_nok"].quantile(0.90),
                "P95": _tx["volume_nok"].quantile(0.95),
                "P99": _tx["volume_nok"].quantile(0.99),
                "max": _tx["volume_nok"].max(),
            }
        ]
    ).round(0)

    _min_value = _tx["volume_nok"].min()
    _max_value = _tx["volume_nok"].max()
    if value_axis_scale.value == "Log":
        _bin_edges = np.logspace(
            np.log10(_min_value), np.log10(_max_value), value_bin_count.value
        )
        _x_scale = alt.Scale(type="log")
        _x_title = "Purchase value (NOK, log scale)"
    else:
        _bin_edges = np.linspace(_min_value, _max_value, value_bin_count.value)
        _x_scale = alt.Scale(type="linear")
        _x_title = "Purchase value (NOK, linear scale)"

    _counts, _edges = np.histogram(_tx["volume_nok"], bins=_bin_edges)
    _hist = pd.DataFrame(
        {"bin_start": _edges[:-1], "bin_end": _edges[1:], "purchases": _counts}
    )
    _hist_chart = (
        alt.Chart(_hist)
        .mark_bar()
        .encode(
            x=alt.X("bin_start:Q", title=_x_title, scale=_x_scale),
            x2="bin_end:Q",
            y=alt.Y(
                "purchases:Q",
                title="Purchases",
                scale=alt.Scale(domain=[0, int(_counts.max() * 1.1)], nice=False),
                axis=alt.Axis(format=","),
            ),
            tooltip=[
                alt.Tooltip("bin_start:Q", title="From", format=",.0f"),
                alt.Tooltip("bin_end:Q", title="To", format=",.0f"),
                alt.Tooltip("purchases:Q", title="Purchases", format=","),
            ],
        )
        .properties(title="Purchase value distribution", height=240)
    )

    _mix = pd.concat(
        [
            _tx_all.groupby("payment_channel", as_index=False)
            .agg(value=("volume_nok", "sum"))
            .assign(metric="GMV"),
            _tx_all.groupby("payment_channel", as_index=False)
            .agg(value=("transaction_id", "size"))
            .assign(metric="Purchases"),
            _tx_all.groupby("payment_channel", as_index=False)
            .agg(value=("revenue_nok", "sum"))
            .assign(metric="Revenue"),
        ]
    )
    _mix["share"] = _mix["value"] / _mix.groupby("metric")["value"].transform("sum")
    _online = _tx_all["payment_channel"] == "online"
    _online_purchase_share = float(_online.mean())
    _online_gmv_share = float(
        _tx_all.loc[_online, "volume_nok"].sum() / _tx_all["volume_nok"].sum()
    )
    _online_revenue_share = float(
        _tx_all.loc[_online, "revenue_nok"].sum() / _tx_all["revenue_nok"].sum()
    )
    _online_revenue_nok = float(_tx_all.loc[_online, "revenue_nok"].sum())
    _in_person_revenue_nok = float(_tx_all.loc[~_online, "revenue_nok"].sum())
    _online_take_rate_pct = (
        _online_revenue_nok / _tx_all.loc[_online, "volume_nok"].sum() * 100
    )
    _in_person_take_rate_pct = (
        _in_person_revenue_nok / _tx_all.loc[~_online, "volume_nok"].sum() * 100
    )
    _mix["channel"] = _mix["payment_channel"].map(
        {"online": "Online", "in_person": "In person"}
    )
    _mix["share_label"] = _mix["share"].map(lambda share: f"{share:.1%}")
    _mix["value_label"] = [
        f"NOK {value:,.0f}"
        if metric in {"GMV", "Revenue"}
        else f"{value:,.0f} purchases"
        for value, metric in zip(_mix["value"], _mix["metric"])
    ]

    _pie_metric = mix_metric_filter.value
    _pie_data = _mix[_mix["metric"] == _pie_metric].copy()
    _pie_data["_channel_order"] = _pie_data["channel"].map(
        {"Online": 0, "In person": 1}
    )
    _pie_data = _pie_data.sort_values("_channel_order")
    _pie_title = {
        "GMV": "GMV share",
        "Purchases": "purchases share",
        "Revenue": "revenue share",
    }[_pie_metric]
    _pie_subtitle = {
        "GMV": "Share of total GMV by channel.",
        "Purchases": "Share of total purchases by channel.",
        "Revenue": "Share of total service revenue by channel.",
    }[_pie_metric]
    _pie_data["legend_label"] = _pie_data["channel"]
    _legend_domain = _pie_data["legend_label"].tolist()
    _legend_range = (
        _pie_data["channel"].map({"Online": "#4c78a8", "In person": "#f58518"}).tolist()
    )
    _pie_arcs = (
        alt.Chart(_pie_data)
        .mark_arc(innerRadius=45, outerRadius=100)
        .encode(
            theta=alt.Theta("share:Q", stack=True),
            order=alt.Order("legend_label:N", sort="ascending"),
            color=alt.Color(
                "legend_label:N",
                title=None,
                scale=alt.Scale(domain=_legend_domain, range=_legend_range),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("channel:N", title="Channel"),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
                alt.Tooltip("value_label:N", title="Value"),
            ],
        )
    )
    _pie_labels = (
        alt.Chart(_pie_data)
        .mark_text(radius=72, fontSize=11, color="#ffffff", fontWeight="bold")
        .encode(
            theta=alt.Theta("share:Q", stack=True),
            order=alt.Order("legend_label:N", sort="ascending"),
            text=alt.Text("share_label:N"),
        )
    )
    _pie_chart = (_pie_arcs + _pie_labels).properties(
        title=alt.TitleParams(
            text=f"Channel mix: {_pie_title}", subtitle=_pie_subtitle
        ),
        height=240,
    )
    mo.vstack(
        [
            mo.md(
                f"Showing **{len(_tx):,} purchases** for "
                f"**{_CHANNEL_LABELS[value_channel_filter.value]}**. The median is "
                f"NOK {_tx['volume_nok'].median():,.0f}, P99 is "
                f"NOK {_tx['volume_nok'].quantile(0.99):,.0f}, and the maximum is "
                f"NOK {_tx['volume_nok'].max():,.0f}. Use the controls above to "
                "change the channel, axis scale, bin count or pie metric."
            ),
            _value_summary,
            mo.hstack([_hist_chart, _pie_chart], widths="equal", gap=1.5),
            mo.hstack(
                [
                    mo.md(
                        "**Purchase value distribution** - each bar counts `transactions.transaction_id` whose `volume_nok` falls in that bin; `payment_channel` applies the channel filter. Axis scale and bin count are display controls only."
                    ),
                    mo.md(
                        "**Channel mix** - share of `sum(volume_nok)` (GMV), `count(transaction_id)` (purchases) or `sum(revenue_nok)` (revenue) by `payment_channel`, chosen by the metric selector."
                    ),
                ],
                widths="equal",
                gap=1.5,
            ),
            mo.md(
                f"**Reading the channel mix:** online is "
                f"{_online_purchase_share:.1%} of purchases, "
                f"{_online_gmv_share:.1%} of GMV and "
                f"{_online_revenue_share:.1%} of service revenue. In absolute "
                f"terms, online revenue is NOK {_online_revenue_nok / 1e6:.2f}m "
                f"versus NOK {_in_person_revenue_nok / 1e6:.2f}m in-store, so "
                "online earns less; its revenue share is higher than its GMV "
                f"share because the online take rate is "
                f"{_online_take_rate_pct:.2f}% versus "
                f"{_in_person_take_rate_pct:.2f}% in-store."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def eda_users_controls(mo):
    user_country_filter = mo.ui.dropdown(
        options=["All countries", "Norway", "Denmark"],
        value="All countries",
        label="Country",
    )
    mo.vstack(
        [
            mo.md("### 4. Users"),
            mo.hstack([user_country_filter], justify="start", align="end"),
        ]
    )
    return (user_country_filter,)


@app.cell(hide_code=True)
def eda_users(alt, mo, np, pd, transactions, user_country_filter, users):
    _users_all = users
    _tx_all = transactions
    _users = (
        _users_all
        if user_country_filter.value == "All countries"
        else _users_all[_users_all["user_country"] == user_country_filter.value]
    )
    _user_ids = _users["user_id"]
    _tx = _tx_all[_tx_all["user_id"].isin(_user_ids)]
    _country_label = (
        "all countries"
        if user_country_filter.value == "All countries"
        else user_country_filter.value
    )

    _summary = pd.DataFrame(
        [
            {
                "users": len(_users),
                "VIP at cutoff": (
                    f"{int(_users['vip_enrolled'].sum()):,} "
                    f"({_users['vip_enrolled'].mean():.1%})"
                ),
                "Norway": (
                    f"{int((_users['user_country'] == 'Norway').sum()):,} "
                    f"({(_users['user_country'] == 'Norway').mean():.1%})"
                ),
                "full-year coverage": int(
                    (
                        _users["observation_start_date"] <= pd.Timestamp("2025-01-01")
                    ).sum()
                ),
                "late coverage": int(
                    (
                        _users["observation_start_date"] > pd.Timestamp("2025-01-01")
                    ).sum()
                ),
            }
        ]
    )

    _age = (
        _users["age_bucket"]
        .value_counts()
        .sort_index()
        .rename_axis("age_bucket")
        .reset_index(name="users")
    )
    _age_bars = (
        alt.Chart(_age)
        .mark_bar()
        .encode(
            x=alt.X("age_bucket:N", title=None, sort=None),
            y=alt.Y("users:Q", title="Users"),
            color=alt.Color(
                "age_bucket:N",
                title=None,
                sort=None,
                scale=alt.Scale(scheme="viridis"),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("age_bucket:N", title="Age"),
                alt.Tooltip("users:Q", title="Users"),
            ],
        )
    )
    _age_labels = (
        alt.Chart(_age)
        .mark_text(dy=-6, fontSize=9)
        .encode(
            x=alt.X("age_bucket:N", sort=None),
            y=alt.Y("users:Q"),
            text=alt.Text("users:Q", format=","),
        )
    )
    age_chart = alt.layer(_age_bars, _age_labels).properties(
        title="Users by age bucket", height=240
    )

    _tx_months = _tx.assign(month=_tx["transaction_timestamp"].dt.to_period("M"))
    _months_active = (
        _tx_months.groupby("user_id")["month"]
        .nunique()
        .reindex(_user_ids, fill_value=0)
    )
    _december_users = int(
        _tx.loc[
            _tx["transaction_timestamp"] >= pd.Timestamp("2025-12-01"), "user_id"
        ].nunique()
    )
    _coverage = (
        _users.assign(
            coverage=lambda frame: np.where(
                frame["observation_start_date"] <= pd.Timestamp("2025-01-01"),
                "Full year",
                "Incomplete year",
            )
        )
        .groupby("coverage")
        .size()
        .reindex(["Full year", "Incomplete year"], fill_value=0)
        .rename("users")
        .reset_index()
    )
    _coverage["share"] = _coverage["users"] / _coverage["users"].sum()
    _coverage["share_label"] = _coverage["share"].map(lambda share: f"{share:.1%}")

    _coverage_arcs = (
        alt.Chart(_coverage)
        .mark_arc(innerRadius=45, outerRadius=100)
        .encode(
            theta=alt.Theta("users:Q", stack=True),
            order=alt.Order("coverage:N", sort="ascending"),
            color=alt.Color(
                "coverage:N",
                title=None,
                scale=alt.Scale(
                    domain=["Full year", "Incomplete year"],
                    range=["#4c78a8", "#f58518"],
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("coverage:N", title="Coverage"),
                alt.Tooltip("users:Q", title="Users", format=","),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
            ],
        )
    )
    _coverage_labels = (
        alt.Chart(_coverage)
        .mark_text(radius=72, fontSize=11, color="#ffffff", fontWeight="bold")
        .encode(
            theta=alt.Theta("users:Q", stack=True),
            order=alt.Order("coverage:N", sort="ascending"),
            text=alt.Text("share_label:N"),
        )
    )
    _coverage_chart = (_coverage_arcs + _coverage_labels).properties(
        title=alt.TitleParams(
            text="Customer coverage",
            subtitle="Full-year vs incomplete 2025 purchase coverage.",
        ),
        height=240,
    )

    _vip_monthly = (
        _users.dropna(subset=["vip_enrolled_at"])
        .assign(
            month=lambda frame: (
                frame["vip_enrolled_at"].dt.to_period("M").dt.to_timestamp()
            )
        )
        .groupby("month")
        .size()
        .rename("new_signups")
        .reindex(pd.date_range("2025-01-01", periods=12, freq="MS"), fill_value=0)
        .rename_axis("month")
        .reset_index()
    )
    _vip_monthly["cumulative_vips"] = _vip_monthly["new_signups"].cumsum()

    _vip_bars = (
        alt.Chart(_vip_monthly)
        .mark_bar(color="#4c78a8", opacity=0.75)
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
            y=alt.Y(
                "new_signups:Q",
                title="New signups",
                axis=alt.Axis(titleColor="#4c78a8"),
            ),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("new_signups:Q", title="New signups", format=","),
            ],
        )
    )
    _vip_line = (
        alt.Chart(_vip_monthly)
        .mark_line(point=True, color="#e45756", strokeWidth=2)
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b")),
            y=alt.Y(
                "cumulative_vips:Q",
                title="Cumulative VIP members",
                axis=alt.Axis(titleColor="#e45756", orient="right"),
            ),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip(
                    "cumulative_vips:Q",
                    title="Cumulative VIP members",
                    format=",",
                ),
            ],
        )
    )
    _vip_chart = (
        alt.layer(_vip_bars, _vip_line)
        .resolve_scale(y="independent")
        .properties(
            title=alt.TitleParams(
                text="VIP enrollment by month",
                subtitle=(
                    "Bars = new signups (left); line = cumulative VIP members (right)."
                ),
            ),
            height=260,
        )
    )

    mo.vstack(
        [
            mo.md(
                f"{len(_users):,} users in {_country_label}, of whom "
                f"{int(_users['vip_enrolled'].sum()):,} are VIP at the cutoff. "
                f"{int((_users['observation_start_date'] > pd.Timestamp('2025-01-01')).sum())} "
                "users start coverage in October-November, so their 2025 totals are "
                "partial and not comparable with the "
                f"{int((_users['observation_start_date'] <= pd.Timestamp('2025-01-01')).sum())} "
                "full-year users."
            ),
            _summary,
            mo.hstack([age_chart, _coverage_chart], widths="equal", gap=1.5),
            mo.hstack(
                [
                    mo.md(
                        "**Users by age bucket** - `count(users.user_id)` grouped by `users.age_bucket`, after the country filter."
                    ),
                    mo.md(
                        "**Customer coverage** - split by `users.observation_start_date`: full-year means coverage starts on or before 2025-01-01; incomplete means it starts later."
                    ),
                ],
                widths="equal",
                gap=1.5,
            ),
            mo.md(
                f"Only {int((_months_active == 12).sum()):,} users transact in all "
                f"12 months, and {_december_users:,} have a December purchase. "
                "Age is spread almost evenly across the 16 buckets, consistent "
                "with synthetic generation rather than a real customer mix."
            ),
            mo.md(
                f"**VIP enrollment by month.** Bars count new `vip_enrolled_at` "
                f"signups; the line is the cumulative total. "
                f"{int(_users['vip_enrolled'].sum()):,} VIP members in the selected "
                "population; no cancellations are modelled."
            ),
            mo.ui.altair_chart(_vip_chart),
            mo.md(
                "**VIP enrollment** - bars count `users.user_id` by month of `users.vip_enrolled_at`; the line is the cumulative sum. Users with a null `vip_enrolled_at` are excluded."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def eda_merchants_controls(mo):
    merchant_country_filter = mo.ui.dropdown(
        options=[
            "All countries",
            "Denmark",
            "Germany",
            "Netherlands",
            "Norway",
            "Sweden",
        ],
        value="All countries",
        label="Merchant country",
    )
    merchant_rank_metric = mo.ui.radio(
        options=["GMV", "Purchases"],
        value="GMV",
        label="Rank by",
        inline=True,
    )
    merchant_top_n = mo.ui.slider(
        start=5,
        stop=30,
        step=5,
        value=10,
        label="Top N",
        show_value=True,
    )
    mo.vstack(
        [
            mo.md("### 5. Merchants"),
            mo.hstack(
                [merchant_country_filter, merchant_rank_metric, merchant_top_n],
                justify="start",
                align="end",
            ),
        ]
    )
    return merchant_country_filter, merchant_rank_metric, merchant_top_n


@app.cell(hide_code=True)
def eda_merchants(
    alt,
    mcc,
    merchant_country_filter,
    merchant_rank_metric,
    merchant_top_n,
    merchants,
    mo,
    transactions,
):
    _merchants_all = merchants
    _tx_all = transactions
    _mcc_names = mcc.set_index("merchant_mcc_code")["category_name"]
    _merchants = (
        _merchants_all
        if merchant_country_filter.value == "All countries"
        else _merchants_all[
            _merchants_all["merchant_country"] == merchant_country_filter.value
        ]
    )
    _merchant_ids = _merchants["merchant_id"]
    _tx = _tx_all[_tx_all["merchant_id"].isin(_merchant_ids)]

    _stats = (
        _tx.groupby("merchant_id")
        .agg(
            gmv_nok=("volume_nok", "sum"),
            revenue_nok=("revenue_nok", "sum"),
            purchases=("transaction_id", "size"),
            users=("user_id", "nunique"),
        )
        .join(
            _merchants.set_index("merchant_id")[
                ["merchant_name", "merchant_country", "merchant_mcc_code"]
            ]
        )
        .sort_values("gmv_nok", ascending=False)
    )
    _stats["take_rate_pct"] = _stats["revenue_nok"] / _stats["gmv_nok"] * 100
    _metric_column = "gmv_nok" if merchant_rank_metric.value == "GMV" else "purchases"
    _metric_title = "GMV (NOK)" if merchant_rank_metric.value == "GMV" else "Purchases"
    _metric_axis = (
        alt.Axis(format="~s")
        if merchant_rank_metric.value == "GMV"
        else alt.Axis(format=",")
    )
    _top = (
        _stats.sort_values(_metric_column, ascending=False)
        .head(merchant_top_n.value)
        .reset_index()
    )

    _top_chart = (
        alt.Chart(_top)
        .mark_bar()
        .encode(
            y=alt.Y("merchant_name:N", sort="-x", title=None),
            x=alt.X(f"{_metric_column}:Q", title=_metric_title, axis=_metric_axis),
            color=alt.Color(
                "merchant_country:N",
                title="Country",
                scale=alt.Scale(scheme="tableau10"),
            ),
            tooltip=[
                alt.Tooltip("merchant_name:N", title="Merchant"),
                alt.Tooltip("merchant_country:N", title="Country"),
                alt.Tooltip("gmv_nok:Q", title="GMV", format=",.0f"),
                alt.Tooltip("purchases:Q", title="Purchases", format=","),
                alt.Tooltip("take_rate_pct:Q", title="Take rate %", format=".2f"),
            ],
        )
        .properties(
            title=f"Top {len(_top)} merchants by {merchant_rank_metric.value}",
            height=320,
        )
    )

    _mcc_mix = (
        _tx.merge(
            _merchants[["merchant_id", "merchant_mcc_code"]],
            on="merchant_id",
            how="left",
        )
        .assign(
            category=lambda frame: (
                frame["merchant_mcc_code"].map(_mcc_names).fillna("Unclassified")
            )
        )
        .groupby("category")["volume_nok"]
        .sum()
        .sort_values(ascending=False)
    )
    _mcc_share = (_mcc_mix / _mcc_mix.sum()).rename("share").reset_index()
    _mcc_chart = (
        alt.Chart(_mcc_share)
        .mark_bar()
        .encode(
            y=alt.Y("category:N", sort="-x", title=None),
            x=alt.X("share:Q", title="GMV share", axis=alt.Axis(format="%")),
            color=alt.Color(
                "category:N",
                title=None,
                scale=alt.Scale(scheme="tableau10"),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("share:Q", title="GMV share", format=".1%"),
            ],
        )
        .properties(title="GMV by MCC category", height=320)
    )

    _total_gmv = float(_stats["gmv_nok"].sum())
    _country_label = (
        "all countries"
        if merchant_country_filter.value == "All countries"
        else merchant_country_filter.value
    )
    _country_count = int(_merchants["merchant_country"].nunique())
    _country_word = "country" if _country_count == 1 else "countries"
    _top5_n = min(5, len(_stats))
    _top10_n = min(10, len(_stats))
    _unclassified_count = int(_stats["merchant_mcc_code"].isna().sum())
    _unclassified_label = "merchant" if _unclassified_count == 1 else "merchants"
    _unclassified_verb = "accounts" if _unclassified_count == 1 else "account"
    _unclassified_share = _mcc_mix.get("Unclassified", 0) / _mcc_mix.sum()
    _unclassified_note = (
        f" {_unclassified_count} {_unclassified_label} without an MCC "
        f"{_unclassified_verb} for {_unclassified_share:.1%} of GMV."
        if _unclassified_count
        else ""
    )

    mo.vstack(
        [
            mo.md(
                f"**{len(_merchants)} merchants** across {_country_count} "
                f"{_country_word} ({_country_label}). GMV is concentrated: the "
                f"top merchant holds "
                f"{_stats['gmv_nok'].iloc[0] / _total_gmv:.1%} of GMV, the top "
                f"{_top5_n} hold "
                f"{_stats['gmv_nok'].head(_top5_n).sum() / _total_gmv:.1%}, and "
                f"the top {_top10_n} hold "
                f"{_stats['gmv_nok'].head(_top10_n).sum() / _total_gmv:.1%}. "
                f"Take rates range from {_stats['take_rate_pct'].min():.2f}% to "
                f"{_stats['take_rate_pct'].max():.2f}% (median "
                f"{_stats['take_rate_pct'].median():.2f}%); revenue is a fixed "
                "share of volume per merchant up to rounding."
                f"{_unclassified_note}"
            ),
            mo.hstack([_top_chart, _mcc_chart], widths="equal"),
        ]
    )
    return


@app.cell(hide_code=True)
def eda_age_mcc(alt, mcc, merchants, mo, transactions, users):
    _users = users[["user_id", "age_bucket"]]
    _mcc_names = mcc.set_index("merchant_mcc_code")["category_name"]
    _purchases = (
        transactions.merge(_users, on="user_id", how="left")
        .merge(
            merchants[["merchant_id", "merchant_mcc_code"]],
            on="merchant_id",
            how="left",
        )
        .assign(
            category=lambda frame: (
                frame["merchant_mcc_code"].map(_mcc_names).fillna("Unclassified")
            )
        )
    )
    _counts = (
        _purchases.groupby(["age_bucket", "category"])
        .agg(
            purchases=("transaction_id", "size"),
            gmv_nok=("volume_nok", "sum"),
        )
        .reset_index()
    )
    _counts["share"] = _counts["purchases"] / _counts.groupby("age_bucket")[
        "purchases"
    ].transform("sum")
    _top_per_age = (
        _counts.sort_values(["age_bucket", "purchases"], ascending=[True, False])
        .groupby("age_bucket", as_index=False)
        .head(1)
        .sort_values("age_bucket")
        .assign(
            share_pct=lambda frame: (frame["share"] * 100).round(1),
            gmv_nok=lambda frame: frame["gmv_nok"].round(0),
        )
        .rename(
            columns={
                "age_bucket": "Age bucket",
                "category": "Top MCC category",
                "purchases": "Purchases",
                "share_pct": "Share (%)",
                "gmv_nok": "GMV (NOK)",
            }
        )[
            [
                "Age bucket",
                "Top MCC category",
                "Purchases",
                "Share (%)",
                "GMV (NOK)",
            ]
        ]
        .reset_index(drop=True)
    )

    _age_order = sorted(_counts["age_bucket"].unique())
    _category_order = (
        _counts.groupby("category")["purchases"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )
    _base = alt.Chart(_counts).encode(
        x=alt.X(
            "age_bucket:N",
            title="Age bucket",
            sort=_age_order,
            axis=alt.Axis(labelAngle=-45),
        ),
        y=alt.Y(
            "category:N",
            title="MCC category",
            sort=_category_order,
            axis=alt.Axis(labelLimit=0),
        ),
    )
    _heat = _base.mark_rect().encode(
        color=alt.Color(
            "share:Q",
            title="Share of purchases",
            scale=alt.Scale(scheme="blues"),
            axis=alt.Axis(format="%"),
        ),
        tooltip=[
            alt.Tooltip("age_bucket:N", title="Age bucket"),
            alt.Tooltip("category:N", title="MCC category"),
            alt.Tooltip("purchases:Q", title="Purchases", format=","),
            alt.Tooltip("share:Q", title="Share", format=".1%"),
            alt.Tooltip("gmv_nok:Q", title="GMV", format=",.0f"),
        ],
    )
    _labels = _base.mark_text(fontSize=8).encode(
        text=alt.condition(
            alt.datum.share > 0.1,
            alt.Text("share:Q", format=".0%"),
            alt.value(""),
        ),
        color=alt.condition(
            alt.datum.share > 0.4,
            alt.value("white"),
            alt.value("#333333"),
        ),
    )
    _heat_chart = (_heat + _labels).properties(
        title="MCC category share of purchases by age bucket",
        height=320,
    )

    if _top_per_age["Top MCC category"].nunique() == 1:
        _top_sentence = (
            f"**{_top_per_age['Top MCC category'].iloc[0]}** is the top category "
            f"in all {len(_top_per_age)} age buckets, with a share between "
            f"{_top_per_age['Share (%)'].min():.1f}% and "
            f"{_top_per_age['Share (%)'].max():.1f}% of purchases."
        )
    else:
        _top_sentence = (
            "The most popular category varies by age bucket; see the table below."
        )

    mo.vstack(
        [
            mo.md("### 6. MCC popularity by age bucket"),
            mo.md(
                "**Most popular** means the MCC category with the highest number "
                "of purchases within an age bucket. The merchant without an MCC is "
                "shown as `Unclassified`."
            ),
            mo.md(_top_sentence),
            _top_per_age,
            mo.ui.altair_chart(_heat_chart),
        ]
    )
    return


@app.cell(hide_code=True)
def build_analytical_marts(
    duckdb,
    experiment_exposure,
    mcc,
    merchants,
    mo,
    transactions,
    users,
):
    _processed_dir = (mo.notebook_location() / ".." / "data" / "processed").resolve()
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


@app.cell(hide_code=True)
def vip_selection_bias(alt, df_user_spine, duckdb, mo, np, pd, transactions):
    _con = duckdb.connect(":memory:")
    _con.register("user_spine", df_user_spine)
    _con.register("transactions", transactions)
    _sel = _con.execute(
        """
        WITH tx AS (
            SELECT
                user_id,
                COUNT(*) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2026-01-01'
                ) AS fy_tx,
                SUM(volume_nok) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2026-01-01'
                ) AS fy_gmv,
                COUNT(*) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2025-05-01'
                ) AS pre_tx,
                SUM(volume_nok) FILTER (
                    WHERE transaction_timestamp >= TIMESTAMP '2025-01-01'
                      AND transaction_timestamp < TIMESTAMP '2025-05-01'
                ) AS pre_gmv
            FROM transactions
            GROUP BY user_id
        ),
        per_user AS (
            SELECT
                s.user_id,
                s.vip_enrolled,
                COALESCE(t.fy_tx, 0) AS fy_tx,
                COALESCE(t.fy_gmv, 0) AS fy_gmv,
                COALESCE(t.pre_tx, 0) AS pre_tx,
                COALESCE(t.pre_gmv, 0) AS pre_gmv
            FROM user_spine s
            LEFT JOIN tx t USING (user_id)
            WHERE s.is_full_year_obs
        )
        SELECT
            CASE WHEN vip_enrolled THEN 'Future VIP' ELSE 'Never VIP' END AS grp,
            COUNT(*) AS users,
            AVG(fy_gmv / 52.142857) AS fy_weekly_gmv,
            AVG(fy_tx / 52.142857) AS fy_weekly_tx,
            AVG(pre_gmv / 17.142857) AS pre_weekly_gmv,
            AVG(pre_tx / 17.142857) AS pre_weekly_tx
        FROM per_user
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    _con.close()

    _sel_long = _sel.melt(
        id_vars=["grp", "users"],
        value_vars=[
            "fy_weekly_gmv",
            "pre_weekly_gmv",
            "fy_weekly_tx",
            "pre_weekly_tx",
        ],
        var_name="measure",
        value_name="value",
    )
    _sel_long["period"] = np.where(
        _sel_long["measure"].str.startswith("fy_"),
        "Full-year",
        "Jan-Apr",
    )
    _sel_long["metric"] = np.where(
        _sel_long["measure"].str.endswith("gmv"),
        "Weekly GMV (NOK)",
        "Weekly purchases",
    )
    _sel_long = _sel_long.rename(columns={"grp": "group"})

    _colors = alt.Scale(
        domain=["Future VIP", "Never VIP"],
        range=["#e45756", "#4c78a8"],
    )

    def _grouped_bar(metric, title, y_title, axis_format, value_format):
        data = _sel_long[_sel_long["metric"] == metric]
        bars = (
            alt.Chart(data)
            .mark_bar()
            .encode(
                x=alt.X("period:N", title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.X("group:N", title=None),
                y=alt.Y("value:Q", title=y_title, axis=alt.Axis(format=axis_format)),
                color=alt.Color("group:N", title=None, scale=_colors),
                tooltip=[
                    alt.Tooltip("group:N", title="Group"),
                    alt.Tooltip("period:N", title="Period"),
                    alt.Tooltip("value:Q", title=y_title, format=value_format),
                    alt.Tooltip("users:Q", title="Users", format=","),
                ],
            )
        )
        labels = (
            alt.Chart(data)
            .mark_text(dy=-6, fontSize=10, color="#333333")
            .encode(
                x=alt.X("period:N", axis=alt.Axis(labelAngle=0)),
                xOffset=alt.X("group:N"),
                y=alt.Y("value:Q"),
                text=alt.Text("value:Q", format=value_format),
            )
        )
        return (bars + labels).properties(title=title, height=260)

    _gmv_chart = _grouped_bar(
        "Weekly GMV (NOK)",
        "Weekly GMV per user",
        "NOK per user per week",
        "~s",
        ",.0f",
    )
    _tx_chart = _grouped_bar(
        "Weekly purchases",
        "Weekly purchases per user",
        "Purchases per user per week",
        ",",
        ",.0f",
    )

    _sel_display = _sel.rename(
        columns={
            "grp": "Group",
            "users": "Users",
            "fy_weekly_gmv": "Full-year weekly GMV (NOK)",
            "pre_weekly_gmv": "Jan-Apr weekly GMV (NOK)",
            "fy_weekly_tx": "Full-year weekly purchases",
            "pre_weekly_tx": "Jan-Apr weekly purchases",
        }
    ).round(1)

    _vip_row = _sel.set_index("grp").loc["Future VIP"]
    _never_row = _sel.set_index("grp").loc["Never VIP"]
    _pre_gmv_ratio = _vip_row["pre_weekly_gmv"] / _never_row["pre_weekly_gmv"]
    _pre_tx_ratio = _vip_row["pre_weekly_tx"] / _never_row["pre_weekly_tx"]
    _fy_gmv_ratio = _vip_row["fy_weekly_gmv"] / _never_row["fy_weekly_gmv"]
    _gap_pct = (_vip_row / _never_row - 1) * 100

    _gap_display = pd.DataFrame(
        {
            "Period": ["Full-year 2025", "Jan-Apr (pre-VIP)"],
            "Weekly GMV gap vs never-VIP (%)": [
                _gap_pct["fy_weekly_gmv"],
                _gap_pct["pre_weekly_gmv"],
            ],
            "Weekly purchases gap vs never-VIP (%)": [
                _gap_pct["fy_weekly_tx"],
                _gap_pct["pre_weekly_tx"],
            ],
        }
    ).round(1)

    mo.vstack(
        [
            mo.md("### 7. Selection Bias & Pre/Post VIP Event Study"),
            mo.md(
                "**PM question 1:** do people who join VIP buy more, the same or "
                "less? 7A shows why a naive comparison is confounded; 7B looks "
                "within users around enrollment."
            ),
            mo.md("#### 7A. Future VIP members were already heavier shoppers"),
            mo.md(
                "Restricted to users observed for the full year. The naive "
                "comparison pools all of 2025; the pre-VIP comparison uses "
                "January-April, before VIP launched in May."
            ),
            mo.hstack([_gmv_chart, _tx_chart], widths="equal"),
            _sel_display,
            mo.md(
                "**Gap vs never-VIP members** (Future VIP mean / Never VIP mean - 1):"
            ),
            _gap_display,
            mo.md(
                f"**Selection check.** Before VIP launched, future members already "
                f"spent {_pre_gmv_ratio:.2f}x more per week "
                f"({_gap_pct['pre_weekly_gmv']:+.1f}%) and made "
                f"{_pre_tx_ratio:.2f}x more purchases per week "
                f"({_gap_pct['pre_weekly_tx']:+.1f}%) than never-VIPs. "
                f"The naive full-year GMV gap is {_fy_gmv_ratio:.2f}x "
                f"({_gap_pct['fy_weekly_gmv']:+.1f}%), so it is "
                "not evidence that joining VIP caused the extra spend."
            ),
            mo.accordion(
                {
                    "How each metric is calculated": mo.md(
                        """
    **Sample.** `df_user_spine` rows with
    `is_full_year_obs == TRUE` (observation starts on or before
    2025-01-01), split by `vip_enrolled` at the 2026-01-01 cutoff:
    "Future VIP" vs "Never VIP".

    **Users.** `COUNT(*)` of those users in each group. Both groups are the
    same users used in every other column, so no rows drop between metrics.

    **Per-user, then averaged.** Every metric is first computed per user,
    then averaged with `AVG(...)` over the group. It is an unweighted mean
    of user rates, not total GMV divided by total users.

    - **Full-year weekly GMV (NOK)** — per user:
      `SUM(volume_nok)` for transactions from 2025-01-01 up to (not
      including) 2026-01-01, divided by `365/7 = 52.142857` weeks.
    - **Full-year weekly purchases** — per user: `COUNT(*)` of transactions
      in the same window, divided by `52.142857`.
    - **Jan-Apr weekly GMV (NOK)** — per user: `SUM(volume_nok)` from
      2025-01-01 up to 2025-05-01, divided by `120/7 = 17.142857` weeks.
    - **Jan-Apr weekly purchases** — per user: `COUNT(*)` in the same window,
      divided by `17.142857`.
    - **Ratios in the text** — group means divided by each other
      (Future VIP / Never VIP), e.g. `_pre_gmv_ratio`.
    - **Gap vs never-VIP (%)** — `(Future VIP mean / Never VIP mean - 1)
      x 100`, applied to each of the four columns above.

    **Zero-fill.** The transaction aggregates are left-joined onto the user
    spine with `COALESCE(..., 0)`, so a user with no purchases in a window
    contributes 0 rather than being excluded. Denominators are fixed
    calendar weeks, not each user's observed weeks.

    **Why Jan-Apr.** VIP launched in May 2025, so January-April activity is
    measured before any future VIP member could have joined. For the
    pre-VIP period the split is still by eventual membership, which is
    what makes the comparison a selection check rather than an effect.
    """
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def vip_event_study(alt, df_weekly_panel, mo, np, pd, stats):
    _panel = df_weekly_panel
    _vip_panel = _panel[
        _panel["vip_cohort"].ne("never_vip")
        & _panel["is_full_year_obs"]
        & _panel["rel_week_to_vip"].between(-8, 8)
    ].copy()
    _complete_weeks = _vip_panel.groupby("user_id")["rel_week_to_vip"].nunique()
    _event = _vip_panel[
        _vip_panel["user_id"].isin(_complete_weeks[_complete_weeks == 17].index)
    ].copy()
    _n_users = int(_event["user_id"].nunique())

    _METRICS = {
        "tx_count": "Purchases",
        "in_person_tx_count": "In-person purchases",
        "online_tx_count": "Online purchases",
        "gmv_nok": "GMV (NOK)",
        "in_person_gmv_nok": "In-person GMV (NOK)",
        "online_gmv_nok": "Online GMV (NOK)",
    }
    _event_pre = _event[_event["rel_week_to_vip"].between(-8, -1)]
    _event_post = _event[_event["rel_week_to_vip"].between(1, 8)]
    _pre_user = _event_pre.groupby("user_id")[list(_METRICS)].mean()
    _post_user = _event_post.groupby("user_id")[list(_METRICS)].mean()
    _pairs = _pre_user.join(_post_user, suffixes=("_pre", "_post")).dropna()

    _rows = []
    for _column, _label in _METRICS.items():
        _before = _pairs[f"{_column}_pre"]
        _after = _pairs[f"{_column}_post"]
        _t_stat, _p_value = stats.ttest_rel(_after, _before)
        _rows.append(
            {
                "metric": _label,
                "pre": _before.mean(),
                "post": _after.mean(),
                "diff": (_after - _before).mean(),
                "pct": (
                    (_after.mean() / _before.mean() - 1) * 100
                    if _before.mean()
                    else np.nan
                ),
                "p": _p_value,
            }
        )
    _summary = pd.DataFrame(_rows)

    def _fmt_p(p_value):
        return f"{p_value:.1e}" if p_value < 0.001 else f"{p_value:.3f}"

    _summary_display = pd.DataFrame(
        {
            "Metric": _summary["metric"],
            "Pre mean": _summary["pre"].round(1),
            "Post mean": _summary["post"].round(1),
            "Difference": _summary["diff"].round(1),
            "Change (%)": _summary["pct"].round(1),
            "p-value": _summary["p"].map(_fmt_p),
        }
    )

    # Calendar-matched never-VIP benchmark: each never-VIP user is assigned one
    # VIP enrollment week (round-robin over the 177 anchors) and read over the
    # same 17 calendar weeks.
    _anchor = (
        _event.loc[_event["rel_week_to_vip"] == 0]
        .set_index("user_id")["week_start"]
        .sort_index()
    )
    _never_ids = np.sort(
        _panel.loc[
            _panel["vip_cohort"].eq("never_vip") & _panel["is_full_year_obs"], "user_id"
        ].unique()
    )
    _n_never = len(_never_ids)
    _anchors = _anchor.to_numpy()
    _match = pd.DataFrame(
        {
            "user_id": _never_ids,
            "anchor": _anchors[np.arange(_n_never) % len(_anchors)],
        }
    )
    _grid = _match.merge(
        pd.DataFrame({"rel_week_to_vip": np.arange(-8, 9)}), how="cross"
    )
    _grid["week_start"] = _grid["anchor"] + pd.to_timedelta(
        7 * _grid["rel_week_to_vip"], unit="D"
    )
    _compare_cols = ["user_id", "week_start", *list(_METRICS)]
    _never_panel = _grid.merge(
        _panel[_compare_cols], on=["user_id", "week_start"], how="left"
    ).fillna(0)
    _never_pre = _never_panel[_never_panel["rel_week_to_vip"].between(-8, -1)]
    _never_post = _never_panel[_never_panel["rel_week_to_vip"].between(1, 8)]

    _compare_rows = []
    for _column, _label in _METRICS.items():
        _vip_pre = _event_pre[_column].mean()
        _vip_post = _event_post[_column].mean()
        _nv_pre = _never_pre[_column].mean()
        _nv_post = _never_post[_column].mean()
        _compare_rows.append(
            {
                "metric": _label,
                "vip_pre": _vip_pre,
                "vip_post": _vip_post,
                "vip_pct": (_vip_post / _vip_pre - 1) * 100 if _vip_pre else np.nan,
                "never_pre": _nv_pre,
                "never_post": _nv_post,
                "never_pct": (_nv_post / _nv_pre - 1) * 100 if _nv_pre else np.nan,
            }
        )
    _compare = pd.DataFrame(_compare_rows)
    _compare["did_pp"] = _compare["vip_pct"] - _compare["never_pct"]

    _compare_display = pd.DataFrame(
        {
            "Metric": _compare["metric"],
            "VIP pre → post": [
                f"{_pre:,.1f} → {_post:,.1f}"
                for _pre, _post in zip(_compare["vip_pre"], _compare["vip_post"])
            ],
            "VIP change (%)": _compare["vip_pct"].round(1),
            "Never VIP pre → post": [
                f"{_pre:,.1f} → {_post:,.1f}"
                for _pre, _post in zip(_compare["never_pre"], _compare["never_post"])
            ],
            "Never VIP change (%)": _compare["never_pct"].round(1),
            "Difference (pp)": _compare["did_pp"].round(1),
        }
    )

    _event_long = _event.melt(
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
    _event_long["channel"] = np.where(
        _event_long["measure"].str.startswith("in_person"),
        "In person",
        "Online",
    )
    _event_long["metric"] = np.where(
        _event_long["measure"].str.endswith("gmv_nok"),
        "GMV",
        "Purchases",
    )
    _event_long["grp"] = "VIP member"
    _event_means = (
        _event_long.groupby(["rel_week_to_vip", "metric", "channel", "grp"])["value"]
        .mean()
        .reset_index()
    )

    _never_means = (
        _never_panel.groupby("rel_week_to_vip")[
            [
                "in_person_tx_count",
                "online_tx_count",
                "in_person_gmv_nok",
                "online_gmv_nok",
            ]
        ]
        .mean()
        .reset_index()
        .melt(id_vars="rel_week_to_vip", var_name="measure", value_name="value")
    )
    _never_means["channel"] = np.where(
        _never_means["measure"].str.startswith("in_person"),
        "In person",
        "Online",
    )
    _never_means["metric"] = np.where(
        _never_means["measure"].str.endswith("gmv_nok"),
        "GMV",
        "Purchases",
    )
    _never_means["grp"] = "Never VIP"

    _CHART_COLUMNS = ["rel_week_to_vip", "metric", "channel", "grp", "value"]
    _chart_data = pd.concat(
        [_event_means[_CHART_COLUMNS], _never_means[_CHART_COLUMNS]],
        ignore_index=True,
    )
    _chart_data["series"] = _chart_data["grp"] + " · " + _chart_data["channel"]
    _SERIES = [
        "VIP member · In person",
        "VIP member · Online",
        "Never VIP · In person",
        "Never VIP · Online",
    ]
    _SERIES_COLORS = ["#f58518", "#4c78a8", "#f7b26a", "#9ec5e8"]
    _GROUPS = ["VIP member", "Never VIP"]
    _event_base = alt.Chart(_chart_data).encode(
        x=alt.X(
            "rel_week_to_vip:Q",
            title="Weeks relative to VIP enrollment",
            axis=alt.Axis(values=list(range(-8, 9))),
        ),
        color=alt.Color(
            "series:N",
            title=None,
            scale=alt.Scale(domain=_SERIES, range=_SERIES_COLORS),
            legend=alt.Legend(orient="top", title=None, columns=2),
        ),
        strokeDash=alt.StrokeDash(
            "grp:N",
            title=None,
            scale=alt.Scale(domain=_GROUPS, range=[[1, 0], [5, 3]]),
            legend=None,
        ),
    )
    _rule = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(strokeDash=[4, 4], color="#666666")
        .encode(x="x:Q")
    )
    _tx_lines = (
        _event_base.transform_filter(alt.datum.metric == "Purchases")
        .mark_line(point=True)
        .encode(
            y=alt.Y("value:Q", title="Mean weekly purchases per user"),
            tooltip=[
                alt.Tooltip("rel_week_to_vip:Q", title="Week"),
                alt.Tooltip("value:Q", title="Mean purchases", format=",.2f"),
                alt.Tooltip("grp:N", title="Group"),
                alt.Tooltip("channel:N", title="Channel"),
            ],
        )
        .properties(title="Weekly purchases: VIP vs never-VIP", height=260)
    )
    _gmv_lines = (
        _event_base.transform_filter(alt.datum.metric == "GMV")
        .mark_line(point=True)
        .encode(
            y=alt.Y(
                "value:Q",
                title="Mean weekly GMV per user (NOK)",
                axis=alt.Axis(format="~s"),
            ),
            tooltip=[
                alt.Tooltip("rel_week_to_vip:Q", title="Week"),
                alt.Tooltip("value:Q", title="Mean GMV", format=",.0f"),
                alt.Tooltip("grp:N", title="Group"),
                alt.Tooltip("channel:N", title="Channel"),
            ],
        )
        .properties(title="Weekly GMV: VIP vs never-VIP", height=260)
    )
    _tx_chart = alt.layer(_tx_lines, _rule)
    _gmv_chart = alt.layer(_gmv_lines, _rule)

    _tx_row = _summary.set_index("metric").loc["Purchases"]
    _gmv_row = _summary.set_index("metric").loc["GMV (NOK)"]
    _in_person_row = _summary.set_index("metric").loc["In-person GMV (NOK)"]
    _online_row = _summary.set_index("metric").loc["Online GMV (NOK)"]
    _cmp_tx = _compare.set_index("metric").loc["Purchases"]
    _cmp_gmv = _compare.set_index("metric").loc["GMV (NOK)"]

    mo.vstack(
        [
            mo.md("#### 7B. Within-user change around VIP enrollment"),
            mo.md(
                f"**{_n_users} full-year VIP members** have a complete 17-week "
                "panel from -8 to +8 weeks around enrollment. Week 0 is the "
                "enrollment week and is excluded from the paired tests."
            ),
            mo.md(
                f"**Calendar-matched comparison.** {_n_never} never-VIP users "
                "observed since 1 January are shown as dashed lines for the "
                "same two channels, each read over the same 17 calendar weeks "
                "as one VIP member (enrollment weeks assigned round-robin). "
                "This is a benchmark, not a randomized control group."
            ),
            mo.hstack([_tx_chart, _gmv_chart], widths="equal"),
            _summary_display,
            mo.md("**VIP vs never-VIP, same calendar weeks:**"),
            _compare_display,
            mo.accordion(
                {
                    "How the plot points and table metrics are calculated": mo.md(
                        """
    **Source table.** `df_weekly_panel`: one row per `user_id` x
    `week_start`, zero-filled activity, plus `vip_cohort`,
    `is_full_year_obs` and `rel_week_to_vip` from the user spine.

    **1. Pick the users.**
    - VIP: `vip_cohort != 'never_vip'`, `is_full_year_obs == True`, and
      all 17 weeks from -8 to +8 present (177 users).
    - Never VIP: `vip_cohort == 'never_vip'` and
      `is_full_year_obs == True` (196 users).

    **2. Map each row to a relative week.**
    - VIP: `rel_week_to_vip` is already in the panel, measured from the
      Monday containing `vip_enrolled_at`.
    - Never VIP: each user is assigned one VIP enrollment week
      (round-robin over the 177 anchors); relative week `r` becomes the
      calendar week `anchor + 7 * r` days, and that `week_start` is looked
      up in the same panel.

    **3. Read the measure.**
    - Purchases chart: `in_person_tx_count` and `online_tx_count`.
    - GMV chart: `in_person_gmv_nok` and `online_gmv_nok`.
    - `*_tx_count` is the number of transactions in that week;
      `*_gmv_nok` is the sum of `volume_nok`. Weeks without purchases are
      0, not missing.

    **4. Average to one point per line.**
    For each `(rel_week_to_vip, group, channel)`, the plotted value is the
    mean of that week's value across users in the group. Because each user
    has exactly one row per week, this is
    `sum(user values) / number of users` (177 VIP, 196 never-VIP). Units
    are purchases per user per week, or NOK per user per week - not
    totals.

    **5. Build the table from the same values.**
    - Purchases: `tx_count`; in-person purchases: `in_person_tx_count`;
      online purchases: `online_tx_count`.
    - GMV: `gmv_nok`; in-person GMV: `in_person_gmv_nok`; online GMV:
      `online_gmv_nok`.
    - Pre window: `rel_week_to_vip` in [-8, -1]; post window: [1, 8];
      week 0 is excluded.
    - Each cell is the mean of the 8 weekly values per user in that
      window, then averaged across users.
    - `VIP change (%)` = (post / pre - 1) x 100; `Never VIP change (%)`
      uses the same formula on the calendar-matched weeks.
    - `Difference (pp)` = VIP change (%) - Never VIP change (%).
    - Paired p-values (VIP table only): two-sided
      `scipy.stats.ttest_rel` on per-user pre and post means.

    **Worked example.** The VIP in-person purchases point at week 0 is the
    sum of `in_person_tx_count` across the 177 users in their enrollment
    week, divided by 177.
    """
                    )
                }
            ),
            mo.md(
                f"**Within-user change.** Weekly purchases rose from "
                f"{_tx_row['pre']:.1f} to {_tx_row['post']:.1f} "
                f"({_tx_row['pct']:+.1f}%, p={_fmt_p(_tx_row['p'])}); weekly GMV "
                f"rose from NOK {_gmv_row['pre']:,.0f} to "
                f"NOK {_gmv_row['post']:,.0f} "
                f"({_gmv_row['pct']:+.1f}%, p={_fmt_p(_gmv_row['p'])}). Online "
                f"GMV was flat ({_online_row['pct']:+.1f}%, "
                f"p={_fmt_p(_online_row['p'])}), while in-person GMV rose "
                f"{_in_person_row['pct']:+.1f}%."
            ),
            mo.md(
                f"**Against never-VIPs.** Over the same calendar weeks, never-VIP "
                f"users changed {_cmp_tx['never_pct']:+.1f}% on weekly purchases "
                f"and {_cmp_gmv['never_pct']:+.1f}% on weekly GMV. The "
                f"difference-in-differences is {_cmp_tx['did_pp']:+.1f} "
                f"percentage points for purchases and {_cmp_gmv['did_pp']:+.1f} "
                "points for GMV, so the VIP increase is not explained by a "
                "common "
                "calendar trend such as seasonality."
            ),
            mo.md(
                "**Interpretation.** The never-VIP benchmark removes common "
                "calendar shocks but not selection: VIP joiners were already "
                "heavier shoppers before enrollment, so the difference-in-"
                "differences is still descriptive, not a randomized causal "
                "effect."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def experiment_waves_overview(alt, df_exp_eval, df_user_spine, mo, pd):
    df_exp_wave = df_exp_eval.merge(
        df_user_spine[["user_id", "experiment_wave"]], on="user_id", how="left"
    )
    df_exp_wave["days_to_cutoff"] = (
        pd.Timestamp("2026-01-01") - df_exp_wave["exposure_timestamp"]
    ).dt.days

    _expo = df_exp_wave.assign(
        week_start=df_exp_wave["exposure_timestamp"].dt.to_period("W").dt.start_time
    )
    _week_counts = (
        _expo.groupby(["week_start", "experiment_wave", "variant"])
        .size()
        .reset_index(name="users")
    )
    _bars = (
        alt.Chart(_week_counts)
        .mark_bar()
        .encode(
            x=alt.X(
                "week_start:T",
                title=None,
                axis=alt.Axis(format="%b %d"),
                scale=alt.Scale(
                    domain=[
                        pd.Timestamp("2025-06-15"),
                        pd.Timestamp("2026-01-20"),
                    ]
                ),
            ),
            xOffset=alt.XOffset("variant:N", title=None),
            y=alt.Y("users:Q", title="Users exposed"),
            color=alt.Color(
                "variant:N",
                title=None,
                scale=alt.Scale(
                    domain=["invitation", "control"],
                    range=["#4c78a8", "#f58518"],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                alt.Tooltip("week_start:T", title="Week of", format="%d %b %Y"),
                alt.Tooltip("experiment_wave:N", title="Wave"),
                alt.Tooltip("variant:N", title="Arm"),
                alt.Tooltip("users:Q", title="Users"),
            ],
        )
    )
    _rules = pd.DataFrame(
        {
            "x": [
                pd.Timestamp("2025-09-01"),
                pd.Timestamp("2025-11-01"),
                pd.Timestamp("2026-01-01"),
            ]
        }
    )
    _rule_layer = (
        alt.Chart(_rules).mark_rule(strokeDash=[4, 4], color="#777777").encode(x="x:T")
    )
    _timeline = alt.layer(_bars, _rule_layer).properties(
        height=260, title="Weekly experiment exposures by wave and arm"
    )

    _summary = (
        df_exp_wave.groupby(["experiment_wave", "variant"])
        .agg(
            users=("user_id", "size"),
            first_exposure=("exposure_timestamp", "min"),
            last_exposure=("exposure_timestamp", "max"),
            median_days_to_cutoff=("days_to_cutoff", "median"),
            full_window_share=("days_to_cutoff", lambda s: (s >= 112).mean() * 100),
        )
        .reset_index()
    )
    _WAVE_LABELS = {"summer": "Summer", "december": "December"}
    _summary_display = pd.DataFrame(
        {
            "Wave": _summary["experiment_wave"].map(_WAVE_LABELS),
            "Variant": _summary["variant"].str.title(),
            "Users": _summary["users"],
            "First exposure": _summary["first_exposure"].dt.strftime("%d %b"),
            "Last exposure": _summary["last_exposure"].dt.strftime("%d %b"),
            "Median days to cutoff": _summary["median_days_to_cutoff"].astype(int),
            "Share with full 16w (%)": _summary["full_window_share"].round(1),
        }
    )

    _summer_rows = df_exp_wave[df_exp_wave["experiment_wave"].eq("summer")]
    _december_rows = df_exp_wave[df_exp_wave["experiment_wave"].eq("december")]
    _summer_n = len(_summer_rows)
    _december_n = len(_december_rows)
    _summer_min_days = int(_summer_rows["days_to_cutoff"].min())
    _december_min_days = int(_december_rows["days_to_cutoff"].min())
    _december_max_days = int(_december_rows["days_to_cutoff"].max())

    mo.vstack(
        [
            mo.md("### 8. Invitation experiment: waves and first-stage take-up"),
            mo.md(
                "**PM question 2, part 1.** Before asking whether inviting people "
                "changes retention, check the experiment ran as intended: who "
                "was exposed, when, and whether the invitation changed signup."
            ),
            mo.md("#### 8A. Exposure timeline and right-censoring"),
            _timeline,
            mo.md(
                "Dashed lines mark 1 Sep (summer wave cut-off), 1 Nov (December "
                "wave start) and 1 Jan 2026 (data cutoff)."
            ),
            _summary_display,
            mo.accordion(
                {
                    "How the timeline and table are calculated": mo.md(
                        """
    `df_exp_wave` is built once in this cell by merging `df_exp_eval`
    (269 rows) with `df_user_spine[["user_id", "experiment_wave"]]` on
    `user_id`.

    | Metric | Calculation | Columns (DataFrame) |
    |---|---|---|
    | Analysis sample | 269 experiment users | `user_id` (`df_exp_eval`) |
    | Wave | Summer if exposure < 1 Sep; December if >= 1 Nov | `experiment_wave` (`df_user_spine`) |
    | Days to cutoff | 1 Jan 2026 minus exposure, in days | `exposure_timestamp` (`df_exp_eval`) |
    | Timeline bars | Count of users per ISO week of exposure x wave x arm | `exposure_timestamp`, `experiment_wave`, `variant` |
    | Users | Count of users per wave x arm | `user_id` |
    | First / last exposure | Min / max exposure | `exposure_timestamp` |
    | Median days to cutoff | Median of days to cutoff | `days_to_cutoff` |
    | Share with full 16w | Mean of `days_to_cutoff >= 112` | `days_to_cutoff` |
    """
                    )
                }
            ),
            mo.md(
                f"**Summer wave.** {_summer_n} users exposed "
                f"{_summer_rows['exposure_timestamp'].min():%d %b} to "
                f"{_summer_rows['exposure_timestamp'].max():%d %b}. The last "
                f"exposure still has {_summer_min_days} days to the cutoff, so "
                "every user has the full 112-day (16-week) observation window."
            ),
            mo.md(
                f"**December wave.** {_december_n} users exposed "
                f"{_december_rows['exposure_timestamp'].min():%d %b} to "
                f"{_december_rows['exposure_timestamp'].max():%d %b}, with only "
                f"{_december_min_days}-{_december_max_days} days to the cutoff. "
                "The 16-week window is truncated for all of them, and exposures "
                "after 18 Dec also truncate the 14-day signup window, so "
                "December retention and late signup are lower bounds."
            ),
        ]
    )
    return (df_exp_wave,)


@app.cell(hide_code=True)
def experiment_signup_rates(alt, df_exp_wave, mo, np, pd, stats):
    _WAVE_LABELS = {"summer": "Summer", "december": "December"}
    _METRIC_ORDER = [
        "Ever enrolled",
        "Enrolled within 14 days of assignment",
    ]
    _december_days = df_exp_wave.loc[
        df_exp_wave["experiment_wave"].eq("december"), "days_to_cutoff"
    ]
    _december_min_days = int(_december_days.min())
    _december_max_days = int(_december_days.max())

    def _z_test(_x1, _n1, _x2, _n2):
        _p1 = _x1 / _n1
        _p2 = _x2 / _n2
        _pool = (_x1 + _x2) / (_n1 + _n2)
        _se = np.sqrt(_pool * (1 - _pool) * (1 / _n1 + 1 / _n2))
        if not _se:
            return np.nan, np.nan
        _z = (_p1 - _p2) / _se
        return _z, 2 * stats.norm.sf(abs(_z))

    _SIGNUP_METRICS = {
        "enrolled_post_exposure": "Ever enrolled",
        "enrolled_within_14d": "Enrolled within 14 days of assignment",
    }
    _ROWS = []
    for _wave in ("summer", "december"):
        _wave_rows = df_exp_wave[df_exp_wave["experiment_wave"].eq(_wave)]
        for _metric, _label in _SIGNUP_METRICS.items():
            _inv = _wave_rows[_wave_rows["variant"].eq("invitation")]
            _ctl = _wave_rows[_wave_rows["variant"].eq("control")]
            _k1, _n1 = int(_inv[_metric].sum()), len(_inv)
            _k2, _n2 = int(_ctl[_metric].sum()), len(_ctl)
            _z, _p = _z_test(_k1, _n1, _k2, _n2)
            for _variant, _k, _n in (
                ("invitation", _k1, _n1),
                ("control", _k2, _n2),
            ):
                _ROWS.append(
                    {
                        "wave": _WAVE_LABELS[_wave],
                        "variant": _variant,
                        "metric": _label,
                        "users": _n,
                        "signups": _k,
                        "rate": _k / _n,
                        "p": _p,
                        "z": _z,
                    }
                )
    _signup = pd.DataFrame(_ROWS)
    _signup["wave"] = pd.Categorical(
        _signup["wave"], ["Summer", "December"], ordered=True
    )
    _signup["metric"] = pd.Categorical(_signup["metric"], _METRIC_ORDER, ordered=True)
    _signup_inv = (
        _signup[_signup["variant"].eq("invitation")]
        .set_index(["wave", "metric"])
        .sort_index()
    )
    _signup_ctl = (
        _signup[_signup["variant"].eq("control")]
        .set_index(["wave", "metric"])
        .sort_index()
    )
    _signup_table = pd.DataFrame(
        {
            "Wave": _signup_inv.index.get_level_values("wave").astype(str),
            "Metric": _signup_inv.index.get_level_values("metric").astype(str),
            "Signups (inv / ctl)": [
                f"{_a} / {_b}"
                for _a, _b in zip(
                    _signup_inv["signups"].to_numpy(),
                    _signup_ctl["signups"].to_numpy(),
                )
            ],
            "Invitation rate (%)": (_signup_inv["rate"] * 100).round(1).to_numpy(),
            "Control rate (%)": (_signup_ctl["rate"] * 100).round(1).to_numpy(),
            "Difference (pp)": ((_signup_inv["rate"] - _signup_ctl["rate"]) * 100)
            .round(1)
            .to_numpy(),
            "p-value": [
                f"{_p:.3f}" if _p >= 0.001 else "<0.001"
                for _p in _signup_inv["p"].to_numpy()
            ],
        }
    )

    _bars = (
        alt.Chart(_signup)
        .mark_bar()
        .encode(
            x=alt.X(
                "metric:N",
                title=None,
                sort=_METRIC_ORDER,
                axis=alt.Axis(labelAngle=0),
            ),
            xOffset=alt.XOffset("variant:N", title=None),
            y=alt.Y(
                "rate:Q",
                title="Share of assigned users",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "variant:N",
                title=None,
                scale=alt.Scale(
                    domain=["invitation", "control"],
                    range=["#4c78a8", "#f58518"],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                alt.Tooltip("wave:N", title="Wave"),
                alt.Tooltip("variant:N", title="Arm"),
                alt.Tooltip("signups:Q", title="Signups"),
                alt.Tooltip("users:Q", title="Users"),
                alt.Tooltip("rate:Q", title="Rate", format=".1%"),
            ],
        )
    )
    _label_encoding = {
        "x": alt.X("metric:N", sort=_METRIC_ORDER),
        "xOffset": alt.XOffset("variant:N"),
        "y": alt.Y("rate:Q"),
        "text": alt.Text("rate:Q", format=".0%"),
    }
    _labels_invitation = (
        alt.Chart(_signup)
        .transform_filter((alt.datum.rate >= 0.2) & (alt.datum.variant == "invitation"))
        .mark_text(dy=10, fontSize=9, color="#ffffff")
        .encode(**_label_encoding)
    )
    _labels_control = (
        alt.Chart(_signup)
        .transform_filter((alt.datum.rate >= 0.2) & (alt.datum.variant == "control"))
        .mark_text(dy=10, fontSize=9, color="#1a1a1a")
        .encode(**_label_encoding)
    )
    _labels_small = (
        alt.Chart(_signup)
        .transform_filter(alt.datum.rate < 0.2)
        .mark_text(dy=-7, fontSize=9, color="#333333")
        .encode(**_label_encoding)
    )
    _signup_chart = (
        alt.layer(_bars, _labels_invitation, _labels_control, _labels_small)
        .properties(width=380, height=170)
        .facet(
            row=alt.Row(
                "wave:N",
                title=None,
                sort=["Summer", "December"],
                header=alt.Header(labelFontSize=11),
            )
        )
        .properties(title="VIP signup rate by wave and arm")
    )

    _summer_inv = _signup_inv.loc[("Summer", "Ever enrolled")]
    _summer_inv14 = _signup_inv.loc[("Summer", "Enrolled within 14 days of assignment")]
    _summer_ctl = _signup_ctl.loc[("Summer", "Ever enrolled")]
    _summer_ctl14 = _signup_ctl.loc[("Summer", "Enrolled within 14 days of assignment")]
    _dec_inv = _signup_inv.loc[("December", "Ever enrolled")]
    _dec_ctl = _signup_ctl.loc[("December", "Ever enrolled")]

    mo.vstack(
        [
            mo.md("#### 8B. Signup rate by wave and arm"),
            mo.md(
                f"Assigned users: {int(_summer_inv['users'])} invitation vs "
                f"{int(_summer_ctl['users'])} control in summer; "
                f"{int(_dec_inv['users'])} vs {int(_dec_ctl['users'])} in "
                "December. The 86 summer joiners counted here are experiment "
                "users who enrolled after assignment; the 90 members who "
                "enrolled in May (Section 4) predate the 1 July experiment and "
                "are outside these arms. Bars show the raw rate; the p-value is "
                "a two-sided "
                "two-proportion z-test within each "
                "wave (a chi-square test on the same 2x2 table gives the same p, "
                "since z squared equals chi-square)."
            ),
            _signup_chart,
            _signup_table,
            mo.accordion(
                {
                    "How the two signup rates are calculated": mo.md(
                        """
    **Denominator.** Every user assigned to the arm in that wave
    (intention-to-treat): 113 invitation vs 113 control in summer, 22 vs 21
    in December. Users who never opened or acted on an invitation stay in
    the denominator.

    **Ever enrolled.** `vip_enrolled == TRUE` and
    `vip_enrolled_at >= exposure_timestamp` in `df_exp_eval`, i.e. VIP
    membership observed at any point from assignment up to the 1 Jan 2026
    cutoff.

    **Enrolled within 14 days.** The same flag plus
    `vip_enrolled_at < exposure_timestamp + INTERVAL 14 DAY`, evaluated on
    exact timestamps (strictly under 336 hours, not calendar-day counts).

    **14 days from what?** `exposure_timestamp` is the randomization
    (assignment) time recorded for every user in `experiment_exposure`,
    including control. It is not an invitation-send or open time, and no
    message is sent to control. Both arms share the same summer assignment
    window (1 Jul-25 Aug, 46 distinct dates each), so "within 14 days" means
    within 14 days of assignment in both arms.

    **Both arms use the identical rule.** Control users receive no
    invitation, so any enrollment is organic/self-serve; it still counts if
    it happens within 14 days of their assignment. That is why summer
    control shows 5.3% within 14 days (6 of 113): these are control-arm
    joiners who contaminate the ITT comparison.

    **Why ever-enrolled can exceed within-14-days.** The two windows
    differ: ever-enrolled runs to the 1 Jan cutoff (up to 16 weeks),
    within-14-days stops on day 14. In summer, 9 control users enrolled but
    only 6 did so within 14 days; the other three joined on days 17, 19 and
    20 after exposure. Invitation shows the same pattern: 77 vs 52, with 25
    joiners arriving after day 14.

    **Censoring.** December exposures run 15-27 Dec, so the 14-day window
    ends between 29 Dec and 10 Jan, after the 1 Jan cutoff. Exposures after
    18 Dec are right-censored, and the observed December within-14-day rate
    equals ever-enrolled (8 of 22 vs 2 of 21) because later enrollments
    cannot be seen.

    | Metric | Calculation | Columns (DataFrame) |
    |---|---|---|
    | Denominator | Rows per wave x arm | `user_id` (`df_exp_eval`) |
    | Ever enrolled | `vip_enrolled` and `vip_enrolled_at >= exposure_timestamp` | `vip_enrolled`, `vip_enrolled_at`, `exposure_timestamp` (`df_exp_eval`) |
    | Within 14 days | Same, plus `vip_enrolled_at < exposure_timestamp + 14 days` | Same |
    | Rate | Signups / users | Derived |
    | Difference (pp) | `(rate_invitation - rate_control) x 100` | Derived |
    | p-value | Two-proportion z-test on signups / users | Derived |

    The two flags are created in `build_analytical_marts` from
    `users.vip_enrolled`, `users.vip_enrolled_at` and
    `experiment_exposure.exposure_timestamp`.
    """
                    )
                }
            ),
            mo.md(
                f"**Summer wave.** Invitation lift is huge: "
                f"{_summer_inv['rate']:.1%} ever enrolled vs "
                f"{_summer_ctl['rate']:.1%} in control "
                f"(+{(_summer_inv['rate'] - _summer_ctl['rate']) * 100:.1f} pp, "
                f"p={_summer_inv['p']:.1e}); within 14 days, "
                f"{_summer_inv14['rate']:.1%} vs {_summer_ctl14['rate']:.1%} "
                f"(+{(_summer_inv14['rate'] - _summer_ctl14['rate']) * 100:.1f} "
                f"pp, p={_summer_inv14['p']:.1e})."
            ),
            mo.md(
                f"**December wave.** {_dec_inv['rate']:.1%} vs "
                f"{_dec_ctl['rate']:.1%} ever enrolled "
                f"(+{(_dec_inv['rate'] - _dec_ctl['rate']) * 100:.1f} pp, "
                f"p={_dec_inv['p']:.3f}), but with only "
                f"{_december_min_days}-{_december_max_days} days observed these "
                "rates are lower bounds."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def experiment_cumulative_signup(alt, df_exp_wave, mo, pd):
    _summer = df_exp_wave[df_exp_wave["experiment_wave"].eq("summer")]
    _CURVE_ROWS = []
    for _variant in ("invitation", "control"):
        _group = _summer[_summer["variant"].eq(_variant)]
        _weeks = _group["days_to_enroll"] / 7
        _n = len(_group)
        for _week in range(17):
            _cum = int((_weeks <= _week).sum())
            _CURVE_ROWS.append(
                {
                    "variant": _variant,
                    "week": _week,
                    "enrolled": _cum,
                    "users": _n,
                    "rate": _cum / _n,
                }
            )
    _curve = pd.DataFrame(_CURVE_ROWS)

    _curve_chart = (
        alt.Chart(_curve)
        .mark_line(interpolate="step-after", point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(
                "week:Q",
                title="Weeks since exposure",
                axis=alt.Axis(values=list(range(0, 17, 2))),
            ),
            y=alt.Y(
                "rate:Q",
                title="Cumulative share of assigned users enrolled",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "variant:N",
                title=None,
                scale=alt.Scale(
                    domain=["invitation", "control"],
                    range=["#4c78a8", "#f58518"],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                alt.Tooltip("variant:N", title="Arm"),
                alt.Tooltip("week:Q", title="Weeks since exposure"),
                alt.Tooltip("enrolled:Q", title="Enrolled"),
                alt.Tooltip("users:Q", title="Assigned"),
                alt.Tooltip("rate:Q", title="Cumulative share", format=".1%"),
            ],
        )
        .properties(
            width=640,
            height=300,
            title="Cumulative signup, summer wave (all exits observed)",
        )
    )

    _curve_display = (
        _curve[_curve["week"].isin([0, 1, 2, 3, 4, 6, 8, 16])]
        .pivot(index="week", columns="variant", values="rate")
        .reindex(columns=["invitation", "control"])
        .mul(100)
        .round(1)
        .reset_index()
        .rename(
            columns={
                "week": "Weeks since exposure",
                "invitation": "Invitation (%)",
                "control": "Control (%)",
            }
        )
    )

    _inv_final = _curve.loc[
        (_curve["variant"].eq("invitation")) & (_curve["week"].eq(16)), "rate"
    ].iloc[0]
    _ctl_final = _curve.loc[
        (_curve["variant"].eq("control")) & (_curve["week"].eq(16)), "rate"
    ].iloc[0]
    _inv_week4 = _curve.loc[
        (_curve["variant"].eq("invitation")) & (_curve["week"].eq(4)), "rate"
    ].iloc[0]

    mo.vstack(
        [
            mo.md("#### 8C. Cumulative signup by weeks since exposure"),
            mo.md(
                "Shares are cumulative over all assigned users (intention-to-"
                "treat), so the curve converges to the ever-enrolled rate in 8B. "
                "Only the summer wave is shown: every summer user has 16 full "
                "weeks, while the December wave has 5-17 days."
            ),
            _curve_chart,
            _curve_display,
            mo.accordion(
                {
                    "How the cumulative series is calculated": mo.md(
                        """
    | Metric | Calculation | Columns (DataFrame) |
    |---|---|---|
    | Weeks since exposure | `days_to_enroll / 7` | `days_to_enroll` (`df_exp_eval`) |
    | Cumulative enrolled at week w | Count of users with `days_to_enroll <= 7w` | `days_to_enroll` |
    | Cumulative share | Cumulative enrolled / users in the arm | `user_id`, `variant` |
    | Sample | Summer wave only (all 16 weeks observed) | `experiment_wave` (`df_exp_wave`) |

    `days_to_enroll` is `date_diff('day', exposure_timestamp, vip_enrolled_at)`
    and is null for users who never enrolled, so they count as not-yet-enrolled
    at every week.
    """
                    )
                }
            ),
            mo.md(
                f"**Take-up is fast.** Invitation take-up reaches "
                f"{_inv_week4:.1%} by week 4 and is unchanged at week 16 "
                f"({_inv_final:.1%}); control reaches {_ctl_final:.1%}. The gap "
                "opens in the first two weeks and then stays flat, so the "
                "16-week window is sufficient for signup and the remaining "
                "question is whether those members stay active."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def experiment_causal_estimates(df_exp_wave, mo, np, pd):
    _SUMMER = df_exp_wave[df_exp_wave["experiment_wave"].eq("summer")].copy()
    _TREAT = _SUMMER["variant"].eq("invitation").to_numpy(dtype=float)
    _COVARIATES = np.column_stack(
        [
            np.ones(len(_SUMMER)),
            _TREAT,
            _SUMMER["june_tx_count"].to_numpy(dtype=float),
            _SUMMER["pre_tx_per_week"].to_numpy(dtype=float),
        ]
    )

    def _diff_means(_y, _t):
        _y1, _y0 = _y[_t == 1], _y[_t == 0]
        _est = _y1.mean() - _y0.mean()
        _se = np.sqrt(_y1.var(ddof=1) / len(_y1) + _y0.var(ddof=1) / len(_y0))
        return _est, _se

    def _ols_hc1(_y, _x):
        _xtx_inv = np.linalg.inv(_x.T @ _x)
        _beta = _xtx_inv @ _x.T @ _y
        _resid = _y - _x @ _beta
        _n, _k = _x.shape
        _omega = np.diag(_resid**2 * _n / (_n - _k))
        _cov = _xtx_inv @ (_x.T @ _omega @ _x) @ _xtx_inv
        return _beta, np.sqrt(np.diag(_cov))

    _RNG = np.random.default_rng(20251103)

    def _late_ci(_y, _t, _first, _reps=2000):
        _n = len(_y)
        _out = np.empty(_reps)
        for _b in range(_reps):
            _idx = _RNG.integers(0, _n, _n)
            _yb, _tb = _y[_idx], _t[_idx]
            _fe, _ = _diff_means(_first[_idx], _tb)
            _oe, _ = _diff_means(_yb, _tb)
            _out[_b] = _oe / _fe if _fe else np.nan
        return np.nanpercentile(_out, [2.5, 97.5])

    _METRIC_SPECS = [
        (
            "Consistency",
            "post_active_week_share_16w",
            "Active week share",
            "share",
        ),
        (
            "Consistency",
            "in_person_active_week_share_16w",
            "In-person active week share",
            "share",
        ),
        (
            "Consistency",
            "online_active_month_share_16w",
            "Online active month share",
            "share",
        ),
        (
            "Velocity & survival",
            "post_median_gap_days",
            "Median days between purchases",
            "days",
        ),
        (
            "Velocity & survival",
            "retained_last_28d",
            "Retained in last 28 days",
            "share",
        ),
        (
            "Volume, revenue & channel",
            "post_tx_per_week_16w",
            "Purchases per week",
            "count",
        ),
        (
            "Volume, revenue & channel",
            "post_gmv_per_week_16w",
            "GMV per week",
            "money",
        ),
        (
            "Volume, revenue & channel",
            "post_rev_per_week_16w",
            "Revenue per week",
            "money",
        ),
        (
            "Volume, revenue & channel",
            "is_dual_channel_16w",
            "Dual channel",
            "share",
        ),
    ]
    _DEFINITION_ORDER = [
        "Consistency",
        "Velocity & survival",
        "Volume, revenue & channel",
    ]
    _METRIC_ORDER = [spec[2] for spec in _METRIC_SPECS]
    _PLOT_EXCLUDE = {"Median days between purchases", "Dual channel"}
    _FIRST_STAGE, _FIRST_STAGE_SE = _diff_means(
        _SUMMER["enrolled_post_exposure"].to_numpy(dtype=float), _TREAT
    )

    _ROWS = []
    for _definition, _column, _label, _unit in _METRIC_SPECS:
        _y = _SUMMER[_column].astype(float).to_numpy()
        _mask = ~np.isnan(_y)
        _y, _t, _x = _y[_mask], _TREAT[_mask], _COVARIATES[_mask]
        _first = _SUMMER.loc[_mask, "enrolled_post_exposure"].to_numpy(dtype=float)
        _control = _y[_t == 0].mean()
        _raw, _raw_se = _diff_means(_y, _t)
        _beta, _beta_se = _ols_hc1(_y, _x)
        _adj, _adj_se = float(_beta[1]), float(_beta_se[1])
        _late = _raw / _FIRST_STAGE
        _late_lo, _late_hi = _late_ci(_y, _t, _first)
        _ROWS.append(
            {
                "definition": _definition,
                "metric": _label,
                "unit": _unit,
                "n": int(_mask.sum()),
                "control": _control,
                "raw": _raw,
                "raw_se": _raw_se,
                "adj": _adj,
                "adj_se": _adj_se,
                "late": _late,
                "late_lo": _late_lo,
                "late_hi": _late_hi,
                "raw_pct": _raw / _control * 100,
                "raw_lo_pct": (_raw - 1.96 * _raw_se) / _control * 100,
                "raw_hi_pct": (_raw + 1.96 * _raw_se) / _control * 100,
                "adj_pct": _adj / _control * 100,
                "adj_lo_pct": (_adj - 1.96 * _adj_se) / _control * 100,
                "adj_hi_pct": (_adj + 1.96 * _adj_se) / _control * 100,
                "late_pct": _late / _control * 100,
                "late_lo_pct": _late_lo / _control * 100,
                "late_hi_pct": _late_hi / _control * 100,
                "plot": _label not in _PLOT_EXCLUDE,
            }
        )

    df_itt = pd.DataFrame(_ROWS)
    df_itt["definition"] = pd.Categorical(
        df_itt["definition"], _DEFINITION_ORDER, ordered=True
    )
    df_itt["metric"] = pd.Categorical(df_itt["metric"], _METRIC_ORDER, ordered=True)
    df_itt = df_itt.sort_values(["definition", "metric"]).reset_index(drop=True)

    def _fmt_mean(_value, _unit):
        if _unit == "share":
            return f"{_value:.1%}"
        if _unit == "days":
            return f"{_value:.2f} d"
        if _unit == "count":
            return f"{_value:.1f}"
        return f"{_value:,.0f} NOK"

    def _fmt_abs(_value, _unit):
        if _unit == "share":
            return f"{_value * 100:+.1f} pp"
        if _unit == "days":
            return f"{_value:+.2f} d"
        if _unit == "count":
            return f"{_value:+.2f}"
        return f"{_value:+,.0f} NOK"

    def _fmt_ci(_est, _se, _unit):
        _lo = _fmt_abs(_est - 1.96 * _se, _unit)
        _hi = _fmt_abs(_est + 1.96 * _se, _unit)
        return f"{_lo} to {_hi}"

    _itt_table = pd.DataFrame(
        {
            "Metric": df_itt["metric"].astype(str),
            "Control mean": [
                _fmt_mean(_row["control"], _row["unit"])
                for _, _row in df_itt.iterrows()
            ],
            "Raw ITT [95% CI]": [
                f"{_fmt_abs(_row['raw'], _row['unit'])} "
                f"[{_fmt_ci(_row['raw'], _row['raw_se'], _row['unit'])}]"
                for _, _row in df_itt.iterrows()
            ],
            "Adjusted ITT [95% CI]": [
                f"{_fmt_abs(_row['adj'], _row['unit'])} "
                f"[{_fmt_ci(_row['adj'], _row['adj_se'], _row['unit'])}]"
                for _, _row in df_itt.iterrows()
            ],
            "LATE (IV) [95% CI]": [
                f"{_fmt_abs(_row['late'], _row['unit'])} "
                f"[{_fmt_abs(_row['late_lo'], _row['unit'])} to "
                f"{_fmt_abs(_row['late_hi'], _row['unit'])}]"
                for _, _row in df_itt.iterrows()
            ],
        }
    )

    mo.vstack(
        [
            mo.md("### 9. Invitation experiment: causal retention and spend impact"),
            mo.md(
                "**PM question 2, part 2.** The summer wave has a full 16-week "
                "post-exposure window (8A). Here the invitation's effect on "
                "retention and spend is estimated three ways: raw intent-to-"
                "treat (ITT), regression-adjusted ITT, and an instrumental-"
                "variables Wald LATE."
            ),
            mo.md(
                f"The first stage is **{_FIRST_STAGE:.1%}** "
                f"(se {_FIRST_STAGE_SE:.1%}): invitation raises ever-enrollment "
                "from 8.0% to 68.1%. Raw ITT is therefore diluted by non-"
                "compliance, and the LATE rescales it by this first stage. "
                "Estimates use the 113 invitation and 113 control users in the "
                "summer wave."
            ),
            _itt_table,
            mo.md(
                "**Two metrics are uninformative in this sample.** Median days "
                "between purchases averages 0.20 days in control because users "
                "make several purchases per day, and dual-channel is 100% in "
                "both arms. Both are kept in the table but excluded from the "
                "forest plot."
            ),
        ]
    )
    return (df_itt,)


@app.cell(hide_code=True)
def experiment_forest_plot(alt, df_itt, mo, pd):
    _ESTIMATORS = ["Raw ITT", "Adjusted ITT", "LATE (IV)"]
    _FOREST_ROWS = []
    for _, _row in df_itt[df_itt["plot"]].iterrows():
        for _name, _pct, _lo, _hi in (
            ("Raw ITT", _row["raw_pct"], _row["raw_lo_pct"], _row["raw_hi_pct"]),
            (
                "Adjusted ITT",
                _row["adj_pct"],
                _row["adj_lo_pct"],
                _row["adj_hi_pct"],
            ),
            (
                "LATE (IV)",
                _row["late_pct"],
                _row["late_lo_pct"],
                _row["late_hi_pct"],
            ),
        ):
            _FOREST_ROWS.append(
                {
                    "definition": str(_row["definition"]),
                    "metric": str(_row["metric"]),
                    "estimator": _name,
                    "pct": _pct,
                    "lo": _lo,
                    "hi": _hi,
                }
            )
    _forest = pd.DataFrame(_FOREST_ROWS)
    _METRIC_SORT = df_itt.loc[df_itt["plot"], "metric"].astype(str).tolist()

    _forest_base = alt.Chart(_forest).encode(
        y=alt.Y("metric:N", sort=_METRIC_SORT, title=None),
        yOffset=alt.YOffset("estimator:N", sort=_ESTIMATORS),
        color=alt.Color(
            "estimator:N",
            title=None,
            scale=alt.Scale(
                domain=_ESTIMATORS,
                range=["#8c8c8c", "#4c78a8", "#f58518"],
            ),
            legend=alt.Legend(orient="top", title=None, columns=3),
        ),
        shape=alt.Shape(
            "estimator:N",
            title=None,
            scale=alt.Scale(
                domain=_ESTIMATORS,
                range=["circle", "square", "diamond"],
            ),
            legend=None,
        ),
    )
    _forest_rules = _forest_base.mark_rule(strokeWidth=1.6).encode(
        x=alt.X("lo:Q", title="% lift vs control mean"),
        x2="hi:Q",
    )
    _forest_points = _forest_base.mark_point(filled=True, size=90).encode(
        x=alt.X("pct:Q", title="% lift vs control mean"),
        tooltip=[
            alt.Tooltip("metric:N", title="Metric"),
            alt.Tooltip("estimator:N", title="Estimator"),
            alt.Tooltip("pct:Q", title="% lift", format="+.1f"),
            alt.Tooltip("lo:Q", title="95% CI low", format="+.1f"),
            alt.Tooltip("hi:Q", title="95% CI high", format="+.1f"),
        ],
    )
    _forest_zero = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(strokeDash=[4, 4], color="#666666")
        .encode(x="x:Q")
    )
    _forest_chart = alt.layer(_forest_zero, _forest_rules, _forest_points).properties(
        height=420,
        title="Effect of VIP invitation on retention and spend (summer wave)",
    )

    _row = df_itt.set_index("metric")
    _purch = _row.loc["Purchases per week"]
    _gmv = _row.loc["GMV per week"]
    _rev = _row.loc["Revenue per week"]
    _active = _row.loc["Active week share"]
    _retained = _row.loc["Retained in last 28 days"]

    mo.vstack(
        [
            mo.md("#### 9A. Forest plot: % lift with 95% confidence intervals"),
            mo.md(
                "Each point is the estimated effect as a percentage of the "
                "control mean, with a 95% interval. Adjusted ITT comes from OLS "
                "with `june_tx_count` and `pre_tx_per_week` as covariates; "
                "LATE scales the ITT by the 60.2 pp first stage. A metric whose "
                "interval crosses zero has no detectable effect."
            ),
            _forest_chart,
            mo.md(
                f"**Result.** After adjustment, weekly purchases move "
                f"{_purch['adj_pct']:+.1f}% "
                f"({_purch['adj_lo_pct']:+.1f} to {_purch['adj_hi_pct']:+.1f}), "
                f"GMV {_gmv['adj_pct']:+.1f}% "
                f"({_gmv['adj_lo_pct']:+.1f} to {_gmv['adj_hi_pct']:+.1f}) and "
                f"revenue {_rev['adj_pct']:+.1f}% "
                f"({_rev['adj_lo_pct']:+.1f} to {_rev['adj_hi_pct']:+.1f}). "
                f"Active-week share is {_active['adj_pct']:+.1f}% and 28-day "
                f"retention {_retained['adj_pct']:+.1f}% "
                f"({_retained['adj_lo_pct']:+.1f} to "
                f"{_retained['adj_hi_pct']:+.1f}). No metric is significant at "
                "95%."
            ),
            mo.md(
                f"**Per complier.** The LATE is larger because it divides by a "
                f"60.2 pp first stage: purchases {_purch['late_pct']:+.1f}% "
                f"({_purch['late_lo_pct']:+.1f} to {_purch['late_hi_pct']:+.1f}) "
                f"and 28-day retention {_retained['late_pct']:+.1f}% "
                f"({_retained['late_lo_pct']:+.1f} to "
                f"{_retained['late_hi_pct']:+.1f}), but the intervals are wide "
                "and include zero."
            ),
            mo.md(
                "**What this means.** Invitation reliably creates members but "
                "does not detectably change 16-week usage. The intervals still "
                "allow moderate gains: the adjusted upper bounds are about +11% "
                "for purchases and +12% for GMV, so effects larger than that "
                "are ruled out. Retention metrics are near ceiling in this "
                "heavy-user sample (89% of weeks active, 66-73% retained), "
                "which limits power to detect small improvements."
            ),
            mo.accordion(
                {
                    "How the ITT, adjusted ITT and LATE are calculated": mo.md(
                        """
    **Sample.** Summer wave only (113 invitation, 113 control), 16-week
    post-exposure outcomes from `df_exp_eval`. The December wave is
    excluded because its window is right-censored (8A).

    **Raw ITT.** Difference in arm means,
    `mean(y | invitation) - mean(y | control)`, with
    `se = sqrt(var_inv / n_inv + var_ctl / n_ctl)` and a normal 95%
    interval (`estimate +/- 1.96 se`). Percent lift divides the estimate
    by the control mean.

    **Adjusted ITT (CUPED-style OLS).** Linear regression

    `y = a + b * invitation + c * june_tx_count + d * pre_tx_per_week`

    where `b` is the adjusted ITT. Standard errors are HC1
    heteroskedasticity-robust. Binary outcomes use a linear probability
    model. Covariates are pre-treatment, so adjustment improves precision
    without changing the estimand; June transactions proxy the
    randomization block and pre-exposure purchases proxy baseline
    activity.

    **LATE (Wald IV).** `ITT_outcome / ITT_enrollment`, where
    `ITT_enrollment` is the invitation effect on `enrolled_post_exposure`
    (60.2 pp). The 95% interval comes from 2,000 bootstrap resamples of
    users (percentile 2.5/97.5, seed 20251103). This is the effect for
    users who enroll only because they were invited; it requires the
    exclusion restriction (invitation affects outcomes only through
    enrollment) and monotonicity (no defiers).

    **Caveats.** LATE is imprecise because the first stage is the
    denominator; confidence intervals are not adjusted for multiple
    metrics; median-gap and dual-channel are degenerate in this sample.

    | Metric | Column (`df_exp_eval`) | Construction (16-week window) |
    |---|---|---|
    | Active week share | `post_active_week_share_16w` | Distinct 7-day buckets with >= 1 purchase / 16 |
    | In-person active week share | `in_person_active_week_share_16w` | Same, in_person only / 16 |
    | Online active month share | `online_active_month_share_16w` | Distinct 28-day buckets with >= 1 online purchase / 4 |
    | Median days between purchases | `post_median_gap_days` | Median `date_diff('day', previous, current)` across post-exposure purchases; null if fewer than 2 |
    | Retained in last 28 days | `retained_last_28d` | At least one purchase from 2025-12-04 to 2025-12-31 |
    | Purchases per week | `post_tx_per_week_16w` | Post-exposure transaction count / 16 |
    | GMV per week | `post_gmv_per_week_16w` | Sum of `volume_nok` / 16 |
    | Revenue per week | `post_rev_per_week_16w` | Sum of `revenue_nok` / 16 |
    | Dual channel | `is_dual_channel_16w` | At least one in_person and one online purchase in the window |

    Treatment is `df_exp_wave.variant`; covariates are
    `df_exp_wave.june_tx_count` and `df_exp_wave.pre_tx_per_week`. The window
    is `[exposure_timestamp, exposure_timestamp + 112 days)` and all count
    and sum outcomes are zero-filled for users without purchases.
    """
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def channel_controls(mo):
    SECTOR_COUNT = 5
    sector_count = mo.ui.slider(
        start=1,
        stop=SECTOR_COUNT,
        step=1,
        value=SECTOR_COUNT,
        label="Sectors shown (sorted by take rate)",
        show_value=True,
    )
    mo.vstack(
        [
            mo.md("### 10. Channel economics and next steps"),
            mo.md("#### 10A. Take rate, ticket size and frequency by category"),
            mo.md(
                "**PM question 3: what should we do next?** In-person volume is "
                "concentrated in Grocery/Food; online categories have higher "
                "tickets and higher take rates but far lower purchase frequency. "
                "The three charts use 2025 purchases by users observed for the "
                "full year."
            ),
            sector_count,
        ]
    )
    return (sector_count,)


@app.cell(hide_code=True)
def channel_economics(
    alt,
    df_user_spine,
    mcc,
    merchants,
    mo,
    pd,
    sector_count,
    transactions,
):
    _CATEGORY = {
        "5411": "Grocery/Food",
        "5499": "Grocery/Food",
        "5651": "Clothing",
        "5732": "Electronics",
        "5712": "Furniture",
        "5942": "Books",
    }
    _tx = transactions.merge(
        merchants[["merchant_id", "merchant_mcc_code"]],
        on="merchant_id",
        how="left",
    ).merge(mcc, on="merchant_mcc_code", how="left")
    _tx = _tx[_tx["transaction_timestamp"].dt.year.eq(2025)].copy()
    _tx["category"] = _tx["merchant_mcc_code"].map(_CATEGORY)
    _full_ids = set(df_user_spine.loc[df_user_spine["is_full_year_obs"], "user_id"])
    _tx_full = _tx[_tx["user_id"].isin(_full_ids)]

    _CHANNEL_LABELS = {"in_person": "In person", "online": "Online"}
    _agg = _tx_full.groupby(["category", "payment_channel"], as_index=False).agg(
        purchases=("transaction_id", "size"),
        gmv=("volume_nok", "sum"),
        revenue=("revenue_nok", "sum"),
        users=("user_id", "nunique"),
    )
    _agg["channel"] = _agg["payment_channel"].map(_CHANNEL_LABELS)
    _agg["take_rate"] = _agg["revenue"] / _agg["gmv"]
    _agg["ticket"] = _agg["gmv"] / _agg["purchases"]
    _agg["freq"] = _agg["purchases"] / _agg["users"] / 52
    _agg = _agg.sort_values("take_rate", ascending=False).reset_index(drop=True)
    _agg_plot = _agg.head(sector_count.value)
    _CATEGORY_ORDER = _agg_plot["category"].tolist()

    _CHANNEL_COLORS = alt.Scale(
        domain=["In person", "Online"], range=["#f58518", "#4c78a8"]
    )

    def _channel_bar(
        _metric, _title, _axis_title, _fmt, _legend, _label_fmt, _inside=True
    ):
        _bars = (
            alt.Chart(_agg_plot)
            .mark_bar()
            .encode(
                x=alt.X(
                    "category:N",
                    title=None,
                    sort=_CATEGORY_ORDER,
                    axis=alt.Axis(labelAngle=-30),
                ),
                y=alt.Y(
                    f"{_metric}:Q",
                    title=_axis_title,
                    axis=alt.Axis(format=_fmt),
                    scale=alt.Scale(nice=True),
                ),
                color=alt.Color(
                    "channel:N",
                    title=None,
                    scale=_CHANNEL_COLORS,
                    legend=alt.Legend(orient="top", title=None) if _legend else None,
                ),
                tooltip=[
                    alt.Tooltip("category:N", title="Category"),
                    alt.Tooltip("channel:N", title="Channel"),
                    alt.Tooltip(f"{_metric}:Q", title=_axis_title, format=_fmt),
                    alt.Tooltip("purchases:Q", title="Purchases", format=","),
                ],
            )
        )
        _label_encoding = {
            "x": alt.X("category:N", sort=_CATEGORY_ORDER),
            "y": alt.Y(f"{_metric}:Q"),
            "text": alt.Text(f"{_metric}:Q", format=_label_fmt),
        }
        if _inside:
            _labels_online = (
                alt.Chart(_agg_plot)
                .transform_filter(alt.datum.channel == "Online")
                .mark_text(dy=10, fontSize=9, color="#ffffff")
                .encode(**_label_encoding)
            )
            _labels_in_person = (
                alt.Chart(_agg_plot)
                .transform_filter(alt.datum.channel == "In person")
                .mark_text(dy=10, fontSize=9, color="#1a1a1a")
                .encode(**_label_encoding)
            )
            return alt.layer(_bars, _labels_online, _labels_in_person).properties(
                width=240, height=260, title=_title
            )
        _labels = (
            alt.Chart(_agg_plot)
            .mark_text(dy=-7, fontSize=9, color="#333333")
            .encode(**_label_encoding)
        )
        return alt.layer(_bars, _labels).properties(width=240, height=260, title=_title)

    _chart_take = _channel_bar(
        "take_rate", "Take rate", "Revenue / GMV", ".1%", True, ".1%"
    )
    _chart_ticket = _channel_bar(
        "ticket", "Average ticket", "NOK per purchase", ",.0f", False, ",.0f"
    )
    _chart_freq = _channel_bar(
        "freq",
        "Purchase frequency",
        "Purchases per active user per week",
        ".1f",
        False,
        ".2f",
        _inside=False,
    )

    _channel_table = pd.DataFrame(
        {
            "Category": _agg_plot["category"],
            "Channel": _agg_plot["channel"],
            "Purchases": _agg_plot["purchases"].map("{:,}".format),
            "Revenue (NOK)": _agg_plot["revenue"].map("{:,.0f}".format),
            "Take rate (%)": (_agg_plot["take_rate"] * 100).round(2),
            "Avg ticket (NOK)": _agg_plot["ticket"].round(0),
            "Purchases/user/week": _agg_plot["freq"].round(2),
        }
    )

    _vip_ids = set(
        df_user_spine.loc[
            df_user_spine["vip_enrolled"] & df_user_spine["is_full_year_obs"],
            "user_id",
        ]
    )
    _vip_tx = _tx[_tx["user_id"].isin(_vip_ids)]
    _per_user = _vip_tx.groupby("user_id").agg(
        total_tx=("transaction_id", "size"),
        in_person_tx=("payment_channel", lambda s: int((s == "in_person").sum())),
        online_tx=("payment_channel", lambda s: int((s == "online").sum())),
    )
    _per_user["in_person_share"] = _per_user["in_person_tx"] / _per_user["total_tx"]
    _target = _per_user[
        (_per_user["in_person_share"] >= 0.9) & (_per_user["total_tx"] >= 52)
    ]
    _n_target = len(_target)
    _current_online = float(_target["online_tx"].mean())
    _benchmark = float(_per_user["online_tx"].quantile(0.75))

    _online = _tx[_tx["payment_channel"].eq("online")]
    _online_ticket = float(_online["volume_nok"].mean())
    _online_take = float(_online["revenue_nok"].sum() / _online["volume_nok"].sum())
    _online_revenue = float(_online["revenue_nok"].sum())
    _total_revenue = float(_tx["revenue_nok"].sum())

    _SCENARIOS = [0.10, 0.25, 0.50]
    _size_rows = []
    for _capture in _SCENARIOS:
        _extra_per_user = (_benchmark - _current_online) * _capture
        _extra_tx = _extra_per_user * _n_target
        _extra_gmv = _extra_tx * _online_ticket
        _extra_rev = _extra_gmv * _online_take
        _size_rows.append(
            {
                "Scenario": f"Close {_capture:.0%} of gap",
                "Extra online purchases / user / yr": _extra_per_user,
                "Extra purchases / yr": _extra_tx,
                "Incremental GMV (NOK)": _extra_gmv,
                "Incremental revenue (NOK)": _extra_rev,
                "% of online revenue": _extra_rev / _online_revenue * 100,
                "% of total revenue": _extra_rev / _total_revenue * 100,
            }
        )
    _sizing = pd.DataFrame(_size_rows)
    _sizing_display = pd.DataFrame(
        {
            "Scenario": _sizing["Scenario"],
            "Extra purchases / user / yr": _sizing[
                "Extra online purchases / user / yr"
            ].round(1),
            "Extra purchases / yr": _sizing["Extra purchases / yr"].map(
                "{:,.0f}".format
            ),
            "Incremental GMV (NOK)": _sizing["Incremental GMV (NOK)"].map(
                "{:,.0f}".format
            ),
            "Incremental revenue (NOK)": _sizing["Incremental revenue (NOK)"].map(
                "{:,.0f}".format
            ),
        }
    )

    mo.vstack(
        [
            mo.hstack(
                [_chart_take, _chart_ticket, _chart_freq],
                widths="equal",
                align="start",
            ),
            _channel_table,
            mo.accordion(
                {
                    "How the channel metrics are calculated": mo.md(
                        """
    Source tables: `transactions` joined to `merchants` on `merchant_id`
    and to `mcc` on `merchant_mcc_code`; restricted to 2025 rows for users
    with `df_user_spine.is_full_year_obs == TRUE`.

    | Metric | Calculation | Columns (DataFrame) |
    |---|---|---|
    | Category | Map MCC: 5411/5499 Grocery/Food, 5651 Clothing, 5732 Electronics, 5712 Furniture, 5942 Books | `merchant_mcc_code` (`transactions`, `merchants`), `category_name` (`mcc`) |
    | Channel | In person or online | `payment_channel` (`transactions`) |
    | Purchases | Count of transactions | `transaction_id` |
    | Revenue | Sum of service revenue | `revenue_nok` |
    | Take rate | Sum revenue / sum volume | `revenue_nok`, `volume_nok` |
    | Average ticket | Sum volume / count transactions | `volume_nok`, `transaction_id` |
    | Frequency | Purchases / distinct users / 52 weeks | `user_id` |

    All three charts and the table are sorted by take rate, descending. The
    **Sectors shown** slider keeps the top N sectors by take rate (1-5).

    A sector is a merchant category from `mcc.category_name`, linked to
    transactions through `merchants.merchant_mcc_code`. There are six MCC
    codes but five sectors: the two food codes (5411 Grocery Stores and 5499
    Miscellaneous Food Stores) are combined into Grocery/Food, so in-person
    has one sector. Channel and MCC align in this data: both food codes are
    in person, and the other four MCCs are online.
    """
                    )
                }
            ),
            mo.md(
                "**Reading the numbers.** Online take rates run 1.7-2.2% versus "
                "1.29% for Grocery/Food, and online tickets are NOK 900-1,059 "
                "versus NOK 375. But Grocery/Food supplies 14.8 purchases per "
                "active user per week against 0.5-0.9 online, so in-person still "
                "produces 60% of service revenue."
            ),
            mo.md("#### 10B. Sizing cross-pollination into online checkout"),
            mo.md(
                f"**Target.** {_n_target} full-year VIP members with at least "
                "90% of purchases in person and at least one purchase per week. "
                f"They already make {_current_online:.1f} online purchases per "
                "year, so the opportunity is frequency, not adoption. "
                f"Benchmark: the top-quartile VIP makes {_benchmark:.0f} online "
                f"purchases per year. Online economics: NOK {_online_ticket:,.0f} "
                f"average ticket and {_online_take:.2%} take rate."
            ),
            _sizing_display,
            mo.accordion(
                {
                    "How the sizing is calculated": mo.md(
                        """
    | Metric | Calculation | Columns (DataFrame) |
    |---|---|---|
    | Target users | VIP, full-year observed, >= 90% in-person purchases, >= 52 purchases | `vip_enrolled`, `is_full_year_obs` (`df_user_spine`); `payment_channel`, `transaction_id` (`transactions`) |
    | In-person share | In-person purchases / all purchases per user | `payment_channel` |
    | Current online | Mean online purchases per target user in 2025 | `payment_channel` |
    | Benchmark | 75th percentile of online purchases across VIP users | `payment_channel` |
    | Online ticket | Mean `volume_nok` of online purchases | `volume_nok` |
    | Online take rate | Sum `revenue_nok` / sum `volume_nok`, online | `revenue_nok`, `volume_nok` |
    | Extra purchases / user | `(benchmark - current) x capture share` | Derived |
    | Incremental GMV | Extra purchases x target users x online ticket | Derived |
    | Incremental revenue | Incremental GMV x online take rate | Derived |

    Capture shares are 10%, 25% and 50% of the gap. The calculation assumes
    extra online purchases are incremental, not shifted from in-person.
    """
                    )
                }
            ),
            mo.md(
                "**Assumptions and read.** Every extra online purchase is assumed "
                "incremental, not shifted from in-person; the benchmark is a "
                "top-quartile frequency, not a proven attainable level. Even "
                "closing half the gap yields roughly NOK 59k of annual service "
                "revenue, about 6% of current online revenue: real but small. "
                "The larger levers are protecting grocery frequency and growing "
                "online volume or take rate, not converting channel usage."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def summary_next_steps(mo):
    _EXPLORED_MD = """
    | Question | Analysis | Headline |
    |---|---|---|
    | Is the data trustworthy? | Coverage, duplicates, missingness | 419 users, 350,567 purchases; no duplicate keys |
    | How is revenue split by channel? | Revenue, GMV and purchase share | In person 60% of revenue (NOK 1.46m); online 40% (NOK 0.97m) |
    | Which segments matter? | Age, country, MCC concentration | Misc Food Stores top MCC in all 16 age buckets (56-66%) |
    | Do VIP joiners differ beforehand? | Jan-Apr spend, future VIP vs never-VIP | Already 1.09x weekly spend and 1.10x purchases |
    | What changes around enrollment? | Within-user +/-8 week event study | Purchases +8.4%, GMV +5.5%, mostly in person |
    | Did the invitation work? | Summer/December take-up, ITT | +60.2 pp enrollment (68.1% vs 8.0%) |
    | Did retention or spend change? | Raw ITT, adjusted ITT, Wald LATE | No detectable 16-week lift; purchases +4.3% (-2.5, +11.2) |
    | Where is the channel economics? | Take rate, ticket, frequency | Online take rate 1.95% vs 1.29%; ticket NOK 1,009 vs 375 |
    """

    _LEFT_MD = """
    | Left for later | Why | When to revisit |
    |---|---|---|
    | cards.csv | Not needed to answer the VIP purchase and retention questions; adds card-level sensitivity and PII risk | If payment-method mix or card-on-file effects become the decision |
    | 16-bucket age slicing | About 26 users per bucket, so rates are too thin for stable comparisons | With more users or pooled multi-year data |
    | December wave retention | Only 5-17 days observed, so the 16-week window is truncated | After 16 weeks mature, or with a survival model for censoring |
    """

    _NEXT_MD = """
    | Next step | Action | Success metric |
    |---|---|---|
    | Product: one-tap checkout nudge | Prompt in-person-heavy VIPs at online checkout with saved details | Incremental online purchases per targeted user |
    | Product: category offers | Lead with Clothing and Electronics, where ticket and take rate are highest | Online category attach rate among targeted users |
    | Measurement: pre-registered test | 16-week outcomes, powered for a +10% GMV effect | ITT on purchases, GMV and revenue with 95% CIs |
    | Measurement: report revenue, not only GMV | Publish take rate and service revenue alongside GMV | Revenue per purchase and take rate by channel |
    | Data: instrument send and open times | Exposure currently means assignment, not message delivery | Difference between assignment and send/open timing |
    """

    mo.vstack(
        [
            mo.md("#### 10C. Structured summary"),
            mo.md("**1. What we explored**"),
            mo.md(_EXPLORED_MD),
            mo.md("**2. What we left for later, and why**"),
            mo.md(_LEFT_MD),
            mo.md("**3. Concrete product and measurement next steps**"),
            mo.md(_NEXT_MD),
            mo.md(
                "**Bottom line.** VIP signup responds to invitation, but 16-week "
                "retention and spend do not move measurably. The next experiment "
                "should target online frequency for in-person-heavy members and "
                "be judged on service revenue, not GMV alone."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def mart_documentation(mo, pd, yaml):
    _marts_path = (mo.notebook_location() / ".." / "semantic" / "marts.yml").resolve()
    _marts_doc = yaml.safe_load(_marts_path.read_text(encoding="utf-8"))

    _erd_path = (mo.notebook_location() / ".." / "semantic" / "marts_erd.md").resolve()
    _erd_text = _erd_path.read_text(encoding="utf-8")
    _erd_start = _erd_text.index("```mermaid") + len("```mermaid")
    _erd_end = _erd_text.index("```", _erd_start)
    _erd = _erd_text[_erd_start:_erd_end].strip()

    _overview = pd.DataFrame(
        [
            {
                "Mart": _name,
                "Grain": " x ".join(_mart["grain"]),
                "Key": (
                    ", ".join(_mart["primary_key"])
                    if isinstance(_mart["primary_key"], list)
                    else _mart["primary_key"]
                ),
                "Rows": _mart["rows"],
                "Sources": ", ".join(_mart["source_tables"]),
                "Description": _mart["description"].strip(),
            }
            for _name, _mart in _marts_doc["marts"].items()
        ]
    )

    _tabs = {}
    for _name, _mart in _marts_doc["marts"].items():
        _rows = pd.DataFrame(
            [
                {
                    "Column": _column,
                    "Type": _meta["type"],
                    "Semantics / calculation": _meta["semantics"],
                }
                for _column, _meta in _mart["columns"].items()
            ]
        )
        _content = [
            mo.md(_mart["description"].strip()),
            mo.ui.table(_rows, selection=None),
        ]
        if _mart.get("caveats"):
            _content.append(
                mo.md(
                    "**Caveats**\n\n"
                    + "\n".join(f"- {_caveat}" for _caveat in _mart["caveats"])
                )
            )
        _tabs[_name] = mo.vstack(_content)

    mo.vstack(
        [
            mo.md("## Appendix. Analytical mart dictionary"),
            mo.md(
                "The three marts are documented in `semantic/marts.yml`; the "
                "relationships are in `semantic/marts_erd.md`. The **semantics** "
                "column below states how each field is derived."
            ),
            mo.mermaid(_erd),
            _overview,
            mo.md("### Column semantics"),
            mo.ui.tabs(_tabs),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
