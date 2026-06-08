"""
app/magnetics/extractor.py
PDF Extraction Engine — uses Claude API to extract magnetic material data
from uploaded datasheets, generating structured JSON with confidence scores.

Workflow:
  1. Designer uploads PDF (e.g. ferroxcube_3C97.pdf)
  2. extractor.extract_from_pdf() calls Claude with structured prompt
  3. Claude extracts material fields + assigns confidence 0-100%
  4. Fields with confidence < 90% are flagged for manual review
  5. Designer reviews flagged fields in the frontend
  6. MagneticsDB.commit_pending() saves approved material

Design notes:
  - Uses claude-sonnet-4-20250514 (Anthropic API)
  - PDF passed as base64 document block
  - Response must be pure JSON (no markdown)
  - Confidence scoring is self-reported by the model per field
  - Low confidence fields go to PENDING state, not live DB
"""
from __future__ import annotations
import json, base64, logging, re
from typing import Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Confidence threshold — fields below this require designer review
CONFIDENCE_THRESHOLD = 90

# ── Extraction result container ───────────────────────────────────────────────
@dataclass
class ExtractedField:
    value:      object
    confidence: int        # 0-100
    source:     str        # "table", "graph", "text", "estimated"
    unit:       str = ""
    note:       str = ""

    @property
    def needs_review(self) -> bool:
        return self.confidence < CONFIDENCE_THRESHOLD

@dataclass
class ExtractionResult:
    material_type:  str                           # "ferrite" or "powder"
    supplier_hint:  str                           # from filename or PDF text
    grade_hint:     str                           # e.g. "3C97"
    fields:         dict[str, ExtractedField] = field(default_factory=dict)
    raw_response:   str  = ""
    parse_errors:   list = field(default_factory=list)

    @property
    def flagged_fields(self) -> dict[str, ExtractedField]:
        return {k: v for k, v in self.fields.items() if v.needs_review}

    @property
    def high_confidence_fields(self) -> dict[str, ExtractedField]:
        return {k: v for k, v in self.fields.items() if not v.needs_review}

    def to_material_dict(self) -> dict:
        """Convert extracted fields to a material JSON dict (may have gaps for flagged fields)."""
        return _fields_to_dict(self.fields, self.material_type, self.supplier_hint, self.grade_hint)

    def to_review_payload(self) -> dict:
        """Payload sent to frontend for designer review."""
        return {
            "material_type":    self.material_type,
            "supplier":         self.supplier_hint,
            "grade":            self.grade_hint,
            "all_fields":       {k: {
                "value":      v.value,
                "confidence": v.confidence,
                "source":     v.source,
                "unit":       v.unit,
                "note":       v.note,
                "needs_review": v.needs_review,
            } for k, v in self.fields.items()},
            "flagged_count":    len(self.flagged_fields),
            "high_conf_count":  len(self.high_confidence_fields),
            "ready_to_commit":  len(self.flagged_fields) == 0,
            "parse_errors":     self.parse_errors,
        }


# ── Extraction prompts ─────────────────────────────────────────────────────────

FERRITE_PROMPT = """You are a magnetics engineer extracting data from a ferrite core material datasheet.
Extract the following fields and return ONLY a JSON object (no markdown, no explanation).

For each field, provide:
  "value": the extracted value (number, list, or 2D array)
  "confidence": 0-100 (95+ if from a clear table, 80-94 if from a graph you digitized, <80 if estimated)
  "source": one of "table", "graph", "text", "calculated", "estimated"
  "unit": the unit as a string
  "note": any relevant caveat

Required JSON structure:
{
  "supplier": {"value": "...", "confidence": 99, "source": "text", "unit": "", "note": ""},
  "grade": {"value": "e.g. 3C97", "confidence": 99, "source": "text", "unit": "", "note": ""},
  "type": {"value": "ferrite", "confidence": 99, "source": "text", "unit": "", "note": ""},
  "mu_initial": {"value": 3000, "confidence": ..., "source": ..., "unit": "dimensionless", "note": ""},
  "mu_initial_tolerance_pct": {"value": 25, ...},
  "curie_temp_C": {"value": 220, ...},
  "Bsat_25C_T": {"value": 0.51, ..., "unit": "T", "note": "At H=1200 A/m"},
  "Bsat_100C_T": {"value": 0.43, ..., "unit": "T"},
  "Bsat_T_curve": {
    "value": {"T_C": [25,60,80,100,120], "Bsat": [0.51,0.47,0.45,0.43,0.39]},
    "confidence": ..., "source": "graph", "unit": "T", "note": "Digitized from Bsat vs T curve"
  },
  "mu_r_T_curve": {
    "value": {"T_C": [25,60,80,100,120], "mu_r": [3000,3200,3300,3000,2500]},
    "confidence": ..., "source": "graph", "unit": "dimensionless"
  },
  "steinmetz_25C": {
    "value": {"Pv_ref_kW_m3": 65.0, "f_ref_kHz": 100, "B_ref_T": 0.10, "alpha": 1.25, "beta": 2.50},
    "confidence": ..., "source": ...,
    "note": "Fitted to Pv vs B curves. Or read directly if datasheet provides α and β."
  },
  "steinmetz_100C": {
    "value": {"Pv_ref_kW_m3": 80.0, "f_ref_kHz": 100, "B_ref_T": 0.10, "alpha": 1.25, "beta": 2.50},
    "confidence": ..., "source": ...
  },
  "core_loss_table_25C": {
    "value": {
      "f_kHz": [25, 50, 100, 200],
      "B_pk_T": [0.05, 0.10, 0.15, 0.20],
      "Pv_kW_m3": [[...], [...], [...], [...]]
    },
    "confidence": ..., "source": ...,
    "note": "Rows=B_pk_T, Cols=f_kHz. Only if explicit table exists in datasheet."
  }
}

Confidence guidelines:
  99: value is in a printed table with clear label and unit
  90-98: value read from a clear graph with labeled axes
  75-89: value estimated from graph with less clear scale
  50-74: value computed or interpolated
  <50: value estimated from similar materials or experience

If a field is not present in the datasheet, set confidence to 0 and value to null.
RETURN ONLY THE JSON OBJECT. No text before or after."""

