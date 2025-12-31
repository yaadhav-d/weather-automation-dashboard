import os
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
    "host": "shortline.proxy.rlwy.net",
    "port": 46617,
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
def get_dict_connection():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"check_hostname": False, "verify_mode": False}
    )

def get_plain_connection():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        ssl={"check_hostname": False, "verify_mode": False}
    )

# =========================
# INGESTION CONTROL (BULLETPROOF)
# =========================
def should_ingest():
    try:
        conn = get_dict_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(recorded_at) AS last_time FROM weather_data")
        row = cursor.fetchone()
        conn.close()

        if not row or row["last_time"] is None:
            return True

        last_time = row["last_time"]

        if isinstance(last_time, str):
            last_time = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")

        now_naive = datetime.now(IST).replace(tzinfo=None)

        return (now_naive - last_time).total_seconds() >= 3600

    except Exception:
        return True

# =========================
# INGEST WEATHER DATA
# =========================
def ingest_weather_once():
    conn = get_dict_connection()
    cursor = conn.cursor()

    for city in CITIES:
        try:
            response = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": API_KEY},
                timeout=10
            )
            data = response.json()

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
        except Exception:
            pass

    conn.commit()
    conn.close()

# Run ingestion safely
if should_ingest():
    ingest_weather_once()

# =========================
# LOAD DATA (NO CURSOR BUG)
# =========================
@st.cache_data(ttl=300)
def load_data():
    conn = get_plain_connection()
    query = """
        SELECT
            city,
            country,
            temperature_c,
            humidity_percent,
            recorded_at
        FROM weather_data
        ORDER BY recorded_at
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

df = load_data()

if df.empty:
    st.warning("No data available yet. Please wait for the first ingestion.")
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
st.dataframe(
    filtered_df.sort_values("recorded_at", ascending=False),
    use_container_width=True
)

st.caption("Fully automated • Cloud-hosted • SQL-backed")
