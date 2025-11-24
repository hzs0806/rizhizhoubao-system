"""
AI大模型日志整理模块
使用免费的AI API来整理和汇总日志内容
"""
import requests
import json
import os
import time
from datetime import datetime
from config import Config
import logging

logger = logging.getLogger(__name__)

# 项目范围选项
PROJECT_SCOPE_OPTIONS = [
    '导诊',
    '预问诊',
    '智能客服',
    'AI门诊生成式病历',
    'AI生成式入院记录',
    'AI生成式首次病程记录',
    'AI生成式查房记录',
    'AI生成式手术记录',
    'AI生成式出院小结'
]

def call_free_ai_api(prompt, max_retries=3):
    """
    调用免费的AI大模型API
    
    支持的免费API：
    1. 通义千问（阿里云）- 需要API Key
    2. 文心一言（百度）- 需要API Key
    3. 本地模型（Ollama等）
    4. Hugging Face Inference API
    
    优先使用配置的API，如果没有配置则使用备用方案
    """
    start_time = time.time()
    prompt_length = len(prompt)
    logger.info(f"[AI API] 开始调用AI API，提示词长度: {prompt_length} 字符，最大重试次数: {max_retries}")
    
    # 方案1：使用通义千问API（如果有配置）
    qwen_api_key = os.environ.get('QWEN_API_KEY') or Config.QWEN_API_KEY if hasattr(Config, 'QWEN_API_KEY') else None
    if qwen_api_key:
        logger.info("[AI API] 使用通义千问API")
        result = call_qwen_api(prompt, qwen_api_key, max_retries)
        elapsed_time = time.time() - start_time
        logger.info(f"[AI API] 通义千问API调用完成，耗时: {elapsed_time:.2f}秒")
        return result
    
    # 方案2：使用文心一言API（如果有配置）
    wenxin_api_key = os.environ.get('WENXIN_API_KEY') or (Config.WENXIN_API_KEY if hasattr(Config, 'WENXIN_API_KEY') else None)
    wenxin_secret_key = os.environ.get('WENXIN_SECRET_KEY') or (Config.WENXIN_SECRET_KEY if hasattr(Config, 'WENXIN_SECRET_KEY') else None)
    if wenxin_api_key and wenxin_secret_key:
        logger.info("[AI API] 使用文心一言API")
        result = call_wenxin_api(prompt, wenxin_api_key, wenxin_secret_key, max_retries)
        elapsed_time = time.time() - start_time
        logger.info(f"[AI API] 文心一言API调用完成，耗时: {elapsed_time:.2f}秒")
        return result
    
    # 方案3：使用Hugging Face Inference API（免费，但需要网络）
    logger.info("[AI API] 使用Hugging Face Inference API（备用方案）")
    result = call_huggingface_api(prompt, max_retries)
    elapsed_time = time.time() - start_time
    logger.info(f"[AI API] Hugging Face API调用完成，耗时: {elapsed_time:.2f}秒")
    return result

