c = open('app/magnetics/db.py', encoding='utf-8').read()

# Fix 1: Add material_line and mu to filter_cores signature
old = 'max_stacks: int = 3, coated_only: bool = True) -> list[dict]:'
new = 'max_stacks: int = 3, coated_only: bool = True, material_line: str = None, mu: int = None) -> list[dict]:'

if old in c:
    c = c.replace(old, new)
    print('Signature fixed')
else:
    print('Signature already updated')

# Fix 2: Add filters inside the loop
old2 = '                        results.append({'
new2 = '''                        if coated_only and str(row.get("coated","true")).lower() != "true":
                            continue
                        if material_line and str(row.get("material_line","")).strip() != str(material_line).strip():
                            continue
                        if mu is not None and int(float(row.get("mu", mu))) != int(mu):
                            continue
                        AL_n = float(row.get("AL_nom_nH", 75))
                        AL_i = float(row.get("AL_min_nH", 69))
                        AL_x = float(row.get("AL_max_nH", 81))
                        results.append({
                            "AL_nom_total": round(AL_n * S),
                            "AL_min_total": round(AL_i * S),
                            "AL_max_total": round(AL_x * S),'''

if '                        results.append({' in c and 'material_line' not in c:
    c = c.replace('                        results.append({', new2, 1)
    print('Filters added')
else:
    print('Filters already present or pattern not found')

open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print('Done')