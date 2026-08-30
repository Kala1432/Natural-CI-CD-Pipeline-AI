import re

with open('backend/repositories/__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Indentation issues in method bodies (lines starting with 8+ spaces but inside a method)
# These are lines that start with whitespace but are inside a function - they have extra indentation
# Pattern: '        something' (8 spaces) should be '    ' (4 spaces) if inside a method body

# First, let's just replace the known bad patterns

# Fix: set__field=value where __ is not valid Python identifier... actually it IS valid
# The issue is that the pattern 'set__field=value' is valid Python keyword arg syntax
# The real issue is just the indentation. Let me use proper replacement.

fixes = [
    # Fix indentation of the mark_synced method body
    ('        self.document_class.objects(id=to_oid(repo_id)).update(\n            set__last_synced=datetime.utcnow\n        )',
     '        self.document_class.objects(id=to_oid(repo_id)).update(\n            set__last_synced=datetime.utcnow\n        )'),
    # Fix: update_status for Pipeline (now using **dict syntax)
    # Lines 389, 695, 731 have set__status=status format which is valid Python
]

# Actually the real issue is that 'set__status=status' is NOT valid Python syntax
# because 'set__status' is not a valid identifier for keyword argument
# In Python, keyword arguments must be valid identifiers
# So 'set__status=status' would be a syntax error

# Let me verify: in Python, you can do:
# def f(**kwargs): pass
# f(**{'set__status': 'running'})  # works
# But f(set__status='running') is a syntax error because 'set__status' is not a valid identifier

# So the replacement script broke the code by creating invalid keyword args
# The correct fix is to use **dict unpacking

# Let me fix lines 389, 695, 731
# Original: self.document_class.objects(...).update(set_(status=status, version_id=...))
# New: self.document_class.objects(...).update(**{'set__status': status, 'set__version_id': ...})

# Fix line 389: set__status=status, set__version_id=Deployment.version_id + 1
content = re.sub(
    r'\.update\(\s*set__status=status,\s*set__version_id=Deployment\.version_id \+ 1\s*\)',
    '.update(**{"set__status": status, "set__version_id": Deployment.version_id + 1})',
    content
)

# Fix line 695: set__pr_url=pr_url, set__pr_number=pr_number, set__pr_status=pr_status
content = re.sub(
    r'\.update\(\s*set__pr_url=pr_url,\s*set__pr_number=pr_number,\s*set__pr_status=pr_status\s*\)',
    '.update(**{"set__pr_url": pr_url, "set__pr_number": pr_number, "set__pr_status": pr_status})',
    content
)

# Fix line 731: set__pipeline_log=pipeline_log, set__ai_diagnosis=ai_diagnosis, set__ai_fix_diff=ai_fix_diff, set__status=status
content = re.sub(
    r'\.update\(\s*set__pipeline_log=pipeline_log,\s*set__ai_diagnosis=ai_diagnosis,\s*set__ai_fix_diff=ai_fix_diff,\s*set__status=status\s*\)',
    '.update(**{"set__pipeline_log": pipeline_log, "set__ai_diagnosis": ai_diagnosis, "set__ai_fix_diff": ai_fix_diff, "set__status": status})',
    content
)

# Fix: indent issues in mark_synced
content = re.sub(
    r'    def mark_synced\(self, repo_id\) -> None:\n        self\.document_class\.objects\(id=to_oid\(repo_id\)\)\.update\(\n            set__last_synced=datetime\.utcnow\n        \)',
    '    def mark_synced(self, repo_id) -> None:\n        self.document_class.objects(id=to_oid(repo_id)).update(set__last_synced=datetime.utcnow)',
    content
)

# Fix: mark_synced still has 12-space indent
content = re.sub(
    r'            self\.document_class\.objects\(id=to_oid\(repo_id\)\)\.update\(\n            set__last_synced=datetime\.utcnow\n        \)',
    '        self.document_class.objects(id=to_oid(repo_id)).update(set__last_synced=datetime.utcnow)',
    content
)

# Fix: set__updated_at=datetime.utcnow (line 131)
content = re.sub(
    r'        self\.document_class\.objects\(id=to_oid\(user_id\)\)\.update\(\n            set__updated_at=datetime\.utcnow\n        \)',
    '        self.document_class.objects(id=to_oid(user_id)).update(set__updated_at=datetime.utcnow)',
    content
)

with open('backend/repositories/__init__.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed!')
