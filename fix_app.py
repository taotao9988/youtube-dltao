#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 app.py 中的语法错误"""

with open(r'C:\Users\win 10\WorkBuddy\20260510183216\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到并修复有问题的行
old = "opts['cookies_from_browser'] = ('chrome', None, None, None)"
new = "opts['cookies_from_browser'] = ('chrome', None, None, None)"

if old in content:
    content = content.replace(old, new)
    print('已修复 cookies_from_browser 行')
else:
    # 尝试找到这行并替换
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'cookies_from_browser' in line and 'None' in line:
            lines[i] = "            opts['cookies_from_browser'] = ('chrome', None, None, None)"
            print(f'已修复第 {i+1} 行')
            break
    content = '\n'.join(lines)

with open(r'C:\Users\win 10\WorkBuddy\20260510183216\app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('修复完成')
