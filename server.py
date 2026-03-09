from flask import Flask, request, jsonify
import joblib
import requests
from datetime import datetime

app = Flask(__name__)

# Load ML models
model_rf = joblib.load("randomForest_plantWater.pkl")
model_lr = joblib.load("logistic_plantWater.pkl")

# Weather API config
API_KEY = "KEY" //Enter your own key here
CITY = "Kelambakkam"


def get_weather():
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={API_KEY}&q={CITY}"
        res = requests.get(url).json()

        weather = {
            "pressure": res["current"]["pressure_mb"] / 10,
            "wind_speed": res["current"]["wind_kph"],
            "wind_gust": res["current"]["gust_kph"]
        }

        return weather

    except Exception as e:
        print("Weather API error:", e)

        # fallback values
        return {
            "air_temp": 30,
            "air_humidity": 60,
            "pressure": 101,
            "wind_speed": 5,
            "wind_gust": 7
        }


def decide(data):

    input_data = [[
        data["soil_moisture"],
        data["soil_temp"],
        data["air_humidity"],
        datetime.now().hour,
        data["air_temp"],
        data["wind_speed"],
        data["air_humidity"],
        data["wind_gust"],
        data["pressure"]
    ]]

    rf = model_rf.predict(input_data)[0]
    lr = model_lr.predict(input_data)[0]

    # safety rules
    if data["soil_moisture"] < 20:
        return 1

    if data["soil_moisture"] > 70:
        return 0

    if datetime.now().hour < 5 or datetime.now().hour > 20:
        return 0

    return int(rf or lr)


@app.route("/predict", methods=["POST"])
def predict():

    esp_data = request.json

    print("\nReceived from ESP32:", esp_data)

    weather = get_weather()

    combined = {**esp_data, **weather}

    print("Combined Data:", combined)

    decision = decide(combined)

    print("Decision:", decision)

    return jsonify({"decision": decision})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
