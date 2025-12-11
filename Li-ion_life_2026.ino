#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "ESP_Wahaj.h"
#include <DHTesp.h>
#include <Adafruit_MCP3008.h>
#include <ACS712.h>

// ====== USER CONFIG ======
const char* WIFI_SSID = "Project";
const char* WIFI_PASS = "12345678";

// DHT
const int DHT_PIN = D0;
DHTesp dht;

// LCD
LiquidCrystal_I2C lcd(0x27, 16, 2);

// MCP3008 ADC
Adafruit_MCP3008 mcp;

// Voltage divider
const float R1 = 30000.0;
const float R2 = 7500.0;

// ACS712 Current Sensor
ACS712 acs(A0, 5, 1023, 185);

// Relay pins
#define RELAY1 D3
#define RELAY2 D4

// ====== SENSOR VARIABLES ======
float temp = 0, hum = 0, vin = 0, cur_mA = 0;

// ====== RELAY STATE ======
bool relay1Active = false;
bool relay2Active = false;
unsigned long relay1Start = 0;
unsigned long relay2Start = 0;
const unsigned long RELAY_ON_DURATION = 10000UL; // 10 seconds

// ====== /5 SEQUENCE VARIABLES ======
enum SeqState {
  SEQ_IDLE,
  SEQ_RUNNING
};
SeqState seqState = SEQ_IDLE;
float ch = 0;
float dh = 0;
unsigned long seqStart = 0;
bool inSeqRelay1 = true;

// ====== FUNCTIONS ======
void readSensors() {
  temp = dht.getTemperature();
  hum  = dht.getHumidity();

  int raw = mcp.readADC(0);
  float adcV = (raw * 5) / 1023.0;
  vin = adcV * (R1 + R2) / R2;

  cur_mA = acs.mA_DC();
}

void updateLCD() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(String(temp, 1) + "C " + String(hum, 0) + "%");
  lcd.setCursor(0, 1);
  lcd.print(String(vin, 2) + "V " + String(cur_mA / 1000.0, 2) + "A");
}

void handleRelayTimeout() {
  unsigned long now = millis();

  if (relay1Active && (now - relay1Start >= RELAY_ON_DURATION)) {
    digitalWrite(RELAY1, HIGH); // OFF (active LOW)
    relay1Active = false;
  }

  if (relay2Active && (now - relay2Start >= RELAY_ON_DURATION)) {
    digitalWrite(RELAY2, HIGH); // OFF (active LOW)
    relay2Active = false;
  }
}

// ====== SEQUENCE HANDLER FOR /5 ======
bool runSequenceFor5(String &responseStr) {
  unsigned long now = millis();
  readSensors();
  updateLCD();

  if (seqState == SEQ_RUNNING) {
    if (inSeqRelay1) {
      if (!relay1Active) {
        digitalWrite(RELAY1, LOW); // ON
        relay1Active = true;
        relay1Start = now;
        ch = 0;
      }
      ch += cur_mA;

      if (now - relay1Start >= RELAY_ON_DURATION) {
        digitalWrite(RELAY1, HIGH); // OFF
        relay1Active = false;
        inSeqRelay1 = false; // move to D4
        relay2Start = now;
        digitalWrite(RELAY2, LOW); // ON D4
        relay2Active = true;
        dh = 0;
      }
    }
    else {
      dh += cur_mA;

      if (now - relay2Start >= RELAY_ON_DURATION) {
        digitalWrite(RELAY2, HIGH); // OFF
        relay2Active = false;
        seqState = SEQ_IDLE;
        inSeqRelay1 = true;

        // Handle ch and dh null/negative range
        if (ch >= -140643.8 && ch <= -100008.6) ch = 0;
        else if (ch < 0) ch = -ch;

        if (dh >= -140643.8 && dh <= -100008.6) dh = 0;
        else if (dh < 0) dh = -dh;


    ch=ch/100;

  if(dh<100000)
{
  dh=0;
  }
  else{
    dh=dh/100;
    }
        // Prepare final response
        responseStr = String(vin, 2) + "," + String(ch, 1) + "," + String(dh, 1) + "," + String(temp, 1) + "," + String(hum, 0);
        return true; // sequence done
      }
    }
  }
  return false; // sequence not done
}

void handleRequest(String path) {
  if (path == "/status") {
    String payload = String(temp, 2) + "," + String(hum, 2) + "," + String(vin, 3) + "," + String(cur_mA, 1);
    returnThisStr(payload);
  }
  else if (path == "/1") {
    digitalWrite(RELAY1, LOW);
    relay1Active = true;
    relay1Start  = millis();
    digitalWrite(RELAY2, HIGH);
    relay2Active = false;
    returnThisStr("Relay1 ON (10s)");
  }
  else if (path == "/2") {
    digitalWrite(RELAY2, LOW);
    relay2Active = true;
    relay2Start  = millis();
    digitalWrite(RELAY1, HIGH);
    relay1Active = false;
    returnThisStr("Relay2 ON (10s)");
  }
  else if (path == "/3") {
    digitalWrite(RELAY1, HIGH);
    digitalWrite(RELAY2, HIGH);
    relay1Active = false;
    relay2Active = false;
    returnThisStr("All OFF");
  }
  else if (path == "/5") {
    seqState = SEQ_RUNNING;
    inSeqRelay1 = true;
    String result = "";
    // Wait until sequence finishes
    while (!runSequenceFor5(result)) {
      yield(); // allow WiFi and other tasks to run
    }
    returnThisStr(result);
  }
  else {
    returnThisStr("Use /status, /1, /2, /3, /5");
  }
}

// ====== SETUP ======
void setup() {
  Serial.begin(115200);

  pinMode(RELAY1, OUTPUT);
  pinMode(RELAY2, OUTPUT);
  digitalWrite(RELAY1, HIGH);
  digitalWrite(RELAY2, HIGH);

  dht.setup(DHT_PIN, DHTesp::DHT11);
  acs.autoMidPoint();

  mcp.begin();

  lcd.begin(); // Changed as per request
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Connecting...");

  start(WIFI_SSID, WIFI_PASS);
  lcd.clear();
  lcd.print("WiFi Connected");
  delay(1000);
}

// ====== LOOP ======
unsigned long lastSensorRead = 0;
const unsigned long SENSOR_INTERVAL = 500;

void loop() {
  // Handle HTTP requests
  if (CheckNewReq()) {
    handleRequest(getPath());
  }

  // Update sensors periodically
  if (millis() - lastSensorRead >= SENSOR_INTERVAL) {
    lastSensorRead = millis();
    readSensors();
    updateLCD();
  }

  // Handle relay auto-off for /1 or /2
  handleRelayTimeout();
}