POWDER_PROMPT = """You are a magnetics engineer extracting data from a powder core material datasheet.
Extract the following fields and return ONLY a JSON object (no markdown, no explanation).

{
  "supplier": {"value": "Magnetics Inc.", "confidence": 99, "source": "text", "unit": ""},
  "material_line": {"value": "Kool Mu", "confidence": 99, "source": "text", "unit": ""},
  "mu_initial": {"value": 60, "confidence": 99, "source": "text", "unit": "dimensionless"},
  "type": {"value": "powder", "confidence": 99, "source": "text", "unit": ""},
  "Bsat_T": {"value": 1.05, "confidence": ..., "source": ..., "unit": "T",
              "note": "Approximate soft saturation onset"},
  "AL_nom_nH": {"value": 75, ..., "unit": "nH/T²",
                "note": "AL at zero bias for a specific core size — note which core"},
  "AL_tolerance_pct": {"value": 8, ..., "unit": "%"},
  "dc_bias_rolloff": {
    "value": {
      "H_Oe": [0, 10, 20, 50, 80, 100, 150, 200, 300, 500],
      "mu_pct": [100, 99, 98, 90, 80, 74, 62, 53, 40, 28]
    },
    "confidence": ..., "source": "graph",
    "note": "Digitized from 'Permeability vs DC Bias' curve for this µ value"
  },
  "steinmetz_25C": {
    "value": {"Pv_ref_kW_m3": 525.0, "f_ref_kHz": 100, "B_ref_T": 0.10, "alpha": 1.32, "beta": 2.50},
    "confidence": ..., "source": ...,
    "note": "From core loss density graph at 25°C"
  },
  "core_loss_table_25C": {
    "value": {
      "f_kHz": [50, 100, 200, 500],
      "B_pk_T": [0.05, 0.10, 0.15],
      "Pv_kW_m3": [[...],[...],[...]]
    },
    "confidence": ..., "source": "graph"
  }
}

For the dc_bias_rolloff: look for the graph titled 'Permeability vs DC Bias' or '% of Initial Permeability'.
X-axis is typically in Oersteds (Oe). Y-axis is percentage (0-100%).
Extract 8-15 points that describe the curve shape, especially in the knee region.

RETURN ONLY THE JSON OBJECT."""


# ── Main extraction function ──────────────────────────────────────────────────

def extract_from_pdf(pdf_bytes: bytes,
                     material_type_hint: Optional[str] = None,
                     supplier_hint: str = "",
                     grade_hint: str = "") -> ExtractionResult:
    """
    Extract magnetic material data from a PDF datasheet using Claude API.

    Parameters:
        pdf_bytes:          Raw PDF file bytes
        material_type_hint: "ferrite" or "powder" (auto-detected if None)
        supplier_hint:      Optional supplier name to include in prompt context
        grade_hint:         Optional grade name to help Claude find the right table

    Returns:
        ExtractionResult with all fields + confidence scores
    """
    try:
        import anthropic
    except ImportError:
        return ExtractionResult(
            material_type=material_type_hint or "unknown",
            supplier_hint=supplier_hint, grade_hint=grade_hint,
            parse_errors=["anthropic package not installed — run: pip install anthropic"]
        )

    client = anthropic.Anthropic()   # API key from ANTHROPIC_API_KEY env var

    # Auto-detect material type from filename hint
    mat_type = material_type_hint or "ferrite"
    prompt = FERRITE_PROMPT if mat_type == "ferrite" else POWDER_PROMPT

    # Build context message
    context = ""
    if supplier_hint: context += f"Supplier: {supplier_hint}. "
    if grade_hint:    context += f"Material grade: {grade_hint}. "
    if context:       context = f"Context: {context}\n\n"

    try:
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf",
                                   "data": pdf_b64}
                    },
                    {
                        "type": "text",
                        "text": context + prompt
                    }
                ]
            }]
        )
        raw = response.content[0].text
        return _parse_extraction_response(raw, mat_type, supplier_hint, grade_hint)

    except Exception as ex:
        log.exception("PDF extraction failed")
        return ExtractionResult(
            material_type=mat_type, supplier_hint=supplier_hint, grade_hint=grade_hint,
            parse_errors=[f"Claude API error: {ex}"]
        )


