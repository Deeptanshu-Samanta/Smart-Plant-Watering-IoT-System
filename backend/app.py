from flask import Flask, request, jsonify, render_template
import sqlite3
import datetime
import joblib
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BACKEND_DIR, "plant_data.db")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)


# ---------------------------------------------------------------------------
# ML models
# ---------------------------------------------------------------------------
def _first_existing_path(paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


rf_path = _first_existing_path([
    os.path.join(BACKEND_DIR, "ML", "randomForest_plantWater.pkl"),
    os.path.join(BASE_DIR, "randomForest_plantWater.pkl"),
])
lr_path = _first_existing_path([
    os.path.join(BACKEND_DIR, "ML", "logistic_plantWater.pkl"),
    os.path.join(BASE_DIR, "logistic_plantWater.pkl"),
])

try:
    rf_model = joblib.load(rf_path) if rf_path else None
    lr_model = joblib.load(lr_path) if lr_path else None
    ML_AVAILABLE = bool(rf_model and lr_model)
    if ML_AVAILABLE:
        print("✓ ML models loaded")
    else:
        print("⚠ ML models not found — fallback logic only")
except Exception as error:
    print(f"⚠ Could not load ML models: {error}")
    rf_model = None
    lr_model = None
    ML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            soil_moisture    REAL,
            temperature      REAL,
            humidity         REAL,
            pump_status      INTEGER,
            reason           TEXT,
            duration_seconds INTEGER,
            timestamp        TEXT
        )
        '''
    )
    for col, col_type in (("reason", "TEXT"), ("duration_seconds", "INTEGER")):
        try:
            cursor.execute(f"ALTER TABLE sensor_data ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


init_db()


def get_last_row():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_recent(limit: int = 20):
    limit = max(1, min(int(limit), 200))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    latest = rows[0] if rows else None
    return rows, latest


# ---------------------------------------------------------------------------
# Pump decision logic
# ---------------------------------------------------------------------------
def predict_pump(data: dict) -> int:
    soil = float(data.get("soil_moisture", 0))

    if not ML_AVAILABLE:
        if soil < 30:
            return 1
        if soil > 70:
            return 0
        return int(data.get("pump_status", 0))

    features = [
        soil,
        float(data.get("soil_temp", data.get("temperature", 0))),
        float(data.get("air_humidity", data.get("humidity", 0))),
        datetime.datetime.now().hour,
        float(data.get("air_temp", data.get("temperature", 0))),
        float(data.get("wind_speed", 0)),
        float(data.get("air_humidity", data.get("humidity", 0))),
        float(data.get("wind_gust", 0)),
        float(data.get("pressure", 0)),
    ]

    try:
        rf_pred = int(rf_model.predict([features])[0])
        lr_pred = int(lr_model.predict([features])[0])
        ml_pred = int(rf_pred or lr_pred)
    except Exception as error:
        print(f"⚠ Prediction failed: {error}")
        ml_pred = int(data.get("pump_status", 0))

    if soil < 20:
        return 1
    if soil > 70:
        return 0
    hour = datetime.datetime.now().hour
    if hour < 5 or hour > 20:
        return 0

    return ml_pred


def build_reason(new_status: int, data: dict) -> str:
    soil = float(data.get("soil_moisture", 0))
    temp = float(data.get("temperature", data.get("air_temp", 0)))
    ml_tag = "ML triggered" if ML_AVAILABLE else "Rule fallback"

    if new_status == 1:
        if soil < 30:
            return f"Soil too dry ({soil:.0f}%) — {ml_tag}"
        if temp > 35:
            return f"High temp ({temp:.1f}°C) — {ml_tag}"
        return f"Moisture threshold — {ml_tag}"

    if soil >= 70:
        return f"Soil sufficient ({soil:.0f}%) — {ml_tag}"
    return f"Watering complete — {ml_tag}"


def calc_duration(last_on_timestamp: str) -> int:
    if not last_on_timestamp:
        return 0
    try:
        start = datetime.datetime.fromisoformat(last_on_timestamp)
        return int((datetime.datetime.now() - start).total_seconds())
    except Exception:
        return 0


def _handle_sensor_payload(payload: dict):
    required = ("soil_moisture",)
    missing = [k for k in required if k not in payload]
    if missing:
        return {"error": f"Missing keys: {', '.join(missing)}"}, 400

    normalized = {
        "soil_moisture": float(payload.get("soil_moisture", 0)),
        "temperature": float(payload.get("temperature", payload.get("air_temp", 0))),
        "humidity": float(payload.get("humidity", payload.get("air_humidity", 0))),
        "soil_temp": float(payload.get("soil_temp", payload.get("temperature", 0))),
        "air_temp": float(payload.get("air_temp", payload.get("temperature", 0))),
        "air_humidity": float(payload.get("air_humidity", payload.get("humidity", 0))),
        "wind_speed": float(payload.get("wind_speed", 0)),
        "wind_gust": float(payload.get("wind_gust", 0)),
        "pressure": float(payload.get("pressure", 0)),
    }

    new_pump = predict_pump(normalized)
    last = get_last_row()
    prev_pump = int(last["pump_status"]) if last else -1

    if new_pump == prev_pump:
        return {
            "message": "No change — not saved",
            "pump_status": new_pump,
        }, 200

    duration = 0
    if new_pump == 0 and last and int(last.get("pump_status", 0)) == 1:
        duration = calc_duration(last.get("timestamp"))

    reason = build_reason(new_pump, normalized)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sensor_data
        (soil_moisture, temperature, humidity, pump_status, reason, duration_seconds, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized["soil_moisture"],
            normalized["temperature"],
            normalized["humidity"],
            new_pump,
            reason,
            duration,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "message": "Pump state changed — saved",
        "pump_status": new_pump,
        "reason": reason,
        "duration_seconds": duration,
    }, 200


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def landing():
    return render_template("index.html")


@app.route('/dashboard')
def dashboard():
    rows, latest = fetch_recent(20)
    return render_template("dashboard.html", data=rows, latest=latest)


@app.route('/api/recent')
def api_recent():
    limit = request.args.get("limit", "20")
    try:
        rows, latest = fetch_recent(int(limit))
    except Exception:
        rows, latest = fetch_recent(20)
    return jsonify({"rows": rows, "latest": latest})


@app.route('/update', methods=['POST'])
def update_data():
    payload = request.get_json(silent=True) or {}
    body, status = _handle_sensor_payload(payload)
    return jsonify(body), status


@app.route('/predict', methods=['POST'])
def predict_data():
    payload = request.get_json(silent=True) or {}
    body, status = _handle_sensor_payload(payload)

    if "pump_status" in body:
        return jsonify({"decision": int(body["pump_status"]), **body}), status
    return jsonify(body), status


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
