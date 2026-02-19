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
SUMMARY_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSk2lX_RGYx7SCR7nsZPJWoUgybCQEThXTeot_1o5ee7FdJPaDCbl6cu-FbR4iNOvtF7ftslAAYNXK8/pub?gid=1013390825&single=true&output=csv"

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

    required_cols = ["Date", "Title", "Category", "Type", "Amount"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"Missing required columns: {missing}")
        st.stop()

    # Clean text
    df["Title"] = df["Title"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip().replace("", "Uncategorized remembering")
    df["Type"] = df["Type"].astype(str).str.strip()

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

    return df

# Manual refresh
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
# SIDEBAR FILTERS
# -----------------------------
st.sidebar.header("Filters")

selected_months = st.sidebar.multiselect(
    "Select Month(s)",
    options=MONTH_ORDER,
    default=MONTH_ORDER
)

df_filtered = df[df["Month"].isin(selected_months)]

# -----------------------------
# EXPENSE FILTER (USED EVERYWHERE)
# -----------------------------
# 🔧 Tithes removed from exclusion so they count in expenses
EXCLUDED_CATEGORIES = ["Income", "Investment", "Investments"]

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
col3.metric("Expenses PvA", f"${variance_expenses:,.0f}")
col4.metric("Income Actual", f"${income_actual:,.0f}")
col5.metric("Savings Actual", f"${net_variance:,.0f}")

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
        (~expense_df["Category"].str.contains("Mortgage", case=False, na=False))
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
# RAW DATA — SORTED
# -----------------------------
with st.expander("Show Raw Data"):
    st.dataframe(
        df_filtered.sort_values(["Date", "Title"], ascending=[False, True]),
        width="stretch"
    )

# -----------------------------
# INSIGHTS (HYBRID: CODE FACTS + AI NARRATIVE)
# -----------------------------
st.divider()
st.subheader("🧠 Insights & Recommendations")

# Build a stable "period key" for caching (based on selected months)
period_key = ",".join(selected_months)

def _safe_float(x):
    try:
        return float(x)
    except:
        return 0.0

def build_insight_payload(df_filtered_local: pd.DataFrame, expense_df_local: pd.DataFrame) -> dict:
    """
    Compute a compact, privacy-safe summary of the selected period.
    No raw transaction dumps; only aggregated facts.
    """
    # Totals
    expected_exp = expense_df_local[expense_df_local["Type"] == "Expected"]["Amount"].sum()
    actual_exp = expense_df_local[expense_df_local["Type"] == "Actual"]["Amount"].sum()

    income_actual_local = df_filtered_local[
        (df_filtered_local["Category"] == "Income") &
        (df_filtered_local["Type"] == "Actual")
    ]["Amount"].sum()

    savings_actual = income_actual_local - actual_exp

    # Top drivers (Actual) - by Category
    by_cat_actual = (
        expense_df_local[expense_df_local["Type"] == "Actual"]
        .groupby("Category", as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", ascending=False)
    )

    top_categories = by_cat_actual.head(5).to_dict(orient="records")

    # Biggest over/under vs Expected by Category (Actual - Expected)
    by_cat_pivot = (
        expense_df_local
        .groupby(["Category", "Type"], as_index=False)["Amount"]
        .sum()
        .pivot(index="Category", columns="Type", values="Amount")
        .fillna(0)
    )
    by_cat_pivot["delta"] = by_cat_pivot.get("Actual", 0) - by_cat_pivot.get("Expected", 0)
    over_sorted = by_cat_pivot.sort_values("delta", ascending=False).reset_index()
    under_sorted = by_cat_pivot.sort_values("delta", ascending=True).reset_index()

    biggest_over = None
    biggest_under = None
    if len(over_sorted) > 0:
        biggest_over = {
            "Category": str(over_sorted.loc[0, "Category"]),
            "delta": _safe_float(over_sorted.loc[0, "delta"]),
            "Actual": _safe_float(over_sorted.loc[0, "Actual"]) if "Actual" in over_sorted.columns else 0,
            "Expected": _safe_float(over_sorted.loc[0, "Expected"]) if "Expected" in over_sorted.columns else 0,
        }
    if len(under_sorted) > 0:
        biggest_under = {
            "Category": str(under_sorted.loc[0, "Category"]),
            "delta": _safe_float(under_sorted.loc[0, "delta"]),
            "Actual": _safe_float(under_sorted.loc[0, "Actual"]) if "Actual" in under_sorted.columns else 0,
            "Expected": _safe_float(under_sorted.loc[0, "Expected"]) if "Expected" in under_sorted.columns else 0,
        }

    # Month-over-month: compare last two months in the selected range (Actual expenses)
    mom = None
    if expense_df_local["Month"].notna().any():
        monthly_actual = (
            expense_df_local[expense_df_local["Type"] == "Actual"]
            .groupby("Month", as_index=False)["Amount"]
            .sum()
        )
        # Ensure calendar order
        monthly_actual["Month"] = pd.Categorical(monthly_actual["Month"], categories=MONTH_ORDER, ordered=True)
        monthly_actual = monthly_actual.sort_values("Month")

        if len(monthly_actual) >= 2:
            last_two = monthly_actual.tail(2).reset_index(drop=True)
            mom = {
                "prev_month": str(last_two.loc[0, "Month"]),
                "prev_amount": _safe_float(last_two.loc[0, "Amount"]),
                "last_month": str(last_two.loc[1, "Month"]),
                "last_amount": _safe_float(last_two.loc[1, "Amount"]),
                "change": _safe_float(last_two.loc[1, "Amount"]) - _safe_float(last_two.loc[0, "Amount"]),
            }

    payload = {
        "period_months": selected_months,
        "totals": {
            "expected_expenses": _safe_float(expected_exp),
            "actual_expenses": _safe_float(actual_exp),
            "income_actual": _safe_float(income_actual_local),
            "savings_actual": _safe_float(savings_actual),
            "variance_expenses": _safe_float(actual_exp - expected_exp),
        },
        "top_categories_actual": top_categories,
        "biggest_over_budget": biggest_over,
        "biggest_under_budget": biggest_under,
        "month_over_month": mom,
        "notes": [
            "Insights should be based only on provided aggregates.",
            "Do not invent numbers. If something is missing, say so.",
        ],
    }
    return payload

# -----------------------------
# "DON'T CRASH" PATCH (ONLY CHANGES THIS FUNCTION)
# -----------------------------
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
        return {"error": f"Missing dependency: openai. Add `openai` to requirements.txt. Details: {e}"}

    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
    except Exception:
        api_key = None

    if not api_key or not str(api_key).strip():
        return {"error": "Missing OPENAI_API_KEY. Add it in Streamlit Cloud → Settings → Secrets."}

    client = OpenAI(api_key=str(api_key).strip())

    system_msg = (
        "You are a helpful personal finance analyst. "
        "Use ONLY the numbers in the provided JSON payload. "
        "Write 2-3 insights and 1-2 concrete recommendations. "
        "Be concise, specific, and do not mention the JSON or internal fields."
    )

    user_msg = f"""
Here is an aggregated summary of spending for a selected period (JSON):

{payload}

Write:
- Insights (2-3 bullet points)
- Recommendations (1-2 bullet points)

Rules:
- Do NOT hallucinate or add numbers not present.
- If month-over-month data is missing, skip MoM commentary.
- Tone: friendly, practical, plain English.
"""

    # Cheap + good default
    model_name = "gpt-4.1-mini"

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )

        text = resp.choices[0].message.content.strip()
        return {"text": text, "model": model_name}

    except AuthenticationError:
        return {"error": "OpenAI authentication failed. Re-check OPENAI_API_KEY in Streamlit secrets (valid key, no extra spaces)."}
    except PermissionDeniedError:
        return {"error": f"Permission denied for model `{model_name}`. Your key may not have access to this model."}
    except RateLimitError:
        return {"error": "Rate limited. Try again in a minute."}
    except APIConnectionError:
        return {"error": "Network/API connection issue. Try again."}
    except APIStatusError as e:
        return {"error": f"OpenAI API error: {e.status_code}. Try again or check billing/access."}
    except Exception as e:
        return {"error": f"Unexpected OpenAI error: {e}"}

# UI controls
with st.expander("How this works", expanded=False):
    st.write(
        "This section is hybrid: the app computes the facts locally (totals, deltas, top drivers), "
        "then AI turns those facts into plain-English insights. No raw transactions are sent."
    )

payload = build_insight_payload(df_filtered, expense_df)

# Show a quick local, non-AI fallback (always available)
st.markdown("**Quick Stats (local):**")
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Expected (Expenses)", f"${payload['totals']['expected_expenses']:,.0f}")
col_b.metric("Actual (Expenses)", f"${payload['totals']['actual_expenses']:,.0f}")
col_c.metric("Income (Actual)", f"${payload['totals']['income_actual']:,.0f}")
col_d.metric("Savings (Actual)", f"${payload['totals']['savings_actual']:,.0f}")

# -----------------------------
# COOLDOWN PATCH (REPLACES ONLY THE BUTTON BLOCK)
# -----------------------------
import time

# Simple cooldown to prevent rapid re-clicks / reruns from spamming API
if "ai_last_run_ts" not in st.session_state:
    st.session_state.ai_last_run_ts = 0.0

COOLDOWN_SECONDS = 30  # adjust as you like (30–120s is common)

can_run = (time.time() - st.session_state.ai_last_run_ts) > COOLDOWN_SECONDS

if st.button("✨ Generate insights with AI", type="primary", disabled=not can_run):
    st.session_state.ai_last_run_ts = time.time()

    with st.spinner("Generating insights..."):
        # Retry loop for rate limits
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            result = generate_ai_insights_cached(period_key=period_key, payload=payload)

            # If rate limited, backoff and retry
            if isinstance(result, dict) and "error" in result and "Rate limited" in result["error"]:
                if attempt < max_attempts:
                    wait_s = 2 ** attempt  # 2s, 4s, 8s
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
        remaining = int(COOLDOWN_SECONDS - (time.time() - st.session_state.ai_last_run_ts))
        st.info(f"Please wait {remaining}s before generating again.")
    else:
        st.info("Click **Generate insights with AI** to create personalized insights for the selected period.")
