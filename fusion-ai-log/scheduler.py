from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from models import db, Project, Log, EmailSetting
from report_generator import generate_weekly_report
from email_utils import send_email, build_email_body_by_project
from flask import Flask

scheduler = None

def init_scheduler(app: Flask):
    """初始化定时任务"""
    global scheduler
    
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        
        # 添加每周六9:00执行的任务
        scheduler.add_job(
            func=generate_weekly_reports_job,
            trigger=CronTrigger(day_of_week='sat', hour=9, minute=0),
            id='weekly_report_generation',
            name='每周六9点生成周报',
            replace_existing=True,
            args=[app]
        )
        # 改为每分钟检查一次，按用户自定义时间触发
        scheduler.add_job(
            func=check_email_dispatch_job,
            trigger=CronTrigger(minute='*/1'),
            id='email_dispatch_check',
            name='检查邮件发送时间（每分钟）',
            replace_existing=True,
            args=[app]
        )
        
        print('定时任务已启动：每周六9:00自动生成周报')

def generate_weekly_reports_job(app: Flask):
    """生成周报的定时任务"""
    with app.app_context():
        # 计算上一周的开始日期（周一）
        today = datetime.now().date()
        # 找到上一个周六
        days_since_saturday = (today.weekday() - 5) % 7
        if days_since_saturday == 0:
            # 如果今天是周六，则上一周是上周一到上周六
            last_saturday = today - timedelta(days=7)
        else:
            last_saturday = today - timedelta(days=days_since_saturday)
        
        # 上一周的开始日期（周一）
        last_week_start = last_saturday - timedelta(days=5)
        
        # 获取所有项目
        projects = Project.query.all()
        
        for project in projects:
            try:
                # 检查该周是否有日志
                week_end = last_week_start + timedelta(days=6)
                logs_count = Log.query.filter_by(project_id=project.id).filter(
                    Log.date >= last_week_start,
                    Log.date <= week_end
                ).count()
                
                if logs_count > 0:
                    # 生成周报（Word格式）
                    generate_weekly_report(project, last_week_start, 'word')
                    print(f'已为项目 {project.name} 生成周报（{last_week_start} 至 {week_end}）')
            except Exception as e:
                print(f'为项目 {project.name} 生成周报时出错: {e}')

def send_daily_logs_job(app: Flask, now_dt: datetime):
    with app.app_context():
        # 改为发送“今日”日志
        target_date = now_dt.date()
        settings = EmailSetting.query.filter_by(daily_enabled=True).all()
        for s in settings:
            try:
                if not s.qq_email:
                    continue
                # 时间匹配（HH:MM）
                if (s.daily_time or '07:00') != now_dt.strftime('%H:%M'):
                    continue
                projects = Project.query.filter_by(user_id=s.user_id).all()
                pids = [p.id for p in projects]
                if not pids:
                    continue
                logs = Log.query.filter(Log.project_id.in_(pids)).filter(Log.date == target_date).order_by(Log.project_id, Log.created_at).all()
                body = build_email_body_by_project(logs, projects, header=f'【{target_date}】实施日志')
                send_email(s.qq_email, f'今日日志-{target_date}', body, attachments=[])
            except Exception as e:
                print(f'[定时发送-每日] 用户{s.user_id} 失败: {e}')

def send_weekly_reports_email_job(app: Flask, now_dt: datetime):
    with app.app_context():
        today = now_dt.date()
        # 计算本周的周一（用于生成范围）
        week_start = today - timedelta(days=today.weekday()+2)  # 提前两天以保证周五时覆盖本周一
        # 实际使用：上一周周一到周日
        last_week_end = today - timedelta(days=today.weekday()+1)
        last_week_start = last_week_end - timedelta(days=6)

        settings = EmailSetting.query.filter_by(weekly_enabled=True).all()
        for s in settings:
            try:
                if not s.qq_email:
                    continue
                # 星期与时间匹配
                weekday = now_dt.weekday()  # 周一=0
                if (s.weekly_weekday if s.weekly_weekday is not None else 4) != weekday:
                    continue
                if (s.weekly_time or '07:00') != now_dt.strftime('%H:%M'):
                    continue
                projects = Project.query.filter_by(user_id=s.user_id).all()
                attachments = []
                for p in projects:
                    count = Log.query.filter_by(project_id=p.id).filter(Log.date >= last_week_start, Log.date <= last_week_end).count()
                    if count == 0:
                        continue
                    docx_path = generate_weekly_report(p, last_week_start, 'word')
                    attachments.append(docx_path)
                    try:
                        from docx2pdf import convert
                        pdf_path = docx_path.replace('.docx', '.pdf')
                        convert(docx_path, pdf_path)
                        attachments.append(pdf_path)
                    except Exception:
                        pass
                if not attachments:
                    continue
                subject = f'周报（{last_week_start} 至 {last_week_end}）'
                body = '本邮件包含本周周报附件（Word/PDF）。'
                send_email(s.qq_email, subject, body, attachments=attachments)
            except Exception as e:
                print(f'[定时发送-每周] 用户{s.user_id} 失败: {e}')

def check_email_dispatch_job(app: Flask):
    """每分钟检查是否需要发送每日/每周邮件"""
    now_dt = datetime.now().replace(second=0, microsecond=0)
    # 每日
    send_daily_logs_job(app, now_dt)
    # 每周
    send_weekly_reports_email_job(app, now_dt)

