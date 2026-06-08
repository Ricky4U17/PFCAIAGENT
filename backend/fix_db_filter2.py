c = open('app/magnetics/db.py', encoding='utf-8').read()

old = '''                        if coated_only and str(row.get("coated","true")).lower() != "true":
                            continue
                        results.append({
                            **row'''

new = '''                        if coated_only and str(row.get("coated","true")).lower() != "true":
                            continue
                        if material_line and str(row.get("material_line","")).strip() != str(material_line).strip():
                            continue
                        AL_n = float(row.get("AL_nom_nH", 75))
                        AL_i = float(row.get("AL_min_nH", 69))
                        AL_x = float(row.get("AL_max_nH", 81))
                        results.append({
                            **row,
                            "AL_nom_total": round(AL_n * S),
                            "AL_min_total": round(AL_i * S),
                            "AL_max_total": round(AL_x * S),'''

c = c.replace(old, new)
open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print('Done' if 'material_line and str' in c else 'FAILED')