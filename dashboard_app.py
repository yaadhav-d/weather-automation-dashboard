import os
import time
import requests
from datetime import datetime
import pytz
import pymysql
import streamlit as st
import pandas as pd
import plotly.express as px

# =========================
# CONFIGURATION
# =========================

API_KEY = os.getenv("efd6b4dcc0f1b762d34a167b399098a5")
DB_PASSWORD = os.getenv("ykAAFwsZzFztPQQSuHcczaLucwqifwqI")

IST = pytz.timezone("Asia/Kolkata")

CITIES = [
    "New Delhi,IN",
    "Chennai,IN",
    "Mumbai,IN",
    "Bengaluru,IN",
    "Hyderabad,IN",
    "Kolkata,IN"
]

DB_CONFIG = {
    "host": "shortline.proxy.rlwy.net",
    "port": 46617,
    "user": "root",
    "password": DB_PASSWORD,
    "database": "weather_dashboard"
}

# 🔴 SAFETY CHECK (MANDATORY)
if not API_KEY or not DB_PASSWORD:
    st.error("Secrets not set. Please add OPENWEATHER_API_KEY and DB_PASSWORD in Streamlit Secrets.")
    st.stop()

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Live Weather Dashboard", layout="wide")
st.title("🌦 Live Weather Dashboard")
st.caption("Automated weather monitoring using Python, SQL, and Streamlit")

# =========================
# INGESTION (RUNS MAX ONCE / HOUR)
# =========================

def ingest_weather_once():
    conn = pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor
    )

    cursor = conn.cursor()

    for city in CITIES:
        try:
            response = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": API_KEY},
                timeout=10
            )
            data = response.json()

            cursor.execute("""
                INSERT INTO weather_data
                (city, country, temperature_c, humidity_percent, recorded_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                data["name"],
                data["sys"]["country"],
                round(data["main"]["temp"] - 273.15, 2),
                data["main"]["humidity"],
                datetime.now(IST)
            ))
        except Exception:
            pass

    conn.commit()
    cursor.close()
    conn.close()

# Controlled execution
if "last_ingest_time" not in st.session_state:
    ingest_weather_once()
    st.session_state["last_ingest_time"] = time.time()

elif time.time() - st.session_state["last_ingest_time"] >= 3600:
    ingest_weather_once()
    st.session_state["last_ingest_time"] = time.time()

# =========================
# LOAD DATA
# =========================

@st.cache_data(ttl=300)
def load_data():
    conn = pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor
    )

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
# KPIs
# =========================
st.subheader("Current Weather Snapshot")

latest = (
    filtered_df.sort_values("recorded_at")
    .groupby("city")
    .tail(1)
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Avg Temp (°C)", round(latest["temperature_c"].mean(), 1))
c2.metric("Avg Humidity (%)", round(latest["humidity_percent"].mean(), 1))
c3.metric("Avg Pressure (hPa)", round(latest["pressure_hpa"].mean(), 1))
c4.metric("Avg Wind (m/s)", round(latest["wind_speed_mps"].mean(), 1))

# =========================
# CHARTS
# =========================
st.subheader("Temperature Trend")

st.plotly_chart(
    px.line(
        filtered_df,
        x="recorded_at",
        y="temperature_c",
        color="city",
        markers=True
    ),
    use_container_width=True
)

st.subheader("Humidity Trend")

st.plotly_chart(
    px.line(
        filtered_df,
        x="recorded_at",
        y="humidity_percent",
        color="city",
        markers=True
    ),
    use_container_width=True
)

# =========================
# DATA TABLE
# =========================
st.subheader("Raw Weather Data")
st.dataframe(filtered_df.sort_values("recorded_at", ascending=False), use_container_width=True)

st.caption("Fully automated • Cloud-hosted • SQL-backed")
