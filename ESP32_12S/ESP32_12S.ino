#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <driver/i2s.h>
#include <math.h>

#define DEFAULT_WIFI_SSID "CMCC-iAGE"
#define DEFAULT_WIFI_PASS "NCFD9522"
#define DEFAULT_SERVER_IP "192.168.1.20"
#define DEFAULT_SERVER_PORT 9880
#define DEFAULT_DEVICE_ID 1
#define DEFAULT_REPORT_INTERVAL_MS 1000
#define ADMIN_PASSWORD "187geufo"

#define STR_HELPER(x) #x
#define STR(x) STR_HELPER(x)
#define CONFIG_SIGNATURE DEFAULT_WIFI_SSID "|" DEFAULT_WIFI_PASS "|" DEFAULT_SERVER_IP "|" STR(DEFAULT_SERVER_PORT) "|" STR(DEFAULT_DEVICE_ID) "|" STR(DEFAULT_REPORT_INTERVAL_MS)

#define I2S_WS 4
#define I2S_SD 2
#define I2S_SCK 15

#define SAMPLE_COUNT 200
#define SAMPLE_RATE 16000
#define WIFI_RETRY_GAP_MS 3000
#define WIFI_CONNECT_WINDOW_MS 15000
#define REMOTE_SYNC_INTERVAL_MS 5000
#define HTTP_CONNECT_TIMEOUT_MS 1500
#define HTTP_RESPONSE_TIMEOUT_MS 2500
#define MIN_REPORT_INTERVAL_MS 200
#define MAX_REPORT_INTERVAL_MS 60000

struct AcousticFrame {
  float raw_rms;
  int sample_min;
  int sample_max;
};

Preferences preferences;
WebServer server(80);
TaskHandle_t webTaskHandle = nullptr;
TaskHandle_t networkTaskHandle = nullptr;

String wifiSsid = DEFAULT_WIFI_SSID;
String wifiPass = DEFAULT_WIFI_PASS;
String serverIp = DEFAULT_SERVER_IP;
int serverPort = DEFAULT_SERVER_PORT;
int deviceId = DEFAULT_DEVICE_ID;
unsigned long localReportIntervalMs = DEFAULT_REPORT_INTERVAL_MS;
unsigned long effectiveReportIntervalMs = DEFAULT_REPORT_INTERVAL_MS;
bool deviceEnabled = true;

unsigned long lastUploadAt = 0;
unsigned long lastRemoteSyncAt = 0;
unsigned long lastWifiAttemptAt = 0;
String lastBackendMessage = "尚未上传";

String jsonEscape(const String& input) {
  String out;
  out.reserve(input.length() + 8);
  for (size_t i = 0; i < input.length(); ++i) {
    char c = input[i];
    if (c == '\\' || c == '"') out += '\\';
    out += c;
  }
  return out;
}

String httpBase() {
  return String("http://") + serverIp + ":" + String(serverPort);
}

bool checkAdminAuth() {
  if (!server.hasArg("password") || server.arg("password") != ADMIN_PASSWORD) {
    server.send(403, "application/json", "{\"error\":\"forbidden\"}");
    return false;
  }
  return true;
}

void loadConfig() {
  preferences.begin("casnoise", false);

  String storedSignature = preferences.getString("cfg_sig", "");
  if (storedSignature != String(CONFIG_SIGNATURE)) {
    wifiSsid = DEFAULT_WIFI_SSID;
    wifiPass = DEFAULT_WIFI_PASS;
    serverIp = DEFAULT_SERVER_IP;
    serverPort = DEFAULT_SERVER_PORT;
    deviceId = DEFAULT_DEVICE_ID;
    localReportIntervalMs = DEFAULT_REPORT_INTERVAL_MS;

    preferences.putString("wifi_ssid", wifiSsid);
    preferences.putString("wifi_pass", wifiPass);
    preferences.putString("server_ip", serverIp);
    preferences.putInt("server_port", serverPort);
    preferences.putInt("device_id", deviceId);
    preferences.putULong("report_ms", localReportIntervalMs);
    preferences.putString("cfg_sig", CONFIG_SIGNATURE);

    Serial.println("检测到固件默认配置变化，已用代码默认值覆盖旧保存配置");
  } else {
    wifiSsid = preferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
    wifiPass = preferences.getString("wifi_pass", DEFAULT_WIFI_PASS);
    serverIp = preferences.getString("server_ip", DEFAULT_SERVER_IP);
    serverPort = preferences.getInt("server_port", DEFAULT_SERVER_PORT);
    deviceId = preferences.getInt("device_id", DEFAULT_DEVICE_ID);
    localReportIntervalMs = preferences.getULong("report_ms", DEFAULT_REPORT_INTERVAL_MS);
  }
  preferences.end();

  if (localReportIntervalMs < MIN_REPORT_INTERVAL_MS) localReportIntervalMs = MIN_REPORT_INTERVAL_MS;
  if (localReportIntervalMs > MAX_REPORT_INTERVAL_MS) localReportIntervalMs = MAX_REPORT_INTERVAL_MS;
  effectiveReportIntervalMs = localReportIntervalMs;
}

