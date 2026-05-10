#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 app.py 中的所有语法错误"""
import re

path = r'C:\Users\win 10\WorkBuddy\20260510183216\app.py'

with open(path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 自动处理 BOM
    content = f.read()

print("原始文件长度: {} 字符".format(len(content)))

# Bug 1: tasks[ask_id] -> tasks[task_id] (缺少字母 t)
count1 = content.count('tasks[ask_id]')
if count1 > 0:
    content = content.replace('tasks[ask_id]', 'tasks[task_id]')
    print("修复 Bug 1: tasks[ask_id] -> tasks[task_id] ({} 处)".format(count1))
else:
    print("Bug 1 不存在 (tasks[ask_id])")

# Bug 2: {'success': True 'task_id'} 缺少逗号
# 查找这种模式：True 'task_id' 或 True "task_id"
pattern2 = r"True\s+'task_id'"
pattern2_alt = r'True\s+"task_id"'
count2 = len(re.findall(pattern2, content)) + len(re.findall(pattern2_alt, content))
if count2 > 0:
    content = re.sub(pattern2, "True, 'task_id'", content)
    content = re.sub(pattern2_alt, 'True, "task_id"', content)
    print("修复 Bug 2: 缺少逗号 ({} 处)".format(count2))
else:
    print("Bug 2 不存在 (缺少逗号)")

# 保存
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# 验证语法
import ast
try:
    ast.parse(content)
    print("\n语法检查通过！")
except SyntaxError as e:
    print("\n语法错误: {}".format(e))
    print("   行号: {}".format(e.lineno))
    print("   内容: {}".format(e.text))

print("\n修复完成！")
