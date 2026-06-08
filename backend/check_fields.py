import sys
sys.path.insert(0, '.')
from app.mode_b.step7_magnetic_calc import DesignResult
import dataclasses
for f in dataclasses.fields(DesignResult):
    print(f.name)