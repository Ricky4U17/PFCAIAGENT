c = open('app/magnetics/db.py', encoding='utf-8').read()

# Add material_line parameter to filter_cores signature
old_sig = 'max_stacks: int = 3, coated_only: bool = True) -> list[dict]:'
new_sig = 'max_stacks: int = 3, coated_only: bool = True, material_line: str = None) -> list[dict]:'

if old_sig in c:
    c = c.replace(old_sig, new_sig)
    print('Signature updated')
else:
    print('Signature already updated or different')

# Add material_line filter inside the loop
old_filter = '''                    if coated_only and str(row.get("coated","true")).lower() != "true":
                        continue
                    results.append({'''

new_filter = '''                    if coated_only and str(row.get("coated","true")).lower() != "true":
                        continue
                    if material_line and str(row.get("material_line","")).strip() != material_line.strip():
                        continue
                    results.append({'''

if old_filter in c:
    c = c.replace(old_filter, new_filter)
    print('Material line filter added')
else:
    print('Filter pattern not found - checking alternate...')
    idx = c.find('results.append({')
    print(c[idx-300:idx+50])

open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print('Done')