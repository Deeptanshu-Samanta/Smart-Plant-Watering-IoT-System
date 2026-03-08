from flask import Flask, request, jsonify
import joblib
import requests
from datetime import datetime

app = Flask(__name__)

# Load models
model2 = joblib.load("randomForest_plantWater.pkl")
model1 = joblib.load("logistic_plantWater.pkl")

API_KEY = "75d10256f63449e9bd7115124260102"
CITY = "Kelambakkam"


def get_weather():
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={API_KEY}&q={CITY}"
        response = requests.get(url, timeout=5)
        data = response.json()

        return {
            "air_temp": float(data["current"]["temp_c"]),
            "air_humidity": float(data["current"]["humidity"]),
            "pressure": float(data["current"]["pressure_mb"]) / 10,
            "wind_speed": float(data["current"]["wind_kph"]),
            "wind_gust": float(data["current"]["gust_kph"])
        }

    except Exception as e:
        print("Weather API Error:", e)
        return {
            "air_temp": 30.0,
            "air_humidity": 50.0,
            "pressure": 101.0,
            "wind_speed": 5.0,
            "wind_gust": 8.0
        }


def decide(data):
    input_data = [[
        float(data["soil_moisture"]),
        30.0,  # placeholder soil temp
        float(data["soil_moisture"]),
        float(datetime.now().hour),
        float(data["air_temp"]),
        float(data["wind_speed"]),
        float(data["air_humidity"]),
        float(data["wind_gust"]),
        float(data["pressure"])
    ]]

    rf = model2.predict(input_data)[0]
    lr = model1.predict(input_data)[0]

    # Rule-based overrides (very important)
    if data["soil_moisture"] < 20 and data["air_humidity"] < 30:
        return 1

    if data["soil_moisture"] > 65:
        return 0

    if datetime.now().hour < 5 or datetime.now().hour > 20:
        return 0

    return int(rf or lr)


@app.route("/predict", methods=["POST"])
def predict():
    soil_data = request.get_json()

    if not soil_data or "soil_moisture" not in soil_data:
        return jsonify({"error": "Invalid data"}), 400

    print("Received from ESP32:", soil_data)

    weather = get_weather()
    combined = {**soil_data, **weather}

    decision = decide(combined)

    print("Final Input:", combined)
    print("Decision:", decision)

    return jsonify({"decision": int(decision)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)