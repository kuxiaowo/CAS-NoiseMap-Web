#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <driver/i2s.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11110000"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.252"
#define SERVER_PORT   9880
#define ADMIN_PASSWORD "187geufo"

#define STR_HELPER(x) #x
#define STR(x) STR_HELPER(x)
#define CONFIG_SIGNATURE WIFI_SSID "|" WIFI_PASS "|" SERVER_IP "|" STR(SERVER_PORT) "|" STR(DEVICE_ID)

/* INMP441 数字麦克风引脚配置 */
#define I2S_WS  4    // Word Select (LRCLK)
#define I2S_SD  2    // Serial Data (DOUT)
#define I2S_SCK 15   // Serial Clock (BCLK)

#define SAMPLE_COUNT 200  // 每次读取的采样点数
#define SAMPLE_RATE 16000 // 采样率（Hz）

bool registered = false;
unsigned long lastRegisterTry = 0;
unsigned long lastRequestTime = 0;
const unsigned long REGISTER_RETRY_INTERVAL = 3000;
const unsigned long REQUEST_TIMEOUT = 600000;

Preferences preferences;
String wifiSsid = WIFI_SSID;
String wifiPass = WIFI_PASS;
String serverIp = SERVER_IP;
int serverPort = SERVER_PORT;
int deviceId = DEVICE_ID;

struct AcousticFrame {
  float raw_rms;
  int sample_min;
  int sample_max;
};

/* ========================================= */

WebServer server(8000);

bool checkAdminAuth() {
  if (!server.hasArg("password") || server.arg("password") != ADMIN_PASSWORD) {
    server.send(403, "application/json", "{\"error\":\"forbidden\"}");
    return false;
  }
  return true;
}

String jsonEscape(const String& input) {
  String out;
  out.reserve(input.length() + 8);
  for (size_t i = 0; i < input.length(); ++i) {
    char c = input[i];
    if (c == '\\' || c == '"') {
      out += '\\';
    }
    out += c;
  }
  return out;
}

void loadConfig() {
  preferences.begin("casnoise", false);

  String storedSignature = preferences.getString("cfg_sig", "");
  if (storedSignature != String(CONFIG_SIGNATURE)) {
    wifiSsid = WIFI_SSID;
    wifiPass = WIFI_PASS;
    serverIp = SERVER_IP;
    serverPort = SERVER_PORT;
    deviceId = DEVICE_ID;

    preferences.putString("wifi_ssid", wifiSsid);
    preferences.putString("wifi_pass", wifiPass);
    preferences.putString("server_ip", serverIp);
    preferences.putInt("server_port", serverPort);
    preferences.putInt("device_id", deviceId);
    preferences.putString("cfg_sig", CONFIG_SIGNATURE);

    Serial.println("检测到新固件默认配置，已用代码配置覆盖已保存配置");
  } else {
    wifiSsid = preferences.getString("wifi_ssid", WIFI_SSID);
    wifiPass = preferences.getString("wifi_pass", WIFI_PASS);
    serverIp = preferences.getString("server_ip", SERVER_IP);
    serverPort = preferences.getInt("server_port", SERVER_PORT);
    deviceId = preferences.getInt("device_id", DEVICE_ID);
  }

  preferences.end();
}

void saveConfig() {
  preferences.begin("casnoise", false);
  preferences.putString("wifi_ssid", wifiSsid);
  preferences.putString("wifi_pass", wifiPass);
  preferences.putString("server_ip", serverIp);
  preferences.putInt("server_port", serverPort);
  preferences.putInt("device_id", deviceId);
  preferences.putString("cfg_sig", CONFIG_SIGNATURE);
  preferences.end();
}

void handleGetConfig() {
  if (!checkAdminAuth()) return;

  String json = "{";
  json += "\"wifi_ssid\":\"" + jsonEscape(wifiSsid) + "\",";
  json += "\"wifi_pass\":\"" + jsonEscape(wifiPass) + "\",";
  json += "\"server_ip\":\"" + jsonEscape(serverIp) + "\",";
  json += "\"server_port\":" + String(serverPort) + ",";
  json += "\"device_id\":" + String(deviceId) + ",";
  json += "\"local_ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";
  server.send(200, "application/json", json);
}

