# Fix 1: pass mu to filter_cores from main.py
c = open('app/main.py', encoding='utf-8').read()

old = '''        mat_line = mat_d.get('material_line', None)
        catalog_cores = _mag_db().filter_cores(
            supplier=sup_tag,
            max_height_mm=req.max_height_mm,
            max_stacks=req.max_stacks,
            coated_only=getattr(req,'coated_only',True),
            material_line=mat_line
        )'''

new = '''        mat_line = mat_d.get('material_line', None)
        mat_mu   = mat_d.get('mu_initial', None)
        catalog_cores = _mag_db().filter_cores(
            supplier=sup_tag,
            max_height_mm=req.max_height_mm,
            max_stacks=req.max_stacks,
            coated_only=getattr(req,'coated_only',True),
            material_line=mat_line,
            mu=mat_mu
        )'''

c = c.replace(old, new)
open('app/main.py', 'w', encoding='utf-8').write(c)
print('main.py updated' if 'mat_mu' in c else 'FAILED')

# Fix 2: add mu parameter to filter_cores in db.py
c = open('app/magnetics/db.py', encoding='utf-8').read()

old2 = 'max_stacks: int = 3, coated_only: bool = True, material_line: str = None) -> list[dict]:'
new2 = 'max_stacks: int = 3, coated_only: bool = True, material_line: str = None, mu: int = None) -> list[dict]:'

c = c.replace(old2, new2)

# Add mu filter inside the loop
old3 = '''                        if material_line and str(row.get("material_line","")).strip() != str(material_line).strip():
                            continue'''

new3 = '''                        if material_line and str(row.get("material_line","")).strip() != str(material_line).strip():
                            continue
                        if mu is not None and int(float(row.get("mu", mu))) != int(mu):
                            continue'''

c = c.replace(old3, new3)
open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print('db.py updated' if 'mu is not None' in c else 'FAILED')