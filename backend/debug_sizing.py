import sys, json, math
sys.path.insert(0, '.')
from app.magnetics.db import MagneticsDB

db = MagneticsDB()

# Check what L_uH the state would give
# Load a test state to see the tsi fields
print("Checking filter_cores for EDGE mu=60 with height 44.45mm:")
cores = db.filter_cores(
    'magnetics_inc',
    max_height_mm=44.45,
    max_stacks=3,
    material_line='EDGE',
    mu=60
)
print(f"Found: {len(cores)} cores")
for c in cores:
    N_est = math.ceil(math.sqrt(240e-6 / (float(c.get('AL_nom_total',75)) * 1e-9)))
    L0 = N_est**2 * float(c.get('AL_nom_total',75)) * 1e-9 * 1e6
    print(f"  {c['part_number']} stacks={c['stacks']} "
          f"AL_total={c.get('AL_nom_total')}nH "
          f"N_est={N_est} L0={L0:.0f}uH")