"""
IP定位服务
先获取外网IP地址，再使用高精度定位API进行定位
支持通过医院名称/项目名称查询地理位置，然后与IP定位结果匹配
"""
import requests
import json
import os
import math
import logging
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logger = logging.getLogger(__name__)

# 缓存配置
_location_cache = {}  # IP定位缓存 {ip: (result, timestamp)}
_hospital_cache = {}  # 医院地理位置缓存 {key: (result, timestamp)}
_cache_ttl = 3600  # 缓存有效期（秒），1小时
_max_workers = 5  # 并发查询的最大线程数

def get_public_ip():
    """
    获取当前外网IP地址
    
    Returns:
        str: 外网IP地址，失败返回None
    """
    logger.info('[IP定位] 开始获取外网IP地址')
    # 使用多个服务获取外网IP，提高成功率
    ip_services = [
        'https://api.ipify.org?format=json',
        'https://api.ip.sb/ip',
        'https://ifconfig.me/ip',
        'https://icanhazip.com',
        'http://ip-api.com/json/?fields=query'
    ]
    
    for service_url in ip_services:
        try:
            logger.debug(f'[IP定位] 尝试从 {service_url} 获取外网IP')
            response = requests.get(service_url, timeout=3)
            if response.status_code == 200:
                data = response.text.strip()
                # 处理不同的返回格式
                if service_url.endswith('json'):
                    try:
                        json_data = response.json()
                        ip = json_data.get('ip') or json_data.get('query')
                        if ip:
                            logger.info(f'[IP定位] 成功获取外网IP: {ip} (来源: {service_url})')
                            return ip
                    except:
                        pass
                else:
                    # 纯文本IP
                    if data and len(data.split('.')) == 4:
                        logger.info(f'[IP定位] 成功获取外网IP: {data} (来源: {service_url})')
                        return data
        except Exception as e:
            logger.debug(f'[IP定位] 从 {service_url} 获取IP失败: {e}')
            continue
    
    logger.warning('[IP定位] 所有服务都无法获取外网IP地址')
    return None

