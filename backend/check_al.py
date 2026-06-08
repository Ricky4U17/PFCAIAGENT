import sys
sys.path.insert(0, '.')
from app.magnetics.db import MagneticsDB

db = MagneticsDB()

# First check what mu values exist for EDGE
import csv
rows = list(csv.DictReader(open('data/magnetic_materials/magnetics_inc/toroid_catalog.csv')))
edge_rows = [r for r in rows if r.get('material_line','').strip() == 'EDGE']
print(f"EDGE rows in catalog: {len(edge_rows)}")
for r in edge_rows[:5]:
    print(f"  {r['part_number']} mu={r['mu']} AL_nom={r['AL_nom_nH']}")

# Filter with mu=60
cores = db.filter_cores(
    'magnetics_inc',
    max_height_mm=44.45,
    max_stacks=3,
    material_line='EDGE',
    mu=60
)
print(f"\nEDGE mu=60 cores found: {len(cores)}")
for c in cores[:5]:
    print(f"  {c.get('part_number')} stacks={c.get('stacks')} AL_nom_total={c.get('AL_nom_total')}")