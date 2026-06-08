c = open('app/magnetics/db.py', encoding='utf-8').read()

# Find where stacked core dict is built and add AL_nom_total
old = '''                    if coated_only and str(row.get("coated","true")).lower() != "true":
                        continue
                    if material_line and row.get("material_line","") != material_line:
                        continue
                    results.append({'''

new = '''                    if coated_only and str(row.get("coated","true")).lower() != "true":
                        continue
                    if material_line and row.get("material_line","") != material_line:
                        continue
                    AL_nom = float(row.get("AL_nom_nH", 75))
                    AL_min = float(row.get("AL_min_nH", 69))
                    AL_max = float(row.get("AL_max_nH", 81))
                    results.append({
                        "AL_nom_total": round(AL_nom * S),
                        "AL_min_total": round(AL_min * S),
                        "AL_max_total": round(AL_max * S),'''

c = c.replace(old, new)
open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print('Done' if 'AL_nom_total' in c else 'FAILED')