void saveConfig() {
  preferences.begin("casnoise", false);
  preferences.putString("wifi_ssid", wifiSsid);
  preferences.putString("wifi_pass", wifiPass);
  preferences.putString("server_ip", serverIp);
  preferences.putInt("server_port", serverPort);
  preferences.putInt("device_id", deviceId);
  preferences.putULong("report_ms", localReportIntervalMs);
  preferences.putString("cfg_sig", CONFIG_SIGNATURE);
  preferences.end();
}

long extractJsonLong(const String& body, const String& key, long fallbackValue) {
  String marker = "\"" + key + "\":";
  int start = body.indexOf(marker);
  if (start < 0) return fallbackValue;
  start += marker.length();
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '\n')) start++;
  int end = start;
  while (end < (int)body.length()) {
    char c = body[end];
    if ((c >= '0' && c <= '9') || c == '-') {
      end++;
      continue;
    }
    break;
  }
  if (end == start) return fallbackValue;
  return body.substring(start, end).toInt();
}

bool extractJsonBool(const String& body, const String& key, bool fallbackValue) {
  String marker = "\"" + key + "\":";
  int start = body.indexOf(marker);
  if (start < 0) return fallbackValue;
  start += marker.length();
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '\n')) start++;
  if (body.startsWith("true", start)) return true;
  if (body.startsWith("false", start)) return false;
  return fallbackValue;
}

String extractJsonString(const String& body, const String& key, const String& fallbackValue) {
  String marker = "\"" + key + "\":\"";
  int start = body.indexOf(marker);
  if (start < 0) return fallbackValue;
  start += marker.length();
  int end = start;
  while (end < (int)body.length()) {
    if (body[end] == '"' && body[end - 1] != '\\') break;
    end++;
  }
  if (end <= start) return fallbackValue;
  return body.substring(start, end);
}

void applyRemoteConfig(const String& body) {
  deviceEnabled = extractJsonBool(body, "enabled", deviceEnabled);
  long remoteInterval = extractJsonLong(body, "report_interval_ms", (long)effectiveReportIntervalMs);
  if (remoteInterval < MIN_REPORT_INTERVAL_MS) remoteInterval = MIN_REPORT_INTERVAL_MS;
  if (remoteInterval > MAX_REPORT_INTERVAL_MS) remoteInterval = MAX_REPORT_INTERVAL_MS;
  effectiveReportIntervalMs = (unsigned long)remoteInterval;

  long remoteId = extractJsonLong(body, "id", deviceId);
  if (remoteId >= 0 && remoteId <= 100) deviceId = (int)remoteId;
}

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

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = -1,
    .data_in_num = I2S_SD,
  };

  i2s_set_pin(I2S_NUM_0, &pin_config);
}

AcousticFrame acquireAcousticFrame() {
  float sqSum = 0.0;
  size_t bytesRead = 0;
  uint8_t i2sData[SAMPLE_COUNT * 2];

  if (i2s_read(I2S_NUM_0, i2sData, SAMPLE_COUNT * 2, &bytesRead, 100) != ESP_OK) {
    return {0.0f, 0, 0};
  }

  int sampleMin = 32767;
  int sampleMax = -32768;

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    int16_t sample = (int16_t)((i2sData[i * 2 + 1] << 8) | i2sData[i * 2]);
    if (sample < sampleMin) sampleMin = sample;
    if (sample > sampleMax) sampleMax = sample;
    sqSum += (float)sample * (float)sample;
  }

  float rawRms = sqrt(sqSum / SAMPLE_COUNT);
  return {rawRms, sampleMin, sampleMax};
}

