# CAS-NoiseMap-Web

这是重构后的 CAS 噪音地图原型，当前架构改为：

- **ESP 主动上报**，不再由服务器高频轮询设备
- **后端集中保存配置**，传感器/地图参数统一保存在 JSON 文件里
- **前端负责地图展示和传感器管理**，网页端可直接修改配置并实时写回后端

## 当前链路

1. ESP 启动后连接 WiFi
2. ESP 本地管理页可修改 WiFi、服务器地址、设备 ID、本地上报频率
3. ESP 定时向后端 `POST /api/upload`
4. 后端根据传感器配置完成：
   - 启用/禁用
   - 上报频率下发
   - 坐标映射
   - 校准换算
   - 在线状态判断
5. 前端请求后端 API 渲染地图，并提供传感器状态与配置管理面板

## 主要文件

- `index.html` 前端页面入口
- `style.css` 前端样式
- `config.js` 前端 API 基础配置
- `app.js` 地图渲染与传感器管理逻辑
- `mock_server.py` 后端服务
- `sensor_simulator.py` 主动上报模式的本地模拟器
- `sensors.json` 传感器配置文件
- `system_config.json` 前端显示配置文件
- `ESP32_12S/ESP32_12S.ino` ESP32 固件
- `ESP32-C3_12S/ESP32-C3_12S.ino` ESP32-C3 固件

## 后端依赖

建议使用已安装的 Miniconda Python：

```bash
/home/kuxiaowo/miniconda3/bin/pip install fastapi uvicorn requests
```

## 运行方式

### 1. 启动后端

```bash
/home/kuxiaowo/miniconda3/bin/python mock_server.py
```

默认监听 `0.0.0.0:9880`

### 2. 启动静态前端

```bash
python3 serve_web.py
```

默认监听 `0.0.0.0:8080`

### 3. 浏览器访问

```bash
http://<server-ip>:8080
```

### 4. 无硬件时启动模拟器

```bash
/home/kuxiaowo/miniconda3/bin/python sensor_simulator.py --backend http://127.0.0.1:9880 --count 5
```

## 关键接口

### 设备侧

- `POST /api/upload`
- `GET /api/device-config?id=<sensor_id>`

### 前端侧

- `GET /api/points`
- `GET /api/devices`
- `GET /api/config`
- `POST /api/sensors`
- `PATCH /api/sensors/<id>`
- `DELETE /api/sensors/<id>`

## 配置文件说明

> 注释说明文件：
> - `sensors.comments.md`
> - `system_config.comments.md`
>
> 之所以单独放说明文件，而不是直接写进 `.json`，是因为当前后端按标准 JSON 解析，JSON 本身不支持注释。

### `sensors.json`
保存：

- 传感器启用状态
- 坐标
- 标签
- 上报频率
- 三点校准参数（3 组 dB / raw RMS）
- 颜色阈值

### `system_config.json`
保存：

- 前端轮询频率
- 地图缩放与锚点
- 热区半径
- 图例配置

## 当前实现说明

- 前端可直接新增、删除、修改传感器配置，保存后会立即写入后端 JSON 配置文件
- 三点校准使用 3 组 `dB + raw RMS` 做对数分段插值，比单参考点更稳
- 传感器禁用后，地图会立刻停止渲染该点
- 本地 ESP 管理页里的上报频率是**本地默认值/兜底值**，后端配置可覆盖它
