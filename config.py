import os
from datetime import timedelta

class Config:
    """应用配置类"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # MySQL数据库配置
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = os.environ.get('DB_PORT') or '3306'
    DB_NAME = os.environ.get('DB_NAME') or 'rzzbxt'
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'mzfxpg'
    
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 周报生成配置
    REPORT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
    REPORT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'templates', 'word_templates', 'weekly_report_template.docx')
    
    # Logo上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'logos')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # 模板文件上传配置
    TEMPLATE_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'templates')
    ALLOWED_TEMPLATE_EXTENSIONS = {'docx', 'doc'}
    
    # 大模型API配置（预留，暂不启用）
    LLM_API_KEY = os.environ.get('LLM_API_KEY') or ''
    LLM_API_URL = os.environ.get('LLM_API_URL') or ''
    LLM_ENABLED = False  # 暂时禁用
    
    # 高德地图API配置
    AMAP_API_KEY = os.environ.get('AMAP_API_KEY') or ''  # 高德地图API Key，用于IP定位

    # 邮件SMTP配置（QQ邮箱）
    MAIL_HOST = os.environ.get('MAIL_HOST', 'smtp.qq.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '465'))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')  # QQ邮箱授权码
    MAIL_SENDER = os.environ.get('MAIL_SENDER', MAIL_USERNAME)
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
    
    # AI大模型API配置（用于日志整理）
    QWEN_API_KEY = os.environ.get('QWEN_API_KEY') or ''  # 通义千问API Key
    WENXIN_API_KEY = os.environ.get('WENXIN_API_KEY') or ''  # 文心一言API Key
    WENXIN_SECRET_KEY = os.environ.get('WENXIN_SECRET_KEY') or ''  # 文心一言Secret Key