void connectWiFiUntilSuccess() {
  WiFi.persistent(false);
  WiFi.setSleep(false);

  while (WiFi.status() != WL_CONNECTED) {
    Serial.printf("正在连接 WiFi: %s\n", wifiSsid.c_str());
    WiFi.disconnect(true, true);
    delay(500);
    WiFi.mode(WIFI_STA);
    delay(200);
    WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());

    unsigned long start = millis();
    while (millis() - start < WIFI_CONNECT_WINDOW_MS) {
      if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("WiFi 已连接: %s\n", WiFi.localIP().toString().c_str());
        return;
      }
      delay(250);
      Serial.print('.');
    }

    Serial.println("\n本轮连接失败，3 秒后重试...");
    delay(WIFI_RETRY_GAP_MS);
  }
}

void ensureWiFiConnected() {
  if (WiFi.status() == WL_CONNECTED) return;
  unsigned long now = millis();
  if (now - lastWifiAttemptAt < WIFI_RETRY_GAP_MS) return;
  lastWifiAttemptAt = now;
  connectWiFiUntilSuccess();
}

void handleStatus() {
  if (!checkAdminAuth()) return;

  String json = "{";
  json += "\"device_id\":" + String(deviceId) + ",";
  json += "\"local_ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"wifi_connected\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"wifi_ssid\":\"" + jsonEscape(wifiSsid) + "\",";
  json += "\"server_ip\":\"" + jsonEscape(serverIp) + "\",";
  json += "\"server_port\":" + String(serverPort) + ",";
  json += "\"local_report_interval_ms\":" + String(localReportIntervalMs) + ",";
  json += "\"effective_report_interval_ms\":" + String(effectiveReportIntervalMs) + ",";
  json += "\"enabled\":" + String(deviceEnabled ? "true" : "false") + ",";
  json += "\"backend_message\":\"" + jsonEscape(lastBackendMessage) + "\"";
  json += "}";
  server.send(200, "application/json", json);
}

void handleGetConfig() {
  if (!checkAdminAuth()) return;

  String json = "{";
  json += "\"wifi_ssid\":\"" + jsonEscape(wifiSsid) + "\",";
  json += "\"wifi_pass\":\"" + jsonEscape(wifiPass) + "\",";
  json += "\"server_ip\":\"" + jsonEscape(serverIp) + "\",";
  json += "\"server_port\":" + String(serverPort) + ",";
  json += "\"device_id\":" + String(deviceId) + ",";
  json += "\"report_interval_ms\":" + String(localReportIntervalMs) + ",";
  json += "\"enabled\":" + String(deviceEnabled ? "true" : "false") + ",";
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
  if (server.hasArg("report_interval_ms")) {
    unsigned long value = (unsigned long)server.arg("report_interval_ms").toInt();
    if (value < MIN_REPORT_INTERVAL_MS) value = MIN_REPORT_INTERVAL_MS;
    if (value > MAX_REPORT_INTERVAL_MS) value = MAX_REPORT_INTERVAL_MS;
    localReportIntervalMs = value;
    effectiveReportIntervalMs = value;
    changed = true;
  }

  if (!changed) {
    server.send(400, "application/json", "{\"error\":\"no valid config provided\"}");
    return;
  }

  saveConfig();
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
body{font-family:Arial,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;background:#0b1220;color:#eef2ff}
.card{background:#131c2f;border:1px solid #2a3858;border-radius:16px;padding:20px;margin-bottom:16px}
label{display:block;margin-top:12px;margin-bottom:6px}
input{width:100%;padding:10px;border-radius:10px;border:1px solid #405179;background:#0f1729;color:#fff;box-sizing:border-box}
button{margin-top:16px;padding:10px 14px;border:0;border-radius:10px;background:#4f46e5;color:#fff;font-weight:700}
small{color:#b7c2e1}.meta{line-height:1.7;color:#b7c2e1}
</style></head><body>
<div class="card"><h2>CAS ESP 管理页</h2>
<div class="meta">
<div>当前 IP: )HTML";
  html += WiFi.localIP().toString();
  html += R"HTML(</div>
<div>设备 ID: )HTML";
  html += String(deviceId);
  html += R"HTML(</div>
<div>本地上报频率: )HTML";
  html += String(localReportIntervalMs);
  html += R"HTML( ms</div>
<div>当前生效上报频率: )HTML";
  html += String(effectiveReportIntervalMs);
  html += R"HTML( ms</div>
<div>后端状态: )HTML";
  html += jsonEscape(lastBackendMessage);
  html += R"HTML(</div></div>
<form method="POST" action="/config">
<input type="hidden" name="password" value=")HTML";
  html += ADMIN_PASSWORD;
  html += R"HTML(">
<label>WiFi 名称</label><input name="wifi_ssid" value=")HTML";
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
<label>本地上报频率（毫秒）</label><input name="report_interval_ms" value=")HTML";
  html += String(localReportIntervalMs);
  html += R"HTML(">
<button type="submit">保存并重启</button></form>
<p><small>访问方式: http://设备IP/?password=187geufo</small></p>
</div></body></html>)HTML";

  server.send(200, "text/html; charset=utf-8", html);
}

