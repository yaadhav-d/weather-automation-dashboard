import os
import requests
from datetime import datetime
import pytz
import pymysql

# =========================
# CONFIGURATION
# =========================

API_KEY = os.getenv("OPENWEATHER_API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

DB_CONFIG = {
    "host": "shortline.proxy.rlwy.net",
    "port": 46617,
    "user": "root",
    "password": DB_PASSWORD,
    "database": "railway",
    "ssl": {"check_hostname": False, "verify_mode": False}
}

CITIES = [
    "New Delhi,IN",
    "Chennai,IN",
    "Mumbai,IN",
    "Bengaluru,IN",
    "Hyderabad,IN",
    "Kolkata,IN",
    "Jaipur,IN",
    "Thiruvananthapuram,IN"
]

IST = pytz.timezone("Asia/Kolkata")

# =========================
# SAFETY CHECK
# =========================
if not API_KEY or not DB_PASSWORD:
    raise RuntimeError("Environment variables not set")

# =========================
# INGESTION
# =========================
def run_ingestion():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    recorded_at = datetime.now(IST).replace(tzinfo=None)

    for city in CITIES:
        try:
            response = requests.get(
                BASE_URL,
                params={"q": city, "appid": API_KEY},
                timeout=10
            )
            data = response.json()

            cursor.execute(
                """
                INSERT INTO weather_data (
                    city, country, temperature_c, feels_like_c,
                    humidity_percent, pressure_hpa, wind_speed_mps,
                    weather_condition, weather_description, recorded_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    data["name"],
                    data["sys"]["country"],
                    round(data["main"]["temp"] - 273.15, 2),
                    round(data["main"]["feels_like"] - 273.15, 2),
                    data["main"]["humidity"],
                    data["main"]["pressure"],
                    data["wind"]["speed"],
                    data["weather"][0]["main"],
                    data["weather"][0]["description"],
                    recorded_at
                )
            )

            print(f"Inserted {data['name']}")

        except Exception as e:
            print(f"Error for {city}: {e}")

    # 7-day retention
    cursor.execute(
        "DELETE FROM weather_data WHERE recorded_at < NOW() - INTERVAL 7 DAY"
    )

    conn.commit()
    cursor.close()
    conn.close()

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    run_ingestion()
