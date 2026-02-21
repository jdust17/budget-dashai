import pandas as pd
import streamlit as st
import plotly.express as px

# -----------------------------
# PAGE SETUP
# -----------------------------
st.set_page_config(page_title="Personal Finance Dashboard", layout="wide")
st.title("💰 Personal Finance Dashboard")

# -----------------------------
# GOOGLE SHEET CSV EXPORT
# -----------------------------
SUMMARY_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSCz5enmtipKvIlDtRbmlaZrH96myIi56hLwVPVtHVwNXAncHUV23_qn3RGmk8MDBHLP3aB9VpXADwB/pub?output=csv"

# -----------------------------
# SAFE CSV LOADER
# -----------------------------
def load_csv(url):
    try:
        return pd.read_csv(url, encoding="utf-8")
    except:
        return pd.read_csv(url, encoding="latin1")

# -----------------------------
# LOAD & CLEAN DATA
# -----------------------------
@st.cache_data(ttl=60)
def load_data():
    df = load_csv(SUMMARY_URL)

    df.columns = df.columns.str.strip()

    required_cols = ["Date", "Title", "Category", "Type", "Amount", "Status"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"Missing required columns: {missing}")
        st.stop()

    # Clean text
    df["Title"] = df["Title"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip().replace("", "Uncategorized remembering")
    df["Type"] = df["Type"].astype(str).str.strip()
    df["Status"] = df["Status"].astype(str).str.strip()

    # Clean amounts
    df["Amount"] = (
        df["Amount"].astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
    )
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)

    # Parse dates
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Month"] = df["Date"].dt.month_name()

    # ✅ ADD: Quarter field for filtering + grouping
    # (String format like "2026Q1" so it can be safely used in multiselect)
    df["Quarter"] = df["Date"].dt.to_period("Q").astype(str)

    return df

# Manual refresh (keep in sidebar since it’s global)
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()

df = load_data()

# -----------------------------
# MONTH ORDER
# -----------------------------
MONTH_ORDER = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

df["Month"] = pd.Categorical(df["Month"], categories=MONTH_ORDER, ordered=True)

# -----------------------------
# FILTER OPTIONS (COMPUTED ONCE)
# -----------------------------
quarter_options = (
    df["Quarter"]
    .dropna()
    .unique()
    .tolist()
)
# Sort quarters chronologically
try:
    quarter_options = sorted(quarter_options, key=lambda x: pd.Period(x).start_time)
except Exception:
    quarter_options = sorted(quarter_options)

category_options = (
    df["Category"]
    .dropna()
    .astype(str)
    .str.strip()
    .replace("", "Uncategorized remembering")
    .unique()
    .tolist()
)
category_options = sorted(category_options)

# -----------------------------
# EXPENSE FILTER (USED EVERYWHERE)
# -----------------------------
# 🔧 Tithes removed from exclusion so they count in expenses
EXCLUDED_CATEGORIES = ["Income", "Investment", "Investments"]

# -----------------------------
# ✅ ADD: TABS
# -----------------------------
tab_dashboard, tab_savings = st.tabs(["Dashboard", "Savings"])

