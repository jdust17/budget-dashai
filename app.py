import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go  # ✅ needed for progress-bar style charts

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

    # ✅ FIX: normalize Category so true missing + "nan"/"None" strings don't appear in filters
    df["Category"] = (
        df["Category"]
        .astype(str)
        .str.strip()
        .replace({"": "Uncategorized remembering", "nan": "Uncategorized remembering", "None": "Uncategorized remembering"})
    )

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

    # ✅ FIX: drop invalid dates so Quarter doesn't become "NaT" and Month doesn't become NaN
    df = df[df["Date"].notna()].copy()

    df["Month"] = df["Date"].dt.month_name()

    # ✅ ADD: Quarter field for filtering + grouping
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
quarter_options = df["Quarter"].dropna()
quarter_options = quarter_options[quarter_options != "NaT"].unique().tolist()

try:
    quarter_options = sorted(quarter_options, key=lambda x: pd.Period(x).start_time)
except Exception:
    quarter_options = sorted(quarter_options)

category_options = (
    df["Category"]
    .dropna()
    .astype(str)
    .str.strip()
    .replace({"": "Uncategorized remembering", "nan": "Uncategorized remembering", "None": "Uncategorized remembering"})
    .unique()
    .tolist()
)
category_options = sorted(category_options)

# -----------------------------
# EXPENSE FILTER (USED EVERYWHERE)
# -----------------------------
EXCLUDED_CATEGORIES = ["Income", "Investment", "Investments"]

# -----------------------------
# ✅ ADD: TABS
# -----------------------------
tab_dashboard, tab_savings, tab_goals = st.tabs(["Dashboard", "Savings", "Goals"])

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

def _safe_money(x):
    try:
        return int(round(float(x)))
    except:
        return 0

import re

def _format_money_in_ai_text(text: str) -> str:
    """
    Post-process AI output for cleaner rendering WITHOUT corrupting percentages/counts.
    - Fix glued words/numbers (at7934 -> at 7934)
    - Normalize $ amounts to $X,XXX (no decimals) ONLY when already $-prefixed
    """
    if not text:
        return text

    text = text.replace("\u00A0", " ")
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)

    def money_repl(m):
        raw = m.group(0)
        num = raw.replace("$", "").replace(",", "")
        try:
            val = int(round(float(num)))
        except:
            return raw
        return f"${val:,}"

    text = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", money_repl, text)
    return text

