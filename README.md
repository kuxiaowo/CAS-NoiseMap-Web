# CAS-NoiseMap-Web Rewrite

这是按现有 ESP32 接入方式重写的一版更规范的噪音地图原型。
## 更新内容
- 增加了设备列表显示
- 将分贝计算逻辑更改到后端处理
## 设计目标
- 不修改现有硬件侧协议
- 仍然由硬件上传 `id`，后端按 `id -> 坐标` 映射
- 颜色在后端判断，前端只负责显示
- 保持轻量，继续使用静态前端 + Python 后端

## 当前链路
1. ESP32 启动后向后端 `POST /api/register`
2. 后端记录传感器 `id -> ip`
3. 后端定时访问 `http://<sensor_ip>:8000/noise`
4. 后端根据传感器 `id` 查找坐标，根据噪音值计算颜色
5. 前端请求 `/api/points` 并渲染地图、点位、影响范围

## 文件说明
- `index.html` 页面入口
- `style.css` 页面样式
- `config.js` 前端显示参数
- `app.js` 前端渲染逻辑
- `mock_server.py` 后端服务，负责注册、轮询、坐标映射、颜色判断
- `serve_web.py` 静态文件服务
- `sensor_simulator.py` 本地模拟传感器
- `sensor_positions.json` 传感器坐标配置
- `map.png` 地图背景图

## 运行方式
### 1. 启动后端
```bash
python mock_server.py
```
默认监听 `0.0.0.0:9880`

### 2. 启动前端静态服务
```bash
python serve_web.py
```
默认监听 `0.0.0.0:8080`

### 3. 浏览器访问
```bash
http://<server-ip>:8080
```

### 4. 如果没有真实硬件，可用模拟器
```bash
python sensor_simulator.py --id 1 --backend http://127.0.0.1:9880
```

## 依赖
```bash
pip install fastapi uvicorn requests
```

## 坐标配置
请编辑 `sensor_positions.json`，按传感器 `id` 配置真实坐标：

```json
{
  "1": { "x": 120, "y": 80, "label": "传感器1" },
  "2": { "x": 220, "y": 60, "label": "传感器2" }
}
```

## 注意
- 颜色阈值在后端统一定义
- 前端不再根据噪音值自行判断颜色
- 如果某个传感器已注册但没有配置坐标，后端会跳过，不渲染到地图上