def call_qwen_api(prompt, api_key, max_retries=3):
    """调用通义千问API"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {api_key[:10]}...",  # 只记录部分API Key用于日志
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen-turbo",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        },
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 2000
        }
    }
    
    logger.info(f"[通义千问] 请求URL: {url}")
    logger.info(f"[通义千问] 请求参数: model=qwen-turbo, temperature=0.7, max_tokens=2000, prompt_length={len(prompt)}")
    
    for attempt in range(max_retries):
        try:
            attempt_start = time.time()
            logger.info(f"[通义千问] 第 {attempt + 1}/{max_retries} 次尝试")
            
            response = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=data, timeout=30)
            attempt_time = time.time() - attempt_start
            
            logger.info(f"[通义千问] HTTP状态码: {response.status_code}，响应时间: {attempt_time:.2f}秒")
            
            response.raise_for_status()
            result = response.json()
            
            # 记录响应信息（不记录完整内容，只记录结构）
            if 'output' in result:
                if 'choices' in result['output']:
                    response_length = len(result['output']['choices'][0]['message']['content']) if result['output']['choices'] else 0
                    logger.info(f"[通义千问] 响应成功，返回内容长度: {response_length} 字符")
                    return result['output']['choices'][0]['message']['content']
                else:
                    response_text = result.get('output', {}).get('text', '')
                    logger.info(f"[通义千问] 响应成功，返回内容长度: {len(response_text)} 字符")
                    return response_text
            else:
                logger.warning(f"[通义千问] 响应格式异常: {json.dumps(result, ensure_ascii=False)[:200]}")
                return result.get('output', {}).get('text', '')
                
        except requests.exceptions.Timeout as e:
            logger.error(f"[通义千问] 请求超时 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"[通义千问] HTTP错误 (尝试 {attempt + 1}/{max_retries}): 状态码={response.status_code}, 错误={str(e)}")
            if attempt == max_retries - 1:
                raise
        except Exception as e:
            logger.error(f"[通义千问] 调用失败 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
            if attempt == max_retries - 1:
                raise
    
    return None

def call_wenxin_api(prompt, api_key, secret_key, max_retries=3):
    """调用文心一言API"""
    # 先获取access_token
    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    token_params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key
    }
    
    logger.info("[文心一言] 开始获取access_token")
    try:
        token_start = time.time()
        token_response = requests.post(token_url, params=token_params, timeout=10)
        token_time = time.time() - token_start
        logger.info(f"[文心一言] access_token获取完成，耗时: {token_time:.2f}秒，状态码: {token_response.status_code}")
        
        token_response.raise_for_status()
        token_result = token_response.json()
        access_token = token_result.get('access_token')
        if not access_token:
            logger.error("[文心一言] access_token为空")
            raise Exception('无法获取access_token')
        logger.info(f"[文心一言] access_token获取成功，长度: {len(access_token)}")
    except Exception as e:
        logger.error(f'[文心一言] 获取access_token失败: {type(e).__name__}: {str(e)}')
        raise
    
    # 调用API
    url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/eb-instant?access_token={access_token[:20]}..."
    data = {
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_output_tokens": 2000
    }
    
    logger.info(f"[文心一言] 请求URL: {url.split('?')[0]}")
    logger.info(f"[文心一言] 请求参数: temperature=0.7, max_output_tokens=2000, prompt_length={len(prompt)}")
    
    for attempt in range(max_retries):
        try:
            attempt_start = time.time()
            logger.info(f"[文心一言] 第 {attempt + 1}/{max_retries} 次尝试")
            
            response = requests.post(f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/eb-instant?access_token={access_token}", json=data, timeout=30)
            attempt_time = time.time() - attempt_start
            
            logger.info(f"[文心一言] HTTP状态码: {response.status_code}，响应时间: {attempt_time:.2f}秒")
            
            response.raise_for_status()
            result = response.json()
            
            response_text = result.get('result', '')
            logger.info(f"[文心一言] 响应成功，返回内容长度: {len(response_text)} 字符")
            return response_text
            
        except requests.exceptions.Timeout as e:
            logger.error(f"[文心一言] 请求超时 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"[文心一言] HTTP错误 (尝试 {attempt + 1}/{max_retries}): 状态码={response.status_code}, 错误={str(e)}")
            if attempt == max_retries - 1:
                raise
        except Exception as e:
            logger.error(f"[文心一言] 调用失败 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
            if attempt == max_retries - 1:
                raise
    
    return None

def call_huggingface_api(prompt, max_retries=3):
    """
    调用Hugging Face Inference API（免费，使用开源模型）
    使用Qwen2.5-7B-Instruct模型
    """
    url = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B-Instruct"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "inputs": prompt,
        "parameters": {
            "temperature": 0.7,
            "max_new_tokens": 2000,
            "return_full_text": False
        }
    }
    
    logger.info(f"[Hugging Face] 请求URL: {url}")
    logger.info(f"[Hugging Face] 请求参数: model=Qwen2.5-7B-Instruct, temperature=0.7, max_new_tokens=2000, prompt_length={len(prompt)}")
    
    for attempt in range(max_retries):
        try:
            attempt_start = time.time()
            logger.info(f"[Hugging Face] 第 {attempt + 1}/{max_retries} 次尝试")
            
            response = requests.post(url, headers=headers, json=data, timeout=60)
            attempt_time = time.time() - attempt_start
            
            logger.info(f"[Hugging Face] HTTP状态码: {response.status_code}，响应时间: {attempt_time:.2f}秒")
            
            response.raise_for_status()
            result = response.json()
            
            # Hugging Face返回格式可能是列表或字典
            response_text = None
            if isinstance(result, list) and len(result) > 0:
                if 'generated_text' in result[0]:
                    response_text = result[0]['generated_text']
                elif isinstance(result[0], dict) and 'text' in result[0]:
                    response_text = result[0]['text']
            elif isinstance(result, dict):
                if 'generated_text' in result:
                    response_text = result['generated_text']
                elif 'text' in result:
                    response_text = result['text']
            
            if response_text:
                logger.info(f"[Hugging Face] 响应成功，返回内容长度: {len(response_text)} 字符")
                return response_text
            else:
                # 如果格式不符合预期，尝试提取文本
                logger.warning(f"[Hugging Face] 响应格式异常，尝试转换为字符串: {type(result)}")
                return str(result)
                
        except requests.exceptions.Timeout:
            logger.error(f'[Hugging Face] 请求超时 (尝试 {attempt + 1}/{max_retries})，超时时间: 60秒')
            if attempt == max_retries - 1:
                # 如果API失败，返回简单的格式化结果
                logger.error("[Hugging Face] 所有重试均失败，返回None")
                return None
        except requests.exceptions.HTTPError as e:
            logger.error(f'[Hugging Face] HTTP错误 (尝试 {attempt + 1}/{max_retries}): 状态码={response.status_code}, 错误={str(e)}')
            if attempt == max_retries - 1:
                return None
        except Exception as e:
            logger.error(f'[Hugging Face] 调用失败 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}')
            if attempt == max_retries - 1:
                return None
    
    return None

def summarize_weekly_logs(logs, project_scope=None):
    """
    使用AI整理本周工作总结
    
    Args:
        logs: 日志列表，每个日志包含 date, category, content 等字段
        project_scope: 项目范围
    
    Returns:
        整理后的工作总结列表，格式：[{'序号': 1, '工作描述': '...', '状态': '已完成', '备注': '...'}, ...]
    """
    if not logs:
        return []
    
    # 构建提示词
    logs_text = ""
    for i, log in enumerate(logs, 1):
        logs_text += f"{i}. 日期：{log.get('date', '')}，分类：{log.get('category', '')}，内容：{log.get('content', '')}\n"
    
    prompt = f"""请根据以下一周的工作日志，整理成本周工作总结表格。要求：
