#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* ssid = "deeptanshu-samanta-Vostro-5625";
const char* password = "4lx9KYj5";
const char* serverName = "http://10.42.0.1:5000/predict";

#define SOIL_PIN 34
#define RELAY_PIN 26

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("Connected!");
}

void loop() {

  int soilRaw = analogRead(SOIL_PIN);
  float soilMoisture = map(soilRaw, 4095, 1500, 0, 100);

  if (WiFi.status() == WL_CONNECTED) {

    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<128> doc;
    doc["soil_moisture"] = soilMoisture;

    String body;
    serializeJson(doc, body);

    int httpCode = http.POST(body);

    if (httpCode > 0) {
      String response = http.getString();
      StaticJsonDocument<128> resDoc;
      deserializeJson(resDoc, response);

      int decision = resDoc["decision"];

      if (decision == 1) {
        digitalWrite(RELAY_PIN, LOW);
        Serial.println("Pump ON");
      } else {
        digitalWrite(RELAY_PIN, HIGH);
        Serial.println("Pump OFF");
      }
    }

    http.end();
  }

  delay(20000);  // check every 20 sec
}