def _parse_extraction_response(raw: str, mat_type: str,
                                 supplier_hint: str, grade_hint: str) -> ExtractionResult:
    """Parse Claude's JSON response into an ExtractionResult."""
    result = ExtractionResult(material_type=mat_type,
                               supplier_hint=supplier_hint,
                               grade_hint=grade_hint,
                               raw_response=raw)
    # Strip markdown fences if present
    text = raw.strip()
    text = re.sub(r"^```json?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as ex:
        result.parse_errors.append(f"JSON parse error: {ex}")
        return result

    for field_name, field_data in data.items():
        if not isinstance(field_data, dict):
            result.parse_errors.append(f"Field {field_name}: expected dict, got {type(field_data)}")
            continue
        try:
            result.fields[field_name] = ExtractedField(
                value      = field_data.get("value"),
                confidence = int(field_data.get("confidence", 0)),
                source     = str(field_data.get("source", "unknown")),
                unit       = str(field_data.get("unit",   "")),
                note       = str(field_data.get("note",   "")),
            )
        except Exception as ex:
            result.parse_errors.append(f"Field {field_name}: {ex}")

    # Update hints from extracted data if not provided
    if not result.supplier_hint and "supplier" in result.fields:
        result.supplier_hint = str(result.fields["supplier"].value or "")
    if not result.grade_hint:
        for key in ("grade", "material_line"):
            if key in result.fields and result.fields[key].value:
                result.grade_hint = str(result.fields[key].value)
                break

    return result


def _fields_to_dict(fields: dict[str, ExtractedField],
                     mat_type: str, supplier: str, grade: str) -> dict:
    """Convert extraction fields to a material JSON dict for MagneticsDB."""
    d: dict = {
        "supplier":    fields.get("supplier",    ExtractedField(supplier, 0,"")).value or supplier,
        "type":        mat_type,
        "data_source": "PDF extraction via Claude API",
        "data_quality": "pdf_extracted",
    }

    # Grade / material line
    if mat_type == "ferrite":
        d["grade"] = fields.get("grade", ExtractedField(grade,0,"")).value or grade
        # basic
        d["basic"] = {
            "mu_initial":            _v(fields, "mu_initial"),
            "mu_initial_tolerance_pct": _v(fields, "mu_initial_tolerance_pct", 25),
            "curie_temp_C":          _v(fields, "curie_temp_C"),
        }
        # Bsat_vs_T
        if "Bsat_T_curve" in fields and fields["Bsat_T_curve"].value:
            d["Bsat_vs_T"] = fields["Bsat_T_curve"].value
        elif "Bsat_25C_T" in fields and "Bsat_100C_T" in fields:
            d["Bsat_vs_T"] = {"T_C": [25, 100],
                               "Bsat": [_v(fields,"Bsat_25C_T"), _v(fields,"Bsat_100C_T")]}
        # mu_r_vs_T
        if "mu_r_T_curve" in fields and fields["mu_r_T_curve"].value:
            d["mu_r_vs_T"] = fields["mu_r_T_curve"].value
        # Steinmetz
        for s_key in ("steinmetz_25C", "steinmetz_100C"):
            if s_key in fields and fields[s_key].value:
                d[s_key] = fields[s_key].value
        # core loss table
        for t_key, d_key in [("core_loss_table_25C","core_loss_surface_25C"),
                              ("core_loss_table_100C","core_loss_surface_100C")]:
            if t_key in fields and fields[t_key].value:
                d[d_key] = fields[t_key].value

    else:  # powder
        d["material_line"] = fields.get("material_line", ExtractedField(grade,0,"")).value or grade
        d["mu_initial"]    = _v(fields, "mu_initial")
        d["basic"] = {
            "Bsat_T":            _v(fields, "Bsat_T"),
            "AL_tolerance_pct":  _v(fields, "AL_tolerance_pct", 8),
        }
        if "dc_bias_rolloff" in fields and fields["dc_bias_rolloff"].value:
            d["dc_bias_rolloff"] = {
                "description": "Extracted from PDF datasheet",
                "x_unit": "Oe",
                **fields["dc_bias_rolloff"].value,
                "data_quality": "pdf_extracted"
            }
        if "steinmetz_25C" in fields and fields["steinmetz_25C"].value:
            d["steinmetz_25C"] = fields["steinmetz_25C"].value
        if "core_loss_table_25C" in fields and fields["core_loss_table_25C"].value:
            d["core_loss_surface_25C"] = fields["core_loss_table_25C"].value

    return d

def _v(fields, key, default=None):
    f = fields.get(key)
    return f.value if (f and f.value is not None) else default
