import json

# Fix 1: Restore EDGE 60µ reference-anchored DC bias curve
# Reference Step 13.4 is validated hardware data — use it for sizing
# Keep corrected Pv_ref=400 (from Magnetics graph) — that was correct
d = json.load(open('data/magnetic_materials/magnetics_inc/edge_60.json', encoding='utf-8'))

# Restore reference-anchored DC bias (validated against Step 13.4 hardware)
d['dc_bias_rolloff']['H_Oe'] = [
    0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 88, 96,
    108, 112, 120, 124, 133, 139, 150, 175, 200, 250, 300, 400, 500, 800
]
d['dc_bias_rolloff']['mu_pct'] = [
    100, 99, 99, 97, 95, 93, 89, 85, 79, 73, 64, 60,
    54, 52, 49, 47, 44, 41, 38, 33, 30, 25, 22, 16, 14, 8
]
d['dc_bias_rolloff']['data_quality'] = 'anchored_to_reference_step13'
d['dc_bias_rolloff']['description'] = (
    'Reference-anchored: N=49, Iavg=14.15A, Le=65.5mm -> H=133Oe -> k=0.437 '
    '-> L=540uH*0.437=236uH matches Step 13.4. '
    'H50%~117 Oe for this specific core geometry. '
    'Note: Magnetics comparison graph H50%=205 Oe is for relative ranking only.'
)
d['data_quality'] = 'anchored_to_reference_step13'
json.dump(d, open('data/magnetic_materials/magnetics_inc/edge_60.json', 'w'), indent=2)
print('EDGE 60mu DC bias restored to reference-anchored values')

# Fix 2: Pass n_parallel to design_one_core in main.py
c = open('app/main.py', encoding='utf-8').read()

old = '''        # Get wire
        wire_opts = _mag_db().get_wire_options("litz", Irms_A, fsw_Hz, 100.0, req.J_target, 5)
        wire = next((w for w in wire_opts if w.get("designation","") == req.wire_designation),
                    wire_opts[0] if wire_opts else None)
        if wire is None:
            raise HTTPException(400, "No suitable wire found — check wire_designation")'''

new = '''        # Get wire — try both litz and tiw catalogs
        wire_opts = _mag_db().get_wire_options("litz", Irms_A, fsw_Hz, 100.0, req.J_target, 10)
        wire_opts += _mag_db().get_wire_options("tiw", Irms_A, fsw_Hz, 100.0, req.J_target, 10)
        wire = next((w for w in wire_opts if w.get("designation","") == req.wire_designation),
                    wire_opts[0] if wire_opts else None)
        if wire is None:
            raise HTTPException(400, "No suitable wire found — check wire_designation")
        # Apply n_parallel from winding style (bifilar=2, trifilar=3)
        n_par = getattr(req, 'n_parallel', 1) or 1
        if n_par > 1 and wire:
            wire = dict(wire)
            wire['Cu_area_mm2'] = wire.get('Cu_area_mm2', 1.0) * n_par
            wire['R_per_m_20C'] = wire.get('R_per_m_20C', 0.01) / n_par
            wire['n_parallel'] = n_par'''

if old in c:
    c = c.replace(old, new)
    print('Wire n_parallel fix applied to main.py')
else:
    print('Wire pattern not found in main.py')
open('app/main.py', 'w', encoding='utf-8').write(c)

# Fix 3: Add n_parallel to _SizingReq
c = open('app/main.py', encoding='utf-8').read()
old2 = '    FFcu_limit: float = 0.40\n    coated_only: bool = True\n    custom_core: dict = {}'
new2 = '    FFcu_limit: float = 0.40\n    coated_only: bool = True\n    custom_core: dict = {}\n    n_parallel: int = 1'
if old2 in c:
    c = c.replace(old2, new2)
    print('n_parallel added to _SizingReq')
open('app/main.py', 'w', encoding='utf-8').write(c)

print('All fixes done')