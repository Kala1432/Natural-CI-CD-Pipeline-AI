import re

with open('backend/repositories/__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove imports of set_ and inc from mongoengine
content = re.sub(r'from mongoengine import .*?(set_|inc).*?\n', '', content)

# Pattern: set_(key=value, ...) -> set__key=value
# We need to handle nested parentheses too
# Simple approach: find all occurrences and replace set_(...)=value patterns

def replace_set_call(match):
    args_str = match.group(1)
    result_parts = []
    # Split by comma but respect parentheses
    depth = 0
    current = ''
    for ch in args_str:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            result_parts.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        result_parts.append(current.strip())

    updates = {}
    for part in result_parts:
        part = part.strip()
        if '=' in part:
            idx = part.index('=')
            key = part[:idx].strip()
            val = part[idx+1:].strip()
            updates[key] = val

    parts = []
    for k, v in updates.items():
        parts.append(f'set__{k}={v}')
    return ', '.join(parts)

# Replace set_(...) patterns with set__... patterns
content = re.sub(r'set_\(([^()]+)\)', replace_set_call, content)
# Handle nested set_(..., set_(...), ...) - simple: replace all set_ occurrences
content = re.sub(r'set_\(', 'set__(', content)

with open('backend/repositories/__init__.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed set_ calls in repositories')
