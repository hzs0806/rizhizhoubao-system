from docxtpl import DocxTemplate
from models import Log, TaskCategory
from datetime import datetime, timedelta
import os
import shutil
from config import Config
from ai_summarizer import summarize_weekly_logs, summarize_next_week_plans, summarize_support_requirements

def generate_weekly_report(project, week_start_date, format_type='word'):
    """
    生成周报（基于Word模板）
    
    Args:
        project: Project对象
        week_start_date: 周开始日期（周一）
        format_type: 'word' 或 'pdf'
    
    Returns:
        生成的文件路径
    """
    week_end_date = week_start_date + timedelta(days=6)
    next_week_start = week_end_date + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    
    # 确定使用的模板路径（优先使用项目自定义模板，否则使用系统默认模板）
    template_path = None
    if project.report_template and os.path.exists(project.report_template):
        template_path = project.report_template
    else:
        # 使用系统默认模板
        template_dir = os.path.dirname(Config.REPORT_TEMPLATE_PATH)
        os.makedirs(template_dir, exist_ok=True)
        
        # 检查模板文件是否存在
        if not os.path.exists(Config.REPORT_TEMPLATE_PATH):
            # 尝试从项目根目录复制模板文件
            project_root = os.path.dirname(os.path.abspath(__file__))
            source_template = os.path.join(project_root, 
                                          '北京高博【门诊生成式病历项目】周报及计划(20251110至20251114).docx')
            if os.path.exists(source_template):
                shutil.copy(source_template, Config.REPORT_TEMPLATE_PATH)
            else:
                raise FileNotFoundError(
                    f'模板文件不存在: {Config.REPORT_TEMPLATE_PATH}\n'
                    f'请将模板文件"北京高博【门诊生成式病历项目】周报及计划(20251110至20251114).docx"复制到: {Config.REPORT_TEMPLATE_PATH}'
                )
        template_path = Config.REPORT_TEMPLATE_PATH
    
    # 加载模板
    doc = DocxTemplate(template_path)
    
    # 获取该周的日志
    logs = Log.query.filter_by(project_id=project.id).filter(
        Log.date >= week_start_date,
        Log.date <= week_end_date
    ).join(TaskCategory, Log.task_category_id == TaskCategory.id).order_by(Log.date, TaskCategory.order).all()
    
    # 按日期组织日志数据
    logs_by_date = {}
    for log in logs:
        date_str = log.date.strftime('%Y-%m-%d')
        if date_str not in logs_by_date:
            logs_by_date[date_str] = []
        logs_by_date[date_str].append({
            'date': log.date.strftime('%Y年%m月%d日'),
            'date_short': log.date.strftime('%m月%d日'),
            'category': log.task_category.name,
            'content': log.content,
            'next_plan': log.next_plan if log.next_plan and log.next_plan.strip() and log.next_plan.strip() != '无' else None
        })
    
    # 准备日志列表（用于模板中的循环）
    logs_list = []
    sorted_dates = sorted(logs_by_date.keys())
    for date_str in sorted_dates:
        for log_item in logs_by_date[date_str]:
            logs_list.append(log_item)
    
    # 按日期分组的日志（用于按日期显示）
    logs_by_date_list = []
    for date_str in sorted_dates:
        logs_for_date = logs_by_date[date_str]
        # 按分类组织
        categories_dict = {}
        for log_item in logs_for_date:
            category = log_item['category']
            if category not in categories_dict:
                categories_dict[category] = []
            categories_dict[category].append(log_item)
        
        logs_by_date_list.append({
            'date': logs_for_date[0]['date'],
            'date_short': logs_for_date[0]['date_short'],
            'categories': [{'name': cat, 'logs': categories_dict[cat]} for cat in sorted(categories_dict.keys())]
        })
    
    # 收集下周计划（从日志的next_plan字段提取，去重）
    # 注意：这个会在AI整理后更新，先创建空列表
    next_plans = []
    
    # 使用AI整理本周工作总结（表格格式）
    logs_for_ai = []
    for log in logs:
        logs_for_ai.append({
            'date': log.date.strftime('%Y年%m月%d日'),
            'category': log.task_category.name,
            'content': log.content
        })
    
    # 调用AI整理工作总结
    try:
        weekly_summary = summarize_weekly_logs(logs_for_ai, project.project_scope)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'AI整理工作总结失败: {e}')
        # 失败时使用简单格式化
        weekly_summary = []
        seen_descriptions = set()
        for i, log in enumerate(logs, 1):
            category = log.task_category.name
            content = log.content
            description = f"【{category}】{content[:50]}{'...' if len(content) > 50 else ''}"
            if description not in seen_descriptions:
                weekly_summary.append({
                    '序号': len(weekly_summary) + 1,
                    '工作描述': description,
                    '状态': '已完成',
                    '备注': content[:100] if len(content) > 100 else content
                })
                seen_descriptions.add(description)
    
    # 使用AI整理下周工作计划（表格格式）
    logs_for_plan_ai = []
    for log in logs:
        if log.next_plan and log.next_plan.strip() and log.next_plan.strip() != '无':
            logs_for_plan_ai.append({
                'date': log.date.strftime('%Y年%m月%d日'),
                'category': log.task_category.name,
                'content': log.content,
                'next_plan': log.next_plan.strip()
            })
    
    # 调用AI整理工作计划
    try:
        next_week_plans_table = summarize_next_week_plans(logs_for_plan_ai, next_week_start.strftime('%Y-%m-%d'), next_week_end.strftime('%Y-%m-%d'))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'AI整理工作计划失败: {e}')
        # 失败时使用简单格式化（会自动估算计划截至日期）
        from ai_summarizer import format_plans_simple
        logs_for_plan_simple = []
        for log in logs:
            if log.next_plan and log.next_plan.strip() and log.next_plan.strip() != '无':
                logs_for_plan_simple.append({
                    'date': log.date.strftime('%Y年%m月%d日'),
                    'category': log.task_category.name,
                    'content': log.content,
                    'next_plan': log.next_plan.strip()
                })
        next_week_plans_table = format_plans_simple(logs_for_plan_simple, next_week_start.strftime('%Y-%m-%d'))
    
    # 如果没有计划，添加默认项
    if not next_week_plans_table:
        # 默认计划截至日期为下周结束日期
        next_week_plans_table.append({
            '序号': 1,
            '工作描述': '（待补充）',
            '预计开始时间': next_week_start.strftime('%Y-%m-%d'),
            '计划截至': next_week_end.strftime('%Y-%m-%d'),
            '备注': ''
        })
    
    # 更新next_plans（旧格式，用于Word模板中的plan变量）
    # 从next_week_plans_table中提取数据，添加预计所需时间字段
    next_plans = []
    for item in next_week_plans_table:
        next_plans.append({
            'content': item.get('工作描述', ''),
            'start_date': item.get('预计开始时间', next_week_start.strftime('%Y-%m-%d')),
            'end_date': item.get('计划截至', next_week_end.strftime('%Y-%m-%d')),
            '预计所需时间': item.get('计划截至', next_week_end.strftime('%Y-%m-%d')),  # AI自动生成的计划截至日期
            'note': item.get('备注', '')
        })
    
    # 使用AI整理支持需求表格
    # 按日志顺序收集所有日志数据（包括支持字段），以便检查后续日志内容
    logs_for_support_ai = []
    for log in logs:
        log_data = {
            'date': log.date.strftime('%Y年%m月%d日'),
            'category': log.task_category.name,
            'content': log.content,
            'next_plan': log.next_plan.strip() if log.next_plan and log.next_plan.strip() and log.next_plan.strip() != '无' else '',
            'need_product_support': log.need_product_support if log.need_product_support and log.need_product_support.strip() and log.need_product_support.strip() != '无' else '',
            'need_dev_support': log.need_dev_support if log.need_dev_support and log.need_dev_support.strip() and log.need_dev_support.strip() != '无' else '',
            'need_test_support': log.need_test_support if log.need_test_support and log.need_test_support.strip() and log.need_test_support.strip() != '无' else '',
            'need_business_support': log.need_business_support if log.need_business_support and log.need_business_support.strip() and log.need_business_support.strip() != '无' else '',
            'need_customer_support': log.need_customer_support if log.need_customer_support and log.need_customer_support.strip() and log.need_customer_support.strip() != '无' else ''
        }
        logs_for_support_ai.append(log_data)
    
    # 调用AI整理支持需求
    try:
        support_requirements_table = summarize_support_requirements(logs_for_support_ai, next_week_start.strftime('%Y-%m-%d'), next_week_end.strftime('%Y-%m-%d'))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'AI整理支持需求失败: {e}')
        # 失败时使用简单格式化（format_support_simple会自动处理后续日志检查）
        from ai_summarizer import format_support_simple
        # 构建支持需求列表（包含后续日志信息）
        support_requirements_list = []
        support_types = {
            'need_product_support': '产品支持',
            'need_dev_support': '研发支持',
            'need_test_support': '测试支持',
            'need_business_support': '商务支持',
            'need_customer_support': '客户支持'
        }
        for i, log_data in enumerate(logs_for_support_ai):
            for support_field, support_name in support_types.items():
                support_content = log_data.get(support_field, '')
                if support_content:
                    # 收集后续日志内容
                    subsequent_contents = []
                    for j in range(i + 1, len(logs_for_support_ai)):
                        subsequent_contents.append({
                            'date': logs_for_support_ai[j].get('date', ''),
                            'content': logs_for_support_ai[j].get('content', '')
                        })
                    support_requirements_list.append({
                        'date': log_data.get('date', ''),
                        'category': log_data.get('category', ''),
                        'content': log_data.get('content', ''),
                        'next_plan': log_data.get('next_plan', ''),
                        'support_type': support_name,
                        'support_content': support_content,
                        'subsequent_contents': subsequent_contents
                    })
        support_requirements_table = format_support_simple(support_requirements_list, next_week_start.strftime('%Y-%m-%d'))
    
    # 处理医院logo图片
    hospital_logo_image = None
    if project.hospital_logo:
        logo_path = project.hospital_logo
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(logo_path):
            # 从/static/uploads/logos/xxx.png转换为实际文件路径
            if logo_path.startswith('/static/'):
                logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), logo_path.lstrip('/'))
            else:
                logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), logo_path)
        
        if os.path.exists(logo_path):
            try:
                # 创建InlineImage对象，设置宽度为40mm（约150像素）
                hospital_logo_image = InlineImage(doc, logo_path, width=Mm(40))
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'无法加载医院logo图片: {e}')
                hospital_logo_image = None
    
    # 准备上下文数据
    context = {
        # 基本信息
        'hospital_name': project.hospital_name or '',
        'project_name': project.name,
        'project_manager': project.project_manager or '（待补充）',
        'dev_manager': project.dev_manager or '',
        'business_manager': project.business_manager or '',
        'project_goal': project.project_goal or '',
        'project_status': project.project_status or '进行中',  # 使用项目配置的状态，如果没有则默认为"进行中"
        'hospital_logo': hospital_logo_image,  # InlineImage对象，在模板中使用{% if hospital_logo %}{{ hospital_logo }}{% endif %}
        
        # 日期信息
        'week_start': week_start_date.strftime('%Y年%m月%d日'),
        'week_end': week_end_date.strftime('%Y年%m月%d日'),
        'week_start_short': week_start_date.strftime('%Y-%m-%d'),
        'week_end_short': week_end_date.strftime('%Y-%m-%d'),
        'report_date': week_end_date.strftime('%Y年%m月%d日'),
        
        # 下周日期
        'next_week_start': next_week_start.strftime('%Y年%m月%d日'),
        'next_week_end': next_week_end.strftime('%Y年 %m月%d日'),
        'next_week_start_short': next_week_start.strftime('%Y-%m-%d'),
        'next_week_end_short': next_week_end.strftime('%Y-%m-%d'),
        
        # 日志数据
        'logs': logs_list,  # 所有日志的平铺列表
        'logs_by_date': logs_by_date_list,  # 按日期分组的日志
        
        # 下周计划（旧格式，保持兼容）
        'next_plans': next_plans,
        
        # AI整理后的表格数据
        'weekly_summary_table': weekly_summary,  # 本周工作总结表格：序号、工作描述、状态、备注
        # 为Word模板添加兼容字段：预计所需时间（等于计划截至）
        'next_week_plans_table': [
            {**item, '预计所需时间': item.get('计划截至', '')} 
            for item in next_week_plans_table
        ],  # 下周工作计划表格：序号、工作描述、预计开始时间、计划截至、预计所需时间、备注
        'support_requirements_table': support_requirements_table,  # 支持需求表格：序号、内容、支持方、时间要求
        
        # 本周完成工作（旧格式，保持兼容）
        'completed_work': [{
            'work_content': item['工作描述'],
            'note': item.get('备注', ''),
            'status': item.get('状态', '已完成')
        } for item in weekly_summary],
        
        # 项目范围
        'project_scope': project.project_scope or project.hospital_name or project.name,
    }
    
    # 渲染模板
    doc.render(context)
    
    # 保存Word文档
    filename = f'{project.name}周报及计划({week_start_date.strftime("%Y%m%d")}至{week_end_date.strftime("%Y%m%d")}).docx'
    file_path = os.path.join(Config.REPORT_OUTPUT_DIR, filename)
    
    # 确保输出目录存在
    os.makedirs(Config.REPORT_OUTPUT_DIR, exist_ok=True)
    
    doc.save(file_path)
    
    # 如果需要PDF格式
    if format_type == 'pdf':
        try:
            from docx2pdf import convert
            pdf_path = file_path.replace('.docx', '.pdf')
            convert(file_path, pdf_path)
            return pdf_path
        except Exception as e:
            print(f'PDF转换失败: {e}')
            return file_path
    
    return file_path