1. 将相似的工作内容合并
2. 提取关键工作描述
3. 状态统一为"已完成"
4. 备注可以简要说明工作要点

项目范围：{project_scope or '未指定'}

工作日志：
{logs_text}

请按照以下JSON格式返回，只返回JSON，不要其他文字：
[
  {{"序号": 1, "工作描述": "工作内容描述", "状态": "已完成", "备注": "备注信息"}},
  {{"序号": 2, "工作描述": "工作内容描述", "状态": "已完成", "备注": "备注信息"}}
]
"""
    
    try:
        logger.info(f"[工作总结整理] 开始整理，日志数量: {len(logs)}，项目范围: {project_scope or '未指定'}")
        ai_response = call_free_ai_api(prompt)
        
        if ai_response:
            logger.info(f"[工作总结整理] AI响应成功，响应长度: {len(ai_response)} 字符")
            # 尝试解析JSON
            # 清理响应文本，提取JSON部分
            import re
            json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    logger.info(f"[工作总结整理] JSON解析成功，整理后条目数: {len(result)}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[工作总结整理] JSON解析失败: {str(e)}，使用简单格式化")
                    return format_logs_simple(logs)
            else:
                logger.warning("[工作总结整理] 响应中未找到JSON格式，使用简单格式化")
                # 如果无法解析JSON，使用简单格式化
                return format_logs_simple(logs)
        else:
            logger.warning("[工作总结整理] AI调用返回空响应，使用简单格式化")
            # AI调用失败，使用简单格式化
            return format_logs_simple(logs)
    except Exception as e:
        logger.error(f'[工作总结整理] AI整理工作总结失败: {type(e).__name__}: {str(e)}', exc_info=True)
        # 失败时使用简单格式化
        return format_logs_simple(logs)

def summarize_next_week_plans(logs, next_week_start, next_week_end):
    """
    使用AI整理下周工作计划
    
    Args:
        logs: 日志列表，包含next_plan字段和content字段
        next_week_start: 下周开始日期
        next_week_end: 下周结束日期
    
    Returns:
        整理后的工作计划列表，格式：[{'序号': 1, '工作描述': '...', '预计开始时间': '...', '计划截至': '...', '备注': '...'}, ...]
    """
    # 收集所有下一步计划及其相关信息（包括日期、工作内容、分类和后续日志内容）
    plans_with_info = []
    for i, log in enumerate(logs):
        if log.get('next_plan') and log.get('next_plan').strip() and log.get('next_plan').strip() != '无':
            plan_text = log.get('next_plan').strip()
            plan_date = log.get('date', '')
            category = log.get('category', '')
            content = log.get('content', '')
            # 收集该计划出现后的所有日志内容，用于判断是否已完成
            subsequent_contents = []
            for j in range(i + 1, len(logs)):
                subsequent_contents.append({
                    'date': logs[j].get('date', ''),
                    'content': logs[j].get('content', '')
                })
            plans_with_info.append({
                'plan': plan_text,
                'date': plan_date,
                'category': category,
                'content': content,
                'subsequent_contents': subsequent_contents
            })
    
    if not plans_with_info:
        return []
    
    # 构建包含日志内容的提示词，让AI判断哪些计划已完成并估算截至日期
    plans_text = ""
    logs_text = ""
    for i, plan_info in enumerate(plans_with_info):
        plans_text += f"{i+1}. 【计划内容】{plan_info['plan']}\n"
        plans_text += f"   【计划日期】{plan_info['date']}\n"
        plans_text += f"   【工作分类】{plan_info['category']}\n"
        if plan_info['content']:
            plans_text += f"   【相关工作内容】{plan_info['content']}\n"
        plans_text += "\n"
        if plan_info['subsequent_contents']:
            logs_text += f"\n计划{i+1}的后续日志内容：\n"
            for content_info in plan_info['subsequent_contents']:
                logs_text += f"  - {content_info['date']}: {content_info['content']}\n"
    
    prompt = f"""请根据以下下一步计划、工作内容和后续日志，整理成下周工作计划表格。要求：