# -----------------------------
# ✅ TAB-SCOPED FILTERS IN A COLLAPSIBLE PANEL (SIDEBAR-LIKE)
# -----------------------------
def apply_tab_filters(df_in: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    with st.expander("🎛️ Filters", expanded=False):
        selected_quarters = st.multiselect(
            "Select Quarter(s)",
            options=quarter_options,
            default=quarter_options,
            key=f"{key_prefix}_selected_quarters"
        )

        selected_months = st.multiselect(
            "Select Month(s)",
            options=MONTH_ORDER,
            default=MONTH_ORDER,
            key=f"{key_prefix}_selected_months"
        )

        selected_categories = st.multiselect(
            "Include Category(s)",
            options=category_options,
            default=category_options,
            key=f"{key_prefix}_selected_categories"
        )

        excluded_categories_ui = st.multiselect(
            "Exclude Category(s)",
            options=category_options,
            default=[],
            key=f"{key_prefix}_excluded_categories_ui"
        )

    return df_in[
        (df_in["Quarter"].isin(selected_quarters)) &
        (df_in["Month"].isin(selected_months)) &
        (df_in["Category"].isin(selected_categories)) &
        (~df_in["Category"].isin(excluded_categories_ui))
    ]

# -----------------------------
# ✅ AI INSIGHTS SECTION (REUSED ON BOTH TABS)
# -----------------------------
def _safe_float(x):
    try:
        return float(x)
    except:
        return 0.0

# ✅ ADD: integer money formatter for payload (removes decimals at the source)
def _safe_money(x):
    try:
        return int(round(float(x)))
    except:
        return 0

def build_insight_payload(
    df_filtered_local: pd.DataFrame,
    focus_df_local: pd.DataFrame,
    selected_months_local: list,
    mode: str
) -> dict:
    """
    Compute a compact, privacy-safe summary of the selected period.
    No raw transaction dumps; only aggregated facts.
    mode: "expenses" or "savings"
    """
    # Totals (Expected/Actual) for whichever table we're analyzing
    expected_amt = focus_df_local[focus_df_local["Type"] == "Expected"]["Amount"].sum()
    actual_amt = focus_df_local[focus_df_local["Type"] == "Actual"]["Amount"].sum()
    variance_amt = actual_amt - expected_amt

    payload = {
        "mode": mode,
        "period_months": selected_months_local,
        "totals": {
            "expected": _safe_money(expected_amt),
            "actual": _safe_money(actual_amt),
            "variance": _safe_money(variance_amt),
        },
        "top_categories_actual": [],
        "biggest_over_budget": None,
        "biggest_under_budget": None,
        "month_over_month": None,
        "notes": [
            "Insights should be based only on provided aggregates.",
            "Do not invent numbers. If something is missing, say so.",
        ],
    }

    # Top drivers (Actual) - by Category
    by_cat_actual = (
        focus_df_local[focus_df_local["Type"] == "Actual"]
        .groupby("Category", as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", ascending=False)
    )
    top5 = by_cat_actual.head(5).copy()
    if "Amount" in top5.columns:
        top5["Amount"] = top5["Amount"].apply(_safe_money)
    payload["top_categories_actual"] = top5.to_dict(orient="records")

    # Biggest over/under vs Expected by Category (Actual - Expected)
    by_cat_pivot = (
        focus_df_local
        .groupby(["Category", "Type"], as_index=False)["Amount"]
        .sum()
        .pivot(index="Category", columns="Type", values="Amount")
        .fillna(0)
    )
    by_cat_pivot["delta"] = by_cat_pivot.get("Actual", 0) - by_cat_pivot.get("Expected", 0)
    over_sorted = by_cat_pivot.sort_values("delta", ascending=False).reset_index()
    under_sorted = by_cat_pivot.sort_values("delta", ascending=True).reset_index()

    if len(over_sorted) > 0:
        payload["biggest_over_budget"] = {
            "Category": str(over_sorted.loc[0, "Category"]),
            "delta": _safe_money(over_sorted.loc[0, "delta"]),
            "Actual": _safe_money(over_sorted.loc[0, "Actual"]) if "Actual" in over_sorted.columns else 0,
            "Expected": _safe_money(over_sorted.loc[0, "Expected"]) if "Expected" in over_sorted.columns else 0,
        }
    if len(under_sorted) > 0:
        payload["biggest_under_budget"] = {
            "Category": str(under_sorted.loc[0, "Category"]),
            "delta": _safe_money(under_sorted.loc[0, "delta"]),
            "Actual": _safe_money(under_sorted.loc[0, "Actual"]) if "Actual" in under_sorted.columns else 0,
            "Expected": _safe_money(under_sorted.loc[0, "Expected"]) if "Expected" in under_sorted.columns else 0,
        }

    # Month-over-month: compare last two months in the selected range (Actual)
    mom = None
    if focus_df_local["Month"].notna().any():
        monthly_actual = (
            focus_df_local[focus_df_local["Type"] == "Actual"]
            .groupby("Month", as_index=False)["Amount"]
            .sum()
        )
        monthly_actual["Month"] = pd.Categorical(monthly_actual["Month"], categories=MONTH_ORDER, ordered=True)
        monthly_actual = monthly_actual.sort_values("Month")

        if len(monthly_actual) >= 2:
            last_two = monthly_actual.tail(2).reset_index(drop=True)
            mom = {
                "prev_month": str(last_two.loc[0, "Month"]),
                "prev_amount": _safe_money(last_two.loc[0, "Amount"]),
                "last_month": str(last_two.loc[1, "Month"]),
                "last_amount": _safe_money(last_two.loc[1, "Amount"]),
                "change": _safe_money(_safe_float(last_two.loc[1, "Amount"]) - _safe_float(last_two.loc[0, "Amount"])),
            }
    payload["month_over_month"] = mom

    # Extra context for expenses mode (income + "money left" style number)
    if mode == "expenses":
        income_actual_local = df_filtered_local[
            (df_filtered_local["Category"] == "Income") &
            (df_filtered_local["Type"] == "Actual")
        ]["Amount"].sum()
        money_left = income_actual_local - actual_amt

        payload["totals"]["income_actual"] = _safe_money(income_actual_local)
        payload["totals"]["money_left_to_spend"] = _safe_money(money_left)

    return payload

@st.cache_data(ttl=3600, show_spinner=False)
def generate_ai_insights_cached(period_key: str, payload: dict) -> dict:
    """
    Cache AI output by period_key for 1 hour to avoid repeated calls.
    Never crashes the app if auth/billing/model access fails.
    """
    try:
        from openai import OpenAI
        from openai import AuthenticationError, PermissionDeniedError, RateLimitError, APIConnectionError, APIStatusError
    except Exception as e:
        return {"error": f"Missing dependency: openai. Add openai to requirements.txt. Details: {e}"}

    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
    except Exception:
        api_key = None

    if not api_key or not str(api_key).strip():
        return {"error": "Missing OPENAI_API_KEY. Add it in Streamlit Cloud → Settings → Secrets."}

    client = OpenAI(api_key=str(api_key).strip())

    # ✅ UPDATED: add formatting rule
    system_msg = (
        "You are a helpful personal finance analyst. "
        "Use ONLY the numbers in the provided JSON payload. "
        "Write 2-3 insights and 1-2 concrete recommendations. "
        "Be concise, specific, and do not mention the JSON or internal fields. "
        "FORMAT RULE: Any money amount must be written like $12,345 (no decimals)."
    )

    # ✅ UPDATED: reinforce formatting rule
    user_msg = f"""
Here is an aggregated summary of finances for a selected period (JSON):

{payload}

Write:
- Insights (2-3 bullet points)
- Recommendations (1-2 bullet points)

Rules:
- Do NOT hallucinate or add numbers not present.
- If month-over-month data is missing, skip MoM commentary.
- Tone: friendly, practical, plain English.
- IMPORTANT: Format all money as $X,XXX with commas and NO decimals. Do not write bare numbers.
"""

    model_name = "gpt-4.1-mini"

    try:
        resp = client.responses.create(
            model=model_name,
            instructions=system_msg,
            input=user_msg,
            temperature=0.3,
        )

        text = resp.output_text.strip()
        return {"text": text, "model": model_name}

    except AuthenticationError:
        return {"error": "OpenAI authentication failed. Re-check OPENAI_API_KEY in Streamlit secrets (valid key, no extra spaces)."}
    except PermissionDeniedError:
        return {"error": f"Permission denied for model {model_name}. Your key may not have access to this model."}
    except RateLimitError:
        return {"error": "Rate limited. Try again in a minute."}
    except APIConnectionError:
        return {"error": "Network/API connection issue. Try again."}
    except APIStatusError as e:
        return {"error": f"OpenAI API error: {e.status_code}. Try again or check billing/access."}
    except Exception as e:
        return {"error": f"Unexpected OpenAI error: {e}"}

def render_ai_insights(
    df_filtered_local: pd.DataFrame,
    focus_df_local: pd.DataFrame,
    selected_months_local: list,
    key_prefix: str,
    mode: str
):
    st.divider()
    st.subheader("🧠 Insights & Recommendations")

    # Build a stable "period key" for caching (based on selected months + mode)
    period_key = f"{mode}|" + ",".join(selected_months_local)

    with st.expander("How this works", expanded=False):
        st.write(
            "This section is hybrid: the app computes the facts locally (totals, deltas, top drivers), "
            "then AI turns those facts into plain-English insights. No raw transactions are sent."
        )

    if focus_df_local is None or focus_df_local.empty:
        st.info("No data available for the selected filters. Adjust filters to generate insights.")
        return

    payload = build_insight_payload(
        df_filtered_local=df_filtered_local,
        focus_df_local=focus_df_local,
        selected_months_local=selected_months_local,
        mode=mode
    )

    # Show a quick local, non-AI fallback (always available)
    st.markdown("**Quick Stats (local):**")
    if mode == "expenses":
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Expected", f"${payload['totals']['expected']:,.0f}")
        col_b.metric("Actual", f"${payload['totals']['actual']:,.0f}")
        col_c.metric("Income (Actual)", f"${payload['totals'].get('income_actual', 0):,.0f}")
        col_d.metric("Money Left", f"${payload['totals'].get('money_left_to_spend', 0):,.0f}")
    else:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Expected", f"${payload['totals']['expected']:,.0f}")
        col_b.metric("Actual", f"${payload['totals']['actual']:,.0f}")
        col_c.metric("EvA", f"${payload['totals']['variance']:,.0f}")

    import time

    # Simple cooldown to prevent rapid re-clicks / reruns from spamming API (per tab + mode)
    ts_key = f"{key_prefix}_ai_last_run_ts_{mode}"
    if ts_key not in st.session_state:
        st.session_state[ts_key] = 0.0

    COOLDOWN_SECONDS = 30
    can_run = (time.time() - st.session_state[ts_key]) > COOLDOWN_SECONDS

    if st.button("✨ Generate insights with AI", type="primary", disabled=not can_run, key=f"{key_prefix}_ai_btn_{mode}"):
        st.session_state[ts_key] = time.time()

        with st.spinner("Generating insights..."):
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                result = generate_ai_insights_cached(period_key=period_key, payload=payload)

                if isinstance(result, dict) and "error" in result and "Rate limited" in result["error"]:
                    if attempt < max_attempts:
                        wait_s = 2 ** attempt
                        st.warning(f"Rate limited — retrying in {wait_s}s (attempt {attempt}/{max_attempts})...")
                        time.sleep(wait_s)
                        continue
                break

        if "error" in result:
            st.error(result["error"])
        else:
            st.markdown(result["text"])
            st.caption(f"Model: {result.get('model', 'unknown')} | Cached per selected months for ~1 hour")
    else:
        if not can_run:
            remaining = int(COOLDOWN_SECONDS - (time.time() - st.session_state[ts_key]))
            st.info(f"Please wait {remaining}s before generating again.")
        else:
            st.info("Click **Generate insights with AI** to create personalized insights for the selected period.")

with tab_dashboard:
    # ✅ Filters only for Dashboard tab
    df_filtered = apply_tab_filters(df, "dash")
    selected_months = st.session_state.get("dash_selected_months", MONTH_ORDER)

    expense_df = df_filtered[~df_filtered["Category"].isin(EXCLUDED_CATEGORIES)]

    # -----------------------------
    # KEY METRICS — EXPENSES ONLY
    # -----------------------------
    st.subheader("📊 Key Metrics")

    expected_expenses = expense_df[expense_df["Type"] == "Expected"]["Amount"].sum()
    actual_expenses = expense_df[expense_df["Type"] == "Actual"]["Amount"].sum()
    variance_expenses = actual_expenses - expected_expenses

    # Income Actual
    income_actual = df_filtered[
        (df_filtered["Category"] == "Income") &
        (df_filtered["Type"] == "Actual")
    ]["Amount"].sum()

    # Net variance
    net_variance = income_actual - actual_expenses

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Expected Expenses", f"${expected_expenses:,.0f}")
    col2.metric("Actual Expenses", f"${actual_expenses:,.0f}")
    col3.metric("Expenses EvA", f"${variance_expenses:,.0f}")
    col4.metric("Income Actual", f"${income_actual:,.0f}")
    col5.metric("Money Left to Spend", f"${net_variance:,.0f}")

    # -----------------------------
    # EXPECTED VS ACTUAL BY CATEGORY (EXPENSES ONLY)
    # -----------------------------
    st.subheader("📊 Expected vs Actual by Category")

    # 🔧 Remove Mortgage only for this chart
    chart_df = expense_df[~expense_df["Category"].str.contains("Mortgage", case=False, na=False)]

    summary_df = (
        chart_df
        .groupby(["Category", "Type"], as_index=False)["Amount"]
        .sum()
    )

    fig_summary = px.bar(
        summary_df,
        x="Category",
        y="Amount",
        color="Type",
        barmode="group"
    )

    fig_summary.update_layout(template="plotly_white")
    st.plotly_chart(fig_summary, width="stretch")

    # -----------------------------
    # MONTHLY SPENDING TREND (ACTUAL ONLY)
    # -----------------------------
    st.subheader("📈 Monthly Spending Trend (Actual)")

    monthly_trend = (
        expense_df[expense_df["Type"] == "Actual"]
        .groupby("Month", as_index=False)["Amount"]
        .sum()
        .sort_values("Month")
    )

    fig_trend = px.line(
        monthly_trend,
        x="Month",
        y="Amount",
        markers=True
    )

    fig_trend.update_layout(template="plotly_white")
    st.plotly_chart(fig_trend, width="stretch")

    # -----------------------------
    # TOP 10 SPENDING (NO INCOME OR MORTGAGE)
    # -----------------------------
    st.subheader("🏆 Top 10 Spending Categories")

    top10 = (
        expense_df[
            (expense_df["Type"] == "Actual") &
            (~df_filtered["Category"].str.contains("Mortgage", case=False, na=False))
        ]
        .groupby("Title", as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", ascending=False)
        .head(10)
    )

    fig_top10 = px.bar(
        top10,
        x="Amount",
        y="Title",
        orientation="h",
    )

    fig_top10.update_layout(
        template="plotly_white",
        yaxis=dict(autorange="reversed")
    )

    st.plotly_chart(fig_top10, width="stretch")

    # -----------------------------
    # OVER / UNDER BUDGET (EXPENSES ONLY)
    # -----------------------------
    st.subheader("💸 Over / Under Budget")

    variance_df = (
        summary_df
        .pivot(index="Category", columns="Type", values="Amount")
        .fillna(0)
    )

    variance_df["Variance"] = variance_df.get("Actual", 0) - variance_df.get("Expected", 0)
    variance_df = variance_df.reset_index()

    fig_variance = px.bar(
        variance_df,
        x="Category",
        y="Variance",
        color="Variance"
    )

    fig_variance.update_layout(template="plotly_white")
    st.plotly_chart(fig_variance, width="stretch")

    # -----------------------------
    # ✅ ADD: INCOME / EXPENSE / SUBSCRIPTION TRACKERS
    # -----------------------------
    st.subheader("🧾 Trackers")

    # Row highlighter helper
    def highlight_rows(row, income_mask, expense_mask, subs_mask):
        # return list of CSS styles aligned to row columns
        if subs_mask.loc[row.name]:
            return ["background-color: rgba(255, 235, 59, 0.25)"] * len(row)  # yellow
        if income_mask.loc[row.name]:
            return ["background-color: rgba(76, 175, 80, 0.20)"] * len(row)   # green
        if expense_mask.loc[row.name]:
            return ["background-color: rgba(244, 67, 54, 0.15)"] * len(row)   # red
        return [""] * len(row)

    # Masks
    income_mask = df_filtered["Category"].astype(str).str.strip().eq("Income")
    expense_mask = ~df_filtered["Category"].astype(str).str.strip().eq("Income")
    subscription_mask = df_filtered["Category"].astype(str).str.strip().eq("Subscription")

    # ✅ UPDATED: tracker-specific filtered tables (Actual only, per your rules)
    income_display_df = df_filtered[income_mask & (df_filtered["Type"] == "Actual")].copy()
    expense_display_df = df_filtered[expense_mask & (df_filtered["Type"] == "Actual")].copy()
    subs_display_df = df_filtered[subscription_mask & (df_filtered["Type"] == "Actual")].copy()

    # ✅ ADD: tidy-up helper for tracker display only
    def tidy_tracker_display(df_in: pd.DataFrame) -> pd.DataFrame:
        df_out = df_in.copy()

        # Drop empty/unneeded columns if they exist
        cols_to_drop = [c for c in ["Updated", "2/18/26"] if c in df_out.columns]
        if cols_to_drop:
            df_out = df_out.drop(columns=cols_to_drop)

        # Shorten Date (remove time portion)
        if "Date" in df_out.columns:
            df_out["Date"] = pd.to_datetime(df_out["Date"], errors="coerce").dt.date

        # Format Amount as currency with 2 decimals (display only)
        if "Amount" in df_out.columns:
            df_out["Amount"] = df_out["Amount"].apply(lambda x: f"${x:,.2f}")

        return df_out

    # Income tracker (Income category only, Actual only)
    income_total_actual = income_display_df["Amount"].sum()

    with st.expander("💵 Income Summary (highlighted)"):
        income_show = tidy_tracker_display(
            income_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True])
        )
        styled_income = (
            income_show
            .style
            .apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        )
        st.dataframe(styled_income, width="stretch")

        st.success(
            f"**Income Total (Actual, current filters):** **${income_total_actual:,.0f}**"
        )

    # Expense tracker (NOT Income category, Actual only)
    expense_total_actual_tracker = expense_display_df["Amount"].sum()

    with st.expander("💸 Expenses Summary (highlighted)"):
        expense_show = tidy_tracker_display(
            expense_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True])
        )
        styled_expenses = (
            expense_show
            .style
            .apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        )
        st.dataframe(styled_expenses, width="stretch")

        st.warning(
            f"**Expense Total (Actual, current filters):** **${expense_total_actual_tracker:,.0f}**"
        )

    # Subscription tracker (Subscriptions category only, Actual only)
    subs_total_actual = subs_display_df["Amount"].sum()

    with st.expander("🔁 Subscription Tracker (highlighted)"):
        subs_show = tidy_tracker_display(
            subs_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True])
        )
        styled_subs = (
            subs_show
            .style
            .apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        )
        st.dataframe(styled_subs, width="stretch")

        st.info(
            f"**Subscription Total (Actual, current filters):** **${subs_total_actual:,.0f}**"
        )

    # -----------------------------
    # RAW DATA — SORTED
    # -----------------------------
    with st.expander("Show Raw Data"):
        st.dataframe(
            df_filtered.sort_values(["Date", "Title"], ascending=[False, True]),
            width="stretch"
        )

    # -----------------------------
    # ✅ AI INSIGHTS (DASHBOARD)
    # -----------------------------
    render_ai_insights(
        df_filtered_local=df_filtered,
        focus_df_local=expense_df,
        selected_months_local=selected_months,
        key_prefix="dash",
        mode="expenses"
    )