def _normalize_title(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.lower()
        .str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

def _pct(numer: float, denom: float) -> float:
    if denom is None or denom == 0:
        return 0.0
    return float(numer) / float(denom)

def build_insight_payload(
    df_filtered_local: pd.DataFrame,
    focus_df_local: pd.DataFrame,
    selected_months_local: list,
    mode: str,
    focus_mode: str
) -> dict:
    work = focus_df_local.copy()
    if "Date" in work.columns:
        work["Date"] = pd.to_datetime(work["Date"], errors="coerce")

    expected_amt = work[work["Type"] == "Expected"]["Amount"].sum()
    actual_amt = work[work["Type"] == "Actual"]["Amount"].sum()
    variance_amt = actual_amt - expected_amt

    required = ["Date", "Title", "Category", "Type", "Amount"]
    missing_cells = 0
    total_cells = 0
    for c in required:
        if c in work.columns:
            total_cells += len(work)
            missing_cells += work[c].isna().sum()
        else:
            total_cells += len(work)
            missing_cells += len(work)
    missing_pct = (missing_cells / total_cells) if total_cells else 1.0

    n_txns = int(len(work))
    n_months_selected = int(len([m for m in selected_months_local if m]))

    work["Title_norm"] = _normalize_title(work["Title"])

    by_cat_actual = (
        work[work["Type"] == "Actual"]
        .groupby("Category", as_index=False)["Amount"]
        .sum()
        .sort_values("Amount", ascending=False)
    )
    total_actual_for_share = float(by_cat_actual["Amount"].sum()) if not by_cat_actual.empty else 0.0

    top3_cat = by_cat_actual.head(3).copy()
    if not top3_cat.empty:
        top3_cat["Amount"] = top3_cat["Amount"].apply(_safe_money)
        top3_cat["share_of_total_actual"] = top3_cat["Amount"].apply(lambda x: round(_pct(x, total_actual_for_share) * 100, 1))

    top10_cat = by_cat_actual.head(10).copy()
    if not top10_cat.empty:
        top10_cat["Amount"] = top10_cat["Amount"].apply(_safe_money)
        top10_cat["share_of_total_actual"] = top10_cat["Amount"].apply(lambda x: round(_pct(x, total_actual_for_share) * 100, 1))

    by_cat_pivot = (
        work
        .groupby(["Category", "Type"], as_index=False)["Amount"]
        .sum()
        .pivot(index="Category", columns="Type", values="Amount")
        .fillna(0)
    )
    by_cat_pivot["delta"] = by_cat_pivot.get("Actual", 0) - by_cat_pivot.get("Expected", 0)
    over_sorted = by_cat_pivot.sort_values("delta", ascending=False).reset_index()
    under_sorted = by_cat_pivot.sort_values("delta", ascending=True).reset_index()

    biggest_over_budget = None
    biggest_under_budget = None
    if len(over_sorted) > 0:
        biggest_over_budget = {
            "Category": str(over_sorted.loc[0, "Category"]),
            "delta": _safe_money(over_sorted.loc[0, "delta"]),
            "Actual": _safe_money(over_sorted.loc[0, "Actual"]) if "Actual" in over_sorted.columns else 0,
            "Expected": _safe_money(over_sorted.loc[0, "Expected"]) if "Expected" in over_sorted.columns else 0,
        }
    if len(under_sorted) > 0:
        biggest_under_budget = {
            "Category": str(under_sorted.loc[0, "Category"]),
            "delta": _safe_money(under_sorted.loc[0, "delta"]),
            "Actual": _safe_money(under_sorted.loc[0, "Actual"]) if "Actual" in under_sorted.columns else 0,
            "Expected": _safe_money(under_sorted.loc[0, "Expected"]) if "Expected" in under_sorted.columns else 0,
        }

    mom = None
    if work["Month"].notna().any():
        monthly_actual = (
            work[work["Type"] == "Actual"]
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

    actual_rows = work[work["Type"] == "Actual"].copy()
    recurring = []
    if not actual_rows.empty and actual_rows["Date"].notna().any():
        actual_rows["YearMonth"] = actual_rows["Date"].dt.to_period("M").astype(str)
        rec = (
            actual_rows
            .groupby(["Title_norm"], as_index=False)
            .agg(
                Title=("Title", "first"),
                count=("Title_norm", "size"),
                months=("YearMonth", pd.Series.nunique),
                avg_amount=("Amount", "mean"),
                total_amount=("Amount", "sum")
            )
            .sort_values(["months", "total_amount"], ascending=[False, False])
        )
        rec = rec[(rec["count"] >= 2) | (rec["months"] >= 2)].head(10).copy()
        if not rec.empty:
            rec["avg_amount"] = rec["avg_amount"].apply(_safe_money)
            rec["total_amount"] = rec["total_amount"].apply(_safe_money)
            recurring = rec[["Title", "count", "months", "avg_amount", "total_amount"]].to_dict(orient="records")

    patterns = {"weekday_spend": [], "week_of_month_spend": []}
    if not actual_rows.empty and actual_rows["Date"].notna().any():
        actual_rows["Weekday"] = actual_rows["Date"].dt.day_name()
        wd = (
            actual_rows
            .groupby("Weekday", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
        )
        if not wd.empty:
            wd["Amount"] = wd["Amount"].apply(_safe_money)
            patterns["weekday_spend"] = wd.head(7).to_dict(orient="records")

        actual_rows["WeekOfMonth"] = ((actual_rows["Date"].dt.day.fillna(1) - 1) // 7 + 1).astype(int)
        wom = (
            actual_rows
            .groupby("WeekOfMonth", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
        )
        if not wom.empty:
            wom["Amount"] = wom["Amount"].apply(_safe_money)
            patterns["week_of_month_spend"] = wom.head(4).to_dict(orient="records")

    budget_targets = []
    if not actual_rows.empty and actual_rows["Date"].notna().any():
        actual_rows["YearMonth"] = actual_rows["Date"].dt.to_period("M").astype(str)
        monthly_by_cat = (
            actual_rows
            .groupby(["Category", "YearMonth"], as_index=False)["Amount"]
            .sum()
        )
        med = (
            monthly_by_cat
            .groupby("Category", as_index=False)["Amount"]
            .median()
            .sort_values("Amount", ascending=False)
            .head(10)
            .copy()
        )
        if not med.empty:
            med["median_monthly"] = med["Amount"].apply(_safe_money)
            med["trim_10pct_target"] = med["median_monthly"].apply(lambda x: _safe_money(x * 0.9))
            med["cap_weekly_target"] = med["median_monthly"].apply(lambda x: _safe_money(x / 4.33))
            budget_targets = med[["Category", "median_monthly", "trim_10pct_target", "cap_weekly_target"]].to_dict(orient="records")

    totals = {
        "expected": _safe_money(expected_amt),
        "actual": _safe_money(actual_amt),
        "variance": _safe_money(variance_amt),
        "variance_pct_of_expected": round(_pct(variance_amt, expected_amt) * 100, 1) if expected_amt else 0.0,
    }

    if mode == "expenses":
        income_actual_local = df_filtered_local[
            (df_filtered_local["Category"] == "Income") &
            (df_filtered_local["Type"] == "Actual")
        ]["Amount"].sum()
        money_left = income_actual_local - actual_amt
        totals["income_actual"] = _safe_money(income_actual_local)
        totals["money_left_to_spend"] = _safe_money(money_left)

    return {
        "mode": mode,
        "focus_mode": focus_mode,
        "period_months": selected_months_local,
        "confidence": {
            "n_transactions": n_txns,
            "n_months_selected": n_months_selected,
            "missing_pct_required_fields": round(missing_pct * 100, 1),
        },
        "totals": totals,
        "top_categories_actual": top10_cat.to_dict(orient="records") if not top10_cat.empty else [],
        "top3_categories_actual": top3_cat.to_dict(orient="records") if not top3_cat.empty else [],
        "biggest_over_budget": biggest_over_budget,
        "biggest_under_budget": biggest_under_budget,
        "month_over_month": mom,
        "recurring_suspects": recurring,
        "patterns": patterns,
        "budget_targets": budget_targets,
        "notes": [
            "Use ONLY numbers present in this payload.",
            "If confidence.missing_pct_required_fields is high or n_transactions is low, recommend data cleanup instead of strong advice.",
        ],
    }

@st.cache_data(ttl=3600, show_spinner=False)
def generate_ai_insights_cached(period_key: str, payload: dict, focus_mode: str) -> dict:
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

    mode = str(payload.get("mode", "")).strip().lower()

    if mode == "savings":
        focus_rules = {
            "Cut expenses": "Do NOT recommend cutting savings categories. Reframe into improving consistency and increasing savings over time.",
            "Reduce subscriptions": "If recurring_suspects look like transfers/deposits, praise consistency; if not enough data, say insufficient data.",
            "Increase savings": "Highlight what went well (ahead of plan), and give concrete ways to increase/automate savings.",
            "Fix budget accuracy": "Focus on Expected vs Actual savings gaps; suggest updating expected values for more realistic goals.",
            "Find anomalies": "Flag spikes/outliers in savings contributions and pattern timing; suggest verifying one-offs or duplicate entries.",
        }
        focus_hint = focus_rules.get(focus_mode, focus_rules["Increase savings"])

        system_msg = (
            "You are a helpful personal finance coach focused on SAVINGS. "
            "Use ONLY the numbers in the provided payload. "
            "Never invent numbers. Never mention JSON, payload, or internal fields. "
            "Output MUST be bullet points only (no paragraphs). "
            "Every bullet MUST include at least one number from the payload. "
            "If you cannot cite numbers for a claim, say 'Insufficient data' and move on. "
            "No moralizing language. Keep it friendly and practical. "
            "FORMAT RULE: Any money amount must be written like $12,345 (no decimals). "
            "Percentages must be like 12.3% (1 decimal ok)."
        )

        user_msg = f"""
Focus mode: {focus_mode}
Goal: {focus_hint}

Here are aggregated SAVINGS results for a selected period:

{payload}

Required output format (bullets only):
- Headline: one sentence like "You were ahead/behind your savings plan by $X (Y%)."
  (Interpretation: variance = actual - expected. Positive is ahead of plan; negative is behind.)
- Where savings went well: 2 bullets using top categories ($ and % share) and/or any over-plan category deltas.
- Why it happened: 1–2 bullets using patterns (recurring_suspects and weekday/week_of_month) if available.
- Do this next: 1–3 bullets that INCREASE or STABILIZE savings (e.g., "add $50/month", "set $X auto-transfer", "keep Category A at $Y/month"), not cutting savings categories.
- Confidence: 1 bullet referencing n_transactions, n_months_selected, missing_pct_required_fields, with a caveat if low.

Rules:
- Use only payload numbers.
- If recurring_suspects is empty, say "Insufficient data" for recurring commentary.
- If weekday/week_of_month patterns are empty, say "Insufficient data" for pattern commentary.
- Do NOT output bare numbers: include $ for money and % for percentages.
"""
    else:
        focus_rules = {
            "Cut expenses": "Prioritize categories/titles to reduce; propose measurable caps.",
            "Reduce subscriptions": "Prioritize recurring_suspects; identify likely subscriptions and next steps to cancel/downgrade.",
            "Increase savings": "Highlight levers to move money into savings; suggest transfer targets.",
            "Fix budget accuracy": "Focus on Expected vs Actual gaps; suggest which categories need updated expected values.",
            "Find anomalies": "Flag spikes/outliers and unusual weekday/week-of-month patterns; suggest checks for one-offs or duplicates.",
        }
        focus_hint = focus_rules.get(focus_mode, focus_rules["Cut expenses"])

        system_msg = (
            "You are a helpful personal finance analyst. "
            "Use ONLY the numbers in the provided payload. "
            "Never invent numbers. Never mention JSON, payload, or internal fields. "
            "Output MUST be bullet points only (no paragraphs). "
            "Every bullet MUST include at least one number from the payload. "
            "If you cannot cite numbers for a claim, say 'Insufficient data' and move on. "
            "No moralizing language. Keep it friendly and practical. "
            "FORMAT RULE: Any money amount must be written like $12,345 (no decimals). "
            "Percentages must be like 12.3% (1 decimal ok)."
        )

        user_msg = f"""
Focus mode: {focus_mode}
Goal: {focus_hint}

Here are aggregated finances for a selected period:

{payload}

Required output format (bullets only):
- Headline: one sentence like "You were over plan by $X mainly due to Y."
- Top drivers: 3 bullets, each includes category name + $ amount + % of total actual.
- Why it happened: 2 bullets using patterns (recurring_suspects and weekday/week_of_month) if available.
- Do this next: 1–3 bullets with measurable targets (e.g., "$30/week", "cut by $120 next month", "cancel X saving $Y/month").
- Confidence: 1 bullet referencing n_transactions, n_months_selected, missing_pct_required_fields, plus a caveat if low.

Rules:
- Use only payload numbers.
- If recurring_suspects is empty, say "Insufficient data" for subscription/recurring commentary.
- If weekday/week_of_month patterns are empty, say "Insufficient data" for pattern commentary.
- Do NOT output bare numbers: include $ for money and % for percentages.
"""

    model_name = "gpt-4.1-mini"

    try:
        resp = client.responses.create(
            model=model_name,
            instructions=system_msg,
            input=user_msg,
            temperature=0.3,
        )
        return {"text": resp.output_text.strip(), "model": model_name}

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

    if focus_df_local is None or focus_df_local.empty:
        st.info("No data available for the selected filters. Adjust filters to generate insights.")
        return

    focus_options = ["Cut expenses", "Reduce subscriptions", "Increase savings", "Fix budget accuracy", "Find anomalies"]
    focus_key = f"{key_prefix}_ai_focus_{mode}"

    if focus_key not in st.session_state:
        st.session_state[focus_key] = "Increase savings" if mode == "savings" else "Cut expenses"

    with st.expander("How this works", expanded=False):
        st.write(
            "This section is hybrid: the app computes the facts locally (totals, deltas, top drivers, patterns), "
            "then AI turns those facts into plain-English insights. No raw transactions are sent."
        )
        st.session_state[focus_key] = st.selectbox(
            "Focus",
            options=focus_options,
            index=focus_options.index(st.session_state[focus_key]) if st.session_state[focus_key] in focus_options else 0,
            key=f"{focus_key}_selectbox"
        )

    focus_mode = st.session_state[focus_key]

    payload = build_insight_payload(
        df_filtered_local=df_filtered_local,
        focus_df_local=focus_df_local,
        selected_months_local=selected_months_local,
        mode=mode,
        focus_mode=focus_mode
    )

    st.markdown("**Insight Snapshot (local):**")

    total_expected = payload["totals"]["expected"]
    total_actual = payload["totals"]["actual"]
    variance = payload["totals"]["variance"]
    variance_pct = payload["totals"].get("variance_pct_of_expected", 0.0)

    if mode == "expenses":
        income_actual = payload["totals"].get("income_actual", 0)
        money_left = payload["totals"].get("money_left_to_spend", 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected", f"${total_expected:,.0f}")
        c2.metric("Actual", f"${total_actual:,.0f}")
        c3.metric("Over/Under (EvA)", f"${variance:,.0f}", f"{variance_pct:.1f}%")
        c4.metric("Money Left", f"${money_left:,.0f}")
        st.caption(f"Income (Actual): ${income_actual:,.0f}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected", f"${total_expected:,.0f}")
        c2.metric("Actual", f"${total_actual:,.0f}")
        c3.metric("Over/Under (EvA)", f"${variance:,.0f}", f"{variance_pct:.1f}%")
        c4.metric("Transactions", f"{payload['confidence']['n_transactions']:,}")

    top3 = payload.get("top3_categories_actual", [])
    if top3:
        top3_df = pd.DataFrame(top3)[["Category", "Amount", "share_of_total_actual"]].copy()
        top3_df["Amount"] = top3_df["Amount"].apply(lambda x: f"${int(x):,}")
        top3_df["% of total (Actual)"] = top3_df["share_of_total_actual"].apply(lambda x: f"{float(x):.1f}%")
        top3_df = top3_df.drop(columns=["share_of_total_actual"])
        st.dataframe(top3_df, width="stretch", hide_index=True)
    else:
        st.info("Top categories: insufficient data for this selection.")

    actual_only = focus_df_local[focus_df_local["Type"].astype(str).str.strip().eq("Actual")].copy()
    if not actual_only.empty:
        st.markdown("**Largest single transaction (Actual):**")
        idx = actual_only["Amount"].astype(float).idxmax()
        row = actual_only.loc[idx]
        dt = pd.to_datetime(row["Date"], errors="coerce")
        dt_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else "Unknown"
        st.write(f"- {row.get('Title','(Unknown)')} — ${float(row.get('Amount',0)):,.0f} on {dt_str}")
    else:
        st.info("Transaction snapshot: insufficient Actual rows for this selection.")

    import time
    period_key = f"{mode}|{focus_mode}|" + ",".join(selected_months_local)

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
                result = generate_ai_insights_cached(period_key=period_key, payload=payload, focus_mode=focus_mode)
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
            formatted = _format_money_in_ai_text(result["text"])
            formatted = formatted.replace("$", r"\$")
            formatted = formatted.replace("\u00A0", " ")
            st.markdown(formatted)
            st.caption(f"Model: {result.get('model', 'unknown')} | Cached per selected months+focus for ~1 hour")

            st.markdown("**Drill-down (local):**")
            d1, d2, d3 = st.columns(3)

            top_driver_cat = None
            if payload.get("top_categories_actual"):
                top_driver_cat = payload["top_categories_actual"][0].get("Category")

            with d1:
                if st.button("Show top driver transactions", key=f"{key_prefix}_drill_topdriver_{mode}"):
                    if top_driver_cat:
                        tx = focus_df_local[
                            (focus_df_local["Type"].astype(str).str.strip().eq("Actual")) &
                            (focus_df_local["Category"].astype(str).str.strip().eq(str(top_driver_cat)))
                        ].copy()
                        st.dataframe(tx.sort_values(["Date", "Amount"], ascending=[False, False]), width="stretch")
                    else:
                        st.info("Insufficient data to identify a top driver.")

            with d2:
                if st.button("Show recurring suspects", key=f"{key_prefix}_drill_recurring_{mode}"):
                    rec = payload.get("recurring_suspects", [])
                    if rec:
                        st.dataframe(pd.DataFrame(rec), width="stretch", hide_index=True)
                    else:
                        st.info("Insufficient data to compute recurring suspects for this selection.")

            with d3:
                if st.button("Highlight recurring items", key=f"{key_prefix}_drill_highlight_{mode}"):
                    tx = focus_df_local[focus_df_local["Type"].astype(str).str.strip().eq("Actual")].copy()
                    if tx.empty:
                        st.info("No Actual transactions available for this selection.")
                    else:
                        tx["Title_norm"] = _normalize_title(tx["Title"])
                        counts = tx.groupby("Title_norm")["Title_norm"].transform("size")
                        tx["Recurring?"] = counts >= 2
                        st.dataframe(tx.sort_values(["Recurring?", "Date", "Amount"], ascending=[False, False, False]), width="stretch")

    else:
        if not can_run:
            remaining = int(COOLDOWN_SECONDS - (time.time() - st.session_state[ts_key]))
            st.info(f"Please wait {remaining}s before generating again.")
        else:
            st.info("Click **Generate insights with AI** to create personalized insights for the selected period.")

with tab_dashboard:
    df_filtered = apply_tab_filters(df, "dash")
    selected_months = st.session_state.get("dash_selected_months", MONTH_ORDER)

    expense_df = df_filtered[~df_filtered["Category"].isin(EXCLUDED_CATEGORIES)]

    st.subheader("📊 Key Metrics")

    expected_expenses = expense_df[expense_df["Type"] == "Expected"]["Amount"].sum()
    actual_expenses = expense_df[expense_df["Type"] == "Actual"]["Amount"].sum()
    variance_expenses = actual_expenses - expected_expenses

    income_actual = df_filtered[
        (df_filtered["Category"] == "Income") &
        (df_filtered["Type"] == "Actual")
    ]["Amount"].sum()

    net_variance = income_actual - actual_expenses

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Expected Expenses", f"${expected_expenses:,.0f}")
    col2.metric("Actual Expenses", f"${actual_expenses:,.0f}")
    col3.metric("Expenses EvA", f"${variance_expenses:,.0f}")
    col4.metric("Income Actual", f"${income_actual:,.0f}")
    col5.metric("Money Left to Spend", f"${net_variance:,.0f}")

    st.subheader("📊 Expected vs Actual by Category")
    chart_df = expense_df[~expense_df["Category"].str.contains("Mortgage", case=False, na=False)]

    summary_df = (
        chart_df
        .groupby(["Category", "Type"], as_index=False)["Amount"]
        .sum()
    )

    fig_summary = px.bar(summary_df, x="Category", y="Amount", color="Type", barmode="group")
    fig_summary.update_layout(template="plotly_white")
    st.plotly_chart(fig_summary, width="stretch")

    st.subheader("📈 Monthly Spending Trend (Actual)")
    monthly_trend = (
        expense_df[expense_df["Type"] == "Actual"]
        .groupby("Month", as_index=False)["Amount"]
        .sum()
        .sort_values("Month")
    )

    fig_trend = px.line(monthly_trend, x="Month", y="Amount", markers=True)
    fig_trend.update_layout(template="plotly_white")
    st.plotly_chart(fig_trend, width="stretch")

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

    fig_top10 = px.bar(top10, x="Amount", y="Title", orientation="h")
    fig_top10.update_layout(template="plotly_white", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_top10, width="stretch")

    st.subheader("💸 Over / Under Budget")
    variance_df = summary_df.pivot(index="Category", columns="Type", values="Amount").fillna(0)
    variance_df["Variance"] = variance_df.get("Actual", 0) - variance_df.get("Expected", 0)
    variance_df = variance_df.reset_index()

    fig_variance = px.bar(variance_df, x="Category", y="Variance", color="Variance")
    fig_variance.update_layout(template="plotly_white")
    st.plotly_chart(fig_variance, width="stretch")

    st.subheader("🧾 Trackers")

    def highlight_rows(row, income_mask, expense_mask, subs_mask):
        if subs_mask.loc[row.name]:
            return ["background-color: rgba(255, 235, 59, 0.25)"] * len(row)
        if income_mask.loc[row.name]:
            return ["background-color: rgba(76, 175, 80, 0.20)"] * len(row)
        if expense_mask.loc[row.name]:
            return ["background-color: rgba(244, 67, 54, 0.15)"] * len(row)
        return [""] * len(row)

    income_mask = df_filtered["Category"].astype(str).str.strip().eq("Income")
    expense_mask = ~df_filtered["Category"].astype(str).str.strip().eq("Income")
    subscription_mask = df_filtered["Category"].astype(str).str.strip().eq("Subscription")

    income_display_df = df_filtered[income_mask & (df_filtered["Type"] == "Actual")].copy()
    expense_display_df = df_filtered[expense_mask & (df_filtered["Type"] == "Actual")].copy()
    subs_display_df = df_filtered[subscription_mask & (df_filtered["Type"] == "Actual")].copy()

    def tidy_tracker_display(df_in: pd.DataFrame) -> pd.DataFrame:
        df_out = df_in.copy()
        cols_to_drop = [c for c in ["Updated", "2/18/26"] if c in df_out.columns]
        if cols_to_drop:
            df_out = df_out.drop(columns=cols_to_drop)

        if "Date" in df_out.columns:
            df_out["Date"] = pd.to_datetime(df_out["Date"], errors="coerce").dt.date

        if "Amount" in df_out.columns:
            df_out["Amount"] = df_out["Amount"].apply(lambda x: f"${x:,.2f}")

        return df_out

    income_total_actual = income_display_df["Amount"].sum()
    with st.expander("💵 Income Summary (highlighted)"):
        income_show = tidy_tracker_display(income_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True]))
        styled_income = income_show.style.apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        st.dataframe(styled_income, width="stretch")
        st.success(f"**Income Total (Actual, current filters):** **${income_total_actual:,.0f}**")

    expense_total_actual_tracker = expense_display_df["Amount"].sum()
    with st.expander("💸 Expenses Summary (highlighted)"):
        expense_show = tidy_tracker_display(expense_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True]))
        styled_expenses = expense_show.style.apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        st.dataframe(styled_expenses, width="stretch")
        st.warning(f"**Expense Total (Actual, current filters):** **${expense_total_actual_tracker:,.0f}**")

    subs_total_actual = subs_display_df["Amount"].sum()
    with st.expander("🔁 Subscription Tracker (highlighted)"):
        subs_show = tidy_tracker_display(subs_display_df.sort_values(["Category", "Date", "Title"], ascending=[True, False, True]))
        styled_subs = subs_show.style.apply(lambda r: highlight_rows(r, income_mask, expense_mask, subscription_mask), axis=1)
        st.dataframe(styled_subs, width="stretch")
        st.info(f"**Subscription Total (Actual, current filters):** **${subs_total_actual:,.0f}**")

    with st.expander("Show Raw Data"):
        st.dataframe(df_filtered.sort_values(["Date", "Title"], ascending=[False, True]), width="stretch")

    render_ai_insights(
        df_filtered_local=df_filtered,
        focus_df_local=expense_df,
        selected_months_local=selected_months,
        key_prefix="dash",
        mode="expenses"
    )

with tab_savings:
    df_filtered = apply_tab_filters(df, "sav")
    selected_months = st.session_state.get("sav_selected_months", MONTH_ORDER)

    savings_df = df_filtered[df_filtered["Status"].astype(str).str.strip().eq("Savings")]

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
            key="savings_summary_empty"
        )

        st.subheader("🏆 Top 5 Savings Categories")
        savings_titles_top10 = (
            df[
                (df["Status"].astype(str).str.strip().eq("Savings")) &
                (df["Type"].astype(str).str.strip().eq("Actual"))
            ]
            .groupby("Title", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
            .head(10)
        )

        fig_savings_titles_top10 = px.bar(savings_titles_top10, x="Amount", y="Title", orientation="h")
        fig_savings_titles_top10.update_layout(template="plotly_white", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_savings_titles_top10, width="stretch", key="savings_titles_top10_empty")

        st.subheader("💸 Over / Under Savings")
        st.plotly_chart(
            px.bar(pd.DataFrame(columns=["Category", "Variance"]), x="Category", y="Variance", color="Variance").update_layout(template="plotly_white"),
            width="stretch",
            key="savings_variance_empty"
        )

        with st.expander("Show Savings Raw Data"):
            st.dataframe(savings_df.sort_values(["Date", "Title"], ascending=[False, True]), width="stretch")

        render_ai_insights(
            df_filtered_local=df_filtered,
            focus_df_local=savings_df,
            selected_months_local=selected_months,
            key_prefix="sav",
            mode="savings"
        )

    else:
        st.subheader("📊 Savings Key Metrics")

        expected_savings = savings_df[savings_df["Type"] == "Expected"]["Amount"].sum()
        actual_savings = savings_df[savings_df["Type"] == "Actual"]["Amount"].sum()
        variance_savings = actual_savings - expected_savings

        s1, s2, s3 = st.columns(3)
        s1.metric("Expected Savings", f"${expected_savings:,.0f}")
        s2.metric("Actual Savings", f"${actual_savings:,.0f}")
        s3.metric("Savings EvA", f"${variance_savings:,.0f}")

        st.subheader("📊 Expected vs Actual Savings by Category")
        savings_summary_df = (
            savings_df
            .groupby(["Category", "Type"], as_index=False)["Amount"]
            .sum()
        )

        fig_savings_summary = px.bar(savings_summary_df, x="Category", y="Amount", color="Type", barmode="group")
        fig_savings_summary.update_layout(template="plotly_white")
        st.plotly_chart(fig_savings_summary, width="stretch")

        st.subheader("🏆 Top 5 Savings Categories")
        savings_titles_top10 = (
            df[
                (df["Status"].astype(str).str.strip().eq("Savings")) &
                (df["Type"].astype(str).str.strip().eq("Actual"))
            ]
            .groupby("Title", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
            .head(10)
        )

        fig_savings_titles_top10 = px.bar(savings_titles_top10, x="Amount", y="Title", orientation="h")
        fig_savings_titles_top10.update_layout(template="plotly_white", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_savings_titles_top10, width="stretch")

        st.subheader("💸 Over / Under Savings")
        savings_variance_df = savings_summary_df.pivot(index="Category", columns="Type", values="Amount").fillna(0)
        savings_variance_df["Variance"] = savings_variance_df.get("Actual", 0) - savings_variance_df.get("Expected", 0)
        savings_variance_df = savings_variance_df.reset_index()

        fig_savings_variance = px.bar(savings_variance_df, x="Category", y="Variance", color="Variance")
        fig_savings_variance.update_layout(template="plotly_white")
        st.plotly_chart(fig_savings_variance, width="stretch")

        with st.expander("Show Savings Raw Data"):
            st.dataframe(savings_df.sort_values(["Date", "Title"], ascending=[False, True]), width="stretch")

        render_ai_insights(
            df_filtered_local=df_filtered,
            focus_df_local=savings_df,
            selected_months_local=selected_months,
            key_prefix="sav",
            mode="savings"
        )

with tab_goals:
    # ✅ Filters only for Goals tab (independent keys)
    df_filtered = apply_tab_filters(df, "gol")

    def _progress_bar_figure(progress_df: pd.DataFrame, title: str) -> go.Figure:
        """
        progress_df columns required:
          - Title
          - Expected
          - Actual
          - FillPct (0..100)
          - Color ("green"/"red")
        """
        if progress_df.empty:
            fig = go.Figure()
            fig.update_layout(template="plotly_white", title=title)
            return fig

        # Background (100%) + overlay filled bar
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=[100] * len(progress_df),
                y=progress_df["Title"],
                orientation="h",
                marker=dict(color="rgba(0,0,0,0.08)"),
                hoverinfo="skip",
                showlegend=False,
                name="Expected baseline"
            )
        )

        color_map = {"green": "#2e7d32", "red": "#c62828"}
        fig.add_trace(
            go.Bar(
                x=progress_df["FillPct"],
                y=progress_df["Title"],
                orientation="h",
                marker=dict(color=[color_map.get(c, "#2e7d32") for c in progress_df["Color"]]),
                customdata=progress_df[["Expected", "Actual", "FillPct"]].values,
                hovertemplate=(
                    "Title: %{y}<br>"
                    "Expected: $%{customdata[0]:,.0f}<br>"
                    "Actual: $%{customdata[1]:,.0f}<br>"
                    "Filled: %{customdata[2]:.1f}%<extra></extra>"
                ),
                showlegend=False,
                name="Progress"
            )
        )

        # ✅ ADD: labels at the exact end of the filled bar (with $)
        # Place annotation at x = FillPct, y = Title.
        annotations = []
        for _, r in progress_df.iterrows():
            label = f"${float(r['Actual']):,.0f} / ${float(r['Expected']):,.0f}"
            annotations.append(
                dict(
                    x=float(r["FillPct"]),
                    y=str(r["Title"]),
                    xref="x",
                    yref="y",
                    text=label,
                    showarrow=False,
                    xanchor="left",   # label extends to the right of bar end
                    align="left",
                    xshift=8          # tiny pixel nudge so it doesn't overlap the bar edge
                )
            )

        fig.update_layout(
            template="plotly_white",
            title=title,
            barmode="overlay",
            xaxis=dict(range=[0, 100], title="Progress (filled %)"),
            yaxis=dict(title=""),
            height=max(320, 40 * len(progress_df) + 120),
            margin=dict(l=40, r=20, t=60, b=40),
            annotations=annotations,
        )
        return fig

    # -----------------------------
    # GOALS: Savings Goals (Expected vs Actual per Title)
    # -----------------------------
    st.subheader("🎯 Savings Goals Progress")

    g_savings = df_filtered[df_filtered["Category"].astype(str).str.strip().eq("Savings Goals")].copy()

    if g_savings.empty:
        st.info("No Savings Goals data for the selected filters yet.")
    else:
        g_savings_sum = (
            g_savings
            .groupby(["Title", "Type"], as_index=False)["Amount"]
            .sum()
            .pivot(index="Title", columns="Type", values="Amount")
            .fillna(0)
            .reset_index()
        )
        g_savings_sum["Expected"] = g_savings_sum.get("Expected", 0).astype(float).abs()
        g_savings_sum["Actual"] = g_savings_sum.get("Actual", 0).astype(float).abs()

        # ✅ per your rule: "filled" is min/ max, so if Expected is 75% of Actual -> fill 75%
        denom = g_savings_sum[["Expected", "Actual"]].max(axis=1).replace(0, 1.0)
        g_savings_sum["FillPct"] = (g_savings_sum[["Expected", "Actual"]].min(axis=1) / denom) * 100

        # ✅ color rules for Savings Goals:
        # - equal => green
        # - Actual > Expected => green
        # - Actual < Expected => red
        g_savings_sum["Color"] = g_savings_sum.apply(
            lambda r: "green" if float(r["Actual"]) >= float(r["Expected"]) else "red",
            axis=1
        )

        g_savings_sum = g_savings_sum.sort_values("Title").copy()
        fig = _progress_bar_figure(g_savings_sum[["Title", "Expected", "Actual", "FillPct", "Color"]], "Savings Goals (Expected vs Actual)")
        st.plotly_chart(fig, width="stretch")

    # -----------------------------
    # GOALS: Debt (Expected vs Actual per Title)
    # -----------------------------
    st.subheader("📉 Debt Progress")

    g_debt = df_filtered[df_filtered["Category"].astype(str).str.strip().eq("Debt")].copy()

    if g_debt.empty:
        st.info("No Debt data for the selected filters yet.")
    else:
        g_debt_sum = (
            g_debt
            .groupby(["Title", "Type"], as_index=False)["Amount"]
            .sum()
            .pivot(index="Title", columns="Type", values="Amount")
            .fillna(0)
            .reset_index()
        )
        g_debt_sum["Expected"] = g_debt_sum.get("Expected", 0).astype(float).abs()
        g_debt_sum["Actual"] = g_debt_sum.get("Actual", 0).astype(float).abs()

        denom = g_debt_sum[["Expected", "Actual"]].max(axis=1).replace(0, 1.0)
        g_debt_sum["FillPct"] = (g_debt_sum[["Expected", "Actual"]].min(axis=1) / denom) * 100

        # ✅ color rules for Debt:
        # - if Actual < Expected => green
        # - if Actual > Expected => red
        # (equal treated as green)
        g_debt_sum["Color"] = g_debt_sum.apply(
            lambda r: "green" if float(r["Actual"]) <= float(r["Expected"]) else "red",
            axis=1
        )

        g_debt_sum = g_debt_sum.sort_values("Title").copy()
        fig = _progress_bar_figure(g_debt_sum[["Title", "Expected", "Actual", "FillPct", "Color"]], "Debt (Expected vs Actual)")
        st.plotly_chart(fig, width="stretch")
