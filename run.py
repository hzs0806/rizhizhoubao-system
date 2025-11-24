#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用启动脚本
"""
from app import create_app

if __name__ == '__main__':
    app = create_app()
    print('=' * 50)
    print('日志记录系统已启动')
    print('访问地址: http://localhost:5000')
    print('=' * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)

