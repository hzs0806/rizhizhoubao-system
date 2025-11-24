#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WSGI 入口文件
用于 Gunicorn 启动应用
"""

import os
from dotenv import load_dotenv

# 在导入 app 之前加载 .env 文件（使用绝对路径和强制覆盖）
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path, override=True)

from app import create_app

# 创建应用实例
app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)

