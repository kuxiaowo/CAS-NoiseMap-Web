# ESP32-analogy (MAX4466 模拟麦克风版本)

## 项目概述

本项目针对 **MAX4466 模拟麦克风** 的 CAS 噪音地图传感器实现。采用 ADC 接口采样，计算 RMS 值，并将其上报到后端服务器进行 dB 转换和处理。

## 硬件配置

### ESP32-S3 DevKit C-1 引脚映射

| 功能 | GPIO | 说明 |
|------|------|------|
| **MIC_PIN** | 14 | MAX4466 输出（ADC1_6） |
| **GND** | GND | 地线 |
| **3.3V** | 3.3V | 电源 |

### MAX4466 引脚连接

```
MAX4466          ESP32-S3
-------          --------
VCC       -----> 3.3V
GND       -----> GND
OUT       -----> GPIO 14 (ADC)
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
#define MIC_PIN       14                // 麦克风接入引脚
```

### ADC 参数调整

在 `setup()` 函数中可调整：

```cpp
analogReadResolution(12);                    // 12 位分辨率（0-4095）
analogSetPinAttenuation(MIC_PIN, ADC_11db); // 11 dB 衰减（3.3V 范围）
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
   - 配置 ADC（12 位分辨率，11 dB 衰减）
   - 连接 WiFi
   - 向后端服务器注册设备（POST /api/register）

2. **运行循环**：
   - 每 2 秒采集 200 个样本
   - 估计直流偏置（麦克风中点值）
   - 从原始值中减去直流偏置，计算 AC 分量的 RMS
   - 等待后端请求，通过 GET /noise 接口返回 RMS 值
   - 如 10 分钟无请求，自动重新注册

3. **数据格式**：
   ```json
   {
     "id": 1,
     "rms": 45.67
   }
   ```

## ADC 工作原理

### 采样过程

1. **直流偏置估计**：
   ```
   平均值 = (样本1 + 样本2 + ... + 样本200) / 200
   ```

2. **AC 分量提取**：
   ```
   AC值 = 原始值 - 直流偏置
   ```

3. **RMS 计算**：
   ```
   RMS = sqrt((AC1² + AC2² + ... + AC200²) / 200)
   ```

### 噪音等级对应

- **绿色** (RMS < 0.05)：低噪音 < 55 dB
- **黄色** (0.05 ≤ RMS < 0.15)：中噪音 55-75 dB  
- **红色** (RMS ≥ 0.15)：高噪音 ≥ 75 dB

## 故障排查

### 问题：ADC 读值波动大或不变
- **原因**：麦克风脱落、接触不良或受干扰
- **解决**：重新插入麦克风，远离干扰源，检查接线

### 问题：无法连接 WiFi
- **原因**：SSID/密码错误或信号弱
- **解决**：检查凭证，靠近路由器

### 问题：无法注册到服务器
- **原因**：服务器 IP/Port 错误或网络不通
- **解决**：验证 SERVER_IP 和 SERVER_PORT，检查防火墙

## 规格指标

- **ADC 分辨率**：12 位（0-4095）
- **采样点数**：200
- **采样间隔**：200 μs（约 5 kHz 有效采样率）
- **更新频率**：由后端轮询决定（通常 2 秒）
- **输出精度**：2 位小数（RMS）
- **测量范围**：0-4095 ADC 单位
- **工作温度**：0°C ~ 50°C
- **功耗**：约 200 mA @ 3.3V

## 性能优化建议

### 降噪

1. **增加采样点数**（需要调整延迟）：
   ```cpp
   #define SAMPLE_COUNT 400  // 更多样本 = 更稳定但响应更慢
   ```

2. **调整采样间隔**：
   ```cpp
   #define SAMPLE_DELAY_US 100  // 更短的间隔 = 更快的采样
   ```

3. **使用高通滤波**：在软件中移除低频漂移

### 提高精度

1. 使用 MAX4466 的增益控制（引脚 GAIN）
2. 定期重新校准直流偏置
3. 在稳定环境中测量

## 参考资源

- [ESP32-S3 官方文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/index.html)
- [MAX4466 数据手册](https://datasheets.maximintegrated.com/en/ds/MAX4466.pdf)
- [ESP32 ADC 文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/adc.html)
- [PlatformIO 文档](https://docs.platformio.org/)
