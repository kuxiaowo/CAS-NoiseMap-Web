#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WebServer.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11112222"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.241"
#define SERVER_PORT   9880

bool registered = false;                 // 是否已成功注册
unsigned long lastRegisterTry = 0;       // 上次尝试时间
const unsigned long REGISTER_INTERVAL = 3000; // 3 秒重试一次


/* ========================================= */

ESP8266WebServer server(8000);

float noise_value = 0.0;

/* --------- 模拟噪声（你以后换成真传感器） --------- */
float readNoise() {
  noise_value += 1.0;
  if (noise_value > 80) noise_value = 40;
  return noise_value;
}

/* ---------------- GET /noise ---------------- */
void handleNoise() {
  float noise = readNoise();

  String json = "{";
  json += "\"id\":" + String(DEVICE_ID) + ",";
  json += "\"noise\":" + String(noise, 1);
  json += "}";

  server.send(200, "application/json", json);
}

/* --------------- 向服务器注册 ---------------- */
bool registerToServer() {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient client;
  HTTPClient http;

  String url = "http://" + String(SERVER_IP) + ":" +
               String(SERVER_PORT) + "/api/register";

  String payload = "{";
  payload += "\"id\":" + String(DEVICE_ID) + ",";
  payload += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  payload += "}";

  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(payload);
  http.end();

  Serial.print("[REGISTER] HTTP code = ");
  Serial.println(code);

  return code == 200;
}



/* ================== SETUP ================== */
void setup() {
  Serial.begin(115200);
  delay(100);

  /* 连接 WiFi */
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());


  /* 启动 HTTP 服务 */
  server.on("/noise", HTTP_GET, handleNoise);
  server.begin();

  Serial.println("Noise server started");
}

/* ================== LOOP ================== */
void loop() {
  server.handleClient();

  // Wi-Fi 掉线：状态清零
  if (WiFi.status() != WL_CONNECTED) {
    registered = false;
    return;
  }

  // 还没注册成功：定时尝试
  if (!registered && millis() - lastRegisterTry > REGISTER_INTERVAL) {
    lastRegisterTry = millis();
    Serial.println("Trying to register to server...");
    registered = registerToServer();
  }
}

