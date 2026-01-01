import os
import requests
from datetime import datetime
import pytz
import pymysql
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

# =========================
# CONFIGURATION
# =========================

API_KEY = os.getenv("OPENWEATHER_API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")

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
    "host": "shinkansen.proxy.rlwy.net",
    "port": 47686,
    "user": "root",
    "password": DB_PASSWORD,
    "database": "railway"
}

# =========================
# SAFETY CHECK
# =========================
if not API_KEY or not DB_PASSWORD:
    st.error("Secrets not set. Please configure OPENWEATHER_API_KEY and DB_PASSWORD.")
    st.stop()

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Live Weather Dashboard", layout="wide")
st.title("🌦 Live Weather Dashboard")
st.caption("Automated weather monitoring using Python, SQL, and Streamlit")

# =========================
# DATABASE CONNECTIONS
# =========================
def get_write_connection():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        ssl={"ssl": {}},     # REQUIRED for Railway
        autocommit=True
    )

def get_read_engine():
    return create_engine(
        f"mysql+pymysql://root:{DB_PASSWORD}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        connect_args={"ssl": {"ssl": {}}},
        pool_pre_ping=True
    )

# =========================
# INGESTION CONTROL (SAFE)
# =========================
def should_ingest():
    try:
        conn = get_write_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(recorded_at) FROM weather_data")
        last_time = cursor.fetchone()[0]
        conn.close()

        if last_time is None:
            return True

        if isinstance(last_time, str):
            last_time = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")

        now_naive = datetime.now(IST).replace(tzinfo=None)
        return (now_naive - last_time).total_seconds() >= 3600

    except Exception:
        # Fail open – do not crash app
        return False

# =========================
# INGEST WEATHER DATA
# =========================
def ingest_weather_once():
    conn = get_write_connection()
    cursor = conn.cursor()

    for city in CITIES:
        try:
            r = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": API_KEY},
                timeout=10
            )
            data = r.json()

            cursor.execute(
                """
                INSERT INTO weather_data
                (city, country, temperature_c, humidity_percent, recorded_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    data["name"],
                    data["sys"]["country"],
                    round(data["main"]["temp"] - 273.15, 2),
                    data["main"]["humidity"],
                    datetime.now(IST).replace(tzinfo=None)
                )
            )

        except Exception as e:
            print(f"Ingestion error for {city}: {e}")

    conn.close()

# 🔒 Run ingestion only once per session
if "ingested" not in st.session_state:
    if should_ingest():
        ingest_weather_once()
    st.session_state["ingested"] = True

# =========================
# LOAD DATA (STABLE)
# =========================
@st.cache_data(ttl=300)
def load_data():
    engine = get_read_engine()
    query = """
        SELECT city, country, temperature_c, humidity_percent, recorded_at
        FROM weather_data
        ORDER BY recorded_at DESC
    """
    return pd.read_sql(query, engine)

df = load_data()

if df.empty:
    st.warning("Waiting for first data ingestion…")
    st.stop()

# =========================
# SIDEBAR FILTERS
# =========================
st.sidebar.header("Filters")

cities = st.sidebar.multiselect(
    "Select City",
    sorted(df["city"].unique()),
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

c1, c2 = st.columns(2)
c1.metric("Avg Temperature (°C)", round(latest["temperature_c"].mean(), 1))
c2.metric("Avg Humidity (%)", round(latest["humidity_percent"].mean(), 1))

# =========================
# CHARTS
# =========================
st.subheader("Temperature Trend")
st.plotly_chart(
    px.line(filtered_df, x="recorded_at", y="temperature_c", color="city"),
    use_container_width=True
)

st.subheader("Humidity Trend")
st.plotly_chart(
    px.line(filtered_df, x="recorded_at", y="humidity_percent", color="city"),
    use_container_width=True
)

# =========================
# DATA TABLE
# =========================
st.subheader("Raw Weather Data")
st.dataframe(filtered_df, use_container_width=True)

st.caption("Fully automated • Cloud-hosted • SQL-backed")
