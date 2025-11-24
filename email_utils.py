import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Optional
import os
import logging
from config import Config

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> bool:
    """发送邮件"""
    if not to_email:
        logger.warning('[邮件] 收件人为空，取消发送')
        return False
    
    if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
        logger.error('[邮件] SMTP配置缺失，请在环境变量中配置 MAIL_USERNAME 和 MAIL_PASSWORD')
        return False

    msg = MIMEMultipart()
    msg['From'] = Config.MAIL_SENDER or Config.MAIL_USERNAME
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    for path in attachments or []:
        try:
            if not os.path.exists(path):
                logger.warning(f'[邮件] 附件不存在: {path}')
                continue
            with open(path, 'rb') as f:
                part = MIMEApplication(f.read())
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                msg.attach(part)
        except Exception as e:
            logger.exception(f'[邮件] 附件添加失败: {path}, {e}')

    try:
        if Config.MAIL_USE_SSL:
            server = smtplib.SMTP_SSL(Config.MAIL_HOST, Config.MAIL_PORT)
        else:
            server = smtplib.SMTP(Config.MAIL_HOST, Config.MAIL_PORT)
            server.starttls()
        server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
        server.sendmail(msg['From'], [to_email], msg.as_string())
        server.quit()
        logger.info(f'[邮件] 已发送至 {to_email}，主题: {subject}，附件数: {len(attachments or [])}')
        return True
    except Exception as e:
        logger.exception(f'[邮件] 发送失败: {e}')
        return False

def build_email_body_by_project(logs, projects, header: str = '') -> str:
    """
    将日志按项目分组，并以“预览模板”格式组织文本。
    为避免循环依赖，所需的模型在函数内部导入。
    """
    if not logs:
        return (header + '\n\n') if header else '无日志。'
    # 延迟导入，避免循环
    from models import TaskCategory
    proj_map = {p.id: p for p in projects}
    proj_to_logs = {}
    for l in logs:
        proj_to_logs.setdefault(l.project_id, []).append(l)
    lines = []
    if header:
        lines.append(header)
        lines.append('')
    cat_map = {c.id: c for c in TaskCategory.query.all()}
    for pid, plogs in proj_to_logs.items():
        p = proj_map.get(pid)
        if not p:
            continue
        # 项目头
        lines.append(f'项目：{p.name}')
        if p.hospital_name:
            lines.append(f'医院：{p.hospital_name}')
        if p.project_manager:
            lines.append(f'项目经理：{p.project_manager}')
        if p.business_manager:
            lines.append(f'商务经理：{p.business_manager}')
        if p.dev_manager:
            lines.append(f'研发经理：{p.dev_manager}')
        lines.append('')
        # 日志项
        for l in plogs:
            cat = cat_map.get(l.task_category_id)
            cat_name = cat.name if cat else (l.project_status or '')
            lines.append(f'【{l.date}】实施日志')
            lines.append(f'项目状态：{cat_name}')
            lines.append('今日处理问题：')
            lines.append(l.content or '')
            # 支持
            supports = []
            if l.need_product_support and l.need_product_support != '无':
                supports.append(f'需要产品支持：{l.need_product_support}')
            if l.need_dev_support and l.need_dev_support != '无':
                supports.append(f'需要研发支持：{l.need_dev_support}')
            if l.need_test_support and l.need_test_support != '无':
                supports.append(f'需要测试支持：{l.need_test_support}')
            if l.need_business_support and l.need_business_support != '无':
                supports.append(f'需要商务支持：{l.need_business_support}')
            if l.need_customer_support and l.need_customer_support != '无':
                supports.append(f'需要客户支持：{l.need_customer_support}')
            if supports:
                lines.extend(supports)
            if l.next_plan and l.next_plan.strip() and l.next_plan.strip() != '无':
                lines.append('下一步计划：')
                lines.append(l.next_plan.strip())
            lines.append('')
        lines.append('')
    return '\n'.join(lines).strip()


