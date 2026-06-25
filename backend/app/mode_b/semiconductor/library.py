"""
Component library — provision for selecting a part instead of entering it by hand.
==================================================================================
A designer can either (a) provide an external part number + datasheet values (the manual
path), or (b) pick a stored part from this library. Each entry is a full component block in
the engine's format ({manufacturer, part_number, …datasheet params}), so a selected part
drops straight into the same cfg the manual path produces — no engine/adapter change.

This is intentionally a small seed. The real local database (curated parts, search/suggest)
will replace `_SEED` / `list_components` later without touching the GUI or the loss engine.
"""
from __future__ import annotations

_SEED = {
    "mosfet": [
        {"manufacturer": "Infineon", "part_number": "IMZ120R030M1H — SiC 1200 V 30 mΩ",
         "tech": "sic", "rdson_25": 0.030, "rdson_tj": [[25, 125], [1.0, 1.4]],
         "ciss": 2300e-12, "qgd": 24e-9, "vth": 4.0, "vpl": 9.0, "qg": 105e-9,
         "eoss_at_v": [[100, 400, 800], [2e-6, 8e-6, 16e-6]], "rth_jc": 0.45,
         "vg": 18.0, "rg": 4.0, "rth_cs": 0.3},
        {"manufacturer": "STMicroelectronics", "part_number": "STW40N60DM6 — Si SJ 600 V",
         "tech": "si", "rdson_25": 0.075, "rdson_tj": [[25, 100], [1.0, 1.9]],
         "ciss": 2700e-12, "qgd": 32e-9, "vth": 3.5, "vpl": 5.5, "qg": 75e-9,
         "eoss_at_v": [[100, 400], [3e-6, 12e-6]], "rth_jc": 0.30,
         "vg": 12.0, "rg": 6.8, "rth_cs": 0.3},
    ],
    "diode": [
        {"manufacturer": "Wolfspeed", "part_number": "C4D20120A — SiC Schottky 1200 V 20 A",
         "is_sic": True, "vf_curve": [[1, 5, 20], [0.9, 1.1, 1.5]], "qc": 18e-9,
         "vf_tco": 0.0015, "rth_jc": 0.6, "rth_cs": 0.3},
        {"manufacturer": "Vishay", "part_number": "VS-15ETH06 — Si fast 600 V",
         "is_sic": False, "vf_curve": [[1, 10, 30], [1.1, 1.5, 1.9]], "qrr": 150e-9,
         "vf_tco": -0.002, "rth_jc": 0.8, "rth_cs": 0.3},
    ],
    "bridge": [
        {"manufacturer": "Vishay", "part_number": "GBPC3508 — 35 A diode bridge",
         "topology": "diode", "vf_curve": [[1, 12, 24], [0.75, 0.95, 1.15]],
         "n_parallel": 2, "rth_jc": 1.0, "rth_cs": 0.5},
    ],
}


def list_components(kind: str | None = None):
    """All library parts, or just one kind ('mosfet'|'diode'|'bridge')."""
    if kind is None:
        return {k: list(v) for k, v in _SEED.items()}
    return list(_SEED.get(kind, []))


def get_component(kind: str, part_number: str):
    for p in _SEED.get(kind, []):
        if p.get("part_number") == part_number:
            return dict(p)
    return None
