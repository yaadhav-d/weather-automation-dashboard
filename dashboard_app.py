import os
from urllib.parse import quote_plus
import streamlit as st
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
from datetime import datetime
import time
from sqlalchemy import create_engine, text
from datetime import timezone, timedelta
import streamlit.components.v1 as components


IST = timezone(timedelta(hours=5, minutes=30))
# -------------------------------------------------
# LOAD ENV (LOCAL + STREAMLIT + RAILWAY SAFE)
# -------------------------------------------------
load_dotenv()

db_user = os.getenv("MYSQLUSER") or os.getenv("DB_USER")
raw_password = os.getenv("MYSQLPASSWORD") or os.getenv("DB_PASSWORD")
db_host = os.getenv("MYSQLHOST") or os.getenv("DB_HOST")
db_port = os.getenv("MYSQLPORT") or os.getenv("DB_PORT")
db_name = os.getenv("MYSQLDATABASE") or os.getenv("DB_NAME")

if not all([db_user, raw_password, db_host, db_port, db_name]):
    st.error("❌ Database environment variables are missing")
    st.stop()

db_port = int(db_port)
db_password = quote_plus(raw_password)

engine = create_engine(
    f"mysql+mysqlconnector://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
    pool_pre_ping=True
)

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Live Weather Dashboard",
    page_icon="🌦️",
    layout="wide"
)
# 🔴 ADDED: CSS page navigation
st.markdown("""
<style>
.page { display: none; }
.page.default { display: block; }

#home:target,
#data:target,
#graph:target {
    display: block;
}

.nav {
    display: flex;
    gap: 20px;
    margin-bottom: 25px;
}
.nav a {
    text-decoration: none;
    padding: 10px 22px;
    background: #1e3c72;
    color: white;
    border-radius: 12px;
    font-weight: bold;
}
.nav a:hover {
    background: #2a5298;
}
</style>
""", unsafe_allow_html=True)

