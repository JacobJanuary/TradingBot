import re

# Read the file
with open('models/validation.py', 'r') as f:
    content = f.read()

# Fix all root validators methods signatures
patterns = [
    (r'def validate_prices\(cls, values\):', 'def validate_prices(self):'),
    (r'values\.get\(([\'"][^\'"]+(Week|Month|week|month)[^\'"]+[\'"])\)', r'self.\1'),
    (r'values\.get\(([\'"][^\'"]+[\'"])\)', r'self.\1'),
    (r'return values', 'return self'),
]

# Apply patterns
for pattern, replacement in patterns:
    content = re.sub(pattern, replacement, content)

# Clean up self.'field' to self.field
content = re.sub(r'self\.[\'"]([^\'"]+)[\'"]', r'self.\1', content)

# Write back
with open('models/validation.py', 'w') as f:
    f.write(content)

print("Fixed validators")