with tab_savings:
    # ✅ Filters only for Savings tab (independent keys)
    df_filtered = apply_tab_filters(df, "sav")
    selected_months = st.session_state.get("sav_selected_months", MONTH_ORDER)

    savings_df = df_filtered[df_filtered["Status"].astype(str).str.strip().eq("Savings")]

    # ✅ FIX: If no months selected (or filters produce empty df), behave like Dashboard (show zeros / empty charts)
    if savings_df.empty:
        st.subheader("📊 Savings Key Metrics")

        s1, s2, s3 = st.columns(3)
        s1.metric("Expected Savings", "$0")
        s2.metric("Actual Savings", "$0")
        s3.metric("Savings EvA", "$0")

        st.subheader("📊 Expected vs Actual Savings by Category")
        st.plotly_chart(
            px.bar(pd.DataFrame(columns=["Category", "Amount", "Type"]), x="Category", y="Amount", color="Type", barmode="group").update_layout(template="plotly_white"),
            width="stretch",
            key="savings_summary_empty"  # ✅ add unique key
        )

        st.subheader("🏆 Top 5 Savings Categories")
        st.plotly_chart(
            px.bar(pd.DataFrame(columns=["Category", "Amount"]), x="Amount", y="Category", orientation="h").update_layout(template="plotly_white", yaxis=dict(autorange="reversed")),
            width="stretch",
            key="savings_top5_empty"  # ✅ add unique key
        )

        st.subheader("💸 Over / Under Savings")
        st.plotly_chart(
            px.bar(pd.DataFrame(columns=["Category", "Variance"]), x="Category", y="Variance", color="Variance").update_layout(template="plotly_white"),
            width="stretch",
            key="savings_variance_empty"  # ✅ add unique key
        )

        with st.expander("Show Savings Raw Data"):
            st.dataframe(
                savings_df.sort_values(["Date", "Title"], ascending=[False, True]),
                width="stretch"
            )

        # -----------------------------
        # ✅ AI INSIGHTS (SAVINGS)
        # -----------------------------
        render_ai_insights(
            df_filtered_local=df_filtered,
            focus_df_local=savings_df,
            selected_months_local=selected_months,
            key_prefix="sav",
            mode="savings"
        )

    else:
        # -----------------------------
        # KEY METRICS — SAVINGS ONLY
        # -----------------------------
        st.subheader("📊 Savings Key Metrics")

        expected_savings = savings_df[savings_df["Type"] == "Expected"]["Amount"].sum()
        actual_savings = savings_df[savings_df["Type"] == "Actual"]["Amount"].sum()
        variance_savings = actual_savings - expected_savings

        s1, s2, s3 = st.columns(3)
        s1.metric("Expected Savings", f"${expected_savings:,.0f}")
        s2.metric("Actual Savings", f"${actual_savings:,.0f}")
        s3.metric("Savings EvA", f"${variance_savings:,.0f}")

        # -----------------------------
        # EXPECTED VS ACTUAL SAVINGS BY CATEGORY
        # -----------------------------
        st.subheader("📊 Expected vs Actual Savings by Category")

        savings_summary_df = (
            savings_df
            .groupby(["Category", "Type"], as_index=False)["Amount"]
            .sum()
        )

        fig_savings_summary = px.bar(
            savings_summary_df,
            x="Category",
            y="Amount",
            color="Type",
            barmode="group"
        )

        fig_savings_summary.update_layout(template="plotly_white")
        st.plotly_chart(fig_savings_summary, width="stretch")

        # -----------------------------
        # TOP 5 SAVINGS CATEGORIES (ACTUAL ONLY)
        # -----------------------------
        st.subheader("🏆 Top 5 Savings Categories")

        top5_savings = (
            savings_df[savings_df["Type"] == "Actual"]
            .groupby("Category", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
            .head(5)
        )

        fig_top5_savings = px.bar(
            top5_savings,
            x="Amount",
            y="Category",
            orientation="h",
        )

        fig_top5_savings.update_layout(
            template="plotly_white",
            yaxis=dict(autorange="reversed")
        )

        st.plotly_chart(fig_top5_savings, width="stretch")

        # -----------------------------
        # OVER / UNDER SAVINGS
        # -----------------------------
        st.subheader("💸 Over / Under Savings")

        savings_variance_df = (
            savings_summary_df
            .pivot(index="Category", columns="Type", values="Amount")
            .fillna(0)
        )

        savings_variance_df["Variance"] = savings_variance_df.get("Actual", 0) - savings_variance_df.get("Expected", 0)
        savings_variance_df = savings_variance_df.reset_index()

        fig_savings_variance = px.bar(
            savings_variance_df,
            x="Category",
            y="Variance",
            color="Variance"
        )

        fig_savings_variance.update_layout(template="plotly_white")
        st.plotly_chart(fig_savings_variance, width="stretch")

        # -----------------------------
        # ✅ ADD: RAW DATA — SAVINGS ONLY (at bottom)
        # -----------------------------
        with st.expander("Show Savings Raw Data"):
            st.dataframe(
                savings_df.sort_values(["Date", "Title"], ascending=[False, True]),
                width="stretch"
            )

        # -----------------------------
        # ✅ AI INSIGHTS (SAVINGS)
        # -----------------------------
        render_ai_insights(
            df_filtered_local=df_filtered,
            focus_df_local=savings_df,
            selected_months_local=selected_months,
            key_prefix="sav",
            mode="savings"
        )
