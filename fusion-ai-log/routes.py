from flask import Blueprint, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Project, Log, TaskCategory, User, UserDevice, UserPreference, EmailSetting
from datetime import datetime, date, timedelta
from report_generator import generate_weekly_report
from ip_location import get_location_by_ip, match_projects_by_location, get_hospital_location
from cities_data import CITIES_DATA, get_all_cities, get_cities_by_province, search_cities
from mac_address import validate_mac_address, normalize_mac_address
import os
from config import Config
from email_utils import send_email, build_email_body_by_project
from werkzeug.utils import secure_filename
import uuid

def register_routes(app):
    """注册所有路由"""
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """登录页面（基于MAC地址+真实姓名）"""
        import logging
        logger = logging.getLogger(__name__)
        if request.method == 'POST':
            real_name = request.form.get('real_name', '').strip()
            mac_address = request.form.get('mac_address', '').strip()
            multi_device_token = request.form.get('multi_device_token', '').strip()
            logger.info(f'[登录] POST real_name="{real_name}", mac="{mac_address}", has_token={bool(multi_device_token)}')
            
            if not real_name:
                flash('请输入真实姓名', 'error')
                return render_template('login.html')
            
            if not mac_address:
                flash('无法识别设备，请刷新页面重试', 'error')
                return render_template('login.html')
            
            # 标准化MAC地址
            mac_address = normalize_mac_address(mac_address)
            logger.info(f'[登录] 规范化MAC: {mac_address}')
            
            # 查找用户：先通过真实姓名+MAC地址查找
            user = User.query.filter_by(real_name=real_name, mac_address=mac_address).first()
            
            if user:
                # 主设备登录
                logger.info(f'[登录] 主设备登录成功 user_id={user.id}')
                login_user(user, remember=True)
                # 更新或创建设备记录
                device = UserDevice.query.filter_by(user_id=user.id, mac_address=mac_address).first()
                if device:
                    device.last_login = datetime.utcnow()
                else:
                    # 如果设备记录不存在，创建它
                    device = UserDevice(user_id=user.id, mac_address=mac_address)
                    db.session.add(device)
                db.session.commit()
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            
            # 尝试多设备登录：通过真实姓名+多设备口令查找
            if multi_device_token:
                user = User.query.filter_by(real_name=real_name).first()
                if user and user.check_multi_device_token(multi_device_token):
                    # 验证通过，添加新设备
                    device = UserDevice.query.filter_by(user_id=user.id, mac_address=mac_address).first()
                    if not device:
                        device = UserDevice(user_id=user.id, mac_address=mac_address)
                        db.session.add(device)
                    device.last_login = datetime.utcnow()
                    db.session.commit()
                    
                    logger.info(f'[登录] 多设备验证通过，添加新设备 user_id={user.id}')
                    login_user(user, remember=True)
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('index'))
                else:
                    logger.warning(f'[登录] 多设备口令校验失败 real_name="{real_name}"')
                    flash('多设备口令不正确', 'error')
                    return render_template('login.html')
            
            logger.info(f'[登录] 未找到匹配用户 real_name="{real_name}", mac="{mac_address}"')
            flash('登录失败：姓名或设备不匹配，如使用新设备请提供多设备登录口令', 'error')
        
        # GET请求：检查设备指纹是否匹配，如果匹配则自动登录
        mac_address = request.args.get('mac_address', '').strip()
        if mac_address:
            mac_address = normalize_mac_address(mac_address)
            # 通过设备指纹查找用户
            device = UserDevice.query.filter_by(mac_address=mac_address).first()
            if device:
                user = User.query.get(device.user_id)
                if user:
                    # 自动登录
                    login_user(user, remember=True)
                    device.last_login = datetime.utcnow()
                    db.session.commit()
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('index'))
            else:
                logger.info(f'[登录] 新设备首次访问，mac={mac_address} 未登记，等待用户输入姓名与多设备口令')
        
        return render_template('login.html')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """注册页面（基于MAC地址+真实姓名）"""
        if request.method == 'POST':
            real_name = request.form.get('real_name', '').strip()
            mac_address = request.form.get('mac_address', '').strip()
            multi_device_token = request.form.get('multi_device_token', '').strip()
            
            if not real_name:
                flash('请输入真实姓名', 'error')
                return render_template('register.html')
            
            if not mac_address:
                flash('无法识别设备，请刷新页面重试', 'error')
                return render_template('register.html')
            
            if not multi_device_token:
                flash('请设置多设备登录口令', 'error')
                return render_template('register.html')
            
            # 标准化MAC地址
            mac_address = normalize_mac_address(mac_address)
            
            if not validate_mac_address(mac_address):
                flash('设备标识无效，请刷新页面重试', 'error')
                return render_template('register.html')
            
            # 检查真实姓名+MAC地址是否已存在
            existing_user = User.query.filter_by(real_name=real_name, mac_address=mac_address).first()
            if existing_user:
                flash('该姓名和设备已注册，请直接登录', 'error')
                return redirect(url_for('login'))
            
            # 检查是否是添加设备模式
            is_add_device = request.form.get('is_add_device', '').strip() == '1'
            
            if is_add_device:
                # 添加新设备模式：通过真实姓名+多设备登录口令验证
                existing_user = User.query.filter_by(real_name=real_name).first()
                if not existing_user:
                    flash('该姓名未注册，请先完成首次注册', 'error')
                    return render_template('register.html', is_add_device=False)
                
                # 验证多设备登录口令
                if not existing_user.check_multi_device_token(multi_device_token):
                    flash('多设备登录口令错误', 'error')
                    return redirect(url_for('register', add_device=1))
                
                # 检查设备是否已添加
                existing_device = UserDevice.query.filter_by(user_id=existing_user.id, mac_address=mac_address).first()
                if existing_device:
                    flash('该设备已添加，请直接登录', 'error')
                    return redirect(url_for('login'))
                
                # 添加新设备
                device = UserDevice(user_id=existing_user.id, mac_address=mac_address)
                db.session.add(device)
                db.session.commit()
                
                # 自动登录
                login_user(existing_user, remember=True)
                flash('新设备添加成功！', 'success')
                return redirect(url_for('index'))
            else:
                # 首次注册模式
                # 检查真实姓名是否已存在（可能是其他设备注册的）
                existing_name = User.query.filter_by(real_name=real_name).first()
                if existing_name:
                    flash('该姓名已注册，如使用新设备请使用多设备登录口令添加设备', 'error')
                    return redirect(url_for('register', add_device=1))
                
                # 创建新用户
                user = User(real_name=real_name, mac_address=mac_address)
                user.set_multi_device_token(multi_device_token)
                db.session.add(user)
                db.session.flush()  # 刷新以获取user.id，但不提交事务
                
                # 创建主设备记录（此时user.id已经可用）
                device = UserDevice(user_id=user.id, mac_address=mac_address)
                db.session.add(device)
                
                db.session.commit()
                
                flash('注册成功！请使用您的姓名登录', 'success')
                return redirect(url_for('login'))
        
        return render_template('register.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        """登出"""
        logout_user()
        flash('已成功登出', 'info')
        return redirect(url_for('login'))
    
    @app.route('/')
    @login_required
    def index():
        """项目展示首页"""
        from sqlalchemy import func
        
        # 优化：使用聚合查询一次性获取所有项目的日志统计，避免N+1查询
        projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
        
        if not projects:
            return render_template('projects_dashboard.html', 
                                 projects_data=[],
                                 show_first_time_tip=False,
                                 location={},
                                 matched_count=0)
        
        # 批量查询日志统计（使用聚合查询优化，避免N+1问题）
        project_ids = [p.id for p in projects]
        
        # 查询每个项目的日志数量和最新日志日期（一次性查询所有项目）
        from sqlalchemy import func
        log_stats = db.session.query(
            Log.project_id,
            func.count(Log.id).label('log_count'),
            func.max(Log.date).label('latest_date')
        ).filter(Log.project_id.in_(project_ids)).group_by(Log.project_id).all()
        
        # 转换为字典便于查找（O(1)查找）
        stats_dict = {stat.project_id: {'count': stat.log_count, 'latest_date': stat.latest_date} for stat in log_stats}
        
        # 性能优化：暂时关闭定位匹配推荐功能，避免首页加载变慢
        matched_projects = []
        location = {}
        matched_count = 0
        matched_project_ids = set()
        
        # 组装项目数据，并按匹配度排序
        projects_data = []
        matched_data = []  # 匹配的项目
        unmatched_data = []  # 未匹配的项目
        
        for project in projects:
            stats = stats_dict.get(project.id, {'count': 0, 'latest_date': None})
            
            project_data = {
                'project': project,
                'log_count': stats['count'],
                'latest_log_date': stats['latest_date'],
                'is_matched': project.id in matched_project_ids
            }
            
            if project.id in matched_project_ids:
                matched_data.append(project_data)
            else:
                unmatched_data.append(project_data)
        
        # 合并：匹配的项目在前，未匹配的项目在后
        projects_data = matched_data + unmatched_data
        
        # 检查是否是第一次创建项目（只有1个项目且URL参数中有created=1）
        show_first_time_tip = False
        created_param = request.args.get('created')
        project_count = len(projects)
        
        # 调试日志
        print(f'[DEBUG] created参数: {created_param}, 项目数量: {project_count}')
        
        if created_param == '1' and project_count == 1:
            show_first_time_tip = True
            print(f'[DEBUG] 显示第一次创建项目的引导提示')
        
        return render_template('projects_dashboard.html', 
                             projects_data=projects_data,
                             show_first_time_tip=show_first_time_tip,
                             location=location,
                             matched_count=matched_count)
    
    @app.route('/email/settings')
    @login_required
    def email_settings_page():
        """邮件设置页面"""
        setting = EmailSetting.query.filter_by(user_id=current_user.id).first()
        return render_template('email_settings.html', setting=setting)
    
    @app.route('/api/email-settings', methods=['GET'])
    @login_required
    def get_email_settings():
        setting = EmailSetting.query.filter_by(user_id=current_user.id).first()
        return jsonify(setting.to_dict() if setting else {
            'user_id': current_user.id,
            'qq_email': '',
            'daily_enabled': False,
            'weekly_enabled': False,
            'daily_time': '07:00',
            'weekly_weekday': 4,
            'weekly_time': '07:00'
        })
    
    @app.route('/api/email-settings', methods=['POST'])
    @login_required
    def save_email_settings():
        data = request.json or {}
        qq_email = (data.get('qq_email') or '').strip()
        daily_enabled = bool(data.get('daily_enabled'))
        weekly_enabled = bool(data.get('weekly_enabled'))
        daily_time = (data.get('daily_time') or '07:00')[:5]
        weekly_time = (data.get('weekly_time') or '07:00')[:5]
        weekly_weekday = data.get('weekly_weekday')
        try:
            weekly_weekday = int(weekly_weekday) if weekly_weekday is not None else 4
            if weekly_weekday < 0 or weekly_weekday > 6:
                weekly_weekday = 4
        except Exception:
            weekly_weekday = 4
        setting = EmailSetting.query.filter_by(user_id=current_user.id).first()
        if not setting:
            setting = EmailSetting(user_id=current_user.id)
            db.session.add(setting)
        setting.qq_email = qq_email or None
        setting.daily_enabled = daily_enabled
        setting.weekly_enabled = weekly_enabled
        setting.daily_time = daily_time
        setting.weekly_time = weekly_time
        setting.weekly_weekday = weekly_weekday
        db.session.commit()
        return jsonify({'success': True})
    
    @app.route('/api/email/test', methods=['POST'])
    @login_required
    def test_email_send():
        """测试发送：发送当天的日志摘要到qq邮箱"""
        try:
            setting = EmailSetting.query.filter_by(user_id=current_user.id).first()
            if not setting or not setting.qq_email:
                return jsonify({'success': False, 'message': '请先在邮件设置中配置QQ邮箱'}), 400
            
            # 检查邮件配置
            from config import Config
            if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
                return jsonify({'success': False, 'message': '邮件服务器配置缺失，请检查环境变量 MAIL_USERNAME 和 MAIL_PASSWORD'}), 500
            
            # 今日日志摘要（按项目预览格式组织）
            today_date = date.today()
            projects = Project.query.filter_by(user_id=current_user.id).all()
            project_ids = [p.id for p in projects]
            logs = Log.query.filter(Log.project_id.in_(project_ids)).filter(Log.date == today_date).order_by(Log.project_id, Log.created_at).all()
            body = build_email_body_by_project(logs, projects, header=f'【{today_date}】实施日志（测试发送）')
            
            ok = send_email(setting.qq_email, f'今日日志（测试发送）-{today_date}', body, attachments=[])
            if ok:
                return jsonify({'success': True, 'message': '测试邮件发送成功，请检查邮箱'})
            else:
                return jsonify({'success': False, 'message': '邮件发送失败，请检查邮件服务器配置和日志'}), 500
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception('测试邮件发送异常')
            return jsonify({'success': False, 'message': f'发送失败：{str(e)}'}), 500

    @app.route('/admin/migrate/email-settings', methods=['POST'])
    @login_required
    def migrate_email_settings_columns():
        """为email_settings表补齐可配置时间的字段（每日/每周），避免Unknown column错误"""
        try:
            engine = db.engine
            with engine.connect() as conn:
                # 检查并添加 daily_time
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='email_settings' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='daily_time'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE email_settings ADD COLUMN daily_time VARCHAR(5) NULL DEFAULT '07:00'"))
                # weekly_weekday
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='email_settings' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='weekly_weekday'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE email_settings ADD COLUMN weekly_weekday INT NULL DEFAULT 4"))
                # weekly_time
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='email_settings' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='weekly_time'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE email_settings ADD COLUMN weekly_time VARCHAR(5) NULL DEFAULT '07:00'"))
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/admin/migrate/project-fields', methods=['POST'])
    @login_required
    def migrate_project_fields():
        """为projects表添加新字段：project_goal、project_status、hospital_logo"""
        try:
            engine = db.engine
            with engine.begin() as conn:
                # 检查并添加 project_goal
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='project_goal'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE projects ADD COLUMN project_goal TEXT NULL"))
                
                # 检查并添加 project_status
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='project_status'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE projects ADD COLUMN project_status VARCHAR(100) NULL"))
                
                # 检查并添加 hospital_logo
                rs = conn.execute(db.text("""
                    SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='projects' AND TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='hospital_logo'
                """))
                if rs.scalar() == 0:
                    conn.execute(db.text("ALTER TABLE projects ADD COLUMN hospital_logo VARCHAR(500) NULL"))
            
            return jsonify({'success': True, 'message': '项目表字段迁移成功'})
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"迁移项目字段错误: {error_msg}")
            print(traceback.format_exc())
            return jsonify({'success': False, 'message': f'迁移失败: {error_msg}'}), 500
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/log/create')
    @login_required
    def create_log():
        """日志录入页面"""
        # 从URL参数获取项目ID
        project_id = request.args.get('project_id')
        selected_project = None
        existing_log = None
        
        if project_id:
            # 如果提供了项目ID，直接获取项目信息
            selected_project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
            if not selected_project:
                flash('项目不存在或无权限访问', 'error')
                return redirect(url_for('index'))
            # 检查今天是否已存在日志
            today_date = date.today()
            existing_log = Log.query.filter_by(project_id=selected_project.id).filter(Log.date == today_date).first()
        
        projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
        task_categories = TaskCategory.query.order_by(TaskCategory.order).all()
        return render_template('index.html', 
                             projects=projects, 
                             task_categories=task_categories,
                             today=date.today().strftime('%Y-%m-%d'),
                             selected_project=selected_project,
                             existing_log=existing_log)
    
    @app.route('/logs')
    @login_required
    def logs():
        """日志中心页面"""
        projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
        task_categories = TaskCategory.query.order_by(TaskCategory.order).all()
        return render_template('logs.html', projects=projects, task_categories=task_categories)
    
    @app.route('/projects')
    @login_required
    def projects():
        """项目配置页面"""
        return render_template('projects.html')
    
    @app.route('/report')
    @login_required
    def report():
        """周报生成页面"""
        projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
        return render_template('report.html', projects=projects)
    
    # API路由
    api = Blueprint('api', __name__, url_prefix='/api')
    
    @api.route('/check-device', methods=['GET'])
    def check_device():
        """检查设备指纹是否已注册（用于自动登录）"""
        mac_address = request.args.get('mac_address', '').strip()
        if not mac_address:
            return jsonify({'matched': False})
        
        mac_address = normalize_mac_address(mac_address)
        
        # 查找设备记录
        device = UserDevice.query.filter_by(mac_address=mac_address).first()
        if device:
            user = User.query.get(device.user_id)
            if user:
                return jsonify({
                    'matched': True,
                    'user_id': user.id,
                    'real_name': user.real_name
                })
        
        return jsonify({'matched': False})
    
    @api.route('/projects', methods=['GET'])
    @login_required
    def get_projects():
        """获取当前用户的所有项目"""
        projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
        projects_list = [p.to_dict() for p in projects]
        # 应用用户级项目顺序（如果存在）
        pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if pref and pref.project_order:
            try:
                order_ids = [int(pid) for pid in pref.project_order.split(',') if pid.strip().isdigit()]
                order_index = {pid: idx for idx, pid in enumerate(order_ids)}
                projects_list.sort(key=lambda x: order_index.get(x['id'], len(order_index)))
            except Exception:
                pass
        return jsonify(projects_list)

    @api.route('/project-order', methods=['GET'])
    @login_required
    def get_project_order():
        """获取当前用户保存的项目顺序"""
        pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        project_order = pref.project_order if pref and pref.project_order else ''
        return jsonify({'project_order': project_order})

    @api.route('/project-order', methods=['POST'])
    @login_required
    def set_project_order():
        """保存当前用户的项目顺序"""
        data = request.json or {}
        order_list = data.get('order', [])
        if not isinstance(order_list, list):
            return jsonify({'success': False, 'message': 'order 必须为数组'}), 400
        # 仅保留当前用户的项目ID
        user_project_ids = {p.id for p in Project.query.filter_by(user_id=current_user.id).all()}
        filtered = [str(pid) for pid in order_list if isinstance(pid, int) and pid in user_project_ids]
        pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if not pref:
            pref = UserPreference(user_id=current_user.id, project_order=','.join(filtered))
            db.session.add(pref)
        else:
            pref.project_order = ','.join(filtered)
        db.session.commit()
        return jsonify({'success': True})
    
    @api.route('/location', methods=['GET'])
    @login_required
    def get_location():
        """获取客户端IP位置信息"""
        client_ip = request.remote_addr
        # 尝试从X-Forwarded-For获取真实IP（如果使用代理）
        if request.headers.get('X-Forwarded-For'):
            client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        
        location = get_location_by_ip(client_ip)
        return jsonify(location)
    
    @api.route('/hospital/location', methods=['GET'])
    @login_required
    def api_hospital_location():
        """通过项目名称/医院名称查询医院所在地（高德地理编码）"""
        name = (request.args.get('name') or '').strip()
        hospital_name = (request.args.get('hospital_name') or '').strip()
        city_hint = (request.args.get('city') or '').strip() or None
        
        if not hospital_name and not name:
            return jsonify({'success': False, 'message': 'name 或 hospital_name 至少提供一个'}), 400
        try:
            import logging, time
            logger = logging.getLogger(__name__)
            start_ts = time.time()
            logger.info(f'[医院定位][请求] name="{name}", hospital_name="{hospital_name}", city_hint="{city_hint}"')
            result = get_hospital_location(
                hospital_name=hospital_name or None,
                project_name=name or None,
                city=city_hint
            )
            elapsed_ms = int((time.time() - start_ts) * 1000)
            if result:
                logger.info(f'[医院定位][成功] {result.get("province","")}-{result.get("city","")} | '
                            f'addr="{result.get("formatted_address","")}" | {elapsed_ms} ms')
            else:
                logger.warning(f'[医院定位][未命中] name="{name}", hospital_name="{hospital_name}" | {elapsed_ms} ms')
            return jsonify({'success': bool(result), 'data': result, 'elapsed_ms': elapsed_ms})
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f'[医院定位][异常] name="{name}", hospital_name="{hospital_name}"')
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @api.route('/projects/match', methods=['GET'])
    @login_required
    def match_projects():
        """根据IP位置匹配项目"""
        # 获取客户端IP（支持VPN和代理）
        client_ip = request.remote_addr
        
        # 尝试从多个头部获取真实IP
        forwarded_for = request.headers.get('X-Forwarded-For')
        real_ip = request.headers.get('X-Real-IP')
        cf_connecting_ip = request.headers.get('CF-Connecting-IP')  # Cloudflare
        
        if cf_connecting_ip:
            client_ip = cf_connecting_ip.split(',')[0].strip()
        elif forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
        elif real_ip:
            client_ip = real_ip.strip()
        
        # 使用外网IP进行定位（get_location_by_ip会自动获取外网IP）
        # 传入None让函数自动获取外网IP，而不是使用客户端IP
        location = get_location_by_ip(None)
        projects = Project.query.filter_by(user_id=current_user.id).all()
        projects_dict = [p.to_dict() for p in projects]
        
        matched = match_projects_by_location(location, projects_dict)
        
        return jsonify({
            'location': location,
            'matched_projects': matched,
            'all_projects': projects_dict,
            'client_ip': client_ip,
            'public_ip': location.get('ip', client_ip)  # 返回实际使用的外网IP
        })
    
    def allowed_file(filename):
        """检查文件扩展名是否允许"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    
    def allowed_template_file(filename):
        """检查模板文件扩展名是否允许"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_TEMPLATE_EXTENSIONS
    
    def save_logo_file(file, project_id):
        """保存logo文件"""
        if file and allowed_file(file.filename):
            # 确保上传目录存在
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            # 生成唯一文件名
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"project_{project_id}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            # 返回相对路径
            return f"/static/uploads/logos/{filename}"
        return None
    
    def save_template_file(file, project_id):
        """保存模板文件"""
        if file and allowed_template_file(file.filename):
            # 确保上传目录存在
            os.makedirs(Config.TEMPLATE_UPLOAD_FOLDER, exist_ok=True)
            # 生成唯一文件名
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"project_{project_id}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(Config.TEMPLATE_UPLOAD_FOLDER, filename)
            file.save(filepath)
            # 返回绝对路径（用于docxtpl加载）
            return filepath
        return None
    
    @api.route('/projects', methods=['POST'])
    @login_required
    def create_project():
        """创建新项目"""
        # 支持FormData和JSON两种格式
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            logo_file = request.files.get('hospital_logo')
            template_file = request.files.get('report_template')
        else:
            data = request.json or {}
            logo_file = None
            template_file = None
        
        name = (data.get('name') or '').strip()
        project_manager = (data.get('project_manager') or '').strip() or None
        dev_manager = (data.get('dev_manager') or '').strip() or None
        business_manager = (data.get('business_manager') or '').strip() or None
        region = (data.get('region') or '').strip() or None
        hospital_name = (data.get('hospital_name') or '').strip() or None
        project_goal = (data.get('project_goal') or '').strip() or None
        project_status = (data.get('project_status') or '').strip() or None
        
        if not name:
            return jsonify({'success': False, 'message': '项目名称不能为空'}), 400
        
        # 验证当前用户是否存在
        if not current_user or not current_user.id:
            return jsonify({'success': False, 'message': '用户信息无效，请重新登录'}), 403
        
        # 检查当前用户是否已有同名项目
        if Project.query.filter_by(user_id=current_user.id, name=name).first():
            return jsonify({'success': False, 'message': '项目名称已存在'}), 400
        
        try:
            project = Project(
                name=name,
                user_id=current_user.id,
                project_manager=project_manager,
                dev_manager=dev_manager,
                business_manager=business_manager,
                project_scope=(data.get('project_scope') or '').strip() or None,
                project_goal=project_goal,
                project_status=project_status,
                region=region,
                hospital_name=hospital_name
            )
            db.session.add(project)
            db.session.flush()  # 获取project.id
            
            # 处理logo上传
            if logo_file:
                logo_path = save_logo_file(logo_file, project.id)
                if logo_path:
                    project.hospital_logo = logo_path
            
            # 处理模板文件上传
            if template_file:
                template_path = save_template_file(template_file, project.id)
                if template_path:
                    project.report_template = template_path
            
            db.session.commit()
            
            return jsonify({'success': True, 'data': project.to_dict()})
        except Exception as e:
            db.session.rollback()
            error_msg = str(e)
            # 检查是否是唯一约束错误
            if 'unique_user_project' in error_msg or 'Duplicate entry' in error_msg:
                return jsonify({'success': False, 'message': '项目名称已存在'}), 400
            # 检查是否是外键约束错误
            elif 'foreign key' in error_msg.lower() or 'user_id' in error_msg.lower():
                return jsonify({'success': False, 'message': '用户信息无效，请重新登录'}), 403
            else:
                # 返回详细错误信息（开发环境）
                import traceback
                print(f"创建项目错误: {error_msg}")
                print(traceback.format_exc())
                return jsonify({'success': False, 'message': f'创建项目失败: {error_msg}'}), 500
    
    @api.route('/projects/<int:project_id>', methods=['PUT'])
    @login_required
    def update_project(project_id):
        """更新项目"""
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        
        # 支持FormData和JSON两种格式
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            logo_file = request.files.get('hospital_logo')
            template_file = request.files.get('report_template')
        else:
            data = request.json or {}
            logo_file = None
            template_file = None
        
        if 'name' in data:
            name = (data['name'] or '').strip()
            if name and name != project.name:
                # 检查新名称是否已存在
                if Project.query.filter_by(user_id=current_user.id, name=name).first():
                    return jsonify({'success': False, 'message': '项目名称已存在'}), 400
                project.name = name
        
        if 'project_manager' in data:
            project.project_manager = (data['project_manager'] or '').strip() or None
        if 'dev_manager' in data:
            project.dev_manager = (data['dev_manager'] or '').strip() or None
        if 'business_manager' in data:
            project.business_manager = (data['business_manager'] or '').strip() or None
        if 'project_scope' in data:
            project.project_scope = (data['project_scope'] or '').strip() or None
        if 'project_goal' in data:
            project.project_goal = (data['project_goal'] or '').strip() or None
        if 'project_status' in data:
            project.project_status = (data['project_status'] or '').strip() or None
        if 'region' in data:
            project.region = (data['region'] or '').strip() or None
        if 'hospital_name' in data:
            project.hospital_name = (data['hospital_name'] or '').strip() or None
        
        # 处理logo上传
        if logo_file:
            # 删除旧logo（如果存在）
            if project.hospital_logo:
                old_logo_path = os.path.join(os.path.dirname(__file__), project.hospital_logo.lstrip('/'))
                if os.path.exists(old_logo_path):
                    try:
                        os.remove(old_logo_path)
                    except:
                        pass
            # 保存新logo
            logo_path = save_logo_file(logo_file, project.id)
            if logo_path:
                project.hospital_logo = logo_path
        
        # 处理模板文件上传或移除
        if template_file:
            # 检查是否是移除标记
            if isinstance(template_file, str) and template_file == 'removed':
                # 删除旧模板（如果存在）
                if project.report_template and os.path.exists(project.report_template):
                    try:
                        os.remove(project.report_template)
                    except:
                        pass
                project.report_template = None
            else:
                # 删除旧模板（如果存在）
                if project.report_template and os.path.exists(project.report_template):
                    try:
                        os.remove(project.report_template)
                    except:
                        pass
                # 保存新模板
                template_path = save_template_file(template_file, project.id)
                if template_path:
                    project.report_template = template_path
        elif 'report_template' in data and data['report_template'] == 'removed':
            # 处理JSON格式的移除请求
            if project.report_template and os.path.exists(project.report_template):
                try:
                    os.remove(project.report_template)
                except:
                    pass
            project.report_template = None
        
        db.session.commit()
        return jsonify({'success': True, 'data': project.to_dict()})
    
    @api.route('/projects/<int:project_id>', methods=['DELETE'])
    @login_required
    def delete_project(project_id):
        """删除项目"""
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        db.session.delete(project)
        db.session.commit()
        return jsonify({'success': True})
    
    @api.route('/projects/<int:project_id>/stats', methods=['GET'])
    @login_required
    def get_project_stats(project_id):
        """获取项目统计信息（日志数量和最新日志日期）"""
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        
        from sqlalchemy import func
        stats = db.session.query(
            func.count(Log.id).label('log_count'),
            func.max(Log.date).label('latest_date')
        ).filter_by(project_id=project_id).first()
        
        return jsonify({
            'log_count': stats.log_count or 0,
            'latest_log_date': stats.latest_date.strftime('%Y-%m-%d') if stats.latest_date else None
        })
    
    @api.route('/task-categories', methods=['GET'])
    @login_required
    def get_task_categories():
        """获取所有任务分类"""
        categories = TaskCategory.query.order_by(TaskCategory.order).all()
        return jsonify([c.to_dict() for c in categories])
    
    @api.route('/cities', methods=['GET'])
    @login_required
    def get_cities():
        """获取城市数据"""
        province = request.args.get('province', '').strip()
        search = request.args.get('search', '').strip()
        
        if search:
            # 搜索城市
            cities = search_cities(search)
            return jsonify({
                'type': 'search',
                'data': cities[:50]  # 限制返回数量
            })
        elif province:
            # 获取指定省份的城市
            cities = get_cities_by_province(province)
            return jsonify({
                'type': 'province',
                'data': cities
            })
        else:
            # 返回所有省份和城市结构
            return jsonify({
                'type': 'all',
                'data': CITIES_DATA
            })
    
    @api.route('/logs', methods=['POST'])
    @login_required
    def create_log():
        """创建日志"""
        data = request.json
        project_id = data.get('project_id')
        log_date = data.get('date')
        task_category_id = data.get('task_category_id')
        content = data.get('content', '').strip()
        project_status = (data.get('project_status') or '').strip() or None
        need_product_support = (data.get('need_product_support') or '无').strip() or '无'
        need_dev_support = (data.get('need_dev_support') or '无').strip() or '无'
        need_test_support = (data.get('need_test_support') or '无').strip() or '无'
        need_business_support = (data.get('need_business_support') or '无').strip() or '无'
        need_customer_support = (data.get('need_customer_support') or '无').strip() or '无'
        next_plan = (data.get('next_plan') or '').strip() or None
        
        if not all([project_id, log_date, task_category_id]):
            return jsonify({'success': False, 'message': '请填写完整信息'}), 400
        
        if not content:
            return jsonify({'success': False, 'message': '工作内容不能为空'}), 400
        
        # 验证项目属于当前用户
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
        if not project:
            return jsonify({'success': False, 'message': '项目不存在或无权限'}), 403
        
        try:
            log_date = datetime.strptime(log_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': '日期格式错误'}), 400
        
        # 去重：同一项目同一天仅允许一条日志
        existed = Log.query.filter_by(project_id=project_id).filter(Log.date == log_date).first()
        if existed:
            return jsonify({
                'success': False,
                'message': '今日该项目日志已存在，已为您加载。',
                'conflict': True,
                'data': existed.to_dict()
            }), 409
        
        # 如果没有指定项目状态，使用任务分类作为默认状态
        if not project_status:
            task_category = TaskCategory.query.get(task_category_id)
            project_status = task_category.name if task_category else None
        
        log = Log(
            project_id=project_id,
            date=log_date,
            task_category_id=task_category_id,
            content=content,
            project_status=project_status,
            need_product_support=need_product_support,
            need_dev_support=need_dev_support,
            need_test_support=need_test_support,
            need_business_support=need_business_support,
            need_customer_support=need_customer_support,
            next_plan=next_plan
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'data': log.to_dict()})
    
    @api.route('/logs/<int:log_id>', methods=['PUT'])
    @login_required
    def update_log(log_id):
        """更新日志"""
        log = Log.query.get_or_404(log_id)
        
        # 验证日志所属项目属于当前用户
        if log.project.user_id != current_user.id:
            return jsonify({'success': False, 'message': '无权限操作'}), 403
        
        data = request.json
        
        if 'project_id' in data:
            # 验证新项目属于当前用户
            new_project = Project.query.filter_by(id=data['project_id'], user_id=current_user.id).first()
            if not new_project:
                return jsonify({'success': False, 'message': '项目不存在或无权限'}), 403
            log.project_id = data['project_id']
        
        if 'date' in data:
            try:
                log.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': '日期格式错误'}), 400
        
        if 'task_category_id' in data:
            log.task_category_id = data['task_category_id']
        
        if 'content' in data:
            content = data['content'].strip()
            if not content:
                return jsonify({'success': False, 'message': '工作内容不能为空'}), 400
            log.content = content
        
        if 'next_plan' in data:
            log.next_plan = data['next_plan'].strip() if data['next_plan'] else None
        
        # 更新支持字段
        if 'need_product_support' in data:
            log.need_product_support = data['need_product_support'].strip() if data['need_product_support'] else '无'
        if 'need_dev_support' in data:
            log.need_dev_support = data['need_dev_support'].strip() if data['need_dev_support'] else '无'
        if 'need_test_support' in data:
            log.need_test_support = data['need_test_support'].strip() if data['need_test_support'] else '无'
        if 'need_business_support' in data:
            log.need_business_support = data['need_business_support'].strip() if data['need_business_support'] else '无'
        if 'need_customer_support' in data:
            log.need_customer_support = data['need_customer_support'].strip() if data['need_customer_support'] else '无'
        
        log.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'data': log.to_dict()})
    
    @api.route('/logs/<int:log_id>', methods=['DELETE'])
    @login_required
    def delete_log(log_id):
        """删除日志"""
        log = Log.query.get_or_404(log_id)
        
        # 验证日志所属项目属于当前用户
        if log.project.user_id != current_user.id:
            return jsonify({'success': False, 'message': '无权限操作'}), 403
        
        db.session.delete(log)
        db.session.commit()
        return jsonify({'success': True})
    
    @api.route('/logs', methods=['GET'])
    @login_required
    def get_logs():
        """获取当前用户的日志列表（支持筛选）"""
        project_id = request.args.get('project_id', type=int)
        week_start = request.args.get('week_start')
        date_str = request.args.get('date')
        search = request.args.get('search', '').strip()
        
        # 构建查询：先获取当前用户的所有项目ID
        user_project_ids = [p.id for p in Project.query.filter_by(user_id=current_user.id).all()]
        
        if not user_project_ids:
            return jsonify([])
        
        # 基于项目ID查询日志
        query = Log.query.filter(Log.project_id.in_(user_project_ids))
        
        if project_id:
            # 验证项目属于当前用户
            if project_id not in user_project_ids:
                return jsonify([])
            query = query.filter(Log.project_id == project_id)
        
        if week_start:
            try:
                week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
                week_end_date = week_start_date + timedelta(days=6)
                query = query.filter(Log.date >= week_start_date, Log.date <= week_end_date)
            except ValueError:
                pass
        
        if date_str:
            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                query = query.filter(Log.date == log_date)
            except ValueError:
                pass
        
        if search:
            query = query.filter(Log.content.like(f'%{search}%'))
        
        logs = query.order_by(Log.date.desc(), Log.created_at.desc()).all()
        
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'查询日志: project_id={project_id}, week_start={week_start}, 找到 {len(logs)} 条日志')
        
        return jsonify([log.to_dict() for log in logs])
    
    @api.route('/weeks', methods=['GET'])
    @login_required
    def get_weeks():
        """获取项目的周列表"""
        project_id = request.args.get('project_id', type=int)
        if not project_id:
            return jsonify([])
        
        # 验证项目属于当前用户
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
        if not project:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'用户 {current_user.id} 尝试访问不属于自己的项目 {project_id}')
            return jsonify([])
        
        # 获取该项目所有日志的日期
        logs = Log.query.filter_by(project_id=project_id).order_by(Log.date).all()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'项目 {project_id} 共有 {len(logs)} 条日志')
        
        if not logs:
            return jsonify([])
        
        # 计算所有周的开始日期
        weeks = set()
        for log in logs:
            # 计算该日期所在周的开始日期（周一）
            days_since_monday = log.date.weekday()
            week_start = log.date - timedelta(days=days_since_monday)
            weeks.add(week_start)
        
        weeks = sorted(list(weeks), reverse=True)
        
        # 格式化返回
        result = []
        for week_start in weeks:
            week_end = week_start + timedelta(days=6)
            # 计算是第几周（从项目开始日期算起）
            first_date = logs[0].date
            days_diff = (week_start - first_date).days
            week_num = (days_diff // 7) + 1
            
            result.append({
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'week_num': week_num,
                'display': f'第{week_num}周 ({week_start.strftime("%Y-%m-%d")} 至 {week_end.strftime("%Y-%m-%d")})'
            })
        
        logger.info(f'项目 {project_id} 共有 {len(result)} 个周')
        return jsonify(result)
    
    @api.route('/dates', methods=['GET'])
    @login_required
    def get_dates():
        """获取指定周的日期列表"""
        project_id = request.args.get('project_id', type=int)
        week_start = request.args.get('week_start')
        
        if not project_id or not week_start:
            return jsonify([])
        
        # 验证项目属于当前用户
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
        if not project:
            return jsonify([])
        
        try:
            week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
        except ValueError:
            return jsonify([])
        
        week_end_date = week_start_date + timedelta(days=6)
        
        # 获取该周有日志的日期
        logs = Log.query.filter_by(project_id=project_id).filter(
            Log.date >= week_start_date,
            Log.date <= week_end_date
        ).order_by(Log.date).all()
        
        dates = sorted(set([log.date for log in logs]), reverse=True)
        
        result = [{
            'date': d.strftime('%Y-%m-%d'),
            'display': d.strftime('%Y年%m月%d日')
        } for d in dates]
        
        return jsonify(result)
    
    @api.route('/report/generate', methods=['POST'])
    @login_required
    def generate_report():
        """生成周报"""
        data = request.json
        project_id = data.get('project_id')
        week_start = data.get('week_start')
        format_type = data.get('format', 'word')  # 'word' or 'pdf'
        
        if not project_id or not week_start:
            return jsonify({'success': False, 'message': '请选择项目和周'}), 400
        
        # 验证项目属于当前用户
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        
        try:
            week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': '日期格式错误'}), 400
        
        file_path = generate_weekly_report(project, week_start_date, format_type)
        
        if file_path and os.path.exists(file_path):
            return jsonify({
                'success': True,
                'file_path': file_path,
                'filename': os.path.basename(file_path)
            })
        else:
            return jsonify({'success': False, 'message': '生成周报失败'}), 500
    
    @api.route('/report/download/<path:filename>')
    @login_required
    def download_report(filename):
        """下载周报文件"""
        file_path = os.path.join(Config.REPORT_OUTPUT_DIR, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    
    app.register_blueprint(api)
