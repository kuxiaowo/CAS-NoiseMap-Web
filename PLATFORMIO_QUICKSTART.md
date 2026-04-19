# PlatformIO 项目快速开始

本目录包含两个完整的 PlatformIO 项目，分别对应两种麦克风硬件。

## 项目结构

```
CAS-NoiseMap-Web-main/
├── project-esp32-12s/       # INMP441 数字麦克风项目
│   ├── platformio.ini
│   ├── src/main.cpp
│   └── README.md
├── project-esp32-analogy/   # MAX4466 模拟麦克风项目
│   ├── platformio.ini
│   ├── src/main.cpp
│   └── README.md
├── mock_server.py           # 后端服务器
├── sensor_simulator.py       # 传感器模拟器
└── serve_web.py             # 前端服务器
```

## 快速开始

### 1. 安装 PlatformIO CLI

```bash
pip install platformio
```

### 2. 选择你的硬件版本

#### 方案 A：使用 INMP441 数字麦克风（推荐）

```bash
cd project-esp32-12s

# 查看硬件配置和完整说明
cat README.md

# 编辑 WiFi 配置
# src/main.cpp 第 10-14 行：修改 WIFI_SSID 和 WIFI_PASS

# 编译
pio run

# 烧录
pio run --target upload

# 查看日志
pio device monitor --baud 115200
```

#### 方案 B：使用 MAX4466 模拟麦克风

```bash
cd project-esp32-analogy

# 查看硬件配置和完整说明
cat README.md

# 编辑 WiFi 配置
# src/main.cpp 第 10-14 行：修改 WIFI_SSID 和 WIFI_PASS

# 编译
pio run

# 烧录
pio run --target upload

# 查看日志
pio device monitor --baud 115200
```

### 3. 修改配置文件

编辑所选项目的 `src/main.cpp`，修改以下部分：

```cpp
#define WIFI_SSID     "你的WiFi名称"
#define WIFI_PASS     "你的WiFi密码"
#define DEVICE_ID     1                 // 传感器 ID（可选，多个设备时修改）
#define SERVER_IP     "192.168.x.x"     // 后端服务器地址
```

### 4. 启动后端和模拟器（开发测试）

```bash
# 终端 1：启动后端
cd ..
python mock_server.py

# 终端 2：启动前端（可选）
python serve_web.py

# 终端 3：启动传感器模拟器（如果不用真实硬件）
python sensor_simulator.py --count 3
```

### 5. 访问网页

打开浏览器，访问：
- http://127.0.0.1:8080 （如果运行了前端）

## 故障排查

### 编译错误

**错误**：`I2S_MODE_STD was not declared`
```
error: 'I2S_MODE_STD' was not declared in this scope
```

**原因**：使用了错误的 I2S 库版本

**解决**：
1. 确保代码使用 `#include <driver/i2s.h>`（ESP32 IDF 标准驱动）
2. 不要使用 `#include <I2S.h>`（Arduino 第三方库）
3. 检查 platformio.ini 中不要添加外部 I2S 库依赖
4. 清空编译产物重新编译：
   ```bash
   pio run --target clean
   pio run --target upload
   ```

**错误**：找不到库
```
undefined reference to `WiFi'
```

**解决**：
```bash
# 更新库
pio lib update

# 或手动指定库依赖
pio run --target upload --verbose
```

### 烧录失败

**错误**：无法识别 COM 端口
```bash
# 列出所有 COM 端口
pio device list

# 指定端口烧录
pio run --target upload --upload-port COM3
```

### 无法连接 WiFi

- 检查 SSID 和密码（中文需要用 UTF-8 编码）
- 确保 ESP32 和 WiFi 路由器在同一网络
- 查看 Serial Monitor 日志

### 无法注册到服务器

- 验证后端服务器是否运行：`python mock_server.py`
- 检查 SERVER_IP 和 SERVER_PORT 是否正确
- 确保 ESP32 和后端在同一网络（或可路由）

## 常用 PlatformIO 命令

```bash
# 编译
pio run

# 编译并烧录
pio run --target upload

# 仅编译（不烧录）
pio run --target build

# 清空编译产物
pio run --target clean

# 查看串口日志
pio device monitor --baud 115200

# 完整信息编译（调试）
pio run --target upload --verbose

# 列出可用的开发板
pio boards
```

## 多个传感器设置

如果要部署多个 ESP32 传感器，修改各设备的 DEVICE_ID：

**设备 1** (project-esp32-12s)：
```cpp
#define DEVICE_ID 1
```

**设备 2** (project-esp32-analogy)：
```cpp
#define DEVICE_ID 2
```

或修改一个项目后复制出来。

## 性能指标

| 项目 | 麦克风 | 采样率 | 精度 | 功耗 |
|------|-------|--------|------|------|
| ESP32-12S | INMP441 | 16 kHz | 4 位小数 | 中等 |
| ESP32-analogy | MAX4466 | ~5 kHz | 2 位小数 | 低 |

## 更多信息

- [ESP32-S3 官方文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/index.html)
- [PlatformIO 官方文档](https://docs.platformio.org/)
- 各项目目录下的 README.md

## 许可证

MIT License