# 🔴 ADDED: Top navigation bar
st.markdown("""
<div class="nav">
  <a href="#home">🏠 Home</a>
  <a href="#data">📊 Data View</a>
  <a href="#graph">📈 Graph View</a>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------
# BACKGROUND BASED ON TEMPERATURE
# -------------------------------------------------
def set_bg_by_temp(temp, condition):
    hour = datetime.now(IST).hour
    condition = condition.lower()

    # 🌙 Night time
    if hour >= 20 or hour < 4:
        if "rain" in condition:
            img = "https://images.pexels.com/photos/110874/pexels-photo-110874.jpeg"  # night rain
        else:
            img = "https://images.pexels.com/photos/813269/pexels-photo-813269.jpeg"  # clear night

    # ☀️ Day time
    else:
        if "rain" in condition:
            img = "https://images.pexels.com/photos/2448749/pexels-photo-2448749.jpeg"  # sun + rain
        elif temp >= 35:
            img = "https://images.pexels.com/photos/1019472/pexels-photo-1019472.jpeg"  # very hot
        elif temp >= 30:
            img = "https://images.pexels.com/photos/301599/pexels-photo-301599.jpeg"   # hot
        elif temp >= 20:
            img = "https://images.pexels.com/photos/8284762/pexels-photo-8284762.jpeg" # moderate
        else:
            img = "https://images.pexels.com/photos/209831/pexels-photo-209831.jpeg"   # cold

    st.markdown(f"""
        <style>
        .stApp {{
            background-image: url("{img}");
            background-size: cover;
            background-attachment: fixed;
        }}
        [data-testid="stAppViewContainer"] {{
            background-color: rgba(0,0,0,0.55);
        }}
        h1,h2,h3,h4,p,label {{
            color: white !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# -------------------------------------------------
# COUNTRY & CITY DATA
# -------------------------------------------------
country_city = {
    "India": {
        "code": "IN",
        "cities": [
            "Bangalore", "Delhi", "Mumbai", "Chennai", "Hyderabad",
            "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Trichy"
        ]
    },

    "USA": {
        "code": "US",
        "cities": [
            "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
            "San Francisco", "San Diego", "Dallas", "Seattle", "Boston"
        ]
    },

    "UK": {
        "code": "GB",
        "cities": [
            "London", "Manchester", "Birmingham", "Liverpool",
            "Leeds", "Bristol", "Nottingham"
        ]
    }


}


# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------

st.sidebar.header("Dashboard Controls")
COUNTRY = st.sidebar.selectbox("Select Country", country_city.keys())
CITY = st.sidebar.selectbox("Select City", country_city[COUNTRY]["cities"])
TIME_OPTION = st.sidebar.selectbox(
    "Time Range",
    ["All","Night","Morning","Afternoon","Evening"]
)
REFRESH_INTERVAL = st.sidebar.selectbox(
    "Auto Refresh",
    [120,300,600,1800,3600],
    format_func=lambda x: "Off" if x == 0 else f"{x//60} min"
)
compare_cities = st.sidebar.multiselect(
    "Compare With Cities",
    country_city[COUNTRY]["cities"],
    default=[]
)


INTERVAL_MINUTES = REFRESH_INTERVAL//60

API_KEY = os.getenv("OPENWEATHER_API_KEY") or "YOUR_API_KEY"

# -------------------------------------------------
# WEATHER API
# -------------------------------------------------
def get_current_weather(city, country_code):
    res = requests.get(
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city},{country_code}&appid={API_KEY}&units=metric"
    ).json()

    if "main" not in res:
        st.error(res.get("message","API Error"))
        st.stop()

    return {
        "temperature": res["main"]["temp"],
        "humidity": res["main"]["humidity"],
        "wind": res["wind"]["speed"],
        "condition": res["weather"][0]["description"]
    }

def get_forecast(city, country_code):
    res = requests.get(
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?q={city},{country_code}&appid={API_KEY}&units=metric"
    ).json()

    rows = []
    for item in res["list"]:
        rows.append({
            "Date & Time": (
                    datetime.fromtimestamp(item["dt"], tz=timezone.utc).astimezone(IST).replace(tzinfo=None) ),
            "Temperature (°C)": item["main"]["temp"]
        })

    return pd.DataFrame(rows)
# -------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------
def insert_sample_past_data(engine, country, city):
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT COUNT(*) FROM weather_history
                WHERE country=:country AND city=:city
            """),
            {"country": country, "city": city}
        ).scalar()
        print(result)

        if result > 5:
            return
        for day in range(7, 0, -1):
            base_date = datetime.now(IST) - pd.Timedelta(days=day)

            for hour in [0, 6, 12, 18]:      # 4 records per day (every 6 hours)
                record_time = base_date.replace(
                    hour=hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )

                conn.execute(
                    text("""
                        INSERT INTO weather_history
                        (country, city, Temperature, humidity, wind, Dates_times)
                        VALUES (:country, :city, :temp, :hum, :wind, :time)
                    """),
                    {
                        "country": country,
                        "city": city,
                        "temp": np.random.uniform(22, 32),
                        "hum": np.random.uniform(50, 80),
                        "wind": np.random.uniform(2, 6),
                        "time": record_time
                    }
                )

def store_live_weather_all_cities(engine, country_city, API_KEY, INTERVAL_MINUTES):
    """
    Stores live weather data for ALL cities in country_city
    with a per-city time gap control.
    """

    with engine.begin() as conn:

        now = datetime.now(IST)

        # 🔁 Loop through all countries
        for country, info in country_city.items():

            country_code = info["code"]   # ✅ country code dict value

            # 🔁 Loop through all cities of that country
            for city in info["cities"]:

                # 1️⃣ Get last stored time for THIS city
                last_time = conn.execute(
                    text("""
                        SELECT MAX(Dates_times)
                        FROM weather_history
                        WHERE country = :c AND city = :ci
                    """),
                    {"c": country, "ci": city}
                ).scalar()

                # 2️⃣ Check INTERVAL_MINUTES gap
                if last_time is not None:
                    last_time = pd.to_datetime(last_time).tz_localize(IST)
                    diff_minutes = (now - last_time).total_seconds() / 60

                    # 🔴 REPLACED: min_gap_minutes → INTERVAL_MINUTES
                    if diff_minutes < INTERVAL_MINUTES:
                        continue   # ⛔ Skip this city only

                # 3️⃣ Fetch live weather
                res = requests.get(
                    f"https://api.openweathermap.org/data/2.5/weather"
                    f"?q={city},{country_code}&appid={API_KEY}&units=metric",
                    timeout=10
                ).json()

                if "main" not in res:
                    continue  # Skip invalid response

                # 4️⃣ Store ALL values in a dictionary ✅
                weather_data = {
                    "country": country,
                    "city": city,
                    "temperature": res["main"]["temp"],
                    "humidity": res["main"]["humidity"],
                    "wind": res["wind"]["speed"],
                    "dt": now
                }

                # 5️⃣ Insert into DB using dictionary
                conn.execute(
                    text("""
                        INSERT INTO weather_history
                        (country, city, Temperature, humidity, wind, Dates_times)
                        VALUES (:country, :city, :temperature, :humidity, :wind, :dt)
                    """),
                    weather_data
                )

def get_past_week(engine, country, city):
    df = pd.read_sql(
        text("""
            SELECT Dates_times, temperature
            FROM weather_history
            WHERE country=:country AND city=:city
            ORDER BY Dates_times DESC
        """),
        engine,
        params={"country": country, "city": city}
    )
    df["Dates_times"] = pd.to_datetime(df["Dates_times"])
    return df.sort_values("Dates_times")
def get_today_weather(engine, country, city):
    df = pd.read_sql(
        text("""
            SELECT Dates_times, temperature
            FROM weather_history
            WHERE country = :country
              AND city = :city
              AND DATE(Dates_times) = CURDATE()
            ORDER BY Dates_times
        """),
        engine,
        params={"country": country, "city": city}
    )

    df["Dates_times"] = pd.to_datetime(df["Dates_times"])
    return df

def filter_by_time(df, time_col, time_option):
    if time_option == "Night":
        return df[df[time_col].dt.hour.between(0, 5)]
    elif time_option == "Morning":
        return df[df[time_col].dt.hour.between(6, 11)]
    elif time_option == "Afternoon":
        return df[df[time_col].dt.hour.between(12, 17)]
    elif time_option == "Evening":
        return df[df[time_col].dt.hour.between(18, 23)]
    else:
        return df.copy()

def get_past_daily_avg(engine, country, city, days=5):
    df = pd.read_sql(
        text("""
            SELECT 
                DATE(Dates_times) AS day,
                ROUND(AVG(temperature), 1) AS avg_temp
            FROM weather_history
            WHERE country = :c
              AND city = :ci
              AND DATE(Dates_times) < CURDATE()     -- ❌ exclude today
            GROUP BY DATE(Dates_times)
            ORDER BY day DESC
            LIMIT :d
        """),
        engine,
        params={"c": country, "ci": city, "d": days}
    )

    # Reverse so it shows Thu → Mon (left to right)
    return df


def get_future_daily_avg(forecast_df, days=5):
    today = datetime.now().date()

    forecast_df["day"] = forecast_df["Date & Time"].dt.date

    daily_avg = (
        forecast_df[forecast_df["day"] > today]   # ❌ exclude today
        .groupby("day")["Temperature (°C)"]
        .mean()
        .round(1)
        .reset_index(name="avg_temp")
        .sort_values("day")
        .head(days)
        .reset_index(drop=True)
    )

    return daily_avg


def get_weather_icon(temp):
    if temp >= 35:
        return "☀️"
    elif temp >= 28:
        return "🌤️"
    elif temp >= 20:
        return "⛅"
    else:
        return "☁️"
def render_weather_cards(df, title):
    st.subheader(title)

    cols = st.columns(len(df))

    for col, (_, row) in zip(cols, df.iterrows()):
        icon = get_weather_icon(row["avg_temp"])

        col.markdown(f"""
        <div style="
            background: linear-gradient(180deg, #1e3c72, #2a5298);
            border-radius: 16px;
            padding: 16px;
            text-align: center;
            color: white;
        ">
            <div style="font-size:14px; opacity:0.9;">
                {pd.to_datetime(row["day"]).strftime('%a')}
            </div>
            <div style="font-size:28px; margin:6px 0;">
                {icon}
            </div>
            <div style="font-size:20px; font-weight:bold;">
                {row["avg_temp"]}°C
            </div>
        </div>
        """, unsafe_allow_html=True)

#for extra intractive
def get_delta(current, previous):
    if previous is None:
        return "—"
    diff = round(current - previous, 1)
    arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
    return f"{arrow} {abs(diff)}"

def city_status(today_df):
    if len(today_df) < 3:
        return "🟢 Stable"
    diff = today_df["temperature"].max() - today_df["temperature"].min()
    if diff < 1.5:
        return "🟢 Stable"
    elif diff < 4:
        return "🟡 Fluctuating"
    else:
        return "🔴 Volatile"

# ---------------------------------
# MAIN LOGIC
# ---------------------------------
country_code = country_city[COUNTRY]["code"]

current = get_current_weather(CITY, country_code)
weak_df = get_forecast(CITY, country_code)


set_bg_by_temp(current["temperature"],current["condition"])

insert_sample_past_data(engine, COUNTRY, CITY)
store_live_weather_all_cities(engine, country_city, API_KEY, INTERVAL_MINUTES)

past_df = get_past_week(engine, COUNTRY, CITY)

today_df = get_today_weather(engine, COUNTRY, CITY)


# -------------------------------
# GET DATA
# -------------------------------
past_daily_df = get_past_daily_avg(engine, COUNTRY, CITY, days=5)
future_daily_df = get_future_daily_avg(weak_df)
past_filtered_df   = filter_by_time(past_df,  "Dates_times", TIME_OPTION)
today_filtered_df  = filter_by_time(today_df, "Dates_times", TIME_OPTION)
future_filtered_df = filter_by_time(weak_df,  "Date & Time", TIME_OPTION)
# ---------------------------------
# UI
# ---------------------------------
st.markdown('<div id="home" class="page default">', unsafe_allow_html=True)
st.title("🌦️ Weather Analytics Dashboard")
st.divider()
prev_temp = today_df["temperature"].iloc[-2] if len(today_df) > 1 else None
delta = get_delta(current["temperature"], prev_temp)
status = city_status(today_df)

col1, col2, col3, col4,col5 = st.columns(5)
col1.metric("🌡️ Temperature (°C)", current["temperature"],delta)
col2.metric("💧 Humidity (%)", current["humidity"],delta)
col3.metric("🌬️ Wind Speed (m/s)", current["wind"],delta)
col4.metric("☁️ Condition", current["condition"].title())
col5.metric("City Status:", status)

last_ts = today_df["Dates_times"].max()
last_ts = last_ts.tz_localize(None)


st.markdown(
    f"**Last Updated:** {last_ts.strftime('%A, %d-%m-%Y %H:%M:%S')} | Location: **{CITY}, {COUNTRY}**"
)


st.divider()
render_weather_cards(past_daily_df, "🕒 Past Days Average")

st.divider()
render_weather_cards(future_daily_df.head(5), "🔮 Future Days Average")

st.divider()
st.subheader("📈 Today Temperature Statistics (Database)")

if not today_df.empty:
    temps = today_df["temperature"].to_numpy(float)
    st.write(f"Max: {temps.max():.2f} °C")
    st.write(f"Min: {temps.min():.2f} °C")
    st.write(f"Avg: {temps.mean():.2f} °C")
st.markdown('</div>', unsafe_allow_html=True)

# =================================================
# 📊 DATA PAGE
# =================================================
st.markdown('<div id="data" class="page">', unsafe_allow_html=True)
st.title("📊 Weather Data")

st.subheader("📊 Past Weather")
st.dataframe(
    past_filtered_df
        .rename(columns={"temperature": "Temperature(°C)"}),
    use_container_width=True)



st.subheader("📊 Today Live Weather")
st.dataframe(
    today_filtered_df
        .rename(columns={"temperature": "Temperature(°C)"}),
    use_container_width=True)


st.subheader("📊 Future Weather")
st.dataframe(
    future_filtered_df[["Date & Time", "Temperature (°C)"]],
    use_container_width=True)


st.markdown('</div>', unsafe_allow_html=True)

# =================================================
# 📈 GRAPH PAGE
# =================================================
st.markdown('<div id="graph" class="page">', unsafe_allow_html=True)

st.title("📈 Weather Trends")

st.subheader("📉  PAST Temperature Trend (Selected Time Range)")

# Safety check (VERY IMPORTANT)
if past_filtered_df.empty:
    st.warning("⚠️ No data available for the selected time range.")
else:
    plt.style.use("seaborn-v0_8")

    fig, ax = plt.subplots(figsize=(12, 5))

    # Line plot
    ax.plot(
        past_filtered_df["Dates_times"],
        past_filtered_df["temperature"],
        color="#FF00AE",
        linewidth=3,
        marker="o",
        markersize=7,
        markerfacecolor="white",
        markeredgecolor="#9500FF"
    )

    # Fill area under curve
    ax.fill_between(
        past_filtered_df["Dates_times"],
        past_filtered_df["temperature"],
        color="#9900FF44",
        alpha=0.25
    )

    # Highlight max temperature
    max_temp = past_filtered_df["temperature"].max()
    max_points = past_filtered_df[
        past_filtered_df["temperature"] == max_temp
    ]

    ax.scatter(
        max_points["Dates_times"],
        max_points["temperature"],
        color="red",
        s=100,
        label="Max Temp"
    )

    # Highlight min temperature
    min_temp = past_filtered_df["temperature"].min()
    min_points = past_filtered_df[
        past_filtered_df["temperature"] == min_temp
    ]

    ax.scatter(
        min_points["Dates_times"],
        min_points["temperature"],
        color="blue",
        s=100,
        label="Min Temp"
    )

    # Titles & labels
    ax.set_title(
        f"Temperature Trend - {CITY}, {COUNTRY}",
        fontsize=15,
        fontweight="bold"
    )
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)

    # Grid & background
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.set_facecolor("#f9f9f9")
    fig.patch.set_facecolor("white")

    # Legend
    ax.legend()

    # X-axis formatting
    ax.xaxis.set_major_locator(plt.MaxNLocator(7))
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    st.pyplot(fig)

# ---------------------------------
# TODAY TEMPERATURE TREND GRAPH
# ---------------------------------
st.subheader("📊 Today Temperature Trend (Live Data)")

if today_df.empty:
    st.warning("⚠️ No weather data recorded today yet.")
else:
    plt.style.use("seaborn-v0_8")

    fig, ax = plt.subplots(figsize=(12, 5))

    # Line plot
    ax.plot(
        today_df["Dates_times"],
        today_df["temperature"],
        color="#FF6F00",
        linewidth=3,
        marker="o",
        markersize=6,
        markerfacecolor="white",
        markeredgecolor="#FF6F00",
        label="Temperature"
    )

    # Fill area
    ax.fill_between(
        today_df["Dates_times"],
        today_df["temperature"],
        color="#FF6F0044",
        alpha=0.3
    )

    # Max & Min
    max_temp = today_df["temperature"].max()
    min_temp = today_df["temperature"].min()

    max_points = today_df[today_df["temperature"] == max_temp]
    min_points = today_df[today_df["temperature"] == min_temp]

    ax.scatter(
        max_points["Dates_times"],
        max_points["temperature"],
        color="red",
        s=120,
        label="Max Temp"
    )

    ax.scatter(
        min_points["Dates_times"],
        min_points["temperature"],
        color="blue",
        s=120,
        label="Min Temp"
    )

    # Titles & labels
    ax.set_title(
        f"Today's Temperature Trend - {CITY}, {COUNTRY}",
        fontsize=15,
        fontweight="bold"
    )
    ax.set_xlabel("Time", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)

    # Grid & background
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.set_facecolor("#f9f9f9")
    fig.patch.set_facecolor("white")

    # X-axis formatting
    ax.xaxis.set_major_locator(plt.MaxNLocator(8))
    plt.xticks(rotation=45, ha="right")

    # Legend
    ax.legend()

    plt.tight_layout()
    st.pyplot(fig)

# -------------------------------
# FUTURE FORECAST GRAPH
# -------------------------------
st.subheader("📈 Future Forecast (Advanced View)")

plt.style.use("seaborn-v0_8-darkgrid")

fig2, ax2 = plt.subplots(figsize=(12, 5))

x = future_filtered_df["Date & Time"]
y = future_filtered_df["Temperature (°C)"]


# 🔥 Main temperature line
ax2.plot(
    x,
    y,
    color="#FF7A00",
    linewidth=3,
    marker="o",
    markersize=6,
    markerfacecolor="white",
    markeredgewidth=2,
    markeredgecolor="#FF7A00",
    label="Forecast Temp"
)

# 🌈 Glow effect (draw multiple transparent lines)
for lw in range(6, 1, -1):
    ax2.plot(x, y, color="#FF7A00", linewidth=lw, alpha=0.08)
    # 1️⃣ Main forecast line
    ax2.plot(
        x, y,
        color="#FF7A00",
        linewidth=3,
        marker="o",
        markersize=6,
        markerfacecolor="white",
        markeredgewidth=2,
        markeredgecolor="#FF7A00",
        label="Forecast Temp"
    )

    # 2️⃣ Glow effect (visual only, no legend)
    for lw in range(6, 1, -1):
        ax2.plot(x, y, color="#FF7A00", linewidth=lw, alpha=0.08)

    # 3️⃣ Expected range (ADD ONLY ONCE ✅)
    ax2.fill_between(
        x,
        y - 1.5,
        y + 1.5,
        color="#4ADE80",
        alpha=0.25,
        label="Expected Range"
    )

    # 4️⃣ Optional: Base fill under curve
    ax2.fill_between(
        x,
        y,
        min(y) - 2,
        color="#FF7A00",
        alpha=0.12
    )

# 🌊 Gradient fill under curve
ax2.fill_between(
    x,
    y,
    min(y) - 2,
    color="#FF7A00",
    alpha=0.18
)

# 🔴 Max temperature annotation
max_temp = y.max()
max_time = x[y.idxmax()]
ax2.scatter(max_time, max_temp, color="red", s=120, zorder=5)
ax2.annotate(
    f"Max {max_temp:.1f}°C",
    (max_time, max_temp),
    xytext=(0, 12),
    textcoords="offset points",
    ha="center",
    fontsize=10,
    fontweight="bold",
    color="red"
)

# 🔵 Min temperature annotation
min_temp = y.min()
min_time = x[y.idxmin()]
ax2.scatter(min_time, min_temp, color="blue", s=120, zorder=5)
ax2.annotate(
    f"Min {min_temp:.1f}°C",
    (min_time, min_temp),
    xytext=(0, -18),
    textcoords="offset points",
    ha="center",
    fontsize=10,
    fontweight="bold",
    color="blue"
)

# 🧭 Titles & labels
ax2.set_title(
    f"Future Temperature Forecast – {CITY}, {COUNTRY}",
    fontsize=16,
    fontweight="bold",
    pad=12
)
ax2.set_xlabel("Date & Time", fontsize=11)
ax2.set_ylabel("Temperature (°C)", fontsize=11)

# 🧱 Styling
ax2.set_facecolor("#0E1117")
fig2.patch.set_facecolor("#0E1117")
ax2.tick_params(colors="white")
ax2.xaxis.label.set_color("white")
ax2.yaxis.label.set_color("white")
ax2.title.set_color("white")

# ⏱ X-axis formatting
ax2.xaxis.set_major_locator(plt.MaxNLocator(8))
plt.xticks(rotation=45, ha="right")

# 📌 Legend
ax2.legend(facecolor="#1f2933", edgecolor="white", labelcolor="white")

# 5️⃣ Max / Min points
ax2.scatter(x[y.idxmax()], y.max(), color="red", s=120, zorder=5, label="Max")
ax2.scatter(x[y.idxmin()], y.min(), color="blue", s=120, zorder=5, label="Min")

# 6️⃣ Legend (ONCE, at the end)
plt.tight_layout()
st.pyplot(fig2)

# comparision
st.subheader("📊 City-wise Temperature Comparison (Today)")

fig, ax = plt.subplots(figsize=(12, 5))

# Main city
ax.plot(
    today_df["Dates_times"],
    today_df["temperature"],
    color="#FF6F00",
    linewidth=3,
    marker="o",
    label=CITY
)


# Comparison city

colors = ["#3B82F6", "#22C55E", "#EF4444", "#A855F7", "#14B8A6"]

for i, city in enumerate(compare_cities):
    compare_df = get_today_weather(engine, COUNTRY, city)

    if not compare_df.empty:
        ax.plot(
            compare_df["Dates_times"],
            compare_df["temperature"],
            linestyle="--",
            linewidth=2,
            marker="o",
            color=colors[i % len(colors)],
            label=city
        )

ax.legend()
st.pyplot(fig)
st.markdown('</div>', unsafe_allow_html=True)
with st.expander("ℹ️ How this dashboard works"):
    st.markdown("""
    - Weather data fetched from **OpenWeatherMap API**
    - Stored every **INTERVAL_MINUTES**
    - All cities tracked independently
    - Averages computed from database (not API)
    - Timezone handled using IST
    """)
components.html(
"""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">

<style>
.footer {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: rgba(15,23,42,0.9);
    backdrop-filter: blur(6px);
    padding: 14px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: white;
    z-index: 9999;
    font-family: Arial, sans-serif;
}

/* Left text */
.footer .emp {
    font-size: 14px;
    opacity: 0.9;
}

/* Social icons */
.footer .social a {
    color: white;
    font-size: 20px;
    margin-left: 18px;
    transition: 0.3s ease;
}
.footer .social a:hover {
    color: #38BDF8;
    transform: scale(1.2);
}

/* 📱 Mobile Responsive */
@media (max-width: 768px) {
    .footer {
        flex-direction: column;
        gap: 10px;
        text-align: center;
        padding: 12px 10px;
    }
    .footer .emp {
        font-size: 13px;
    }
    .footer .social a {
        margin: 0 12px;
        font-size: 22px;
    }
}
</style>

<div class="footer">
    <div class="emp">
        Project done by | Employee Code: <b>YAADHAV </b>
    </div>

    <div class="social">
        <a href="https://www.facebook.com" target="_blank" title="Facebook">
            <i class="fab fa-facebook"></i>
        </a>
        <a href="https://www.google.com" target="_blank" title="Google">
            <i class="fab fa-google"></i>
        </a>
        <a href="https://github.com/yaadhav-d/weather-automation-dashboard.git" target="_blank" title="Github">
            <i class="fab fa-github"></i>
        </a>
    </div>
</div>
""",
height=100,
)

# -------------------------------------------------
# AUTO REFRESH
# -------------------------------------------------
if REFRESH_INTERVAL > 0:
    time.sleep(REFRESH_INTERVAL)
    st.rerun()