void syncRemoteConfig() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (millis() - lastRemoteSyncAt < REMOTE_SYNC_INTERVAL_MS) return;
  lastRemoteSyncAt = millis();

  HTTPClient http;
  String url = httpBase() + "/api/device-config?id=" + String(deviceId);
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);
  http.begin(url);
  int code = http.GET();
  if (code >= 200 && code < 300) {
    String body = http.getString();
    applyRemoteConfig(body);
    lastBackendMessage = "配置同步成功";
  } else if (code > 0) {
    String body = http.getString();
    lastBackendMessage = String("配置同步失败 HTTP ") + code;
    Serial.printf("配置同步失败 url=%s http=%d body=%s\n", url.c_str(), code, body.c_str());
  } else {
    String reason = http.errorToString(code);
    lastBackendMessage = String("配置同步失败: ") + reason;
    Serial.printf("配置同步失败 url=%s code=%d reason=%s wifi=%d ip=%s\n", url.c_str(), code, reason.c_str(), WiFi.status(), WiFi.localIP().toString().c_str());
  }
  http.end();
}

void uploadFrame() {
  if (WiFi.status() != WL_CONNECTED) return;

  AcousticFrame frame = acquireAcousticFrame();
  HTTPClient http;
  String url = httpBase() + "/api/upload";
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"id\":" + String(deviceId) + ",";
  payload += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  payload += "\"port\":80,";
  payload += "\"raw_rms\":" + String(frame.raw_rms, 2) + ",";
  payload += "\"sample_min\":" + String(frame.sample_min) + ",";
  payload += "\"sample_max\":" + String(frame.sample_max) + ",";
  payload += "\"uptime_ms\":" + String(millis()) + ",";
  payload += "\"wifi_rssi\":" + String(WiFi.RSSI());
  payload += "}";

  int code = http.POST(payload);
  if (code >= 200 && code < 300) {
    String body = http.getString();
    applyRemoteConfig(body);
    lastBackendMessage = "上传成功";
    Serial.printf("上传成功 url=%s http=%d raw_rms=%.2f min=%d max=%d\n", url.c_str(), code, frame.raw_rms, frame.sample_min, frame.sample_max);
  } else if (code > 0) {
    String body = http.getString();
    lastBackendMessage = String("上传失败 HTTP ") + code;
    Serial.printf("上传失败 url=%s http=%d body=%s raw_rms=%.2f wifi=%d ip=%s\n", url.c_str(), code, body.c_str(), frame.raw_rms, WiFi.status(), WiFi.localIP().toString().c_str());
  } else {
    String reason = http.errorToString(code);
    lastBackendMessage = String("上传失败: ") + reason;
    Serial.printf("上传失败 url=%s code=%d reason=%s raw_rms=%.2f wifi=%d ip=%s\n", url.c_str(), code, reason.c_str(), frame.raw_rms, WiFi.status(), WiFi.localIP().toString().c_str());
  }

  http.end();
  lastUploadAt = millis();
}

void setupServer() {
  server.on("/", HTTP_GET, handleAdminPage);
  server.on("/admin", HTTP_GET, handleAdminPage);
  server.on("/config", HTTP_GET, handleGetConfig);
  server.on("/config", HTTP_POST, handleSetConfig);
  server.on("/status", HTTP_GET, handleStatus);
  server.begin();
}

void webServerTask(void* parameter) {
  while (true) {
    server.handleClient();
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void networkTask(void* parameter) {
  while (true) {
    ensureWiFiConnected();
    syncRemoteConfig();

    if (deviceEnabled && millis() - lastUploadAt >= effectiveReportIntervalMs) {
      uploadFrame();
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  loadConfig();
  initI2S();
  connectWiFiUntilSuccess();
  setupServer();
  syncRemoteConfig();

  xTaskCreate(webServerTask, "webServerTask", 4096, NULL, 2, &webTaskHandle);
  xTaskCreate(networkTask, "networkTask", 8192, NULL, 1, &networkTaskHandle);

  Serial.println("ESP32 噪音传感器已启动，网页服务与上传任务已分离");
}

void loop() {
  delay(1000);
}
