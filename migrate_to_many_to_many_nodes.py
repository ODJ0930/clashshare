#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将节点和订阅的关系从一对多迁移到多对多
保留所有现有数据
"""

import sqlite3
from datetime import datetime
import sys
import io

# 设置 stdout 为 UTF-8 编码（解决 Windows 控制台编码问题）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def migrate_database():
    """执行数据库迁移"""
    db_path = 'instance/clash_manager.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("="*60)
        print("开始迁移数据库：节点订阅关系 一对多 -> 多对多")
        print("="*60)
        
        # 1. 检查是否已存在 subscription_node 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='subscription_node'
        """)
        
        if cursor.fetchone():
            print("\n[INFO] subscription_node 表已存在")
            # 检查是否有数据
            cursor.execute("SELECT COUNT(*) FROM subscription_node")
            existing_count = cursor.fetchone()[0]
            
            if existing_count > 0:
                print(f"[INFO] 表中已有 {existing_count} 条记录，跳过迁移")
                print("\n[SUCCESS] 数据库已经是多对多关系，无需迁移！")
                return
            else:
                print("[INFO] 表为空，将从 nodes 表导入数据")
                # 不需要删除表，直接导入数据即可
        else:
            # 2. 创建 subscription_node 多对多关联表
            cursor.execute("""
                CREATE TABLE subscription_node (
                    subscription_id INTEGER NOT NULL,
                    node_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (subscription_id, node_id),
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE,
                    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
                )
            """)
            print("\n[+] 创建 subscription_node 表")
        
        # 3. 从 nodes 表迁移现有的订阅关系
        cursor.execute("""
            SELECT id, subscription_id 
            FROM nodes 
            WHERE subscription_id IS NOT NULL
        """)
        
        existing_relations = cursor.fetchall()
        migrated_count = 0
        
        for node_id, subscription_id in existing_relations:
            cursor.execute("""
                INSERT INTO subscription_node (node_id, subscription_id, created_at)
                VALUES (?, ?, ?)
            """, (node_id, subscription_id, datetime.utcnow()))
            migrated_count += 1
        
        print(f"[+] 迁移了 {migrated_count} 条节点-订阅关系")
        
        # 4. 提交更改
        conn.commit()
        
        # 5. 验证迁移结果
        cursor.execute("SELECT COUNT(*) FROM subscription_node")
        total_relations = cursor.fetchone()[0]
        
        print("\n" + "="*60)
        print("[SUCCESS] 迁移完成！")
        print("="*60)
        print(f"[INFO] 多对多关系表中共有 {total_relations} 条记录")
        print("\n注意事项：")
        print("1. nodes 表中的 subscription_id 字段已保留用于兼容性")
        print("2. 新系统将使用 subscription_node 表来管理节点和订阅的关系")
        print("3. 节点现在可以同时属于多个订阅分组")
        print("\n可以安全地重启应用程序了！")
        
    except sqlite3.Error as e:
        print(f"\n[ERROR] 数据库迁移失败: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    try:
        migrate_database()
    except Exception as e:
        print(f"\n[ERROR] 迁移过程出错: {e}")
        exit(1)

