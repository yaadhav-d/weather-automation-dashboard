import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Live Weather Dashboard", layout="wide")

st.title("🌦 Live Weather Dashboard")
st.caption("Automated weather monitoring using Python, SQL, and Streamlit")

# =========================
# DATABASE CONNECTION
# =========================
DB_CONFIG = {
    "host": "shortline.proxy.rlwy.net",
    "port": 46617,
    "user": "root",
    "password": "ykAAFwsZzFztPQQSuHcczaLucwqifwqI",
    "database": "weather_dashboard"
}


@st.cache_data(ttl=300)
def load_data():
    conn = mysql.connector.connect(**DB_CONFIG)
    query = """
        SELECT city, country, temperature_c, feels_like_c,
               humidity_percent, pressure_hpa, wind_speed_mps,
               weather_condition, recorded_at
        FROM weather_data
        ORDER BY recorded_at
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

df = load_data()

# =========================
# SIDEBAR FILTERS
# =========================
st.sidebar.header("Filters")

cities = st.sidebar.multiselect(
    "Select City",
    options=sorted(df["city"].unique()),
    default=sorted(df["city"].unique())
)

date_range = st.sidebar.date_input(
    "Select Date Range",
    [df["recorded_at"].min().date(), df["recorded_at"].max().date()]
)

filtered_df = df[
    (df["city"].isin(cities)) &
    (df["recorded_at"].dt.date >= date_range[0]) &
    (df["recorded_at"].dt.date <= date_range[1])
]

# =========================
# KPIs (Latest Snapshot)
# =========================
st.subheader("Current Weather Snapshot")

latest = (
    filtered_df.sort_values("recorded_at")
    .groupby("city")
    .tail(1)
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Avg Temperature (°C)", round(latest["temperature_c"].mean(), 1))
col2.metric("Avg Humidity (%)", round(latest["humidity_percent"].mean(), 1))
col3.metric("Avg Pressure (hPa)", round(latest["pressure_hpa"].mean(), 1))
col4.metric("Avg Wind Speed (m/s)", round(latest["wind_speed_mps"].mean(), 1))

# =========================
# CHARTS
# =========================
st.subheader("Temperature Trend (Last 7 Days)")

temp_fig = px.line(
    filtered_df,
    x="recorded_at",
    y="temperature_c",
    color="city",
    labels={"temperature_c": "Temperature (°C)", "recorded_at": "Time"}
)
st.plotly_chart(temp_fig, use_container_width=True)

st.subheader("Humidity Trend")

hum_fig = px.line(
    filtered_df,
    x="recorded_at",
    y="humidity_percent",
    color="city",
    labels={"humidity_percent": "Humidity (%)", "recorded_at": "Time"}
)
st.plotly_chart(hum_fig, use_container_width=True)

# =========================
# DATA TABLE
# =========================
st.subheader("Raw Weather Data")
st.dataframe(filtered_df.sort_values("recorded_at", ascending=False), use_container_width=True)

st.caption(f"Last updated from database")