1. 仔细检查每个计划的后续日志内容，如果日志中明确提到该计划已完成、已实现、已结束、已完成相关任务等，则不要将该计划放入下周计划中
2. 合并相似的计划内容
3. 提取关键工作描述
4. **重要**：根据每个计划的工作描述、工作分类、相关工作内容，智能估算计划截至日期。估算原则：
   - 简单任务（如配置、安装、验证等）：1-3天，截至日期为{next_week_start}至{next_week_end}之间的具体日期
   - 中等任务（如对接、调研、培训等）：3-5天，截至日期为{next_week_start}至{next_week_end}之间的具体日期
   - 复杂任务（如开发、部署、上线等）：5-7天，截至日期可以是{next_week_end}或之后的具体日期
   - 根据工作分类判断：接口对接、配置类任务通常较快；调研、开发类任务需要更长时间
   - 必须返回具体的日期格式：YYYY-MM-DD（如：{next_week_start}、{next_week_end}等）
5. 预计开始时间统一为：{next_week_start}

计划内容：
{plans_text}

{logs_text}

请按照以下JSON格式返回，只返回JSON，不要其他文字（只返回未完成的计划，计划截至日期必须是具体日期）：
[
  {{"序号": 1, "工作描述": "工作内容描述", "预计开始时间": "{next_week_start}", "计划截至": "2025-11-25", "备注": "备注信息"}},
  {{"序号": 2, "工作描述": "工作内容描述", "预计开始时间": "{next_week_start}", "计划截至": "2025-11-28", "备注": "备注信息"}}
]
"""
    
    try:
        logger.info(f"[工作计划整理] 开始整理，计划数量: {len(plans_with_info)}，下周时间: {next_week_start} 至 {next_week_end}")
        ai_response = call_free_ai_api(prompt)
        
        if ai_response:
            logger.info(f"[工作计划整理] AI响应成功，响应长度: {len(ai_response)} 字符")
            # 尝试解析JSON
            import re
            json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    logger.info(f"[工作计划整理] JSON解析成功，整理后条目数: {len(result)}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[工作计划整理] JSON解析失败: {str(e)}，使用简单格式化")
                    return format_plans_simple(plans_with_info, next_week_start)
            else:
                logger.warning("[工作计划整理] 响应中未找到JSON格式，使用简单格式化")
                # 如果无法解析JSON，使用简单格式化
                return format_plans_simple(plans_with_info, next_week_start)
        else:
            logger.warning("[工作计划整理] AI调用返回空响应，使用简单格式化")
            # AI调用失败，使用简单格式化
            return format_plans_simple(plans_with_info, next_week_start)
    except Exception as e:
        logger.error(f'[工作计划整理] AI整理工作计划失败: {type(e).__name__}: {str(e)}', exc_info=True)
        # 失败时使用简单格式化
        return format_plans_simple(plans_with_info, next_week_start)

def format_logs_simple(logs):
    """简单格式化日志（AI失败时的备用方案）"""
    result = []
    seen_descriptions = set()
    
    for i, log in enumerate(logs, 1):
        category = log.get('category', '')
        content = log.get('content', '')
        # 简化描述
        description = f"【{category}】{content[:50]}{'...' if len(content) > 50 else ''}"
        
        # 去重
        if description not in seen_descriptions:
            result.append({
                '序号': len(result) + 1,
                '工作描述': description,
                '状态': '已完成',
                '备注': content[:100] if len(content) > 100 else content
            })
            seen_descriptions.add(description)
    
    return result

def format_plans_simple(plans_with_info, start_date):
    """简单格式化计划（AI失败时的备用方案），过滤已完成的计划，智能估算截至日期"""
    from datetime import datetime, timedelta
    
    result = []
    seen_plans = set()
    
    # 完成关键词列表
    completion_keywords = ['已完成', '已实现', '已结束', '已完成相关', '已做完', '已搞定', '已解决', '已交付']
    
    # 根据工作分类估算天数的规则
    def estimate_days(plan_text, category):
        """根据计划内容和分类估算所需天数"""
        plan_lower = plan_text.lower()
        category_lower = category.lower() if category else ''
        
        # 快速任务（1-2天）
        quick_keywords = ['配置', '安装', '验证', '测试', '检查', '确认']
        if any(kw in plan_lower or kw in category_lower for kw in quick_keywords):
            return 2
        
        # 中等任务（3-5天）
        medium_keywords = ['对接', '调研', '培训', '部署', '调试']
        if any(kw in plan_lower or kw in category_lower for kw in medium_keywords):
            return 4
        
        # 复杂任务（5-7天）
        complex_keywords = ['开发', '上线', '实施', '建设', '搭建']
        if any(kw in plan_lower or kw in category_lower for kw in complex_keywords):
            return 6
        
        # 默认3天
        return 3
    
    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
    except:
        # 如果日期格式错误，使用当前日期
        start_date_obj = datetime.now()
    
    for plan_info in plans_with_info:
        plan = plan_info['plan']
        if plan not in seen_plans:
            # 检查后续日志内容，判断计划是否已完成
            is_completed = False
            for content_info in plan_info['subsequent_contents']:
                content = content_info['content']
                # 检查日志内容中是否包含完成关键词，并且提到了该计划
                for keyword in completion_keywords:
                    if keyword in content:
                        # 简单匹配：如果日志内容中包含计划的关键词，认为可能已完成
                        # 提取计划的前几个关键词进行匹配
                        plan_keywords = [word for word in plan.split() if len(word) > 2][:3]
                        if any(keyword in content for keyword in plan_keywords):
                            is_completed = True
                            break
                if is_completed:
                    break
            
            # 只添加未完成的计划
            if not is_completed:
                # 智能估算截至日期
                category = plan_info.get('category', '')
                estimated_days = estimate_days(plan, category)
                end_date_obj = start_date_obj + timedelta(days=estimated_days)
                end_date = end_date_obj.strftime('%Y-%m-%d')
                
                result.append({
                    '序号': len(result) + 1,
                    '工作描述': plan[:100] + '...' if len(plan) > 100 else plan,
                    '预计开始时间': start_date,
                    '计划截至': end_date,
                    '备注': ''
                })
                seen_plans.add(plan)
    
    return result

def summarize_support_requirements(logs, next_week_start, next_week_end):
    """
    使用AI整理支持需求表格
    
    Args:
        logs: 日志列表，包含各种支持字段（need_product_support, need_dev_support等）
        next_week_start: 下周开始日期
        next_week_end: 下周结束日期
    
    Returns:
        整理后的支持需求列表，格式：[{'序号': 1, '内容': '...', '支持方': '...', '时间要求': '...'}, ...]
    """
    # 收集所有支持需求及其相关信息（包括日期和后续日志内容）
    support_requirements = []
    support_types = {
        'need_product_support': '产品支持',
        'need_dev_support': '研发支持',
        'need_test_support': '测试支持',
        'need_business_support': '商务支持',
        'need_customer_support': '客户支持'
    }
    
    for i, log in enumerate(logs):
        for support_field, support_name in support_types.items():
            support_content = log.get(support_field, '')
            if support_content and support_content.strip() and support_content.strip() != '无':
                # 收集该支持需求出现后的所有日志内容，用于判断是否已完成
                subsequent_contents = []
                for j in range(i + 1, len(logs)):
                    subsequent_contents.append({
                        'date': logs[j].get('date', ''),
                        'content': logs[j].get('content', '')
                    })
                support_requirements.append({
                    'date': log.get('date', ''),
                    'category': log.get('category', ''),
                    'content': log.get('content', ''),
                    'next_plan': log.get('next_plan', ''),
                    'support_type': support_name,
                    'support_content': support_content.strip(),
                    'subsequent_contents': subsequent_contents
                })
    
    if not support_requirements:
        return []
    
    # 构建包含后续日志内容的提示词，让AI判断哪些支持需求已完成
    support_text = ""
    logs_text = ""
    for i, req in enumerate(support_requirements, 1):
        support_text += f"{i}. 【{req['support_type']}】\n"
        support_text += f"   日期：{req['date']}\n"
        support_text += f"   分类：{req['category']}\n"
        support_text += f"   工作内容：{req['content']}\n"
        if req['next_plan']:
            support_text += f"   下一步计划：{req['next_plan']}\n"
        support_text += f"   支持需求：{req['support_content']}\n\n"
        if req['subsequent_contents']:
            logs_text += f"\n支持需求{i}的后续日志内容：\n"
            for content_info in req['subsequent_contents']:
                logs_text += f"  - {content_info['date']}: {content_info['content']}\n"
    
    prompt = f"""请根据以下支持需求信息和后续日志内容，整理成支持需求表格。要求：
