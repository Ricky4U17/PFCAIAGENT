# Fix 1: filter_cores must filter by material_line for powder
c = open('app/magnetics/db.py', encoding='utf-8').read()

old = "def filter_cores(self, supplier: str, shape: Optional[str] = None,\n                     max_height_mm: float = 9999, min_Ae_mm2: float = 0,\n                     max_stacks: int = 3, coated_only: bool = True) -> list[dict]:"
new = "def filter_cores(self, supplier: str, shape: Optional[str] = None,\n                     max_height_mm: float = 9999, min_Ae_mm2: float = 0,\n                     max_stacks: int = 3, coated_only: bool = True,\n                     material_line: str = None) -> list[dict]:"
c = c.replace(old, new)

old2 = "                    if coated_only and str(row.get(\"coated\",\"true\")).lower() != \"true\":\n                        continue\n                    results.append({"
new2 = "                    if coated_only and str(row.get(\"coated\",\"true\")).lower() != \"true\":\n                        continue\n                    if material_line and row.get(\"material_line\",\"\") != material_line:\n                        continue\n                    results.append({"
c = c.replace(old2, new2)
open('app/magnetics/db.py', 'w', encoding='utf-8').write(c)
print("Fix 1 done: filter_cores now filters by material_line")

# Fix 2: pass material_line to filter_cores in main.py
c = open('app/main.py', encoding='utf-8').read()
old3 = "        catalog_cores = _mag_db().filter_cores(\n            supplier=sup_tag,\n            max_height_mm=req.max_height_mm,\n            max_stacks=req.max_stacks,\n            coated_only=getattr(req,'coated_only',True)\n        )"
new3 = "        mat_line = mat_d.get('material_line', None)\n        catalog_cores = _mag_db().filter_cores(\n            supplier=sup_tag,\n            max_height_mm=req.max_height_mm,\n            max_stacks=req.max_stacks,\n            coated_only=getattr(req,'coated_only',True),\n            material_line=mat_line\n        )"
if old3 in c:
    c = c.replace(old3, new3)
    print("Fix 2 done: material_line passed to filter_cores")
else:
    print("Fix 2 pattern not found - skipping")
open('app/main.py', 'w', encoding='utf-8').write(c)

# Fix 3: n_top=3 in Step7Wizard
c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()
c = c.replace('max_stacks: maxStacks, J_target: jTarget, n_top:1,',
              'max_stacks: maxStacks, J_target: jTarget, n_top:3,')
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print("Fix 3 done: n_top set to 3")

# Fix 4: handle multiple results - pick best passing one
old4 = "      const top = d.top_5?.[0]?.result ?? null"
new4 = "      const candidates = d.top_5 ?? []\n      const passing = candidates.filter((c:any) => c.result?.passed)\n      const best = passing.length ? passing[0] : candidates[0]\n      const top = best?.result ?? null\n      if (top) { top.label = best?.label ?? ''; top.rank = best?.rank ?? 1 }"
c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()
c = c.replace(old4, new4)
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print("Fix 4 done: picks best passing result from top 3")

print("\nAll fixes applied. Restart backend.")