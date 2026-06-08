c = open('app/main.py', encoding='utf-8').read()

old = '''        catalog_cores = _mag_db().filter_cores(
            supplier=sup_tag,
            max_height_mm=req.max_height_mm,
            max_stacks=req.max_stacks
        )'''

new = '''        mat_line = mat_d.get('material_line', None)
        mat_mu   = mat_d.get('mu_initial', None)
        catalog_cores = _mag_db().filter_cores(
            supplier=sup_tag,
            max_height_mm=req.max_height_mm,
            max_stacks=req.max_stacks,
            coated_only=getattr(req, 'coated_only', True),
            material_line=mat_line,
            mu=mat_mu
        )'''

if old in c:
    c = c.replace(old, new)
    print('Done')
else:
    print('Pattern not found - checking current state...')
    idx = c.find('filter_cores')
    print(c[idx:idx+300])

open('app/main.py', 'w', encoding='utf-8').write(c)