void handleSetConfig() {
  if (!checkAdminAuth()) return;

  bool changed = false;

  if (server.hasArg("wifi_ssid")) {
    wifiSsid = server.arg("wifi_ssid");
    changed = true;
  }
  if (server.hasArg("wifi_pass")) {
    wifiPass = server.arg("wifi_pass");
    changed = true;
  }
  if (server.hasArg("server_ip")) {
    serverIp = server.arg("server_ip");
    changed = true;
  }
  if (server.hasArg("server_port")) {
    int value = server.arg("server_port").toInt();
    if (value > 0 && value <= 65535) {
      serverPort = value;
      changed = true;
    }
  }
  if (server.hasArg("device_id")) {
    int value = server.arg("device_id").toInt();
    if (value >= 0 && value <= 100) {
      deviceId = value;
      changed = true;
    }
  }

  if (!changed) {
    server.send(400, "application/json", "{\"error\":\"no valid config provided\"}");
    return;
  }

  saveConfig();
  registered = false;
  server.send(200, "application/json", "{\"status\":\"ok\",\"message\":\"config saved, rebooting\"}");
  delay(500);
  ESP.restart();
}

void handleAdminPage() {
  if (!checkAdminAuth()) return;

  String html = R"HTML(
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CAS ESP 管理页</title>
<style>
body{font-family:Arial,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;background:#0b1220;color:#eef2ff}
.card{background:#131c2f;border:1px solid #2a3858;border-radius:16px;padding:20px}
label{display:block;margin-top:12px;margin-bottom:6px}
input{width:100%;padding:10px;border-radius:10px;border:1px solid #405179;background:#0f1729;color:#fff}
button{margin-top:16px;padding:10px 14px;border:0;border-radius:10px;background:#4f46e5;color:#fff;font-weight:700}
small{color:#b7c2e1}
</style></head><body>
<div class="card"><h2>CAS ESP 管理页</h2>
<form method="POST" action="/config">
<input type="hidden" name="password" value=")HTML";
  html += ADMIN_PASSWORD;
  html += R"HTML(">
<label>WiFi SSID</label><input name="wifi_ssid" value=")HTML";
  html += jsonEscape(wifiSsid);
  html += R"HTML(">
<label>WiFi 密码</label><input name="wifi_pass" value=")HTML";
  html += jsonEscape(wifiPass);
  html += R"HTML(">
<label>服务器 IP</label><input name="server_ip" value=")HTML";
  html += jsonEscape(serverIp);
  html += R"HTML(">
<label>服务器端口</label><input name="server_port" value=")HTML";
  html += String(serverPort);
  html += R"HTML(">
<label>设备 ID</label><input name="device_id" value=")HTML";
  html += String(deviceId);
  html += R"HTML(">
<button type="submit">保存并重启</button></form>
<p><small>访问方式: http://设备IP/admin?password=187geufo</small></p>
</div></body></html>
)HTML";

  server.send(200, "text/html; charset=utf-8", html);
}

/* ============ I2S 初始化 ============ */

void initI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = (i2s_comm_format_t)(I2S_COMM_FORMAT_I2S | I2S_COMM_FORMAT_I2S_MSB),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 64,
    .use_apll = false,
  };

  if (i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL) != ESP_OK) {
    Serial.println("I2S 驱动安装失败");
    return;
  }

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = -1,
    .data_in_num = I2S_SD,
  };

  if (i2s_set_pin(I2S_NUM_0, &pin_config) != ESP_OK) {
    Serial.println("I2S 引脚配置失败");
    return;
  }

  Serial.println("I2S 初始化成功");
}

