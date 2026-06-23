#!/usr/bin/env python3
"""
数据库模型和配置管理
使用SQLite存储配置和历史记录
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = "/app/data/up139.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # qBittorrent配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qb_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Alist配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alist_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                source_dir TEXT DEFAULT '/下载',
                target_dir TEXT DEFAULT '/中国移动云盘/影视/待整理',
                organized_dir TEXT DEFAULT '/中国移动云盘/影视/已整理',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 系统配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 上传历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS upload_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                torrent_hash TEXT NOT NULL,
                torrent_name TEXT NOT NULL,
                qb_config_id INTEGER,
                alist_config_id INTEGER,
                file_size BIGINT,
                upload_status TEXT DEFAULT 'pending',
                upload_started_at TIMESTAMP,
                upload_completed_at TIMESTAMP,
                cloud_check_status TEXT DEFAULT 'pending',
                cloud_check_completed_at TIMESTAMP,
                is_complete BOOLEAN DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (qb_config_id) REFERENCES qb_config(id),
                FOREIGN KEY (alist_config_id) REFERENCES alist_config(id)
            )
        ''')
        
        # 插入默认配置
        self._insert_default_config(cursor)
        
        conn.commit()
        conn.close()
    
    def _insert_default_config(self, cursor):
        """插入默认配置"""
        # 默认qBittorrent配置
        cursor.execute("SELECT COUNT(*) FROM qb_config")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO qb_config (name, url, username, password, is_active)
                VALUES (?, ?, ?, ?, ?)
            ''', ('默认qBittorrent', 'http://localhost:8080', 'admin', 'adminadmin', 1))
        
        # 默认Alist配置
        cursor.execute("SELECT COUNT(*) FROM alist_config")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO alist_config (name, url, username, password, source_dir, target_dir, organized_dir, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('默认Alist', 'http://134.185.85.200:5243', 'admin', 'admin.319',
                  '/下载', '/中国移动云盘/影视/待整理', '/中国移动云盘/影视/已整理', 1))
        
        # 默认系统配置
        defaults = {
            'seed_hours': '72',  # 默认做种72小时
            'disk_threshold_gb': '50',  # 默认磁盘阈值50GB
            'auto_cleanup': '1',  # 默认开启自动清理
            'monitor_interval': '60',  # 监控间隔60秒
        }
        
        for key, value in defaults.items():
            cursor.execute("SELECT COUNT(*) FROM system_config WHERE key=?", (key,))
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO system_config (key, value) VALUES (?, ?)",
                    (key, value)
                )
    
    # qBittorrent配置管理
    def get_qb_configs(self, active_only=False):
        conn = self.get_connection()
        if active_only:
            rows = conn.execute("SELECT * FROM qb_config WHERE is_active=1 ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM qb_config ORDER BY id").fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def add_qb_config(self, name, url, username, password):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO qb_config (name, url, username, password) VALUES (?, ?, ?, ?)",
            (name, url, username, password)
        )
        config_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return config_id
    
    def update_qb_config(self, config_id, **kwargs):
        conn = self.get_connection()
        fields = ", ".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [config_id]
        conn.execute(f"UPDATE qb_config SET {fields} WHERE id=?", values)
        conn.commit()
        conn.close()
    
    def delete_qb_config(self, config_id):
        conn = self.get_connection()
        conn.execute("DELETE FROM qb_config WHERE id=?", (config_id,))
        conn.commit()
        conn.close()
    
    # Alist配置管理
    def get_alist_configs(self, active_only=False):
        conn = self.get_connection()
        if active_only:
            rows = conn.execute("SELECT * FROM alist_config WHERE is_active=1 ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM alist_config ORDER BY id").fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def add_alist_config(self, name, url, username, password, source_dir, target_dir, organized_dir):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO alist_config (name, url, username, password, source_dir, target_dir, organized_dir) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, url, username, password, source_dir, target_dir, organized_dir)
        )
        config_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return config_id
    
    def update_alist_config(self, config_id, **kwargs):
        conn = self.get_connection()
        fields = ", ".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [config_id]
        conn.execute(f"UPDATE alist_config SET {fields} WHERE id=?", values)
        conn.commit()
        conn.close()
    
    def delete_alist_config(self, config_id):
        conn = self.get_connection()
        conn.execute("DELETE FROM alist_config WHERE id=?", (config_id,))
        conn.commit()
        conn.close()
    
    # 系统配置管理
    def get_system_config(self, key):
        conn = self.get_connection()
        row = conn.execute("SELECT value FROM system_config WHERE key=?", (key,)).fetchone()
        conn.close()
        return row['value'] if row else None
    
    def set_system_config(self, key, value):
        conn = self.get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_all_system_config(self):
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM system_config").fetchall()
        conn.close()
        return {row['key']: row['value'] for row in rows}
    
    # 上传历史管理
    def add_upload_history(self, torrent_hash, torrent_name, qb_config_id=None, alist_config_id=None, file_size=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO upload_history (torrent_hash, torrent_name, qb_config_id, alist_config_id, file_size, upload_started_at) VALUES (?, ?, ?, ?, ?, ?)",
            (torrent_hash, torrent_name, qb_config_id, alist_config_id, file_size, datetime.now().isoformat())
        )
        history_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return history_id
    
    def update_upload_status(self, torrent_hash, status, error_message=None):
        conn = self.get_connection()
        if status == 'completed':
            conn.execute(
                "UPDATE upload_history SET upload_status=?, upload_completed_at=?, error_message=? WHERE torrent_hash=?",
                (status, datetime.now().isoformat(), error_message, torrent_hash)
            )
        else:
            conn.execute(
                "UPDATE upload_history SET upload_status=?, error_message=? WHERE torrent_hash=?",
                (status, error_message, torrent_hash)
            )
        conn.commit()
        conn.close()
    
    def update_cloud_check(self, torrent_hash, status, exists=False):
        conn = self.get_connection()
        is_complete = 1 if (status == 'exists' and exists) else 0
        conn.execute(
            "UPDATE upload_history SET cloud_check_status=?, cloud_check_completed_at=?, is_complete=? WHERE torrent_hash=?",
            (status, datetime.now().isoformat(), is_complete, torrent_hash)
        )
        conn.commit()
        conn.close()
    
    def get_upload_history(self, limit=100, offset=0):
        conn = self.get_connection()
        rows = conn.execute(
            """SELECT h.*, q.name as qb_name, a.name as alist_name 
               FROM upload_history h 
               LEFT JOIN qb_config q ON h.qb_config_id = q.id 
               LEFT JOIN alist_config a ON h.alist_config_id = a.id 
               ORDER BY h.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_history_by_hash(self, torrent_hash):
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM upload_history WHERE torrent_hash=?", (torrent_hash,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_history_stats(self):
        conn = self.get_connection()
        stats = {}
        
        # 总记录数
        row = conn.execute("SELECT COUNT(*) as total FROM upload_history").fetchone()
        stats['total'] = row['total']
        
        # 上传成功数
        row = conn.execute("SELECT COUNT(*) as count FROM upload_history WHERE upload_status='completed'").fetchone()
        stats['upload_success'] = row['count']
        
        # 云盘已存在数
        row = conn.execute("SELECT COUNT(*) as count FROM upload_history WHERE cloud_check_status='exists'").fetchone()
        stats['cloud_exists'] = row['count']
        
        # 完整链路数
        row = conn.execute("SELECT COUNT(*) as count FROM upload_history WHERE is_complete=1").fetchone()
        stats['complete'] = row['count']
        
        conn.close()
        return stats
