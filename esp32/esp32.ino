#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11112222"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.252"
#define SERVER_PORT   9880

#define MIC_PIN 14        // 模拟麦克风接入引脚（ADC）

#define SAMPLE_COUNT 200  // 每次读取的采样点数
#define SAMPLE_DELAY_US 200  // 采样间隔（us）

bool registered = false;
unsigned long lastRegisterTry = 0;
unsigned long lastRequestTime = 0;
const unsigned long REGISTER_INTERVAL = 3000;
const unsigned long REQUEST_TIMEOUT = 600000;

/* ========================================= */

WebServer server(8000);

/* ============ 噪音采集 & 强度计算 ============ */

/**
 * 读取一段时间内的噪音强度（RMS + 对数压缩）
 * 返回：相对噪音强度值（伪 dB）
 */
float readNoise() {
  long sum = 0;

  // 1️⃣ 先估计直流偏置（麦克风中点）
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    sum += analogRead(MIC_PIN);
    delayMicroseconds(SAMPLE_DELAY_US);
  }
  float dc = sum / (float)SAMPLE_COUNT;

  // 2️⃣ 计算 RMS
  float sqSum = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    float v = analogRead(MIC_PIN) - dc;
    sqSum += v * v;
    delayMicroseconds(SAMPLE_DELAY_US);
  }

  float rms = sqrt(sqSum / SAMPLE_COUNT);

  // 3️⃣ 映射到对数刻度（相对分贝）
  float intensity = 20.0 * log10(rms + 1.0);

  return intensity;
}

/* ---------------- GET /noise ---------------- */

void handleNoise() {
  float noise = readNoise();

  String json = "{";
  json += "\"id\":" + String(DEVICE_ID) + ",";
  json += "\"noise\":" + String(noise, 1);
  json += "}";

  server.send(200, "application/json", json);

  lastRequestTime = millis();
}

/* ---------------- 注册到服务器 ---------------- */

void registerToServer() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/api/register";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"id\":" + String(DEVICE_ID) + ",";
  payload += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  payload += "}";

  int code = http.POST(payload);

  if (code > 0) {
    Serial.println("已向服务器注册");
    registered = true;
    lastRequestTime = millis();
  } else {
    Serial.println("注册失败");
  }

  http.end();
}

/* ---------------- 重新注册 ---------------- */

void tryReRegister() {
  if (millis() - lastRequestTime > REQUEST_TIMEOUT) {
    if (millis() - lastRegisterTry > REGISTER_INTERVAL) {
      lastRegisterTry = millis();
      Serial.println("尝试重新注册...");
      registerToServer();
    }
  }
}

/* ================== setup ================== */

void setup() {
  Serial.begin(115200);

  analogReadResolution(12);
  analogSetPinAttenuation(MIC_PIN, ADC_11db);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi连接成功!");
  Serial.println(WiFi.localIP());

  registerToServer();

  server.on("/noise", HTTP_GET, handleNoise);
  server.begin();

  lastRequestTime = millis();
}

/* =================== loop =================== */

void loop() {
  server.handleClient();
  tryReRegister();
}
