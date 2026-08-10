"""
registry.py — the canonical parameter registry for semiconductor loss parameters.
=================================================================================
`canonical_parameters.json` is the single source of truth for NAMING. This module loads it,
validates it against the engine dataclasses, and provides the helpers that let every layer speak
one vocabulary:

    extraction  ->  canonical key
    confirmation ->  report_label + display unit + conditions
    engine      ->  engine_fields
    report      ->  report_label

Three problems this exists to prevent, all of them observed in this codebase:

  1. ONE QUANTITY UNDER TWO NAMES. `vg` (switching model) and `vg_drive` (gate loss) are the same
     physical gate-drive voltage. `to_block` wrote only `vg`, so gate loss silently used the
     dataclass default of 12 V while switching used 15 V. The registry declares both under one key
     and `expand_to_engine_fields()` writes them together, so the split cannot recur.
  2. A NAME CHANGING BETWEEN LAYERS. The vendor column is `rdson`, the engine field is `rdson_25`,
     the report says "R_DS(on)". The mapping now lives in one declaration instead of being
     rediscovered in each module.
  3. A FIELD DRIFTING OUT OF SIGHT. `audit_engine_dataclasses()` asserts every dataclass field is
     accounted for, so adding a field to the engine without registering it fails the suite.

WHAT THIS MODULE DOES NOT DO. It does not read values, validate magnitudes against the catalogue
(that is `app/plausibility.py`), or enforce that required fields were actually supplied (that is
M1). It is naming and structure only.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REGISTRY_PATH = os.path.join(_HERE, "canonical_parameters.json")

_CACHE: Optional[dict] = None


class RegistryError(ValueError):
    """Raised when the registry is internally inconsistent, or a caller asks for a name that is not
    in it. Deliberately loud: a silent miss here is how a quantity acquires a second name."""


# ── loading ───────────────────────────────────────────────────────────────────────────────────
def load() -> dict:
    """Load and self-validate the registry. Cached; the file is read once per process."""
    global _CACHE
    if _CACHE is None:
        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            reg = json.load(f)
        _validate(reg)
        _CACHE = reg
    return _CACHE


def _validate(reg: dict) -> None:
    """Structural checks that must hold before anything trusts the file."""
    if not reg.get("schema_version"):
        raise RegistryError("registry has no schema_version")

    units, classes = reg["units"], reg["device_classes"]
    seen_keys: set[str] = set()
    seen_engine_fields: dict[str, str] = {}

    for p in reg["parameters"]:
        key = p.get("key")
        if not key:
            raise RegistryError(f"parameter with no key: {p}")
        if key in seen_keys:
            raise RegistryError(f"duplicate canonical key {key!r}")
        seen_keys.add(key)

        for u in (p["si_unit"], p["display_unit"]):
            if u not in units:
                raise RegistryError(f"{key}: unit {u!r} is not in the units table")
        if units[p["display_unit"]]["si"] != p["si_unit"]:
            raise RegistryError(
                f"{key}: display unit {p['display_unit']!r} does not belong to SI unit "
                f"{p['si_unit']!r}")

        for dc in p["device_classes"]:
            if dc not in classes:
                raise RegistryError(f"{key}: unknown device class {dc!r}")

        if p["source"] not in ("datasheet", "design", "derived"):
            raise RegistryError(f"{key}: source must be datasheet|design|derived, got {p['source']!r}")

        # An engine field may belong to exactly ONE canonical key. Two keys claiming one field is
        # the ambiguity this registry exists to remove.
        for ef in p.get("engine_fields", []):
            if ef in seen_engine_fields:
                raise RegistryError(
                    f"engine field {ef!r} is claimed by both {seen_engine_fields[ef]!r} and {key!r}")
            seen_engine_fields[ef] = key

        rng = p.get("plausible")
        if rng and not (rng["min"] < rng["max"]):
            raise RegistryError(f"{key}: plausible range is not ordered")


# ── lookup ────────────────────────────────────────────────────────────────────────────────────
def parameters(device_class: Optional[str] = None) -> list[dict]:
    """Every parameter, or only those applying to one device class."""
    ps = load()["parameters"]
    if device_class is None:
        return list(ps)
    if device_class not in load()["device_classes"]:
        raise RegistryError(f"unknown device class {device_class!r}")
    return [p for p in ps if device_class in p["device_classes"]]


def get(key: str) -> dict:
    """One parameter by canonical key. Raises rather than returning None — a caller that guesses a
    key must find out immediately, not carry a silent None into a calculation."""
    for p in load()["parameters"]:
        if p["key"] == key:
            return p
    raise RegistryError(f"no canonical parameter named {key!r}")


def key_for_engine_field(field: str) -> str:
    """Reverse lookup: which canonical quantity does this engine field carry?"""
    for p in load()["parameters"]:
        if field in p.get("engine_fields", []):
            return p["key"]
    raise RegistryError(f"engine field {field!r} is not in the registry")


def device_class(name: str) -> dict:
    try:
        return load()["device_classes"][name]
    except KeyError:
        raise RegistryError(f"unknown device class {name!r}") from None


def conduction_loss_form(name: str) -> str:
    """The conduction-loss form is a property of the DEVICE CLASS, not a global assumption.
    I^2*R is right for a MOSFET and wrong for an IGBT (V_ce0*I_avg + r_ce*I_rms^2)."""
    return device_class(name)["conduction_loss_form"]


def required_keys(device_class_name: str, consumer: str = "loss_engine") -> list[str]:
    """Canonical keys a given consumer cannot do without, for this device class. M1 turns this into
    a hard gate; here it is only the declaration."""
    return [p["key"] for p in parameters(device_class_name)
            if p.get("required") and consumer in p.get("consumed_by", [])]


# ── units ─────────────────────────────────────────────────────────────────────────────────────
def to_si(key: str, value: float, unit: Optional[str] = None) -> float:
    """Convert a value in its display (or a named) unit into SI for storage."""
    p = get(key)
    u = unit or p["display_unit"]
    units = load()["units"]
    if u not in units:
        raise RegistryError(f"{key}: unknown unit {u!r}")
    if units[u]["si"] != p["si_unit"]:
        raise RegistryError(f"{key}: unit {u!r} is not compatible with SI unit {p['si_unit']!r}")
    return float(value) * units[u]["factor"]


def to_display(key: str, si_value: float) -> tuple[float, str]:
    """SI value -> (number, unit label) for the confirmation screen and the report. Reviewers must
    see `33 mΩ`, not `0.033`."""
    p = get(key)
    u = load()["units"][p["display_unit"]]
    return float(si_value) / u["factor"], u["label"]


# ── the anti-disconnect helper ────────────────────────────────────────────────────────────────
def expand_to_engine_fields(values: dict) -> dict:
    """Canonical values -> engine dataclass kwargs, writing EVERY alias of each quantity.

        expand_to_engine_fields({"V_GS_drive": 18.0}) -> {"vg": 18.0, "vg_drive": 18.0}

    This is the structural fix for defect 1. A caller cannot write one alias and forget the other,
    because it never names the engine fields at all.
    """
    out: dict[str, Any] = {}
    for key, val in values.items():
        p = get(key)                       # unknown key raises, by design
        for ef in p.get("engine_fields", []):
            out[ef] = val
    return out


def to_record_fields(values: dict) -> dict:
    """Canonical values -> the names this quantity carries OUTSIDE the registry.

        to_record_fields({"V_DSS": 650.0, "I_FSM": 180.0}) -> {"vdss": 650.0, "ifsm_A": 180.0}

    Two such names exist and both are already declared: `db_field` is the vendor catalogue's column
    and `meta_field` is the part-block metadata key. The plausibility rules read part RECORDS in
    that shape, so this is what lets a datasheet-sourced profile be screened by the same rules that
    screen a catalogue row — without a second mapping table living in a module, which is precisely
    how `vdss`/`vrrm` and `V_DSS`/`V_RRM` drift apart.

    A canonical quantity with neither name is skipped: it exists only inside the registry.
    """
    out: dict[str, Any] = {}
    for key, val in values.items():
        p = get(key)                       # unknown key raises, by design
        field = p.get("db_field") or p.get("meta_field")
        if field:
            out[field] = val
    return out


def record_field_owners() -> dict[str, str]:
    """External field name -> the canonical key that owns it. Used to prove every input the
    plausibility rules read is reachable from the registry."""
    out: dict[str, str] = {}
    for p in load()["parameters"]:
        field = p.get("db_field") or p.get("meta_field")
        if field:
            out.setdefault(field, p["key"])
    return out


def aliased_keys() -> dict[str, list[str]]:
    """Canonical keys whose quantity is carried by more than one engine field. Each of these is a
    latent disconnect that `expand_to_engine_fields` closes."""
    return {p["key"]: p["engine_fields"] for p in load()["parameters"]
            if len(p.get("engine_fields", [])) > 1}


# ── audits ────────────────────────────────────────────────────────────────────────────────────
def audit_engine_dataclasses() -> dict[str, list[str]]:
    """Compare the registry against the engine dataclasses in both directions.

    Returns {"unregistered": [...], "orphaned": [...]}:
      unregistered — a dataclass field no canonical key claims (the engine grew a parameter and the
                     registry was not told)
      orphaned     — a registry engine_field that no dataclass has (the engine dropped or renamed a
                     field and the registry was not told)
    Both are naming disconnects; both should be empty.
    """
    import dataclasses as dc
    from app.mode_b.semiconductor.pfc_loss_model import Mosfet, Diode, Bridge

    engine_fields: set[str] = set()
    for cls in (Mosfet, Diode, Bridge):
        engine_fields |= {f.name for f in dc.fields(cls)}

    registered: set[str] = set()
    for p in load()["parameters"]:
        registered |= set(p.get("engine_fields", []))

    return {"unregistered": sorted(engine_fields - registered),
            "orphaned": sorted(registered - engine_fields)}


def audit_device_classes() -> list[dict]:
    """Check every class's declared engine_fields against ITS OWN dataclass.

    `audit_engine_dataclasses` pools Mosfet, Diode and Bridge into one set, so a field that exists
    on ANY of them looks covered on ALL of them. That pooling hid eleven declarations — `n_parallel`
    and `share_worst` on the diode classes, the Q_rr curves on the bridge, `tech` on both — where
    the class claimed a field its dataclass does not have. None of them had fired yet only because
    no builder had written one; the first that did would have raised TypeError inside the engine
    constructor, which is the naming disconnect this registry exists to make impossible.
    """
    import dataclasses as dc
    from app.mode_b.semiconductor.pfc_loss_model import Mosfet, Diode, Bridge

    known = {"Mosfet": Mosfet, "Diode": Diode, "Bridge": Bridge}
    data = load()
    out: list[dict] = []
    for name, cls in data["device_classes"].items():
        engine = cls.get("engine_dataclass")
        if engine not in known:               # a class with no engine binding yet (e.g. igbt)
            continue
        fields = {f.name for f in dc.fields(known[engine])}
        for p in data["parameters"]:
            if name not in (p.get("device_classes") or []):
                continue
            for ef in p.get("engine_fields", []):
                if ef not in fields:
                    out.append({"device_class": name, "key": p["key"],
                                "engine_field": ef, "engine_dataclass": engine})
    return out


# Engine fields a class deliberately does NOT claim. Most of these are the point of a design
# decision rather than an oversight: a SiC Schottky must not carry `qrr` and a silicon diode must
# not carry `qc`, because that is what stops a wrong `is_sic` from quietly reading a stale number
# from the other technology (C210). Listing them here is what lets the unclaimed-field report be
# useful instead of nine lines of noise that pressure someone into breaking the property.
DELIBERATELY_UNCLAIMED = {
    "sic_schottky": {"qrr", "qrr_didt_curve", "qrr_if_curve", "qrr_tco", "k_qrr"},
    "si_diode": {"qc", "k_qc"},
    "gan_hemt": {"vsd", "qrr_body"},          # no body diode to characterise
}


def unclaimed_engine_fields() -> list[dict]:
    """Engine fields of a class's dataclass that no parameter of that class supplies.

    INFORMATIONAL, not an error. Such a field can only ever hold its dataclass default, which is
    fine when that is deliberate and a silent gap when it is not — so each is reported with whether
    it was declared deliberate. The pooled audit cannot see any of this: the field is normally
    declared for some OTHER class, which is how `k_rdson` came to be a Bridge field that no bridge
    parameter claims.
    """
    import dataclasses as dc
    from app.mode_b.semiconductor.pfc_loss_model import Mosfet, Diode, Bridge

    known = {"Mosfet": Mosfet, "Diode": Diode, "Bridge": Bridge}
    data = load()
    out: list[dict] = []
    for name, cls in data["device_classes"].items():
        engine = cls.get("engine_dataclass")
        if engine not in known:
            continue
        fields = {f.name for f in dc.fields(known[engine])}
        claimed = {ef for p in data["parameters"]
                   if name in (p.get("device_classes") or [])
                   for ef in p.get("engine_fields", [])}
        for field in sorted(fields - claimed):
            out.append({"device_class": name, "engine_field": field,
                        "engine_dataclass": engine,
                        "deliberate": field in DELIBERATELY_UNCLAIMED.get(name, set())})
    return out


def audit_block(block: dict, strict: bool = False) -> list[dict]:
    """Check one engine block for alias disconnects — the same quantity written under one field
    name but not its siblings, or written with different values.

    Returns a list of findings; empty means every aliased quantity is internally consistent.
    `strict` also reports a quantity where no alias was written at all, which is legitimate when
    the engine default is intended and a defect when it is not (M1 decides that).
    """
    findings = []
    for key, fields in aliased_keys().items():
        present = {f: block[f] for f in fields if f in block and block[f] is not None}
        if not present:
            if strict:
                findings.append({"key": key, "fields": fields, "issue": "not_written",
                                 "message": f"{key} was not written to any of {fields}; the engine "
                                            f"default will be used for all of them."})
            continue
        missing = [f for f in fields if f not in present]
        if missing:
            findings.append({"key": key, "fields": fields, "written": present, "missing": missing,
                             "issue": "partial_write",
                             "message": f"{key} was written to {sorted(present)} but not to "
                                        f"{missing}; those fall back to the engine default, so one "
                                        f"physical quantity ends up with two values."})
        elif len(set(present.values())) > 1:
            findings.append({"key": key, "fields": fields, "written": present,
                             "issue": "inconsistent",
                             "message": f"{key} has different values across its engine fields: "
                                        f"{present}."})
    return findings


def summary() -> dict:
    """Registry contents, for a diagnostics endpoint or a report provenance section."""
    reg = load()
    by_source: dict[str, int] = {}
    for p in reg["parameters"]:
        by_source[p["source"]] = by_source.get(p["source"], 0) + 1
    return {
        "schema_version": reg["schema_version"],
        "parameters": len(reg["parameters"]),
        "by_source": by_source,
        "curves": sum(1 for p in reg["parameters"] if p.get("is_curve")),
        "multi_valued": sorted(p["key"] for p in reg["parameters"] if p.get("multi_valued")),
        "aliased": aliased_keys(),
        "device_classes": {k: {"conduction_loss_form": v["conduction_loss_form"],
                               "active": v.get("active", False)}
                           for k, v in reg["device_classes"].items()},
    }
