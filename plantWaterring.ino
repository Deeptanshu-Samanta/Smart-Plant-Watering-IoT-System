#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>

const char* ssid = "deeptanshu-samanta-Vostro-5625";
const char* password = "4lx9KYj5";
const char* serverName = "http://10.42.0.1:5000/predict";

/* Pins */
#define SOIL_PIN 34
#define RELAY_PIN 26
#define DHTPIN 4
#define DHTTYPE DHT22
#define ONE_WIRE_BUS 5

/* Sensor Objects */
DHT dht(DHTPIN, DHTTYPE);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

void setup() {

  Serial.begin(115200);

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);   // relay OFF (active LOW)

  dht.begin();
  ds18b20.begin();

  WiFi.begin(ssid, password);

  Serial.print("Connecting WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnected!");
}

void loop() {

  /* Read Soil Moisture */
  int soilRaw = analogRead(SOIL_PIN);
  float soilMoisture = map(soilRaw, 4095, 1500, 0, 100);

  /* Read DHT22 */
  float airTemp = dht.readTemperature();
  float airHumidity = dht.readHumidity();

  /* Read DS18B20 */
  ds18b20.requestTemperatures();
  float soilTemp = ds18b20.getTempCByIndex(0);

  Serial.println("------ SENSOR DATA ------");

  Serial.print("Soil Moisture: ");
  Serial.println(soilMoisture);

  Serial.print("Air Temp: ");
  Serial.println(airTemp);

  Serial.print("Air Humidity: ");
  Serial.println(airHumidity);

  Serial.print("Soil Temp: ");
  Serial.println(soilTemp);

  if (WiFi.status() == WL_CONNECTED) {

    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<256> doc;

    doc["soil_moisture"] = soilMoisture;
    doc["air_temp"] = airTemp;
    doc["air_humidity"] = airHumidity;
    doc["soil_temp"] = soilTemp;

    String body;
    serializeJson(doc, body);

    Serial.println("Sending Data:");
    Serial.println(body);

    int httpCode = http.POST(body);

    if (httpCode > 0) {

      String response = http.getString();

      Serial.println("Server Response:");
      Serial.println(response);

      StaticJsonDocument<128> resDoc;
      deserializeJson(resDoc, response);

      int decision = resDoc["decision"];

      if (decision == 1) {

        digitalWrite(RELAY_PIN, LOW);   // pump ON
        Serial.println("Pump ON");

      } else {

        digitalWrite(RELAY_PIN, HIGH);  // pump OFF
        Serial.println("Pump OFF");

      }

    } else {

      Serial.print("HTTP Error: ");
      Serial.println(httpCode);

    }

    http.end();
  }

  delay(20000);  // check every 20 seconds
}