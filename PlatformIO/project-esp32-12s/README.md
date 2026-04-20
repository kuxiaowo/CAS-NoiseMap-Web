# ESP32-12S (INMP441 数字麦克风版本)

## 项目概述

本项目针对 **INMP441 数字麦克风** 的 CAS 噪音地图传感器实现。采用 I2S 接口采样，计算 RMS 值，并将其上报到后端服务器进行 dB 转换和处理。

## 硬件配置

### ESP32-S3 DevKit C-1 引脚映射

| 功能 | GPIO | 说明 |
|------|------|------|
| **I2S_SCK** | 32 | Serial Clock (BCLK) |
| **I2S_WS** | 25 | Word Select (LRCLK) |
| **I2S_SD** | 33 | Serial Data (DOUT) |
| **GND** | GND | 地线 |
| **3.3V** | 3.3V | 电源 |

### INMP441 引脚连接

```
INMP441          ESP32-S3
---------        --------
VDD       -----> 3.3V
GND       -----> GND
CLK       -----> GPIO 32 (I2S_SCK)
WS        -----> GPIO 25 (I2S_WS)
SD        -----> GPIO 33 (I2S_SD)
L/R       -----> GND (立体声左声道)
```

## 软件配置

### WiFi 设置

编辑 `src/main.cpp` 中的以下常量：

```cpp
#define WIFI_SSID     "你的WiFi名称"
#define WIFI_PASS     "你的WiFi密码"
#define SERVER_IP     "192.168.43.252"  // 后端服务器 IP
#define SERVER_PORT   9880              // 后端服务器端口
#define DEVICE_ID     1                 // 传感器 ID（1-100）
```

## 编译和烧录

### 使用 PlatformIO

1. **安装 PlatformIO CLI**：
   ```bash
   pip install platformio
   ```

2. **编译**：
   ```bash
   pio run
   ```

3. **烧录**（自动检测端口）：
   ```bash
   pio run --target upload
   ```

4. **查看串口日志**：
   ```bash
   pio device monitor --baud 115200
   ```

### 使用 Arduino IDE

1. 安装 ESP32 开发板支持
2. 在 Arduino IDE 中打开 `src/main.cpp`
3. 选择开发板：**ESP32S3 Dev Module**
4. 选择串口并上传

## 工作流程

1. **初始化**：
   - 使用 ESP32 IDF 标准 I2S 驱动配置（`driver/i2s.h`）
   - 采样率 16 kHz，16 位深度
   - 左声道单声道采集
   - 连接 WiFi
   - 向后端服务器注册设备（POST /api/register）

2. **运行循环**：
   - 每次请求采集 200 个样本（约 12.5 ms）
   - 计算 RMS 值
   - 等待后端请求，通过 GET /noise 接口返回 RMS 值
   - 如 10 分钟无请求，自动重新注册

3. **数据格式**：
   ```json
   {
     "id": 1,
     "rms": 0.1234
   }
   ```

## 故障排查

### 问题：I2S 初始化失败
- **原因**：GPIO 配置错误或麦克风硬件问题
- **解决**：检查接线，验证 GPIO 25、32、33 无冲突

### 问题：编译错误 "I2S_MODE_STD was not declared"
- **原因**：使用了错误的 I2S 库
- **解决**：确保代码使用 `#include <driver/i2s.h>` 而非 `#include <I2S.h>`
- **检查**：platformio.ini 中不要包含外部 I2S 库，使用 Arduino 框架内置的 ESP-IDF I2S 驱动

### 问题：无法连接 WiFi
- **原因**：SSID/密码错误或信号弱
- **解决**：检查凭证，靠近路由器

### 问题：无法注册到服务器
- **原因**：服务器 IP/Port 错误或网络不通
- **解决**：验证 SERVER_IP 和 SERVER_PORT，检查防火墙

## 规格指标

- **采样率**：16 kHz
- **采样点数**：200
- **更新频率**：由后端轮询决定（通常 2 秒）
- **输出精度**：4 位小数（RMS）
- **工作温度**：0°C ~ 50°C
- **功耗**：约 500 mA @ 3.3V

## 参考资源

- [ESP32-S3 官方文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/index.html)
- [INMP441 数据手册](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf)
- [PlatformIO 文档](https://docs.platformio.org/)
