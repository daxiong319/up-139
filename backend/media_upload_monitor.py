#!/usr/bin/env python3
"""
媒体上传监控脚本 v3
功能：
1. 监控 qBittorrent 下载完成的影片
2. 通过 Alist fs/copy API 复制到移动云盘待整理目录（服务端复制，速度快）
3. 检查复制任务结果
4. 自动重试失败的复制
"""

import requests
import json
import time
import os
import sys
import re
from datetime import datetime

# ============ 配置 ============
# 容器内访问宿主机服务需要使用 host.docker.internal 或宿主机IP
QB_URL = "http://host.docker.internal:8080"  # 或者使用 http://172.17.0.1:8080
QB_USER = "admin"
QB_PASS = "adminadmin"

ALIST_URL = "http://134.185.85.200:5243"
ALIST_USER = "admin"
ALIST_PASS = "admin.319"

SRC_DIR = "/下载"
DST_DIR = "/中国移动云盘/影视/待整理"

QB_POLL_INTERVAL = 60      # 检查 qBittorrent 间隔（秒）
COPY_CHECK_INTERVAL = 30   # 检查复制任务间隔（秒）
MAX_COPY_WAIT = 1800       # 最大等待复制时间（秒）
SEEDING_MAX_DAYS = 3       # 做种超过此天数自动删除

PROCESSED_FILE = "/app/data/processed_torrents.json"
LOG_FILE = "/app/data/media_monitor.log"
NOTIFY_FILE = "/app/data/media_monitor_notify.txt"

ORGANIZED_DIR = "/中国移动云盘/影视/已整理"
ORGANIZE_CHECK_INTERVAL = 300   # 检查整理结果的间隔（秒）
ORGANIZE_MAX_WAIT = 7200        # 最大等待整理时间（秒）

