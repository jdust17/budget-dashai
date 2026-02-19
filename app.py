import pandas as pd
import streamlit as st
import plotly.express as px

# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(page_title="Personal Finance Dashboard", layout="wide")
st.title("💰 Personal Finance Dashboard")

# -----------------------------
# Load data (BULLETPROOF VERSION)
# -----------------------------
@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSk2lX_RGYx7SCR7nsZPJWoUgybCQEThXTeot_1o5ee7FdJPaDCbl6cu-FbR4iNOvtF7ftslAAYNXK8/pub?gid=1013390825&single=true&output=csv"

    df = pd.read_csv(url)

    # Ensure only first 4 columns are used
    df = df.iloc[:, :4]
    df.columns = ["Month", "Category", "Type", "Amount"]

    # Strip whitespace
    df["Month"] = df["Month"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip()
    df["Type"] = df["Type"].astype(str).str.strip()

    # Robust amount cleaning (handles $, commas, spaces, unicode)
    df["Amount"] = (
        df["Amount"]
        .astype(str)
        .str.replace(r"[^\d.\-]", "", regex=True)
    )
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    # Drop bad rows
    df = df.dropna(subset=["Amount"])

    return df

df = load_data()

# -----------------------------
# Month ordering
# -----------------------------
MONTH_ORDER = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

df["Month"] = pd.Categorical(df["Month"], categories=MONTH_ORDER, ordered=True)

# -----------------------------
# Category grouping
# -----------------------------
category_map = {
    "income": ["Jacob Income", "Zoe Income", "Rental Home Income", "Bank Account Interest"],
    "tithes": ["Tithing", "Newman Center", "St Ann's"],
    "fixed": ["Mortgage", "Internet", "Spotify + YouTube", "Kof C Insurance"],
    "needs": ["Utilities", "Groceries", "Car/Gas", "Water", "Trash"],
    "wants": ["Eating Out", "Travel", "Gifts", "Date Night"]
}

def assign_category_group(category):
    for group, categories in category_map.items():
        if category in categories:
            return group
    return "other"

df["category_group"] = df["Category"].apply(assign_category_group)

# -----------------------------
# Sidebar filters
# -----------------------------
st.sidebar.header("Filters")

selected_months = st.sidebar.multiselect(
    "Select Month(s)",
    options=MONTH_ORDER,
    default=MONTH_ORDER
)

include_income = st.sidebar.toggle("Include Income in Charts", value=False)

df_filtered = df[df["Month"].isin(selected_months)]

# -----------------------------
# Exclusion rules
# -----------------------------
EXCLUDE_KEYWORDS = [
    "total",
    "non-investment",
    "jacob income",
    "zoe income",
    "rental",
    "interest"
]

def exclude_rows(df):
    return df[
        ~df["Category"].str.lower().str.contains("|".join(EXCLUDE_KEYWORDS), na=False)
    ]

df_spending = exclude_rows(df_filtered)

if include_income:
    df_spending = df_filtered

# -----------------------------
# SUMMARY CHART
# -----------------------------
summary_df = (
    df_spending
    .groupby(["category_group", "Type"], as_index=False)["Amount"]
    .sum()
)

fig_summary = px.bar(
    summary_df,
    x="category_group",
    y="Amount",
    color="Type",
    barmode="group",
    title="Expected vs Actual by Category Group"
)

fig_summary.update_layout(template="plotly_white")
st.plotly_chart(fig_summary, use_container_width=True)

# -----------------------------
# Monthly Spending Trend
# -----------------------------
st.subheader("📈 Monthly Spending Trend (Actual)")

monthly_trend = (
    df_spending[df_spending["Type"] == "Actual"]
    .groupby("Month", as_index=False)["Amount"]
    .sum()
    .sort_values("Month")
)

fig_trend = px.line(
    monthly_trend,
    x="Month",
    y="Amount",
    markers=True,
    title="Total Actual Spending by Month"
)

fig_trend.update_layout(template="plotly_white")
st.plotly_chart(fig_trend, use_container_width=True)

# -----------------------------
# Over / Under Budget
# -----------------------------
st.subheader("💸 Over / Under Budget")

variance_df = (
    summary_df
    .pivot(index="category_group", columns="Type", values="Amount")
    .fillna(0)
)

# Ensure columns exist to prevent KeyError
variance_df["Actual"] = variance_df.get("Actual", 0)
variance_df["Expected"] = variance_df.get("Expected", 0)

variance_df["Variance"] = variance_df["Actual"] - variance_df["Expected"]
variance_df = variance_df.reset_index()

fig_variance = px.bar(
    variance_df,
    x="category_group",
    y="Variance",
    color="Variance",
    title="Over / Under Budget"
)

fig_variance.update_layout(template="plotly_white")
st.plotly_chart(fig_variance, use_container_width=True)

# -----------------------------
# Top 10 Spending Categories
# -----------------------------
st.subheader("🏆 Top 10 Spending Categories")

# Exclude mortgage ONLY here
df_top10_base = df_spending[
    ~df_spending["Category"].str.lower().str.contains("mortgage", na=False)
]

top10 = (
    df_top10_base[df_top10_base["Type"] == "Actual"]
    .groupby("Category", as_index=False)["Amount"]
    .sum()
    .sort_values("Amount", ascending=False)
    .head(10)
)

fig_top10 = px.bar(
    top10,
    x="Amount",
    y="Category",
    orientation="h",
    title="Top 10 Spending Categories"
)

fig_top10.update_layout(template="plotly_white", yaxis=dict(autorange="reversed"))
st.plotly_chart(fig_top10, use_container_width=True)

# -----------------------------
# Monthly Trend for Top 10 Categories
# -----------------------------
st.subheader("📊 Monthly Trend — Top 10 Categories")

top10_categories = top10["Category"].tolist()

monthly_top10 = (
    df_top10_base[
        (df_top10_base["Type"] == "Actual") &
        (df_top10_base["Category"].isin(top10_categories))
    ]
    .groupby(["Month", "Category"], as_index=False)["Amount"]
    .sum()
    .sort_values(["Category", "Month"])
)

fig_monthly_top10 = px.bar(
    monthly_top10,
    x="Month",
    y="Amount",
    color="Category",
    facet_col="Category",
    facet_col_wrap=2,
    title="Monthly Spending for Top Categories"
)

fig_monthly_top10.update_layout(template="plotly_white", height=1000)
st.plotly_chart(fig_monthly_top10, use_container_width=True)

# -----------------------------
# Key Metrics
# -----------------------------
st.subheader("📊 Key Metrics")

actual_total = df_spending[df_spending["Type"] == "Actual"]["Amount"].sum()
expected_total = df_spending[df_spending["Type"] == "Expected"]["Amount"].sum()
variance_total = actual_total - expected_total

col1, col2, col3 = st.columns(3)
col1.metric("Actual Spending", f"${actual_total:,.0f}")
col2.metric("Expected Spending", f"${expected_total:,.0f}")
col3.metric("Over / Under", f"${variance_total:,.0f}")

# -----------------------------
# Raw Data
# -----------------------------
with st.expander("Show Raw Data"):
    st.dataframe(df_filtered, use_container_width=True)