def get_location_by_ip(ip_address=None):
    """
    通过外网IP地址获取高精度地理位置信息（带缓存）
    
    流程：
    1. 如果未提供IP，先获取外网IP
    2. 检查缓存
    3. 使用外网IP查询高精度定位
    
    Args:
        ip_address: IP地址，如果为None则先获取外网IP
    
    Returns:
        dict: 包含城市、省份等信息
    """
    from config import Config
    
    # 如果没有提供IP，先获取外网IP
    if not ip_address:
        logger.info('[IP定位] 未提供IP地址，开始获取外网IP')
        ip_address = get_public_ip()
        if not ip_address:
            logger.warning('[IP定位] 无法获取外网IP地址，使用备用方案')
            return _get_location_fallback(None)
        logger.info(f'[IP定位] 使用外网IP进行定位: {ip_address}')
    else:
        logger.info(f'[IP定位] 使用提供的IP地址进行定位: {ip_address}')
    
    # 检查缓存
    cache_key = ip_address
    if cache_key in _location_cache:
        result, timestamp = _location_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            logger.info(f'[IP定位] 使用缓存结果: {ip_address}')
            return result
        else:
            # 缓存过期，删除
            del _location_cache[cache_key]
    
    # 使用高精度IP定位服务
    # 方案1：优先使用高德地图API（对中国IP定位最准确）
    api_key = Config.AMAP_API_KEY
    if api_key:
        try:
            logger.info(f'[IP定位] 使用高德地图API查询IP位置: {ip_address}')
            url = f'https://restapi.amap.com/v3/ip?ip={ip_address}&key={api_key}'
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == '1' and data.get('info') == 'OK':
                    # 处理可能返回列表的情况
                    province = data.get('province', '')
                    city = data.get('city', '')
                    
                    # 如果是列表，转换为字符串
                    if isinstance(province, list):
                        province = province[0] if province else ''
                    if isinstance(city, list):
                        city = city[0] if city else ''
                    
                    # 确保是字符串类型
                    province = str(province) if province else ''
                    city = str(city) if city else ''
                    
                    # 如果城市和省份都为空，说明高德地图无法定位，继续尝试其他API
                    if not province and not city:
                        logger.warning(f'[IP定位] 高德地图API返回空值（可能无法定位该IP），继续尝试其他API')
                    else:
                        location_result = {
                            'city': city,
                            'region': province,
                            'country': '中国',
                            'country_code': 'CN',
                            'ip': ip_address,
                            'adcode': str(data.get('adcode', '')) if data.get('adcode') else '',
                            'rectangle': str(data.get('rectangle', '')) if data.get('rectangle') else '',
                            'success': True
                        }
                        logger.info(f'[IP定位] 高德地图定位成功: {province} - {city}')
                        # 缓存结果
                        _location_cache[ip_address] = (location_result, time.time())
                        if len(_location_cache) > 100:
                            oldest_key = min(_location_cache.items(), key=lambda x: x[1][1])[0]
                            del _location_cache[oldest_key]
                        return location_result
                else:
                    logger.warning(f'[IP定位] 高德地图API返回失败: {data.get("info", "未知错误")}')
        except Exception as e:
            logger.error(f'[IP定位] 高德地图API查询失败: {e}')
    else:
        logger.debug('[IP定位] 未配置高德地图API Key，跳过')
    
    # 方案2：使用ipinfo.io（免费，对国内IP定位较准确）
    try:
        logger.info(f'[IP定位] 使用ipinfo.io查询IP位置: {ip_address}')
        url = f'https://ipinfo.io/{ip_address}/json'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('city') or data.get('region'):
                # 解析经纬度
                loc = data.get('loc', '').split(',')
                latitude = float(loc[0]) if len(loc) == 2 and loc[0] else None
                longitude = float(loc[1]) if len(loc) == 2 and loc[1] else None
                
                location_result = {
                    'city': data.get('city', ''),
                    'region': data.get('region', ''),  # 省份/州
                    'country': data.get('country', ''),
                    'country_code': data.get('country', ''),
                    'ip': data.get('ip', ip_address),
                    'latitude': latitude,
                    'longitude': longitude,
                    'timezone': data.get('timezone', ''),
                    'isp': data.get('org', ''),  # ISP信息
                    'success': True
                }
                logger.info(f'[IP定位] ipinfo.io定位成功: {location_result.get("country")} - {location_result.get("region")} - {location_result.get("city")} (经纬度: {latitude}, {longitude})')
                # 缓存结果
                _location_cache[ip_address] = (location_result, time.time())
                if len(_location_cache) > 100:
                    oldest_key = min(_location_cache.items(), key=lambda x: x[1][1])[0]
                    del _location_cache[oldest_key]
                return location_result
            else:
                logger.warning(f'[IP定位] ipinfo.io返回数据不完整')
        else:
            logger.warning(f'[IP定位] ipinfo.io返回失败: HTTP {response.status_code}')
    except Exception as e:
        logger.error(f'[IP定位] ipinfo.io查询失败: {e}')
    
    # 方案3：使用ipapi.co（备用方案）
    try:
        logger.info(f'[IP定位] 使用ipapi.co查询IP位置: {ip_address}')
        url = f'https://ipapi.co/{ip_address}/json/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if not data.get('error'):
                location_result = {
                    'city': data.get('city', ''),
                    'region': data.get('region', ''),  # 省份/州
                    'country': data.get('country_name', ''),
                    'country_code': data.get('country_code', ''),
                    'ip': data.get('ip', ip_address),
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'timezone': data.get('timezone', ''),
                    'isp': data.get('org', ''),  # ISP信息
                    'success': True
                }
                logger.info(f'[IP定位] ipapi.co定位成功: {location_result.get("country")} - {location_result.get("region")} - {location_result.get("city")} (经纬度: {location_result.get("latitude")}, {location_result.get("longitude")})')
                # 缓存结果
                _location_cache[ip_address] = (location_result, time.time())
                if len(_location_cache) > 100:
                    oldest_key = min(_location_cache.items(), key=lambda x: x[1][1])[0]
                    del _location_cache[oldest_key]
                return location_result
            else:
                logger.warning(f'[IP定位] ipapi.co返回错误: {data.get("reason", "未知错误")}')
    except Exception as e:
        logger.error(f'[IP定位] ipapi.co查询失败: {e}')
    
    # 备用方案
    return _get_location_fallback(ip_address)

