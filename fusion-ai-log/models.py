from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """用户表"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    real_name = db.Column(db.String(100), nullable=False)  # 真实姓名（作为用户名）
    mac_address = db.Column(db.String(50), nullable=False)  # MAC地址（主设备）
    multi_device_token = db.Column(db.String(255), nullable=True)  # 多设备登录口令（加密存储）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联关系
    projects = db.relationship('Project', backref='user', lazy=True, cascade='all, delete-orphan')
    devices = db.relationship('UserDevice', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_multi_device_token(self, token):
        """设置多设备登录口令"""
        self.multi_device_token = generate_password_hash(token)
    
    def check_multi_device_token(self, token):
        """验证多设备登录口令"""
        if not self.multi_device_token:
            return False
        return check_password_hash(self.multi_device_token, token)
    
    def to_dict(self):
        return {
            'id': self.id,
            'real_name': self.real_name,
            'mac_address': self.mac_address,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

class UserDevice(db.Model):
    """用户设备表（用于多设备登录）"""
    __tablename__ = 'user_devices'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mac_address = db.Column(db.String(50), nullable=False)  # 设备MAC地址
    device_name = db.Column(db.String(100), nullable=True)  # 设备名称（可选）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 唯一约束：同一用户的同一MAC地址只能有一条记录
    __table_args__ = (db.UniqueConstraint('user_id', 'mac_address', name='unique_user_device'),)

class Project(db.Model):
    """项目表"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # 项目配置字段
    project_manager = db.Column(db.String(100), nullable=True)  # 项目经理
    dev_manager = db.Column(db.String(100), nullable=True)  # 研发经理
    business_manager = db.Column(db.String(100), nullable=True)  # 商务经理
    project_scope = db.Column(db.String(100), nullable=True)  # 项目范围
    project_goal = db.Column(db.Text, nullable=True)  # 项目目标
    project_status = db.Column(db.String(100), nullable=True)  # 项目状态
    hospital_logo = db.Column(db.String(500), nullable=True)  # 医院logo路径
    report_template = db.Column(db.String(500), nullable=True)  # 报告模板文件路径
    # 地域信息（用于IP匹配）
    region = db.Column(db.String(100), nullable=True)  # 地域/城市
    hospital_name = db.Column(db.String(200), nullable=True)  # 医院名称（用于提示）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 唯一约束：同一用户的项目名称不能重复
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='unique_user_project'),)
    
    # 关联关系
    logs = db.relationship('Log', backref='project', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'project_manager': self.project_manager,
            'dev_manager': self.dev_manager,
            'business_manager': self.business_manager,
            'project_scope': self.project_scope,
            'project_goal': self.project_goal,
            'project_status': self.project_status,
            'hospital_logo': self.hospital_logo,
            'report_template': self.report_template,
            'region': self.region,
            'hospital_name': self.hospital_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

class UserPreference(db.Model):
    """用户偏好（用户级记忆）"""
    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    # 以逗号分隔保存项目顺序，简单可靠（也可扩展为JSON）
    project_order = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'project_order': self.project_order or ''
        }

class EmailSetting(db.Model):
    """邮件发送设置"""
    __tablename__ = 'email_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    qq_email = db.Column(db.String(200), nullable=True)
    daily_enabled = db.Column(db.Boolean, default=False)
    weekly_enabled = db.Column(db.Boolean, default=False)
    # 可配置时间
    daily_time = db.Column(db.String(5), nullable=True, default='07:00')  # HH:MM 24h
    weekly_weekday = db.Column(db.Integer, nullable=True, default=4)  # 0-6 (周一=0)，默认周五
    weekly_time = db.Column(db.String(5), nullable=True, default='07:00')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'qq_email': self.qq_email or '',
            'daily_enabled': bool(self.daily_enabled),
            'weekly_enabled': bool(self.weekly_enabled),
            'daily_time': self.daily_time or '07:00',
            'weekly_weekday': self.weekly_weekday if self.weekly_weekday is not None else 4,
            'weekly_time': self.weekly_time or '07:00'
        }
class TaskCategory(db.Model):
    """任务分类表（固定11个分类）"""
    __tablename__ = 'task_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    order = db.Column(db.Integer, default=0)  # 排序字段
    
    # 关联关系
    logs = db.relationship('Log', backref='task_category', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'order': self.order
        }

class Log(db.Model):
    """日志记录表"""
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    task_category_id = db.Column(db.Integer, db.ForeignKey('task_categories.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # 新增字段
    project_status = db.Column(db.String(100), nullable=True)  # 项目状态
    need_product_support = db.Column(db.String(500), nullable=True, default='无')  # 需要产品支持
    need_dev_support = db.Column(db.String(500), nullable=True, default='无')  # 需要研发支持
    need_test_support = db.Column(db.String(500), nullable=True, default='无')  # 需要测试支持
    need_business_support = db.Column(db.String(500), nullable=True, default='无')  # 需要商务支持
    need_customer_support = db.Column(db.String(500), nullable=True, default='无')  # 需要客户支持
    next_plan = db.Column(db.Text, nullable=True)  # 下一步计划
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,
            'task_category_id': self.task_category_id,
            'task_category_name': self.task_category.name if self.task_category else None,
            'content': self.content,
            'project_status': self.project_status,
            'need_product_support': self.need_product_support,
            'need_dev_support': self.need_dev_support,
            'need_test_support': self.need_test_support,
            'need_business_support': self.need_business_support,
            'need_customer_support': self.need_customer_support,
            'next_plan': self.next_plan,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

