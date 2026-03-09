from flask import Flask, request, jsonify, render_template
import sqlite3
import datetime
import os

import joblib
import requests

# ---------------------------------------------------------------------------
# Paths — project root is one level up from this file
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "plant_data.db")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

# ---------------------------------------------------------------------------
# ML models (loaded once at startup)
# ---------------------------------------------------------------------------
try:
    model_rf = joblib.load(os.path.join(BASE_DIR, "randomForest_plantWater.pkl"))
    model_lr = joblib.load(os.path.join(BASE_DIR, "logistic_plantWater.pkl"))
    MODELS_LOADED = True
    print("✓ ML models loaded successfully")
except Exception as e:
    model_rf = model_lr = None
    MODELS_LOADED = False
    print(f"⚠ ML models not loaded ({e}) — /predict will be unavailable")

# ---------------------------------------------------------------------------
# Weather API config
# ---------------------------------------------------------------------------
API_KEY = "8a16f844a85643388cc163615260903"
CITY = "Kelambakkam"  


def get_weather(city=None):
    """Fetch pressure & wind from WeatherAPI. air_temp/air_humidity come from ESP32 sensors."""
    q = city or CITY
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={API_KEY}&q={q}"
        res = requests.get(url, timeout=5).json()
        return {
            "pressure": res["current"]["pressure_mb"] / 10,
            "wind_speed": res["current"]["wind_kph"],
            "wind_gust": res["current"]["gust_kph"],
        }
    except Exception as e:
        print("Weather API error:", e)
        return {
            "pressure": 101,
            "wind_speed": 5,
            "wind_gust": 7,
        }


def decide(data):
    """Run ML models + rule-based overrides to decide pump ON(1) / OFF(0)."""
    input_data = [[
        data["soil_moisture"],
        data["soil_temp"],
        data["air_humidity"],
        datetime.datetime.now().hour,
        data["air_temp"],
        data["wind_speed"],
        data["air_humidity"],
        data["wind_gust"],
        data["pressure"],
    ]]

    rf = model_rf.predict(input_data)[0]
    lr = model_lr.predict(input_data)[0]

    # Safety rules
    if data["soil_moisture"] < 20:
        return 1
    if data["soil_moisture"] > 70:
        return 0
    if datetime.datetime.now().hour < 5 or datetime.datetime.now().hour > 20:
        return 0

    return int(rf or lr)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            soil_moisture REAL,
            temperature REAL,
            humidity REAL,
            pump_status INTEGER,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()


def fetch_recent(limit: int = 20):
    limit = max(1, min(int(limit), 200))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    latest = rows[0] if rows else None
    return rows, latest


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route('/')
def landing():
    return render_template("index.html")


@app.route('/dashboard')
def dashboard():
    rows, latest = fetch_recent(20)
    return render_template("dashboard.html", data=rows, latest=latest, city=CITY)


# ---------------------------------------------------------------------------
# Data logging API  (ESP32 → server)
# ---------------------------------------------------------------------------
@app.route('/update', methods=['POST'])
def update_data():
    data = request.get_json(silent=True) or {}
    required = ("soil_moisture", "temperature", "humidity", "pump_status")
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing keys: {', '.join(missing)}"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO sensor_data (soil_moisture, temperature, humidity, pump_status, timestamp) VALUES (?, ?, ?, ?, ?)",
        (data["soil_moisture"], data["temperature"],
         data["humidity"], data["pump_status"],
         datetime.datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

    return jsonify({"message": "Data saved"})


@app.route('/api/recent')
def api_recent():
    limit = request.args.get("limit", "20")
    try:
        rows, latest = fetch_recent(int(limit))
    except Exception:
        rows, latest = fetch_recent(20)
    return jsonify({"rows": rows, "latest": latest})


# ---------------------------------------------------------------------------
# City configuration API
# ---------------------------------------------------------------------------
@app.route('/set_city', methods=['POST'])
def set_city():
    global CITY
    body = request.get_json(silent=True) or {}
    new_city = body.get('city', '').strip()
    if not new_city:
        return jsonify({"error": "City name is required"}), 400
    CITY = new_city
    print(f"City updated to: {CITY}")
    return jsonify({"message": f"City set to {CITY}", "city": CITY})


@app.route('/get_city')
def get_city():
    return jsonify({"city": CITY})


# ---------------------------------------------------------------------------
# ML prediction API  (ESP32 → server)
# ---------------------------------------------------------------------------
@app.route("/predict", methods=["POST"])
def predict():
    if not MODELS_LOADED:
        return jsonify({"error": "ML models not loaded"}), 503

    soil_data = request.get_json()
    if not soil_data or "soil_moisture" not in soil_data:
        return jsonify({"error": "Invalid data"}), 400

    print("\nReceived from ESP32:", soil_data)

    weather = get_weather()
    combined = {**soil_data, **weather}

    print("Combined Data:", combined)

    decision = decide(combined)

    print("Decision:", decision)

    # ---- persist every prediction so the dashboard updates in real-time ----
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sensor_data "
            "(soil_moisture, temperature, humidity, pump_status, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                float(soil_data["soil_moisture"]),
                float(soil_data.get("air_temp", 0)),       # from ESP32 DHT22
                float(soil_data.get("air_humidity", 0)),   # from ESP32 DHT22
                int(decision),
                datetime.datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()
        print("✓ Prediction logged to DB")
    except Exception as db_err:
        print(f"⚠ DB insert failed: {db_err}")

    return jsonify({"decision": int(decision)})


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
