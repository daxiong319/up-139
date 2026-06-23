# UP-139 媒体上传监控系统

🎬 智能监控 qBittorrent 下载完成，自动上传至 Alist 云盘的可视化管理系统

## 功能特性

- ✅ 实时监控 qBittorrent 下载完成的种子
- ✅ 自动通过 Alist fs/copy API 复制到云盘
- ✅ 检查复制任务结果并自动重试
- ✅ 监控 symedia 整理结果
- ✅ Telegram 通知推送
- ✅ WebUI 可视化管理界面
- ✅ 实时日志查看
- ✅ 自动清理过期种子

## 快速部署

### 方式一：Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/daxiong319/up-139.git
cd up-139

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 访问 WebUI
# http://localhost:33303
```

### 方式二：手动构建

```bash
# 构建镜像
docker build -t up-139 .

# 运行容器
docker run -d \
  --name up-139 \
  -p 33303:33303 \
  -v $(pwd)/data:/app/data \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  up-139
```

## 配置说明

### qBittorrent 配置

在 `backend/media_upload_monitor.py` 中修改：

```python
QB_URL = "http://localhost:8080"
QB_USER = "admin"
QB_PASS = "adminadmin"
```

### Alist 配置

```python
ALIST_URL = "http://134.185.85.200:5243"
ALIST_USER = "admin"
ALIST_PASS = "admin.319"
```

### 目录配置

```python
SRC_DIR = "/下载"                      # qBittorrent 下载目录
DST_DIR = "/中国移动云盘/影视/待整理"  # Alist 待整理目录
ORGANIZED_DIR = "/中国移动云盘/影视/已整理"  # 已整理目录
```

## WebUI 功能

### 控制面板
- 启动/停止/重启监控服务
- 实时状态显示

### 实时日志
- WebSocket 实时推送
- 日志刷新和清空

### 通知管理
- 查看最近通知记录
- Telegram 通知状态

### 统计信息
- 已处理种子数量
- 上传成功数量
- 整理完成数量

## API 接口

- `GET /` - WebUI 主页面
- `GET /api/status` - 获取服务状态
- `POST /api/start` - 启动监控
- `POST /api/stop` - 停止监控
- `POST /api/restart` - 重启监控
- `GET /api/logs` - 获取日志
- `GET /api/processed` - 获取处理记录
- `GET /api/notifications` - 获取通知
- `WS /ws/logs` - WebSocket 实时日志

## 目录结构

```
up-139/
├── backend/
│   ├── main.py                      # FastAPI 后端主程序
│   ├── media_upload_monitor.py      # 监控脚本（核心）
│   ├── requirements.txt             # Python 依赖
│   └── data/                        # 数据目录（自动创建）
├── frontend/
│   └── index.html                   # WebUI 前端
├── Dockerfile                       # Docker 镜像构建文件
├── docker-compose.yml               # Docker Compose 配置
├── .gitignore                       # Git 忽略文件
└── README.md                        # 说明文档
```

## 技术栈

- **后端**: Python 3.11 + FastAPI + Uvicorn
- **前端**: 原生 HTML/CSS/JavaScript
- **容器**: Docker + Docker Compose
- **通信**: REST API + WebSocket

## 常见问题

### 1. 容器启动后无法访问

检查端口映射是否正确：
```bash
docker ps | grep up-139
```

### 2. 监控服务无法启动

查看容器日志：
```bash
docker logs up-139
```

### 3. 如何修改配置

编辑 `backend/media_upload_monitor.py` 后重新构建：
```bash
docker-compose down
docker-compose up -d --build
```

## License

MIT License

## 作者

daxiong319
