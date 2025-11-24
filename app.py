from flask import Flask
from flask_login import LoginManager
from config import Config
from models import db, User
from routes import register_routes
from scheduler import init_scheduler
from dotenv import load_dotenv
import os
import logging

# 加载.env文件中的环境变量
# 使用绝对路径和强制覆盖，确保 Gunicorn 运行时也能找到 .env 文件
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path, override=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # 初始化数据库
    db.init_app(app)
    
    # 初始化Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = '请先登录'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    # 注册路由
    register_routes(app)
    
    # 初始化定时任务
    init_scheduler(app)
    
    # 创建必要的目录
    os.makedirs(Config.REPORT_OUTPUT_DIR, exist_ok=True)
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.TEMPLATE_UPLOAD_FOLDER, exist_ok=True)
    
    # 创建数据库表
    with app.app_context():
        db.create_all()
        # 初始化任务分类数据
        from models import TaskCategory
        if TaskCategory.query.count() == 0:
            categories = [
                {'name': '服务器、算力配置沟通确认', 'order': 1},
                {'name': '接口对接', 'order': 2},
                {'name': '门诊业务调研', 'order': 3},
                {'name': '住院业务调研', 'order': 4},
                {'name': '医生电脑设备安装及软件安装', 'order': 5},
                {'name': '门诊-大模型配置', 'order': 6},
                {'name': '住院-大模型配置', 'order': 7},
                {'name': '系统功能验证', 'order': 8},
                {'name': '上线前准备工作', 'order': 9},
                {'name': '上线及培训', 'order': 10},
                {'name': '其他', 'order': 11}
            ]
            for cat in categories:
                task_cat = TaskCategory(name=cat['name'], order=cat['order'])
                db.session.add(task_cat)
            db.session.commit()
    
    return app

# 创建应用实例（供 Gunicorn 使用）
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

