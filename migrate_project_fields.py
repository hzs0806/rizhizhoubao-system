"""
数据库迁移脚本：为projects表添加新字段
执行方式：python migrate_project_fields.py
"""
from app import create_app
from models import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        engine = db.engine
        with engine.begin() as conn:
            # 检查并添加 project_goal
            rs = conn.execute(text("""
                SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='project_goal'
            """))
            if rs.scalar() == 0:
                conn.execute(text("ALTER TABLE projects ADD COLUMN project_goal TEXT NULL"))
                print("✓ 已添加 project_goal 字段")
            else:
                print("✓ project_goal 字段已存在")
            
            # 检查并添加 project_status
            rs = conn.execute(text("""
                SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='project_status'
            """))
            if rs.scalar() == 0:
                conn.execute(text("ALTER TABLE projects ADD COLUMN project_status VARCHAR(100) NULL"))
                print("✓ 已添加 project_status 字段")
            else:
                print("✓ project_status 字段已存在")
            
            # 检查并添加 hospital_logo
            rs = conn.execute(text("""
                SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='hospital_logo'
            """))
            if rs.scalar() == 0:
                conn.execute(text("ALTER TABLE projects ADD COLUMN hospital_logo VARCHAR(500) NULL"))
                print("✓ 已添加 hospital_logo 字段")
            else:
                print("✓ hospital_logo 字段已存在")
        
        print("\n✅ 数据库迁移完成！")
    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()

