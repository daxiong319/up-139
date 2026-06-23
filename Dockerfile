FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制后端依赖
COPY backend/requirements.txt /app/backend/requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 复制应用代码
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 33303

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:33303/api/status || exit 1

# 启动命令
CMD ["python3", "/app/backend/main.py"]
