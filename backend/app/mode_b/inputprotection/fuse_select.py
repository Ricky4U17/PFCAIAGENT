#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fuse_select.py
====================================================================
Line-fuse selection + coordination for the PFC front end. The fuse is
the upstream protective element for the whole input stage: it must

  1. NOT nuisance-blow on the (NTC-limited) startup pulse -> its melting
     I2t must EXCEED the worst-case startup I2t with margin.
  2. Carry the continuous worst-case input RMS current with margin,
     derated for ambient.
  3. Withstand the mains at the high-line voltage (AC voltage rating).
  4. Safely interrupt the available fault current (breaking capacity),
     which is what makes an MOV / GDT fail-short safe (Ch9 coordination).

Every threshold derives from the design (line, I_rms) or a named,
overridable margin; a missing datasheet field (e.g. melting I2t) or a
missing site input (available fault current) is surfaced as DATA
MISSING / OPEN, never silently passed. The per-candidate screen lives
in database.screen_table_fuse against the vendor Fuse_Database.xlsx.

Run:  python3 fuse_select.py --selftest
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
import sys


@dataclass
class FuseSpec:
    vac_max: float = 264.0             # Vac high-line corner (AC voltage rating gate)
    i_rms: float = 0.0                 # A, worst-case continuous input RMS (from the grid)
    available_fault_current_A: float = None  # A, site fault current (breaking-cap gate); None -> OPEN
    current_margin: float = 1.5        # I_rated >= margin * I_rms / ambient_derate
    i2t_margin: float = 2.0            # melting I2t must exceed margin * startup I2t (no nuisance blow)
    ambient_derate: float = 1.0        # fuse current derating at ambient (<1 for hot ambient)
    oversize_factor: float = 4.0       # reject fuses rated > this * the minimum (won't clear a small overload)


def requirements(fs: FuseSpec, startup_i2t: float = None) -> dict:
    """The selection thresholds a candidate fuse must meet."""
    i_rated_min = fs.current_margin * fs.i_rms / max(fs.ambient_derate, 1e-3) if fs.i_rms else 0.0
    return {
        "v_min": fs.vac_max,
        "i_rated_min": i_rated_min,
        "i_rated_max": i_rated_min * fs.oversize_factor if i_rated_min else None,
        "bc_min": fs.available_fault_current_A,          # None -> breaking-cap check OPEN
        "i2t_min": (fs.i2t_margin * startup_i2t) if startup_i2t else None,  # None -> ride-inrush OPEN
        "startup_i2t": startup_i2t,
    }


def self_test():
    print("Running fuse self-test...")
    fs = FuseSpec(vac_max=264, i_rms=20.0, available_fault_current_A=1500, current_margin=1.5)
    req = requirements(fs, startup_i2t=16.4)
    assert abs(req["i_rated_min"] - 30.0) < 1e-6, req              # 1.5 * 20
    assert req["v_min"] == 264
    assert req["bc_min"] == 1500
    assert abs(req["i2t_min"] - 32.8) < 1e-6, req                  # 2.0 * 16.4
    print(f"  [ok] thresholds: I_rated>={req['i_rated_min']:.0f}A, V>={req['v_min']:.0f}V, "
          f"BC>={req['bc_min']:.0f}A, melt-I2t>={req['i2t_min']:.1f}A2s")
    # missing inputs -> OPEN
    r2 = requirements(FuseSpec(vac_max=264, i_rms=20.0), startup_i2t=None)
    assert r2["bc_min"] is None and r2["i2t_min"] is None
    print("  [ok] missing fault current / startup I2t -> OPEN thresholds")
    print("ALL FUSE SELF-TESTS PASSED.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        self_test()
    else:
        fs = FuseSpec(i_rms=20.0, available_fault_current_A=1500)
        print("fuse requirements:", requirements(fs, startup_i2t=16.4))