def _get_location_fallback(ip_address=None):
    """
    备用IP定位方案（当所有主要API都不可用时）
    """
    logger.warning('[IP定位] 所有主要API都不可用，使用备用方案')
    
    # 尝试使用ip.sb（国内服务，对国内IP较准确）
    try:
        logger.info(f'[IP定位] 使用ip.sb查询IP位置: {ip_address or "当前IP"}')
        if ip_address:
            url = f'https://api.ip.sb/geoip/{ip_address}'
        else:
            url = 'https://api.ip.sb/geoip'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('city') or data.get('region'):
                location_result = {
                    'city': data.get('city', ''),
                    'region': data.get('region', ''),
                    'country': data.get('country', ''),
                    'country_code': data.get('country_code', ''),
                    'ip': data.get('ip', ip_address or ''),
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'timezone': data.get('timezone', ''),
                    'isp': data.get('isp', ''),
                    'success': True
                }
                logger.info(f'[IP定位] ip.sb定位成功: {location_result.get("country")} - {location_result.get("region")} - {location_result.get("city")}')
                return location_result
    except Exception as e:
        logger.error(f'[IP定位] ip.sb查询失败: {e}')
    
    logger.error('[IP定位] 所有IP定位服务都失败')
    return {
        'city': '',
        'region': '',
        'country': '',
        'country_code': '',
        'ip': ip_address or '',
        'success': False
    }

