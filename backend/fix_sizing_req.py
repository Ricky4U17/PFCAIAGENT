from pathlib import Path

c = Path('app/main.py').read_text(encoding='utf-8')

# Use Optional dict to accept both null and dict
c = c.replace(
    'from pydantic import BaseModel',
    'from pydantic import BaseModel\nfrom typing import Optional'
)
c = c.replace(
    '    custom_core: dict = {}',
    '    custom_core: Optional[dict] = None'
)

# Fix usage of custom_core in the endpoint
c = c.replace(
    "        custom = getattr(req, 'custom_core', None)\n        if custom and isinstance(custom, dict) and custom.get('part_number'):",
    "        custom = req.custom_core\n        if custom and isinstance(custom, dict) and custom.get('part_number'):"
)

Path('app/main.py').write_text(c, encoding='utf-8')
print('Done')