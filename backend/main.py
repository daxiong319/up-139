#!/usr/bin/env python3
"""
UP-139 WebUI 后端服务
功能：提供媒体上传监控的Web管理界面
"""

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
import subprocess
import asyncio
import json
import os
import signal
import threading
from datetime import datetime
from typing import Optional

app = FastAPI(title="UP-139 媒体上传监控", version="1.0.0")

# 全局状态
monitor_process: Optional[subprocess.Popen] = None
monitor_running = False

SCRIPT_PATH = "/app/backend/media_upload_monitor.py"
LOG_FILE = "/app/data/media_monitor.log"
PROCESSED_FILE = "/app/data/processed_torrents.json"
NOTIFY_FILE = "/app/data/media_monitor_notify.txt"

def read_process_output(proc):
    """后台线程：持续读取进程输出"""
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            # 跳过已经带时间戳的日志行（监控脚本已输出）
            if line.startswith('[') and len(line) > 20 and line[1:5].isdigit():
                continue
            if line:
                # 写入日志文件
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] {line}\n")
    except Exception as e:
        print(f"读取进程输出异常: {e}")

def log(msg):
    """记录日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="/app/frontend"), name="static")

@app.get("/")
async def root():
    """返回主页面"""
    return HTMLResponse(content=open("/app/frontend/index.html", encoding="utf-8").read())

@app.get("/api/status")
async def get_status():
    """获取监控服务状态"""
    global monitor_running, monitor_process
    
    # 检查进程是否还在运行
    if monitor_running and monitor_process:
        poll_result = monitor_process.poll()
        if poll_result is not None:
            # 进程已退出
            monitor_running = False
            if poll_result != 0:
                # 非正常退出，记录错误码
                log(f"监控进程异常退出，错误码: {poll_result}")
    
    return {
        "running": monitor_running,
        "pid": monitor_process.pid if monitor_process else None,
        "uptime": None
    }

@app.post("/api/start")
async def start_monitor():
    """启动监控服务"""
    global monitor_process, monitor_running
    
    if monitor_running:
        return {"status": "already_running", "message": "监控服务已在运行"}
    
    try:
        monitor_process = subprocess.Popen(
            ["python3", "-u", SCRIPT_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        monitor_running = True
        log(f"监控服务已启动，PID: {monitor_process.pid}")
        
        # 启动后台线程读取输出
        output_thread = threading.Thread(target=read_process_output, args=(monitor_process,), daemon=True)
        output_thread.start()
        
        return {"status": "started", "message": f"监控服务已启动，PID: {monitor_process.pid}"}
    except Exception as e:
        log(f"启动监控服务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")

@app.post("/api/stop")
async def stop_monitor():
    """停止监控服务"""
    global monitor_process, monitor_running
    
    if not monitor_running or not monitor_process:
        return {"status": "not_running", "message": "监控服务未运行"}
    
    try:
        monitor_process.terminate()
        monitor_process.wait(timeout=10)
        monitor_running = False
        return {"status": "stopped", "message": "监控服务已停止"}
    except Exception as e:
        # 强制杀死进程
        monitor_process.kill()
        monitor_running = False
        return {"status": "killed", "message": f"强制停止: {str(e)}"}

@app.post("/api/restart")
async def restart_monitor():
    """重启监控服务"""
    await stop_monitor()
    await asyncio.sleep(2)
    return await start_monitor()

@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """获取最新日志"""
    try:
        if not os.path.exists(LOG_FILE):
            return {"logs": []}
        
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return {"logs": all_lines[-lines:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {str(e)}")

@app.get("/api/processed")
async def get_processed():
    """获取已处理记录"""
    try:
        if not os.path.exists(PROCESSED_FILE):
            return {"processed": {}}
        
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"processed": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取记录失败: {str(e)}")

@app.get("/api/notifications")
async def get_notifications():
    """获取通知记录"""
    try:
        if not os.path.exists(NOTIFY_FILE):
            return {"notifications": []}
        
        with open(NOTIFY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return {"notifications": lines[-50:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取通知失败: {str(e)}")

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket实时日志推送"""
    await websocket.accept()
    
    try:
        if not os.path.exists(LOG_FILE):
            await websocket.send_text(json.dumps({"error": "日志文件不存在"}))
            return
        
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # 先发送现有日志
            f.seek(0, 2)  # 移动到文件末尾
            
            while True:
                line = f.readline()
                if line:
                    await websocket.send_text(line.strip())
                else:
                    await asyncio.sleep(1)
    except Exception as e:
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=33303)
