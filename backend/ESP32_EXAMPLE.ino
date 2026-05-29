// ESP32 Smart Door — Production Code
// ====================================
// Flow:
//   1. Poll GET /api/command (every 2s) → execute action
//   2. Read ultrasonic sensors → POST /api/sensor/update
//   3. No flooding, proper connection handling

#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <WiFi.h>

// ===== CONFIGURATION =====
const char *WIFI_SSID = "YOUR_SSID";
const char *WIFI_PASSWORD = "YOUR_PASSWORD";
const char *BACKEND_URL = "http://192.168.X.X:8000";
const char *DEVICE_ID = "esp32-1";

// Timing (ms)
const unsigned long COMMAND_POLL_INTERVAL = 2000; // Poll commands every 2s
const unsigned long SENSOR_SEND_INTERVAL = 2000;  // Send sensor every 2s
const unsigned long WIFI_RECONNECT_DELAY = 5000;
const int HTTP_TIMEOUT = 5000;

// Servo
const int SERVO_PIN = 13;
const int SERVO_OPEN_ANGLE = 90;
const int SERVO_CLOSE_ANGLE = 0;

// Ultrasonic sensor 1 (outer - entry side)
const int TRIG_PIN_1 = 5;
const int ECHO_PIN_1 = 18;

// Ultrasonic sensor 2 (inner - room side)
const int TRIG_PIN_2 = 19;
const int ECHO_PIN_2 = 21;

// ===== STATE =====
Servo doorServo;
bool doorIsOpen = false;
unsigned long lastCommandPoll = 0;
unsigned long lastSensorSend = 0;

// ===== SETUP =====
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[SMART DOOR] Starting...");

  // Servo
  doorServo.attach(SERVO_PIN);
  doorServo.write(SERVO_CLOSE_ANGLE);
  doorIsOpen = false;

  // Ultrasonic pins
  pinMode(TRIG_PIN_1, OUTPUT);
  pinMode(ECHO_PIN_1, INPUT);
  pinMode(TRIG_PIN_2, OUTPUT);
  pinMode(ECHO_PIN_2, INPUT);

  // WiFi
  connectWiFi();
}

// ===== MAIN LOOP =====
void loop() {
  // Reconnect WiFi if needed
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Disconnected, reconnecting...");
    connectWiFi();
    return;
  }

  unsigned long now = millis();

  // 1. Poll commands from backend
  if (now - lastCommandPoll >= COMMAND_POLL_INTERVAL) {
    lastCommandPoll = now;
    pollCommand();
  }

  // 2. Read & send sensor data
  if (now - lastSensorSend >= SENSOR_SEND_INTERVAL) {
    lastSensorSend = now;
    readAndSendSensors();
  }

  delay(100); // Small delay to prevent CPU hogging
}

// ===== WiFi =====
void connectWiFi() {
  WiFi.disconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Connecting");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("[WiFi] Connected! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] FAILED. Retry in 5s...");
    delay(WIFI_RECONNECT_DELAY);
  }
}

// ===== POLL COMMAND =====
void pollCommand() {
  HTTPClient http;
  String url = String(BACKEND_URL) + "/api/command?device_id=" + DEVICE_ID;

  http.begin(url);
  http.setTimeout(HTTP_TIMEOUT);
  http.addHeader("Connection", "close"); // Prevent ECONNRESET

  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();

    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
      Serial.print("[CMD] JSON parse error: ");
      Serial.println(err.c_str());
      http.end();
      return;
    }

    const char *action = doc["action"];
    if (action != nullptr) {
      Serial.print("[CMD] Action: ");
      Serial.println(action);
      executeAction(String(action));
    }
  } else if (httpCode > 0) {
    Serial.print("[CMD] HTTP error: ");
    Serial.println(httpCode);
  } else {
    Serial.print("[CMD] Connection error: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

// ===== EXECUTE ACTION =====
void executeAction(String action) {
  if (action == "open_door") {
    if (!doorIsOpen) {
      Serial.println("[DOOR] Opening...");
      doorServo.write(SERVO_OPEN_ANGLE);
      doorIsOpen = true;
    } else {
      Serial.println("[DOOR] Already open, ignoring");
    }
  } else if (action == "close_door") {
    if (doorIsOpen) {
      Serial.println("[DOOR] Closing...");
      doorServo.write(SERVO_CLOSE_ANGLE);
      doorIsOpen = false;
    } else {
      Serial.println("[DOOR] Already closed, ignoring");
    }
  } else if (action == "enable") {
    Serial.println("[SYS] System enabled");
  } else if (action == "disable") {
    Serial.println("[SYS] System disabled");
  } else {
    Serial.print("[CMD] Unknown action: ");
    Serial.println(action);
  }
}

// ===== READ & SEND SENSORS =====
void readAndSendSensors() {
  float d1 = readUltrasonic(TRIG_PIN_1, ECHO_PIN_1);
  float d2 = readUltrasonic(TRIG_PIN_2, ECHO_PIN_2);

  // Send to backend
  HTTPClient http;
  String url = String(BACKEND_URL) + "/api/sensor/update";

  StaticJsonDocument<200> doc;
  doc["device_id"] = DEVICE_ID;
  doc["distance1"] = d1;
  doc["distance2"] = d2;

  String payload;
  serializeJson(doc, payload);

  http.begin(url);
  http.setTimeout(HTTP_TIMEOUT);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Connection", "close"); // Prevent ECONNRESET

  int httpCode = http.POST(payload);

  if (httpCode == 200) {
    String response = http.getString();

    // Check if backend detected entry/exit
    StaticJsonDocument<256> resDoc;
    if (deserializeJson(resDoc, response) == DeserializationError::Ok) {
      const char *event = resDoc["event"];
      if (event != nullptr) {
        Serial.print("[SENSOR] Backend event: ");
        Serial.println(event);
      }
    }
  } else if (httpCode > 0) {
    Serial.print("[SENSOR] HTTP error: ");
    Serial.println(httpCode);
  } else {
    Serial.print("[SENSOR] Connection error: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

// ===== READ ULTRASONIC SENSOR =====
float readUltrasonic(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000); // 30ms timeout

  if (duration == 0) {
    return 400.0; // Out of range
  }

  float distance = (duration * 0.034) / 2.0;

  // Clamp to valid range
  if (distance <= 0 || distance > 400) {
    return 400.0;
  }

  return distance;
}

// ===== NOTES =====
/*
FLOW:
  1. ESP polls GET /api/command → backend returns {action: "open_door"} or
{action: null}
  2. ESP reads sensors → POST /api/sensor/update → backend detects entry/exit
  3. Backend handles ALL logic (identity, cooldown, state machine)
  4. ESP just executes actions and reports sensor data

PREVENTING ECONNRESET:
  - Connection: close header on every request
  - 2 second minimum between requests
  - HTTP timeout set to 5 seconds
  - WiFi reconnect on disconnect

IMPORTANT:
  - Do NOT poll /api/access separately — /api/command includes access decision
  - Do NOT flood the backend — minimum 2s between requests
  - Backend is the brain, ESP is the muscle
*/
