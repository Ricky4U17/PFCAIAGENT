c = open('app/magnetics/db.py', encoding='utf-8').read()

old = '''                        if coated_only and str(row.get("coated","true")).lower() != "true":
                            continue
                        results.append({'''

new = '''                        if coated_only and str(row.get("coated","true")).lower() != "true":
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

if old in c:
    c = c.replace(old, new)
    print('Done')
else:
    print('Pattern not found')

open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)