def get_hospital_location(hospital_name, project_name=None, city=None):
    """
    通过医院名称或项目名称查询医院的实际地理位置（带缓存）
    
    Args:
        hospital_name: 医院名称
        project_name: 项目名称（可选）
        city: 城市名称（可选，用于提高查询精度）
    
    Returns:
        dict: 包含城市、省份、经纬度等信息，失败返回None
    """
    from config import Config
    
    api_key = Config.AMAP_API_KEY
    if not api_key:
        logger.warning('[医院定位] 未配置高德地图API Key，无法查询医院地理位置')
        return None
    
    # 构建查询关键词（优先使用医院名称，如果没有则使用项目名称）
    query_keyword = hospital_name or project_name
    if not query_keyword:
        logger.warning('[医院定位] 医院名称和项目名称都为空，无法查询')
        return None
    
    # 构建缓存键
    cache_key = f"{query_keyword}_{city or ''}"
    
    # 检查缓存
    if cache_key in _hospital_cache:
        result, timestamp = _hospital_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            logger.debug(f'[医院定位] 使用缓存结果: {query_keyword}')
            return result
        else:
            # 缓存过期，删除
            del _hospital_cache[cache_key]
    
    # 如果提供了城市信息，在查询关键词中包含城市名，提高查询精度
    original_keyword = query_keyword
    if city:
        query_keyword = f"{city}{query_keyword}"
        logger.info(f'[医院定位] 查询关键词: {query_keyword} (医院: {hospital_name or "无"}, 项目: {project_name or "无"}, 城市: {city})')
    else:
        logger.info(f'[医院定位] 查询关键词: {query_keyword} (医院: {hospital_name or "无"}, 项目: {project_name or "无"})')
    
    try:
        # 高德地图地理编码API
        # 文档：https://lbs.amap.com/api/webservice/guide/api/georegeo
        url = f'https://restapi.amap.com/v3/geocode/geo'
        params = {
            'key': api_key,
            'address': query_keyword,
            'output': 'json'
        }
        
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            # 高德地图返回格式：
            # {
            #   "status": "1",
            #   "info": "OK",
            #   "count": "1",
            #   "geocodes": [{
            #     "formatted_address": "北京市朝阳区xxx",
            #     "country": "中国",
            #     "province": "北京市",
            #     "city": "北京市",
            #     "district": "朝阳区",
            #     "location": "116.397128,39.916527"
            #   }]
            # }
            
            if data.get('status') == '1' and data.get('count') != '0':
                geocode = data.get('geocodes', [{}])[0]
                location_str = geocode.get('location', '')
                
                if location_str:
                    lon, lat = map(float, location_str.split(','))
                    
                    location_result = {
                        'city': geocode.get('city', ''),
                        'region': geocode.get('province', ''),
                        'district': geocode.get('district', ''),
                        'formatted_address': geocode.get('formatted_address', ''),
                        'latitude': lat,
                        'longitude': lon,
                        'success': True
                    }
                    logger.info(f'[医院定位] 查询成功: {location_result.get("region")} - {location_result.get("city")} - {location_result.get("district")} (地址: {location_result.get("formatted_address")}, 经纬度: {lat}, {lon})')
                    
                    # 缓存结果
                    _hospital_cache[cache_key] = (location_result, time.time())
                    # 限制缓存大小
                    if len(_hospital_cache) > 200:
                        oldest_key = min(_hospital_cache.items(), key=lambda x: x[1][1])[0]
                        del _hospital_cache[oldest_key]
                    
                    return location_result
                else:
                    logger.warning(f'[医院定位] 查询结果中无经纬度信息: {query_keyword}')
            else:
                logger.warning(f'[医院定位] 高德地图API查询失败: {data.get("info", "未知错误")} (关键词: {query_keyword})')
    except Exception as e:
        logger.error(f'[医院定位] 查询医院地理位置失败 ({query_keyword}): {e}')
    
    logger.warning(f'[医院定位] 无法获取医院地理位置: {query_keyword}')
    return None

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    计算两个经纬度之间的距离（公里）
    使用Haversine公式
    
    Args:
        lat1, lon1: 第一个点的纬度和经度
        lat2, lon2: 第二个点的纬度和经度
    
    Returns:
        float: 距离（公里）
    """
    if not all([lat1, lon1, lat2, lon2]):
        return None
    
    # 将角度转换为弧度
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    # Haversine公式
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    # 地球半径（公里）
    R = 6371.0
    
    return R * c

def match_projects_by_location(location_info, projects):
    """
    根据地理位置信息匹配项目（优化版）
    
    新的匹配逻辑：
    1. 获取IP定位信息（城市、省份、国家、经纬度）
    2. 对每个项目，通过医院名称/项目名称查询实际地理位置
    3. 比较医院地理位置与IP定位结果：
       - 优先比较城市、省份（文本匹配）
       - 如果有经纬度，计算距离（距离越近分数越高）
    4. 支持VPN用户降分
    5. 返回匹配的项目列表
    
    Args:
        location_info: IP定位信息字典（包含city, region, country, latitude, longitude等）
        projects: 项目列表
    
    Returns:
        list: 匹配的项目列表，按匹配度排序
    """
    logger.info('[项目匹配] 开始匹配项目')
    logger.info(f'[项目匹配] IP定位信息: {location_info}')
    
    if not location_info.get('success'):
        logger.warning('[项目匹配] IP定位失败，无法进行匹配')
        return []
    
    # IP定位信息（处理可能为列表或None的情况）
    ip_city_raw = location_info.get('city', '')
    ip_region_raw = location_info.get('region', '')
    ip_country_raw = location_info.get('country', '')
    
    # 转换为字符串并清理
    if isinstance(ip_city_raw, list):
        ip_city = str(ip_city_raw[0]) if ip_city_raw else ''
    else:
        ip_city = str(ip_city_raw) if ip_city_raw else ''
    
    if isinstance(ip_region_raw, list):
        ip_region = str(ip_region_raw[0]) if ip_region_raw else ''
    else:
        ip_region = str(ip_region_raw) if ip_region_raw else ''
    
    if isinstance(ip_country_raw, list):
        ip_country = str(ip_country_raw[0]) if ip_country_raw else ''
    else:
        ip_country = str(ip_country_raw) if ip_country_raw else ''
    
    # 清理空白字符
    ip_city = ip_city.strip()
    ip_region = ip_region.strip()
    ip_country = ip_country.strip()
    
    ip_lat = location_info.get('latitude')
    ip_lon = location_info.get('longitude')
    
    logger.info(f'[项目匹配] IP定位结果: 国家={ip_country}, 省份={ip_region}, 城市={ip_city}, 经纬度=({ip_lat}, {ip_lon})')
    logger.info(f'[项目匹配] 待匹配项目数量: {len(projects)}')
    
    # 标准化IP定位的城市和省份名称
    ip_city_lower = ip_city.lower()
    ip_region_lower = ip_region.lower()
    ip_country_lower = ip_country.lower()
    
    # 标准化处理（移除常见后缀）
    ip_city_normalized = ip_city_lower.replace('市', '').replace('县', '').replace('区', '').replace('自治州', '').replace('地区', '').replace('盟', '')
    ip_region_normalized = ip_region_lower.replace('省', '').replace('市', '').replace('自治区', '').replace('特别行政区', '').replace('维吾尔', '').replace('回族', '').replace('壮族', '')
    
    # 如果检测到非中国IP（可能是VPN），降低匹配要求
    is_vpn = ip_country_lower and 'china' not in ip_country_lower and '中国' not in ip_country_lower
    if is_vpn:
        logger.info('[项目匹配] 检测到VPN用户（非中国IP），匹配分数将降低30%')
    
    matched_projects = []
    
    # 预处理：过滤无效项目，准备并发查询
    valid_projects = []
    for project in projects:
        project_name = (project.get('name') or '').strip()
        hospital_name = (project.get('hospital_name') or '').strip()
        if project_name or hospital_name:
            valid_projects.append(project)
        else:
            project_id = project.get('id', '未知')
            logger.debug(f'[项目匹配] 项目 ID={project_id} 没有项目名称和医院名称，跳过')
    
    if not valid_projects:
        logger.info('[项目匹配] 没有有效的项目需要匹配')
        return []
    
    logger.info(f'[项目匹配] 有效项目数量: {len(valid_projects)}/{len(projects)}')
    
    # 并发查询医院地理位置
    def query_hospital_location(project):
        """查询单个项目的地理位置"""
        project_id = project.get('id', '未知')
        project_name = (project.get('name') or '').strip()
        hospital_name = (project.get('hospital_name') or '').strip()
        project_region = (project.get('region') or '').strip()
        
        hospital_location = get_hospital_location(
            hospital_name=hospital_name,
            project_name=project_name,
            city=project_region
        )
        
        return project, hospital_location
    
    # 使用线程池并发查询
    hospital_locations = {}
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=_max_workers) as executor:
        future_to_project = {
            executor.submit(query_hospital_location, project): project 
            for project in valid_projects
        }
        
        for future in as_completed(future_to_project):
            try:
                project, hospital_location = future.result()
                hospital_locations[project.get('id')] = hospital_location
            except Exception as e:
                project = future_to_project[future]
                project_id = project.get('id', '未知')
                logger.error(f'[项目匹配] 项目 ID={project_id} 查询地理位置失败: {e}')
                hospital_locations[project.get('id')] = None
    
    query_time = time.time() - start_time
    logger.info(f'[项目匹配] 并发查询完成，耗时: {query_time:.2f}秒')
    
    # 进行匹配评分
    for idx, project in enumerate(valid_projects, 1):
        project_id = project.get('id', '未知')
        logger.debug(f'[项目匹配] [{idx}/{len(valid_projects)}] 处理项目 ID={project_id}')
        project_name = (project.get('name') or '').strip()
        hospital_name = (project.get('hospital_name') or '').strip()
        project_region = (project.get('region') or '').strip()
        
        # 获取已查询的地理位置
        hospital_location = hospital_locations.get(project_id)
        
        score = 0
        distance_km = None
        match_details = []  # 记录匹配详情
        
        if hospital_location and hospital_location.get('success'):
            # 获取医院的实际地理位置
            hospital_city = hospital_location.get('city', '').strip()
            hospital_region = hospital_location.get('region', '').strip()
            hospital_lat = hospital_location.get('latitude')
            hospital_lon = hospital_location.get('longitude')
            
            # 标准化医院地理位置
            hospital_city_lower = hospital_city.lower()
            hospital_region_lower = hospital_region.lower()
            hospital_city_normalized = hospital_city_lower.replace('市', '').replace('县', '').replace('区', '').replace('自治州', '').replace('地区', '').replace('盟', '')
            hospital_region_normalized = hospital_region_lower.replace('省', '').replace('市', '').replace('自治区', '').replace('特别行政区', '').replace('维吾尔', '').replace('回族', '').replace('壮族', '')
            
            # 1. 城市匹配（最高优先级）
            if ip_city_lower and hospital_city_lower:
                # 完全匹配
                if ip_city_lower == hospital_city_lower:
                    score += 50
                    match_details.append('城市完全匹配(+50)')
                # 标准化后完全匹配
                elif ip_city_normalized and hospital_city_normalized and ip_city_normalized == hospital_city_normalized:
                    score += 45
                    match_details.append('城市标准化完全匹配(+45)')
                # 包含匹配
                elif ip_city_lower in hospital_city_lower or hospital_city_lower in ip_city_lower:
                    score += 40
                    match_details.append('城市包含匹配(+40)')
                # 标准化后包含匹配
                elif ip_city_normalized and hospital_city_normalized:
                    if ip_city_normalized in hospital_city_normalized or hospital_city_normalized in ip_city_normalized:
                        score += 35
                        match_details.append('城市标准化包含匹配(+35)')
            
            # 2. 省份匹配
            if ip_region_lower and hospital_region_lower:
                # 完全匹配
                if ip_region_lower == hospital_region_lower:
                    score += 30
                    match_details.append('省份完全匹配(+30)')
                # 标准化后完全匹配
                elif ip_region_normalized and hospital_region_normalized and ip_region_normalized == hospital_region_normalized:
                    score += 25
                    match_details.append('省份标准化完全匹配(+25)')
                # 包含匹配
                elif ip_region_lower in hospital_region_lower or hospital_region_lower in ip_region_lower:
                    score += 20
                    match_details.append('省份包含匹配(+20)')
                # 标准化后包含匹配
                elif ip_region_normalized and hospital_region_normalized:
                    if ip_region_normalized in hospital_region_normalized or hospital_region_normalized in ip_region_normalized:
                        score += 15
                        match_details.append('省份标准化包含匹配(+15)')
            
            # 3. 距离匹配（如果有经纬度信息）
            if ip_lat and ip_lon and hospital_lat and hospital_lon:
                distance_km = calculate_distance(ip_lat, ip_lon, hospital_lat, hospital_lon)
                if distance_km is not None:
                    # 距离越近，分数越高
                    # 0-10公里：+30分
                    # 10-50公里：+20分
                    # 50-100公里：+10分
                    # 100-200公里：+5分
                    # 超过200公里：+0分
                    if distance_km <= 10:
                        score += 30
                        match_details.append(f'距离匹配(≤10km, +30)')
                    elif distance_km <= 50:
                        score += 20
                        match_details.append(f'距离匹配(≤50km, +20)')
                    elif distance_km <= 100:
                        score += 10
                        match_details.append(f'距离匹配(≤100km, +10)')
                    elif distance_km <= 200:
                        score += 5
                        match_details.append(f'距离匹配(≤200km, +5)')
                    logger.info(f'[项目匹配] 项目 ID={project_id} 距离计算: {distance_km:.2f}公里')
        else:
            # 如果无法查询到医院地理位置，回退到文本匹配
            logger.warning(f'[项目匹配] 项目 ID={project_id} 无法查询到医院地理位置，使用文本匹配')
            # 使用项目配置的region字段或从项目名称/医院名称中提取
            project_region_lower = project_region.lower() if project_region else ''
            project_region_normalized = project_region_lower.replace('市', '').replace('县', '').replace('区', '').replace('自治州', '').replace('地区', '').replace('盟', '')
            
            # 城市匹配
            if ip_city_lower and project_region_lower:
                if ip_city_lower == project_region_lower:
                    score += 30
                    match_details.append('城市完全匹配(文本, +30)')
                elif ip_city_lower in project_region_lower or project_region_lower in ip_city_lower:
                    score += 25
                    match_details.append('城市包含匹配(文本, +25)')
                elif ip_city_normalized and project_region_normalized:
                    if ip_city_normalized == project_region_normalized:
                        score += 28
                        match_details.append('城市标准化完全匹配(文本, +28)')
                    elif ip_city_normalized in project_region_normalized or project_region_normalized in ip_city_normalized:
                        score += 22
                        match_details.append('城市标准化包含匹配(文本, +22)')
            
            # 从项目名称/医院名称中提取城市信息
            search_text = (project_name + ' ' + hospital_name).lower()
            if ip_city_normalized and len(ip_city_normalized) >= 2 and ip_city_normalized in search_text:
                score += 15
                match_details.append('城市名称匹配(文本, +15)')
            if ip_region_normalized and len(ip_region_normalized) >= 2 and ip_region_normalized in search_text:
                score += 10
                match_details.append('省份名称匹配(文本, +10)')
        
        # 如果使用VPN，降低匹配分数
        original_score = score
        if is_vpn:
            score = int(score * 0.7)  # 降低30%的匹配分数
            match_details.append(f'VPN降分({original_score} -> {score})')
        
        logger.info(f'[项目匹配] 项目 ID={project_id} 匹配结果: 分数={score} (详情: {", ".join(match_details) if match_details else "无匹配项"})')
        
        # 匹配阈值：分数 >= 10 的项目才会被返回
        if score >= 10:
            matched_projects.append({
                'project': project,
                'score': score,
                'distance_km': distance_km
            })
            logger.info(f'[项目匹配] 项目 ID={project_id} 匹配成功，分数={score}，距离={distance_km if distance_km else "未知"}km')
        else:
            logger.info(f'[项目匹配] 项目 ID={project_id} 匹配失败，分数={score} < 10（阈值）')
    
    # 按匹配度排序（分数高的在前，如果分数相同，距离近的在前）
    matched_projects.sort(key=lambda x: (
        -x['score'],  # 分数降序
        x['distance_km'] if x['distance_km'] is not None else float('inf')  # 距离升序
    ))
    
    logger.info(f'[项目匹配] 匹配完成，共找到 {len(matched_projects)} 个匹配项目')
    for idx, item in enumerate(matched_projects, 1):
        project_id = item['project'].get('id', '未知')
        logger.info(f'[项目匹配] 匹配项目 [{idx}]: ID={project_id}, 分数={item["score"]}, 距离={item["distance_km"] if item["distance_km"] else "未知"}km')
    
    return [item['project'] for item in matched_projects]

