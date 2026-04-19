#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11112222"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.252"
#define SERVER_PORT   9880

#define MIC_PIN 14        // MAX4466 模拟麦克风接入引脚（ADC）

#define SAMPLE_COUNT 200  // 每次读取的采样点数
#define SAMPLE_DELAY_US 200  // 采样间隔（us）

bool registered = false;
unsigned long lastRegisterTry = 0;
unsigned long lastRequestTime = 0;
const unsigned long REGISTER_INTERVAL = 3000;
const unsigned long REQUEST_TIMEOUT = 600000;

/* ========================================= */

WebServer server(8000);

/* ============ 噪音采集 - 计算 RMS ============ */

/**
 * 从 MAX4466 读取模拟信号并计算 RMS
 * 返回：原始 RMS 值（不做 log10 转换，由后端处理）
 */
float calculateRMS() {
  long sum = 0;

  // 1️⃣ 先估计直流偏置（麦克风中点）
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    sum += analogRead(MIC_PIN);
    delayMicroseconds(SAMPLE_DELAY_US);
  }
  float dc = sum / (float)SAMPLE_COUNT;

  // 2️⃣ 计算 RMS（AC 分量）
  float sqSum = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    float v = analogRead(MIC_PIN) - dc;
    sqSum += v * v;
    delayMicroseconds(SAMPLE_DELAY_US);
  }

  float rms = sqrt(sqSum / SAMPLE_COUNT);

  return rms;
}

/* ---------------- GET /noise ---------------- */

void handleNoise() {
  float rms = calculateRMS();
  
  String json = "{";
  json += "\"id\":" + String(DEVICE_ID) + ",";
  json += "\"rms\":" + String(rms, 2);  // 保留 2 位小数
  json += "}";
  
  server.send(200, "application/json", json);
  
  lastRequestTime = millis();
  Serial.print("RMS: ");
  Serial.println(rms, 2);
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
  delay(1000);
  
  Serial.println("\n=== ESP32-MAX4466 模拟麦克风初始化 ===");

  // 配置 ADC
  analogReadResolution(12);
  analogSetPinAttenuation(MIC_PIN, ADC_11db);
  Serial.println("ADC 初始化完成");

  // 连接 WiFi
  Serial.println("正在连接 WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED && timeout < 20) {
    delay(500);
    Serial.print(".");
    timeout++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi 连接成功!");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi 连接失败");
  }

  registerToServer();

  server.on("/noise", HTTP_GET, handleNoise);
  server.begin();
  
  Serial.println("Web 服务器已启动 (port 8000)");
  Serial.println("=== 初始化完成 ===\n");

  lastRequestTime = millis();
}

/* =================== loop =================== */

void loop() {
  server.handleClient();
  tryReRegister();
  delay(10);
}
