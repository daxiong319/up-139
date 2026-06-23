#!/bin/bash
# UP-139 快速部署脚本

echo "========================================="
echo "  UP-139 媒体上传监控系统 - 部署脚本"
echo "========================================="
echo ""

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

echo "✅ Docker 版本: $(docker --version)"
echo "✅ Docker Compose 版本: $(docker compose version)"
echo ""

# 创建数据目录
echo "📁 创建数据目录..."
mkdir -p data
echo ""

# 停止旧容器
echo "🛑 停止旧容器（如果存在）..."
docker compose down 2>/dev/null
echo ""

# 构建镜像
echo "🔨 构建 Docker 镜像..."
docker compose build
echo ""

# 启动容器
echo "🚀 启动容器..."
docker compose up -d
echo ""

# 等待启动
echo "⏳ 等待服务启动..."
sleep 5
echo ""

# 检查状态
echo "📊 容器状态:"
docker ps | grep up-139
echo ""

# 测试API
echo "🔍 测试 API 连接..."
if curl -s http://localhost:33303/api/status > /dev/null 2>&1; then
    echo "✅ WebUI 可访问: http://localhost:33303"
    echo "✅ API 状态: 正常"
else
    echo "❌ WebUI 无法访问，请检查日志"
    docker logs up-139 --tail 20
fi

echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
echo ""
echo "📱 访问地址: http://你的服务器IP:33303"
echo "📋 查看日志: docker logs -f up-139"
echo "🔄 重启服务: docker compose restart"
echo "🛑 停止服务: docker compose down"
echo ""
