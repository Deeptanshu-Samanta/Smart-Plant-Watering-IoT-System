from flask import Flask, request, jsonify, render_template
import sqlite3
import datetime

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="/assets")

# Create database
def init_db():
    conn = sqlite3.connect("plant_data.db")
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
    conn = sqlite3.connect("plant_data.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    latest = rows[0] if rows else None
    return rows, latest

# Landing page
@app.route('/')
def landing():
    return render_template("index.html")

# Receive sensor data (API)
@app.route('/update', methods=['POST'])
def update_data():
    data = request.get_json(silent=True) or {}
    required = ("soil_moisture", "temperature", "humidity", "pump_status")
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing keys: {', '.join(missing)}"}), 400

    conn = sqlite3.connect("plant_data.db")
    c = conn.cursor()
    c.execute("INSERT INTO sensor_data (soil_moisture, temperature, humidity, pump_status, timestamp) VALUES (?, ?, ?, ?, ?)",
              (data["soil_moisture"], data["temperature"],
               data["humidity"], data["pump_status"],
               datetime.datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

    return jsonify({"message": "Data saved"})

# Recent data (API)
@app.route('/api/recent')
def api_recent():
    limit = request.args.get("limit", "20")
    try:
        rows, latest = fetch_recent(int(limit))
    except Exception:
        rows, latest = fetch_recent(20)
    return jsonify({"rows": rows, "latest": latest})

# Dashboard page
@app.route('/dashboard')
def dashboard():
    rows, latest = fetch_recent(20)
    return render_template("dashboard.html", data=rows, latest=latest)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)