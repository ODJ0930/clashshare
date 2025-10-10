#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加 custom_slug 字段
为 User 和 Subscription 表添加自定义后缀支持
"""

import sqlite3
import os
import sys

# 设置 Windows 控制台编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

def migrate_database():
    """执行数据库迁移"""
    db_path = 'instance/clash_manager.db'
    
    if not os.path.exists(db_path):
        print(f"[ERROR] 数据库文件不存在: {db_path}")
        print("请先运行 app.py 初始化数据库")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("开始数据库迁移...")
        print("="*60)
        
        # 检查 users 表是否已有 custom_slug 字段
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'custom_slug' not in columns:
            print("[OK] 为 users 表添加 custom_slug 字段...")
            # SQLite 不支持直接添加 UNIQUE 列，先添加普通列
            cursor.execute("""
                ALTER TABLE users ADD COLUMN custom_slug VARCHAR(100)
            """)
            print("   users 表迁移成功")
            
            # 创建唯一索引来保证唯一性
            try:
                cursor.execute("""
                    CREATE UNIQUE INDEX idx_users_custom_slug ON users(custom_slug) WHERE custom_slug IS NOT NULL
                """)
                print("   创建 users.custom_slug 唯一索引成功")
            except sqlite3.OperationalError:
                print("   索引已存在，跳过")
        else:
            print("[SKIP] users 表已有 custom_slug 字段，跳过")
        
        # 检查 subscriptions 表是否已有 custom_slug 字段
        cursor.execute("PRAGMA table_info(subscriptions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'custom_slug' not in columns:
            print("[OK] 为 subscriptions 表添加 custom_slug 字段...")
            # SQLite 不支持直接添加 UNIQUE 列，先添加普通列
            cursor.execute("""
                ALTER TABLE subscriptions ADD COLUMN custom_slug VARCHAR(100)
            """)
            print("   subscriptions 表迁移成功")
            
            # 创建唯一索引来保证唯一性
            try:
                cursor.execute("""
                    CREATE UNIQUE INDEX idx_subscriptions_custom_slug ON subscriptions(custom_slug) WHERE custom_slug IS NOT NULL
                """)
                print("   创建 subscriptions.custom_slug 唯一索引成功")
            except sqlite3.OperationalError:
                print("   索引已存在，跳过")
        else:
            print("[SKIP] subscriptions 表已有 custom_slug 字段，跳过")
        
        conn.commit()
        print("="*60)
        print("[SUCCESS] 数据库迁移完成！")
        print("\n新增功能说明:")
        print("- 用户和订阅分组现在支持自定义链接后缀")
        print("- 自定义后缀和系统生成的token都可以使用")
        print("- 在管理面板编辑用户时可以设置自定义后缀")
        print("\n示例:")
        print("  系统链接: https://your-domain/sub/user/7AWeu6YdLp_ey1pn49zQgIjNPNDMuueo3liQgUjMq9M")
        print("  自定义链接: https://your-domain/sub/user/my-custom-link")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("数据库迁移工具 - 添加自定义后缀支持")
    print("="*60 + "\n")
    
    migrate_database()

