#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试邮件配置脚本
用于检查邮件配置是否正确
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    print(f"✓ 已加载 .env 文件: {env_path}")
else:
    print(f"⚠ .env 文件不存在: {env_path}")

# 检查邮件配置
from config import Config

print("\n=== 邮件配置检查 ===")
print(f"MAIL_HOST: {Config.MAIL_HOST}")
print(f"MAIL_PORT: {Config.MAIL_PORT}")
print(f"MAIL_USERNAME: {Config.MAIL_USERNAME or '(未设置)'}")
print(f"MAIL_PASSWORD: {'已设置' if Config.MAIL_PASSWORD else '(未设置)'}")
print(f"MAIL_USE_SSL: {Config.MAIL_USE_SSL}")

if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
    print("\n✗ 邮件配置不完整！")
    print("请在 .env 文件中设置：")
    print("  MAIL_USERNAME=your_email@qq.com")
    print("  MAIL_PASSWORD=your_email_password")
else:
    print("\n✓ 邮件配置完整")
    
    # 测试连接
    print("\n=== 测试邮件服务器连接 ===")
    try:
        import smtplib
        if Config.MAIL_USE_SSL:
            server = smtplib.SMTP_SSL(Config.MAIL_HOST, Config.MAIL_PORT, timeout=10)
        else:
            server = smtplib.SMTP(Config.MAIL_HOST, Config.MAIL_PORT, timeout=10)
            server.starttls()
        print(f"✓ 成功连接到 {Config.MAIL_HOST}:{Config.MAIL_PORT}")
        
        # 测试登录
        try:
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            print("✓ 邮件服务器登录成功")
            server.quit()
        except smtplib.SMTPAuthenticationError as e:
            print(f"✗ 邮件服务器登录失败: {e}")
            print("  请检查 MAIL_USERNAME 和 MAIL_PASSWORD 是否正确")
        except Exception as e:
            print(f"✗ 登录时出错: {e}")
    except Exception as e:
        print(f"✗ 连接邮件服务器失败: {e}")
        print("  请检查网络连接和邮件服务器配置")

