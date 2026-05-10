import sys
import ast

try:
    with open('app.py', 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print('SYNTAX OK')
except SyntaxError as e:
    print(f'SyntaxError at line {e.lineno}, offset {e.offset}:')
    print(f'  {e.text}')
    print(f'  {e.msg}')
    sys.exit(1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