AcousticFrame acquireAcousticFrame() {
  float sqSum = 0.0;
  size_t bytes_read = 0;
  uint8_t i2s_data[SAMPLE_COUNT * 2];

  if (i2s_read(I2S_NUM_0, i2s_data, SAMPLE_COUNT * 2, &bytes_read, 100) != ESP_OK) {
    Serial.println("I2S 读取失败");
    return {0.0f, 0, 0};
  }

  int sampleMin = 32767;
  int sampleMax = -32768;

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    int16_t sample = (int16_t)((i2s_data[i * 2 + 1] << 8) | i2s_data[i * 2]);
    if (sample < sampleMin) sampleMin = sample;
    if (sample > sampleMax) sampleMax = sample;
    sqSum += (float)sample * (float)sample;
  }

  float rawRms = sqrt(sqSum / SAMPLE_COUNT);
  return {rawRms, sampleMin, sampleMax};
}

void handleNoise() {
  AcousticFrame frame = acquireAcousticFrame();

  String json = "{";
  json += "\"id\":" + String(deviceId) + ",";
  json += "\"raw_rms\":" + String(frame.raw_rms, 2) + ",";
  json += "\"sample_min\":" + String(frame.sample_min) + ",";
  json += "\"sample_max\":" + String(frame.sample_max);
  json += "}";

  server.send(200, "application/json", json);

  lastRequestTime = millis();
  Serial.printf("RAW_RMS: %.2f min=%d max=%d\n", frame.raw_rms, frame.sample_min, frame.sample_max);
}

void connectWiFiUntilSuccess() {
  WiFi.mode(WIFI_STA);

  while (WiFi.status() != WL_CONNECTED) {
    Serial.printf("正在连接 WiFi: %s\n", wifiSsid.c_str());
    WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());

    int dots = 0;
    while (WiFi.status() != WL_CONNECTED && dots < 20) {
      delay(500);
      Serial.print(".");
      dots++;
    }

    if (WiFi.status() == WL_CONNECTED) {
      break;
    }

    Serial.println("\n本轮 WiFi 连接失败，3 秒后重试...");
    WiFi.disconnect(true, true);
    delay(3000);
  }

  Serial.println("\nWiFi 连接成功!");
  Serial.println(WiFi.localIP());
}

void registerToServer() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String("http://") + serverIp + ":" + serverPort + "/api/register";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"id\":" + String(deviceId) + ",";
  payload += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  payload += "}";

  int code = http.POST(payload);

  if (code > 0) {
    Serial.println("已向服务器注册");
    registered = true;
    lastRequestTime = millis();
  } else {
    String reason = http.errorToString(code);
    Serial.printf("注册失败, url=%s, code=%d, reason=%s\n", url.c_str(), code, reason.c_str());
    registered = false;
  }

  http.end();
}

void tryReRegister() {
  unsigned long now = millis();

  if (!registered) {
    if (now - lastRegisterTry > REGISTER_RETRY_INTERVAL) {
      lastRegisterTry = now;
      Serial.println("设备尚未注册，正在重试注册...");
      registerToServer();
    }
    return;
  }

  if (now - lastRequestTime > REQUEST_TIMEOUT) {
    if (now - lastRegisterTry > REGISTER_RETRY_INTERVAL) {
      lastRegisterTry = now;
      Serial.println("长时间未收到请求，尝试重新注册...");
      registerToServer();
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=== ESP32-I2S INMP441 初始化 ===");

  initI2S();
  loadConfig();
  connectWiFiUntilSuccess();

  lastRegisterTry = millis();
  registerToServer();

  server.on("/noise", HTTP_GET, handleNoise);
  server.on("/config", HTTP_GET, handleGetConfig);
  server.on("/config", HTTP_POST, handleSetConfig);
  server.on("/admin", HTTP_GET, handleAdminPage);
  server.begin();

  Serial.println("Web 服务器已启动 (port 8000)");
  Serial.println("管理页: /admin?password=187geufo");
  Serial.println("=== 初始化完成 ===\n");

  lastRequestTime = millis();
}

void loop() {
  server.handleClient();
  tryReRegister();
  delay(10);
}