# ============ 日志 ============
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def notify(msg):
    log(f"📢 {msg}")
    with open(NOTIFY_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def send_telegram(msg):
    """通过 hermes send 直接发送 Telegram 消息"""
    notify(msg)
    try:
        import subprocess
        subprocess.run(
            ["hermes", "send", "-t", "telegram", msg],
            capture_output=True, timeout=30
        )
    except Exception as e:
        log(f"Telegram 发送失败: {e}")
        # 备用：写入通知文件
        tg_file = "/root/.hermes/scripts/media_telegram_notify.txt"
        with open(tg_file, "a") as f:
            f.write(f"{msg}\n---\n")

# ============ qBittorrent ============
class QBClient:
    def __init__(self):
        self.session = requests.Session()
        self._login()

    def _login(self):
        self.session.post(f"{QB_URL}/api/v2/auth/login",
                          data={"username": QB_USER, "password": QB_PASS})

    def get_completed_torrents(self):
        try:
            r = self.session.get(f"{QB_URL}/api/v2/torrents/info",
                                 params={"filter": "completed"})
            if r.status_code == 403:
                self._login()
                r = self.session.get(f"{QB_URL}/api/v2/torrents/info",
                                     params={"filter": "completed"})
            return r.json()
        except Exception as e:
            log(f"qBittorrent 查询失败: {e}")
            return []

    def get_all_torrents(self):
        """获取所有种子（包括做种中的）"""
        try:
            r = self.session.get(f"{QB_URL}/api/v2/torrents/info")
            if r.status_code == 403:
                self._login()
                r = self.session.get(f"{QB_URL}/api/v2/torrents/info")
            return r.json()
        except Exception as e:
            log(f"qBittorrent 查询失败: {e}")
            return []

    def delete_torrent(self, torrent_hash, delete_files=True):
        """删除种子及其文件"""
        try:
            r = self.session.post(f"{QB_URL}/api/v2/torrents/delete",
                                  data={"hashes": torrent_hash, "deleteFiles": str(delete_files).lower()})
            return r.status_code == 200
        except Exception as e:
            log(f"删除种子失败: {e}")
            return False

# ============ Alist ============
class AlistClient:
    def __init__(self):
        self.token = None
        self._login()

    def _login(self):
        try:
            r = requests.post(f"{ALIST_URL}/api/auth/login",
                              json={"username": ALIST_USER, "password": ALIST_PASS})
            self.token = r.json()['data']['token']
        except Exception as e:
            log(f"Alist 登录失败: {e}")

    def _headers(self):
        return {"Authorization": self.token, "Content-Type": "application/json"}

    def list_dir(self, path, refresh=False):
        try:
            r = requests.post(f"{ALIST_URL}/api/fs/list",
                              headers=self._headers(),
                              json={"path": path, "page": 1, "per_page": 200, "refresh": refresh})
            data = r.json()
            if data.get('code') == 200:
                return data['data'].get('content') or []
            elif data.get('code') == 401:
                self._login()
                r = requests.post(f"{ALIST_URL}/api/fs/list",
                                  headers=self._headers(),
                                  json={"path": path, "page": 1, "per_page": 200, "refresh": refresh})
                data = r.json()
                if data.get('code') == 200:
                    return data['data'].get('content') or []
            return []
        except Exception as e:
            log(f"列出目录异常 {path}: {e}")
            return []

    def copy_files(self, src_dir, dst_dir, names):
        """通过 Alist fs/copy 服务端复制文件"""
        try:
            r = requests.post(f"{ALIST_URL}/api/fs/copy",
                              headers=self._headers(),
                              json={"src_dir": src_dir, "dst_dir": dst_dir, "names": names})
            data = r.json()
            if data.get('code') == 200:
                return data['data'].get('tasks', [])
            elif data.get('code') == 401:
                self._login()
                r = requests.post(f"{ALIST_URL}/api/fs/copy",
                                  headers=self._headers(),
                                  json={"src_dir": src_dir, "dst_dir": dst_dir, "names": names})
                data = r.json()
                if data.get('code') == 200:
                    return data['data'].get('tasks', [])
            log(f"复制失败: {data.get('message', 'unknown')}")
            return []
        except Exception as e:
            log(f"复制异常: {e}")
            return []

    def get_copy_tasks(self, status="undone"):
        """获取复制任务状态"""
        try:
            r = requests.get(f"{ALIST_URL}/api/task/copy/{status}",
                             headers=self._headers())
            data = r.json()
            if data.get('code') == 200:
                return data.get('data') or []
            return []
        except Exception as e:
            log(f"获取任务状态异常: {e}")
            return []

    def wait_copy_tasks(self, task_ids, timeout=MAX_COPY_WAIT):
        """等待复制任务完成"""
        start = time.time()
        remaining = set(task_ids)

        while remaining and (time.time() - start) < timeout:
            time.sleep(COPY_CHECK_INTERVAL)

            # 检查未完成任务
            undone = self.get_copy_tasks("undone")
            undone_ids = {t['id'] for t in undone}

            # 检查已完成任务
            done = self.get_copy_tasks("done")
            done_map = {t['id']: t for t in done}

            # 更新剩余任务
            still_running = remaining & undone_ids
            completed = remaining - undone_ids

            for tid in completed:
                if tid in done_map:
                    t = done_map[tid]
                    if t.get('error'):
                        log(f"  ❌ 复制失败: {t['name'][:50]}... 错误: {t['error'][:80]}")
                    else:
                        log(f"  ✅ 复制完成: {t['name'][:50]}...")
                else:
                    log(f"  ⚠️ 任务 {tid} 未找到")

            remaining = still_running
            if remaining:
                elapsed = int(time.time() - start)
                log(f"  ⏳ 还有 {len(remaining)} 个任务进行中... ({elapsed}s)")

        return len(remaining) == 0

    def check_target_files(self, refresh=False):
        """检查目标目录的文件"""
        return self.list_dir(DST_DIR, refresh=refresh)

    def search_organized(self, keywords):
        """在已整理目录中搜索匹配的文件/目录"""
        results = []
        try:
            # 清理关键词：去除标点符号便于模糊匹配
            def normalize(s):
                return re.sub(r'[：:·\s\-_\'\"!！?？()（）\[\]【】{}]', '', s).lower()
            
            norm_keywords = [normalize(kw) for kw in keywords if normalize(kw)]
            
            dirs = self.list_dir(ORGANIZED_DIR)
            for d in dirs:
                if not d.get('is_dir'):
                    continue
                # 搜索子目录（欧美剧集、欧美电影等）
                cat_path = f"{ORGANIZED_DIR}/{d['name']}"
                sub_dirs = self.list_dir(cat_path)
                for sub in sub_dirs:
                    if not sub.get('is_dir'):
                        continue
                    # 模糊匹配：标准化后包含关键词
                    norm_name = normalize(sub['name'])
                    if any(nkw in norm_name or norm_name in nkw for nkw in norm_keywords):
                        # 获取详细信息
                        detail_path = f"{cat_path}/{sub['name']}"
                        detail_files = self.list_dir(detail_path)
                        results.append({
                            'category': d['name'],
                            'name': sub['name'],
                            'path': detail_path,
                            'files': detail_files
                        })
        except Exception as e:
            log(f"搜索已整理目录异常: {e}")
        return results

# ============ 已处理记录 ============
def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            return json.load(f)
    return {}

def save_processed(data):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============ 核心流程 ============

def cleanup_expired_torrents(qb):
    """删除做种超过3天的种子及其文件"""
    max_seconds = SEEDING_MAX_DAYS * 86400
    torrents = qb.get_all_torrents()
    cleaned = []

    for t in torrents:
        seeding_time = t.get('seeding_time', 0)
        if seeding_time >= max_seconds:
            name = t['name']
            thash = t['hash']
            days = seeding_time / 86400
            log(f"🗑️ 做种 {days:.1f} 天，超过 {SEEDING_MAX_DAYS} 天限制: {name[:50]}")

            if qb.delete_torrent(thash, delete_files=True):
                log(f"  ✅ 已删除: {name[:50]}")
                cleaned.append(name)
            else:
                log(f"  ❌ 删除失败: {name[:50]}")

    if cleaned:
        msg = f"🗑️ 自动清理 {len(cleaned)} 个过期种子（做种>{SEEDING_MAX_DAYS}天）:\n"
        for n in cleaned:
            msg += f"  • {n[:50]}\n"
        send_telegram(msg.strip())

def check_organized_and_notify(torrent_name):
    """检查 symedia 整理结果并发送 Telegram 通知"""
    # 提取关键词用于匹配
    keywords = []
    
    # 1. 提取方括号内的中文名（最有用的关键词）
    bracket_matches = re.findall(r'\[([^\]]+)\]', torrent_name)
    for bm in bracket_matches:
        # 去掉"第X季"等后缀，保留核心名
        core = re.sub(r'\s*第[一二三四五六七八九十\d]+季\s*', '', bm).strip()
        core = re.sub(r'\s*Complete\s*', '', core, flags=re.IGNORECASE).strip()
        if core:
            keywords.append(core)
    
    # 2. 提取非括号部分的英文名
    clean = re.sub(r'\[.*?\]', '', torrent_name).strip()
    clean = re.sub(r'\.(S\d+|Complete|Bluray|WEB-DL|720p|1080p|2160p|x264|x265|H264|H265|AAC|AC3|DTS|10bit).*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\.(mkv|mp4|avi)$', '', clean, flags=re.IGNORECASE).strip()
    if clean:
        # 用点号分割，取前2个词
        parts = [p for p in clean.split('.') if len(p) > 2]
        for p in parts[:2]:
            keywords.append(p)

    if not keywords:
        keywords = [torrent_name[:10]]

    # 去重
    keywords = list(dict.fromkeys(keywords))

    log(f"搜索已整理目录，关键词: {keywords}")
    alist = AlistClient()
    results = alist.search_organized(keywords)

    if not results:
        return None

    # 构建通知消息
    for r in results:
        total_files = 0
        total_size = 0
        episodes = []

        for f in r.get('files', []):
            if f.get('is_dir'):
                # 可能是 Season 子目录
                season_files = alist.list_dir(f"{r['path']}/{f['name']}")
                for sf in season_files:
                    if not sf.get('is_dir'):
                        total_files += 1
                        total_size += sf.get('size', 0)
                        ep_match = re.search(r'[Ss]\d+[Ee](\d+)', sf['name'])
                        if ep_match:
                            episodes.append(int(ep_match.group(1)))
            else:
                total_files += 1
                total_size += f.get('size', 0)
                ep_match = re.search(r'[Ss]\d+[Ee](\d+)', f['name'])
                if ep_match:
                    episodes.append(int(ep_match.group(1)))

        size_gb = total_size / (1024**3)

        if episodes:
            # 剧集
            eps_sorted = sorted(episodes)
            if eps_sorted == list(range(eps_sorted[0], eps_sorted[-1]+1)):
                eps_str = f"E{eps_sorted[0]:02d}-E{eps_sorted[-1]:02d} (全{len(eps_sorted)}集)"
            else:
                eps_str = f"E{',E'.join(f'{e:02d}' for e in eps_sorted)} ({len(eps_sorted)}集)"

            msg = f"🎬 整理完成\n"
            msg += f"📺 {r['name']}\n"
            msg += f"📁 分类: {r['category']}\n"
            msg += f"📊 {eps_str} | {size_gb:.1f}GB\n"
            msg += f"📍 {r['path']}"
        else:
            # 电影
            msg = f"🎬 整理完成\n"
            msg += f"🎥 {r['name']}\n"
            msg += f"📁 分类: {r['category']}\n"
            msg += f"📊 {total_files}个文件 | {size_gb:.1f}GB\n"
            msg += f"📍 {r['path']}"

        send_telegram(msg)
        return r

    return None


def extract_episodes_from_files(file_list):
    """从文件列表中提取集数信息"""
    episodes = {}
    for f in file_list:
        m = re.search(r'[Ss]\d+[Ee](\d+)', f['name'])
        if m:
            episodes[int(m.group(1))] = f['name']
    return episodes

def process_torrent(torrent):
    """处理单个完成的种子"""
    name = torrent['name']
    thash = torrent['hash']
    save_path = torrent.get('save_path', '')

    log(f"开始处理: {name}")

    alist = AlistClient()

    # ===== 第0步：检查已整理目录是否已存在该作品 =====
    # 提取搜索关键词
    keywords = []
    bracket_matches = re.findall(r'\[([^\]]+)\]', name)
    for bm in bracket_matches:
        core = re.sub(r'\s*第[一二三四五六七八九十\d]+季\s*', '', bm).strip()
        core = re.sub(r'\s*Complete\s*', '', core, flags=re.IGNORECASE).strip()
        if core:
            keywords.append(core)
    clean = re.sub(r'\[.*?\]', '', name).strip()
    clean = re.sub(r'\.(S\d+|Complete|Bluray|WEB-DL|720p|1080p|2160p|x264|x265|H264|H265|AAC|AC3|DTS|10bit).*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\.(mkv|mp4|avi)$', '', clean, flags=re.IGNORECASE).strip()
    if clean:
        parts = [p for p in clean.split('.') if len(p) > 2]
        for p in parts[:2]:
            keywords.append(p)
    keywords = list(dict.fromkeys(keywords))

    if keywords:
        log(f"检查已整理目录，关键词: {keywords}")
        existing = alist.search_organized(keywords)
        if existing:
            for item in existing:
                log(f"  ⏭️ 已整理目录已存在: {item['name']} ({item['category']})")
                msg = f"⏭️ 已归档跳过\n📺 {item['name']}\n📁 分类: {item['category']}\n✅ 作品已在已整理目录中，无需重复上传"
                send_telegram(msg)
                log(f"  已发送通知：作品已在已整理目录中，跳过上传")
                return {'skip_code': 'already_organized'}

    # ===== 第1步：在 Alist /下载 目录下找到对应的源文件/目录 =====
    src_dir = None
    src_files = []

    # 先尝试直接匹配
    direct_path = f"{SRC_DIR}/{name}"
    files_list = alist.list_dir(direct_path)
    if files_list:
        src_dir = direct_path
        src_files = files_list
    else:
        # 在 /下载 根目录搜索
        root_files = alist.list_dir(SRC_DIR)
        for f in root_files:
            if f['is_dir'] and (name in f['name'] or f['name'] in name):
                candidate = f"{SRC_DIR}/{f['name']}"
                files_list = alist.list_dir(candidate)
                if files_list:
                    src_dir = candidate
                    src_files = files_list
                    break

        # 非目录情况（单文件种子）
        if not src_dir:
            for f in root_files:
                if not f['is_dir'] and f['name'] == name:
                    src_dir = SRC_DIR
                    src_files = root_files
                    break

    if not src_dir:
        log(f"找不到源文件: {name}")
        notify(f"❌ 找不到源文件: {name}")
        return False

    log(f"源目录: {src_dir}, 文件数: {len(src_files)}")

    # 过滤视频文件
    video_exts = ['.mkv', '.mp4', '.avi', '.rmvb', '.ts', '.flv', '.wmv']
    upload_files = [f for f in src_files if not f['is_dir'] and
                    any(f['name'].lower().endswith(ext) for ext in video_exts)]

    if not upload_files:
        log(f"没有找到视频文件: {src_dir}")
        return False

    log(f"待复制文件: {len(upload_files)} 个")

    # 检查目标目录已有哪些文件
    existing = alist.check_target_files(refresh=True)
    existing_names = {f['name'] for f in existing}

    # 找出需要复制的文件
    files_to_copy = [f for f in upload_files if f['name'] not in existing_names]

    if not files_to_copy:
        log(f"所有文件已在待整理目录中")
        # 记录已上传的文件列表（用于后续整理对比）
        return upload_files  # 返回文件列表而非 True

    log(f"需要复制: {len(files_to_copy)}/{len(upload_files)} 个文件")

    # 批量复制（Alist fs/copy 支持多个文件）
    names = [f['name'] for f in files_to_copy]
    tasks = alist.copy_files(src_dir, DST_DIR, names)

    if not tasks:
        log(f"复制任务创建失败")
        notify(f"❌ {name} - 复制任务创建失败")
        return False

    task_ids = [t['id'] for t in tasks]
    log(f"已创建 {len(task_ids)} 个复制任务，等待完成...")

    # 等待复制完成
    all_done = alist.wait_copy_tasks(task_ids)

    # 第1步：验证实际传到待整理目录的文件
    time.sleep(5)
    final_files = alist.check_target_files(refresh=True)
    uploaded_names = {f['name'] for f in final_files}

    # 统计本次上传结果
    uploaded_count = sum(1 for f in upload_files if f['name'] in uploaded_names)
    failed_names = [f['name'] for f in upload_files if f['name'] not in uploaded_names]

    log(f"📊 上传结果: {uploaded_count}/{len(upload_files)} 个文件到达待整理目录")
    if failed_names:
        log(f"❌ 未到达: {failed_names}")

    if uploaded_count < len(upload_files):
        notify(f"⚠️ {name} - 复制不完整 {uploaded_count}/{len(upload_files)}")
        return False

    notify(f"📤 {name} - 全部 {uploaded_count} 个文件已到达待整理目录，等待 symedia 整理...")
    return upload_files  # 返回完整文件列表

def check_and_update_organized():
    """
    检查所有待整理种子的 symedia 整理状态
    流程：
    1. 检查待整理目录中该种子的文件是否还在（还在=未被symedia处理）
    2. 如果文件已消失，在已整理目录中搜索
    3. 对比整理后的文件数量 vs 上传数量
    4. 发送详细通知：整理了多少集、具体哪些集、缺失多少集、具体缺哪些
    """
    processed = load_processed()
    updated = False
    alist = AlistClient()

    for thash, info in processed.items():
        if info.get('upload_status') != 'completed':
            continue
        if info.get('organize_status') in ('organized', 'timeout'):
            continue

        torrent_name = info.get('name', '')
        uploaded_files = info.get('uploaded_files', [])
        uploaded_episodes = info.get('uploaded_episodes', {})

        if not uploaded_files:
            log(f"⚠️ {torrent_name[:40]} 无上传记录，跳过整理检查")
            continue

        log(f"检查整理状态: {torrent_name[:50]}")

        # ===== 第1步：检查待整理目录中该种子的文件是否还在 =====
        # symedia 用移动方式归档，文件消失 = 已被 symedia 处理
        still_in_pending = []
        for fname in uploaded_files:
            path = f"{DST_DIR}/{fname}"
            try:
                r = requests.post(f"{ALIST_URL}/api/fs/get",
                                  headers=alist._headers(),
                                  json={"path": path})
                if r.json().get('code') == 200:
                    still_in_pending.append(fname)
            except:
                pass

        if still_in_pending:
            log(f"  ⏳ 还有 {len(still_in_pending)}/{len(uploaded_files)} 个文件在待整理中，symedia 尚未处理完")
            copy_time = info.get('completed_at', '')
            if copy_time:
                try:
                    ct = datetime.fromisoformat(copy_time)
                    waited = (datetime.now() - ct).total_seconds()
                    if waited > ORGANIZE_MAX_WAIT:
                        log(f"  ⏳ 等待整理超时({ORGANIZE_MAX_WAIT/3600:.0f}h)")
                        processed[thash]['organize_status'] = 'timeout'
                        updated = True
                        send_telegram(f"⚠️ 整理超时\n{torrent_name[:50]}\n等待{ORGANIZE_MAX_WAIT/3600:.0f}小时\n仍有{len(still_in_pending)}个文件在待整理中未被处理")
                except:
                    pass
            continue

        # ===== 第2步：文件已从待整理消失 = symedia 已移动，搜索已整理目录 =====
        log(f"  📁 待整理文件已全部消失，搜索已整理目录...")

        # 提取搜索关键词
        keywords = []
        bracket_matches = re.findall(r'\[([^\]]+)\]', torrent_name)
        for bm in bracket_matches:
            core = re.sub(r'\s*第[一二三四五六七八九十\d]+季\s*', '', bm).strip()
            core = re.sub(r'\s*Complete\s*', '', core, flags=re.IGNORECASE).strip()
            if core:
                keywords.append(core)
        clean = re.sub(r'\[.*?\]', '', torrent_name).strip()
        clean = re.sub(r'\.(S\d+|Complete|Bluray|WEB-DL|720p|1080p|2160p|x264|x265|H264|H265|AAC|AC3|DTS|10bit).*', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\.(mkv|mp4|avi)$', '', clean, flags=re.IGNORECASE).strip()
        if clean:
            parts = [p for p in clean.split('.') if len(p) > 2]
            for p in parts[:2]:
                keywords.append(p)
        keywords = list(dict.fromkeys(keywords)) or [torrent_name[:10]]

        results = alist.search_organized(keywords)

        if not results:
            log(f"  ❌ 已整理目录中未找到匹配内容")
            continue

        # ===== 第3步：对比整理结果 vs 上传数量 =====
        for result in results:
            organized_files = []
            organized_episodes = {}
            total_size = 0

            for f in result.get('files', []):
                if f.get('is_dir'):
                    # Season 子目录
                    season_files = alist.list_dir(f"{result['path']}/{f['name']}")
                    for sf in season_files:
                        if not sf.get('is_dir'):
                            organized_files.append(sf['name'])
                            total_size += sf.get('size', 0)
                            ep_match = re.search(r'[Ss]\d+[Ee](\d+)', sf['name'])
                            if ep_match:
                                organized_episodes[int(ep_match.group(1))] = sf['name']
                else:
                    organized_files.append(f['name'])
                    total_size += f.get('size', 0)
                    ep_match = re.search(r'[Ss]\d+[Ee](\d+)', f['name'])
                    if ep_match:
                        organized_episodes[int(ep_match.group(1))] = f['name']

            size_gb = total_size / (1024**3)

            # ===== 第4步：构建对比报告并通知 =====
            uploaded_count = len(uploaded_files)
            organized_count = len(organized_files)

            if uploaded_episodes:
                # 剧集模式 — 逐集对比
                uploaded_eps_set = set(int(e) for e in uploaded_episodes.keys())
                organized_eps_set = set(organized_episodes.keys())
                missing_eps = sorted(uploaded_eps_set - organized_eps_set)
                extra_eps = sorted(organized_eps_set - uploaded_eps_set)

                eps_sorted = sorted(organized_eps_set)
                if eps_sorted and eps_sorted == list(range(eps_sorted[0], eps_sorted[-1]+1)):
                    eps_str = f"E{eps_sorted[0]:02d}-E{eps_sorted[-1]:02d} (全{len(eps_sorted)}集)"
                else:
                    eps_str = f"E{',E'.join(f'{e:02d}' for e in eps_sorted)} ({len(eps_sorted)}集)"

                msg = f"🎬 整理归档完成\n"
                msg += f"📺 {result['name']}\n"
                msg += f"📁 分类: {result['category']}\n"
                msg += f"📊 已整理: {organized_count}/{uploaded_count} 集 | {size_gb:.1f}GB\n"
                msg += f"✅ 具体: {eps_str}\n"

                if missing_eps:
                    missing_str = f"E{',E'.join(f'{e:02d}' for e in missing_eps)}"
                    msg += f"❌ 缺失: {len(missing_eps)} 集 → {missing_str}\n"
                else:
                    msg += f"✅ 无缺失，全部到齐\n"

                msg += f"📍 {result['path']}"
            else:
                # 电影模式
                msg = f"🎬 整理归档完成\n"
                msg += f"🎥 {result['name']}\n"
                msg += f"📁 分类: {result['category']}\n"
                msg += f"📊 {organized_count} 个文件 | {size_gb:.1f}GB\n"
                if organized_count < uploaded_count:
                    msg += f"❌ 缺失: {uploaded_count - organized_count} 个文件\n"
                else:
                    msg += f"✅ 无缺失\n"
                msg += f"📍 {result['path']}"

            send_telegram(msg)
            log(f"  ✅ 整理对比完成: {organized_count}/{uploaded_count}")

        # 关键修复：搜到结果就设 organized，无论是否有 missing_eps
        processed[thash]['organize_status'] = 'organized'
        processed[thash]['organized_at'] = datetime.now().isoformat()
        updated = True

    if updated:
        save_processed(processed)

# ============ 主监控循环 ============
def run_monitor():
    log("🚀 启动媒体上传监控服务 v3 (Alist fs/copy)")
    log(f"qBittorrent: {QB_URL}")
    log(f"Alist: {ALIST_URL}")
    log(f"轮询间隔: {QB_POLL_INTERVAL}秒")

    qb = QBClient()
    processed = load_processed()
    last_organize_check = 0
    last_cleanup_check = 0

    while True:
        try:
            now = time.time()

            # 获取已完成的种子
            completed = qb.get_completed_torrents()

            for t in completed:
                thash = t['hash']
                # 先刷新状态，避免 stale 数据导致重复处理
                processed = load_processed()
                # 跳过已完成的、已归档跳过的，重试 pending/failed 的
                if thash in processed and processed[thash].get('upload_status') in ('completed', 'skipped_existing'):
                    continue

                # 新完成的种子
                log(f"发现新完成种子: {t['name']}")
                processed[thash] = {
                    'name': t['name'],
                    'completed_at': datetime.now().isoformat(),
                    'upload_status': 'processing'
                }
                save_processed(processed)

                # 处理上传
                result = process_torrent(t)

                if isinstance(result, dict) and result.get('skip_code') == 'already_organized':
                    # process_torrent 检测到已归档，直接标记并跳过
                    processed[thash]['upload_status'] = 'skipped_existing'
                    processed[thash]['reason'] = 'already_organized'
                    save_processed(processed)
                    log(f"  ⏭️ 已归档跳过，标记为 skipped_existing")
                    continue
                elif result is None:
                    # 未知原因返回 None，标记失败避免永循环
                    processed[thash]['upload_status'] = 'failed'
                    processed[thash]['reason'] = 'unknown_none_return'
                    save_processed(processed)
                    log(f"  ⚠️ 种子返回 None，标记为 failed")
                    continue
                elif result and isinstance(result, list):
                    # 上传成功，保存文件列表用于后续整理对比
                    episodes = extract_episodes_from_files(result)
                    processed[thash]['upload_status'] = 'completed'
                    processed[thash]['uploaded_files'] = [f['name'] for f in result]
                    processed[thash]['uploaded_episodes'] = {str(k): v for k, v in episodes.items()}
                    processed[thash]['uploaded_count'] = len(result)
                    processed[thash]['organize_status'] = 'pending'
                elif result:
                    processed[thash]['upload_status'] = 'completed'
                    processed[thash]['organize_status'] = 'pending'
                else:
                    processed[thash]['upload_status'] = 'failed'
                save_processed(processed)

            # 定期检查做种清理（每10分钟）
            if now - last_cleanup_check >= 600:
                cleanup_expired_torrents(qb)
                last_cleanup_check = now

            # 定期检查 symedia 整理结果（每5分钟）
            if now - last_organize_check >= ORGANIZE_CHECK_INTERVAL:
                check_and_update_organized()
                last_organize_check = now

        except Exception as e:
            log(f"监控周期异常: {e}")
            import traceback
            log(traceback.format_exc())

        time.sleep(QB_POLL_INTERVAL)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # 单次处理模式
        qb = QBClient()
        processed = load_processed()
        completed = qb.get_completed_torrents()
        for t in completed:
            if t['hash'] not in processed or processed[t['hash']].get('upload_status') != 'completed':
                log(f"处理: {t['name']}")
                processed[t['hash']] = {
                    'name': t['name'],
                    'completed_at': datetime.now().isoformat(),
                    'upload_status': 'processing'
                }
                save_processed(processed)
                success = process_torrent(t)
                processed[t['hash']]['upload_status'] = 'completed' if success else 'failed'
                save_processed(processed)
    else:
        run_monitor()
