"""
MAC地址获取工具
支持从客户端获取MAC地址（通过JavaScript）
"""
import re

def validate_mac_address(mac):
    """
    验证MAC地址格式
    
    Args:
        mac: MAC地址字符串
    
    Returns:
        bool: 是否有效
    """
    if not mac:
        return False
    
    # 标准化MAC地址（移除分隔符，转为大写）
    mac = mac.replace(':', '').replace('-', '').replace('.', '').upper()
    
    # 检查长度（应该是12个十六进制字符）
    if len(mac) != 12:
        return False
    
    # 检查是否为有效的十六进制
    if not re.match(r'^[0-9A-F]{12}$', mac):
        return False
    
    return True

def normalize_mac_address(mac):
    """
    标准化MAC地址格式（统一为 XX:XX:XX:XX:XX:XX）
    
    Args:
        mac: MAC地址字符串
    
    Returns:
        str: 标准化后的MAC地址
    """
    if not mac:
        return ''
    
    # 移除所有分隔符
    mac = mac.replace(':', '').replace('-', '').replace('.', '').upper()
    
    # 检查长度
    if len(mac) != 12:
        return mac
    
    # 添加冒号分隔符
    return ':'.join([mac[i:i+2] for i in range(0, 12, 2)])

