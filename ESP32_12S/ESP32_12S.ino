#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <driver/i2s.h>

/* ================= 配置区 ================= */

#define WIFI_SSID     "酷小我的Pura 70 Pro"
#define WIFI_PASS     "11110000"

#define DEVICE_ID     1

#define SERVER_IP     "192.168.43.252"
#define SERVER_PORT   9880

/* INMP441 数字麦克风引脚配置 */
#define I2S_WS  4    // Word Select (LRCLK)
#define I2S_SD  2    // Serial Data (DOUT)
#define I2S_SCK 15    // Serial Clock (BCLK)

#define SAMPLE_COUNT 200  // 每次读取的采样点数
#define SAMPLE_RATE 16000 // 采样率（Hz）

bool registered = false;
unsigned long lastRegisterTry = 0;
unsigned long lastRequestTime = 0;
const unsigned long REGISTER_INTERVAL = 3000;
const unsigned long REQUEST_TIMEOUT = 600000;

/* ========================================= */

WebServer server(8000);

/* ============ I2S 初始化 ============ */

void initI2S() {
  // 配置 I2S
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

  // 安装 I2S 驱动
  if (i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL) != ESP_OK) {
    Serial.println("I2S 驱动安装失败");
    return;
  }

  // 配置 I2S 引脚
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

/* ============ 噪音采集 - 计算 RMS ============ */

/**
 * 从 INMP441 读取采样数据并计算 RMS
 * 返回：原始 RMS 值（不做 log10 转换，由后端处理）
 */
float calculateRMS() {
  float sqSum = 0.0;
  size_t bytes_read = 0;
  uint8_t i2s_data[SAMPLE_COUNT * 2];  // 16 位采样 = 2 字节

  // 读取 I2S 数据
  if (i2s_read(I2S_NUM_0, i2s_data, SAMPLE_COUNT * 2, &bytes_read, 100) != ESP_OK) {
    Serial.println("I2S 读取失败");
    return 0.0;
  }

  // 处理采样数据
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    // 读取 16 位有符号整数（小端）
    int16_t sample = (int16_t)((i2s_data[i * 2 + 1] << 8) | i2s_data[i * 2]);
    
    // 归一化到 -1.0 ~ 1.0
    float normalized = (float)sample / 32768.0;
    
    sqSum += normalized * normalized;
  }

  float rms = sqrt(sqSum / SAMPLE_COUNT);

  return rms;
}

/* ---------------- GET /noise ---------------- */

void handleNoise() {
  float rms = calculateRMS();
  
  String json = "{";
  json += "\"id\":" + String(DEVICE_ID) + ",";
  json += "\"rms\":" + String(rms, 4);  // 保留 4 位小数
  json += "}";
  
  server.send(200, "application/json", json);
  
  lastRequestTime = millis();
  Serial.print("RMS: ");
  Serial.println(rms, 4);
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
  
  Serial.println("\n=== ESP32-I2S INMP441 初始化 ===");

  // 初始化 I2S
  initI2S();

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
