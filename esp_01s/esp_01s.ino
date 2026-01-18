#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11112222"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.252"
#define SERVER_PORT   9880

#define MIC_PIN 14   // SD 接到 GPIO32

bool registered = false;                 // 是否已成功注册
unsigned long lastRegisterTry = 0;       // 上次尝试时间
unsigned long lastRequestTime = 0;       // 上次接收到请求的时间
const unsigned long REGISTER_INTERVAL = 3000; // 3 秒重试一次
const unsigned long REQUEST_TIMEOUT = 600000; // 10分钟没有请求后重新注册（600,000毫秒）

/* ========================================= */

WebServer server(8000);

float noise_value = 0.0;


float readNoise() {
  int adc = analogRead(MIC_PIN);   // 0 ~ 4095
  return (float)adc;
}

/* ---------------- GET /noise ---------------- */
void handleNoise() {
  float noise = readNoise();

  String json = "{";
  json += "\"id\":" + String(DEVICE_ID) + ",";
  json += "\"noise\":" + String(noise, 1);
  json += "}";

  server.send(200, "application/json", json);

  // 更新最后请求的时间
  lastRequestTime = millis();
}

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
    lastRequestTime = millis();   // ⭐ 关键：当作一次“已联系”
  } else {
    Serial.println("注册失败");
  }

  http.end();
}

/* ---------------- 重新注册 ---------------- */
void tryReRegister() {
  // 判断是否超过10分钟没有接收到请求
  if (millis() - lastRequestTime > REQUEST_TIMEOUT) {
    // 尝试重新注册
    if (millis() - lastRegisterTry > REGISTER_INTERVAL) {
      lastRegisterTry = millis();
      // 重新注册的操作，比如通过HTTP请求发送注册信息
      Serial.println("尝试重新注册...");
      registerToServer();
    }
  }
}

void setup() {
  Serial.begin(115200);

  analogReadResolution(12);              // ESP32 默认 12 位
  analogSetPinAttenuation(MIC_PIN, ADC_11db); // 量程到 ~3.3V
  // 连接到Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi连接成功!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  registerToServer();   // 一连上注册

  // 启动Web服务器
  server.on("/noise", HTTP_GET, handleNoise);
  server.begin();

  // 初始化时间
  lastRequestTime = millis();
}

void loop() {
  server.handleClient();

  // 检查是否需要重新注册
  tryReRegister();
}