1. 仔细检查每个支持需求的后续日志内容，如果日志中明确提到该支持需求已完成、已实现、已解决、已提供支持等，则不要将该支持需求放入表格中
2. 合并相似的支持需求内容
3. 提取关键支持内容描述
4. 根据工作内容和下一步计划，合理估算时间要求（如：{next_week_start}、{next_week_end}、紧急、尽快等）
5. 支持方包括：产品支持、研发支持、测试支持、商务支持、客户支持

支持需求信息：
{support_text}

{logs_text}

请按照以下JSON格式返回，只返回JSON，不要其他文字（只返回未完成的支持需求）：
[
  {{"序号": 1, "内容": "支持内容描述", "支持方": "产品支持", "时间要求": "{next_week_start}"}},
  {{"序号": 2, "内容": "支持内容描述", "支持方": "研发支持", "时间要求": "尽快"}}
]
"""
    
    try:
        logger.info(f"[支持需求整理] 开始整理，支持需求数量: {len(support_requirements)}，下周时间: {next_week_start} 至 {next_week_end}")
        ai_response = call_free_ai_api(prompt)
        
        if ai_response:
            logger.info(f"[支持需求整理] AI响应成功，响应长度: {len(ai_response)} 字符")
            # 尝试解析JSON
            import re
            json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    logger.info(f"[支持需求整理] JSON解析成功，整理后条目数: {len(result)}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[支持需求整理] JSON解析失败: {str(e)}，使用简单格式化")
                    return format_support_simple(support_requirements, next_week_start)
            else:
                logger.warning("[支持需求整理] 响应中未找到JSON格式，使用简单格式化")
                return format_support_simple(support_requirements, next_week_start)
        else:
            logger.warning("[支持需求整理] AI调用返回空响应，使用简单格式化")
            return format_support_simple(support_requirements, next_week_start)
    except Exception as e:
        logger.error(f'[支持需求整理] AI整理支持需求失败: {type(e).__name__}: {str(e)}', exc_info=True)
        return format_support_simple(support_requirements, next_week_start)

def format_support_simple(support_requirements, start_date):
    """简单格式化支持需求（AI失败时的备用方案），过滤已完成的支持需求"""
    result = []
    seen_supports = set()
    
    # 完成关键词列表
    completion_keywords = ['已完成', '已实现', '已解决', '已提供', '已支持', '已交付', '已搞定', '已结束']
    
    for req in support_requirements:
        # 使用支持类型和内容作为唯一标识
        support_key = f"{req['support_type']}:{req['support_content']}"
        if support_key not in seen_supports:
            # 检查后续日志内容，判断支持需求是否已完成
            is_completed = False
            for content_info in req.get('subsequent_contents', []):
                content = content_info.get('content', '')
                # 检查日志内容中是否包含完成关键词，并且提到了该支持需求
                for keyword in completion_keywords:
                    if keyword in content:
                        # 简单匹配：如果日志内容中包含支持需求的关键词，认为可能已完成
                        # 提取支持内容的前几个关键词进行匹配
                        support_keywords = [word for word in req['support_content'].split() if len(word) > 2][:3]
                        if any(keyword in content for keyword in support_keywords):
                            is_completed = True
                            break
                if is_completed:
                    break
            
            # 只添加未完成的支持需求
            if not is_completed:
                result.append({
                    '序号': len(result) + 1,
                    '内容': req['support_content'][:100] + '...' if len(req['support_content']) > 100 else req['support_content'],
                    '支持方': req['support_type'],
                    '时间要求': start_date
                })
                seen_supports.add(support_key)
    
    return result

