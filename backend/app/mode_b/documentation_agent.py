"""
backend/app/mode_b/documentation_agent.py
Documentation Agent — Phase 3 (updated with chapter-based report builder)

Chapter structure aligned with planning PDFs (June 2026):
  Chapter 1  Specifications                       — always ready after Mode A
  Chapter 2  Topology and Control Scheme          — always ready after Mode A
  Chapter 3  PFC Inductor Sizing                  — ready when approved_design present
  Chapter 4  PFC Inductor Performance Analysis    — ready when approved_design present
  Chapter 5  DC Bus Capacitor Selection           — ready when step15_result present
  Chapter 6  Control Scheme                       — ready when step16_params present

Chapter colours: Ch1=navy, Ch2=d.green, Ch3=d.amber, Ch4=d.purple, Ch5=d.teal, Ch6=d.slate

Rules:
  - READ-ONLY with respect to DesignState (never writes design fields)
  - generate_chapter_report() uses the new chapter-based builder (doc_report_builder.py)
  - generate() falls back to existing generators if chapter builder fails
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChapterStatus:
    chapter:   int
    title:     str
    status:    str          # "ready" | "pending" | "partial"
    sections:  list[str]    = field(default_factory=list)
    missing:   list[str]    = field(default_factory=list)
    note:      str          = ""


class DocumentationAgent:
    """
    Orchestrates chapter-based PDF report generation using typed DesignState access.

    Usage
    -----
        agent = DocumentationAgent(raw_state_dict)
        status = agent.report_status(approved_design, step15_result, step16_params)
        pdf    = agent.generate_chapter_report(approved_design, step15_result, step16_params)
    """

    def __init__(self, state: dict):
        from app.design_state import DesignState
        self.ds  = DesignState.model_validate(state)
        self.raw = state

    # ── public API ────────────────────────────────────────────────────────────

    def report_status(
        self,
        approved_design:  Optional[dict] = None,
        step15_result:    Optional[dict] = None,
        step16_params:    Optional[dict] = None,
    ) -> dict:
        """Return a chapter-by-chapter readiness map (aligned with planning PDFs)."""
        chapters = self._assess_chapters(approved_design, step15_result, step16_params)
        ready    = [c for c in chapters if c.status == "ready"]
        pending  = [c for c in chapters if c.status != "ready"]

        if step16_params and approved_design and step15_result:
            ready_label = "Chapters 1–6 (complete)"
        elif step15_result and approved_design:
            ready_label = "Chapters 1–5"
        elif approved_design:
            ready_label = "Chapters 1–4"
        else:
            ready_label = "Chapters 1–2"

        missing_for_full = []
        if not approved_design:
            missing_for_full.append("approved_design (complete Step 7 Magnetic Design)")
        if not step15_result:
            missing_for_full.append("step15_result (complete Step 15 Capacitor Design)")
        if not step16_params:
            missing_for_full.append("step16_params (complete Step 16 Control Design)")

        return {
            "project_id":        self.ds.project_id,
            "topology":          self.ds.selected_topology,
            "mode":              self.ds.selected_mode,
            "channels":          self.ds.selected_channels,
            "ready_label":       ready_label,
            "can_generate":      True,
            "chapters":          [self._chapter_dict(c) for c in chapters],
            "ready_count":       len(ready),
            "pending_count":     len(pending),
            "missing_for_full":  missing_for_full,
        }

    def generate_chapter_report(
        self,
        approved_design:  Optional[dict] = None,
        step15_result:    Optional[dict] = None,
        step16_params:    Optional[dict] = None,
        include_ch6:      bool = True,
    ) -> bytes:
        """
        Generate chapter-based PDF using the new documentation standards:
          - Chapter splash pages (full-page colour panel per chapter)
          - CONCEPT / THEORY / PITFALL / DECISION / INSIGHT annotation boxes
          - 4-line equation template: label → symbolic → numerical → result
          - 3-level decimal numbering (X.Y.Z)
          - Table standard: name + intro + body + interpretation
        Validates DesignState completeness first.
        """
        issues = self._validate_mode_a()
        if issues:
            raise ValueError("DesignState incomplete — " + "; ".join(issues))

        from app.mode_b.doc_report_builder import build_full_report
        return build_full_report(
            state           = self.raw,
            approved_design = approved_design,
            step15_result   = step15_result,
            step16_params   = step16_params,
            include_ch6     = include_ch6,
        )

    def generate(
        self,
        approved_design:  Optional[dict] = None,
        step15_result:    Optional[dict] = None,
        step16_params:    Optional[dict] = None,
        include_ch6:      bool = True,
    ) -> bytes:
        """
        Generate PDF — routes to chapter-based builder first, falls back to
        existing generators if builder fails (backward compatibility).
        include_ch6=False omits the Chapter 6 splash/placeholder (used when the
        full detailed Chapter 6 is merged in separately, to avoid a duplicate heading).
        """
        try:
            return self.generate_chapter_report(
                approved_design = approved_design,
                step15_result   = step15_result,
                step16_params   = step16_params,
                include_ch6     = include_ch6,
            )
        except Exception:
            return self._generate_legacy(approved_design, step15_result, step16_params)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _generate_legacy(self, approved_design, step15_result, step16_params) -> bytes:
        """Fallback: existing generators (unchanged)."""
        issues = self._validate_mode_a()
        if issues:
            raise ValueError("DesignState incomplete — " + "; ".join(issues))
        from app.mode_b.generate_report import generate_full_report as _gen_1_12
        pdf_1_12 = _gen_1_12(self.raw)
        if not approved_design:
            return pdf_1_12
        from app.mode_b.generate_combined_report import generate_combined_report
        return generate_combined_report(
            state               = self.raw,
            approved_design     = approved_design,
            steps1_12_pdf_bytes = pdf_1_12,
            step15_result       = step15_result,
            step16_params       = step16_params,
        )

    def _validate_mode_a(self) -> list[str]:
        """Return list of missing required Mode-A fields."""
        issues = []
        ds = self.ds
        if not ds.project_id:
            issues.append("project_id missing")
        if not ds.intake:
            issues.append("intake missing — complete Mode A first")
        elif not (ds.intake.application and ds.intake.application.output_bus_voltage_v):
            issues.append("intake.application incomplete — resubmit Mode A intake")
        if not ds.selected_topology:
            issues.append("selected_topology missing — approve topology first")
        if not ds.topology_specific_inputs:
            issues.append("topology_specific_inputs missing — submit mini-intake")
        elif not ds.topology_specific_inputs.confirmed_L_uH:
            issues.append("confirmed_L_uH missing — submit mini-intake to confirm L")
        return issues

    def _assess_chapters(self, approved_design, step15_result, step16_params) -> list[ChapterStatus]:
        """
        Chapter numbering per planning PDFs (June 2026):
          1 = Specifications
          2 = Topology and Control Scheme Selection
          3 = PFC Inductor Sizing
          4 = PFC Inductor Performance Analysis
          5 = DC Bus Capacitor Selection
          6 = Control Scheme
        """
        mode_a_ok = not self._validate_mode_a()
        chapters  = []

        # ── Chapter 1 — Specifications ────────────────────────────────────────
        chapters.append(ChapterStatus(
            chapter=1, title="Specifications",
            status="ready" if mode_a_ok else "pending",
            sections=["1.1 Electrical requirements",
                      "1.2 Thermal requirements",
                      "1.3 Application class and compliance",
                      "1.4 Derived design targets (L, fsw, crest ratio)"],
            missing=self._validate_mode_a() if not mode_a_ok else [],
            note="Complete Mode A to enable" if not mode_a_ok else "Mode A complete",
        ))

        # ── Chapter 2 — Topology and Control Scheme ───────────────────────────
        chapters.append(ChapterStatus(
            chapter=2, title="Topology and Control Scheme Selection",
            status="ready" if mode_a_ok else "pending",
            sections=["2.1 Topology selection and scoring",
                      "2.2 Selected topology rationale",
                      "2.3 Control strategy selection",
                      "2.4 Phase count and switching frequency"],
            missing=[] if mode_a_ok else ["Complete Mode A first"],
            note="Topology and controller approved" if mode_a_ok else "Complete Mode A first",
        ))

        # ── Chapter 3 — PFC Inductor Sizing ───────────────────────────────────
        chapters.append(ChapterStatus(
            chapter=3, title="PFC Inductor Sizing",
            status="ready" if approved_design else "pending",
            sections=["3.1 Inductor design requirements (L-target derivation, per-phase currents)",
                      "3.2 Ripple and interleaving analysis — K(D) at all 9 points",
                      "3.3 Core material selection rationale",
                      "3.4 Core geometry selection — sizing engine results",
                      "3.5 Winding design — wire type, skin depth, turns, fill factor",
                      "3.6 First-pass loss and thermal estimate",
                      "3.7 Sizing summary — approved design parameters"],
            missing=["approved_design — approve a core candidate in Step 7"] if not approved_design else [],
            note="Approved design data present" if approved_design else "Approve Step 7 first",
        ))

        # ── Chapter 4 — PFC Inductor Performance Analysis ─────────────────────
        chapters.append(ChapterStatus(
            chapter=4, title="PFC Inductor Performance Analysis",
            status="ready" if approved_design else "pending",
            sections=["4.1 Physical model and assembled dimensions",
                      "4.2 Inductance vs DC bias — L(H) at all operating points",
                      "4.3 Flux density analysis — Bac,pk(t) waveforms",
                      "4.4 Core loss — cycle-averaged iGSE (more accurate than Ch.3)",
                      "4.5 Copper loss and thermal summary across all 9 Vin"],
            missing=["approved_design — approve Step 7 first"] if not approved_design else [],
            note="Approved design data present" if approved_design else "Approve Step 7 first",
        ))

        # ── Chapter 5 — DC Bus Capacitor Selection ────────────────────────────
        chapters.append(ChapterStatus(
            chapter=5, title="DC Bus Capacitor Selection",
            status="ready" if step15_result else "pending",
            sections=["5.1 Capacitor sizing — hold-up and ripple requirements",
                      "5.2 Bank configuration and selected capacitor",
                      "5.3 Ripple current and voltage verification at all 9 points",
                      "5.4 Capacitor lifetime analysis (Arrhenius)",
                      "5.5 Capacitor bank summary — design margins"],
            missing=["step15_result — complete Step 15 Capacitor Design"] if not step15_result else [],
            note="Capacitor data present" if step15_result else "Complete Step 15 first",
        ))

        # ── Chapter 6 — Control Scheme ────────────────────────────────────────
        chapters.append(ChapterStatus(
            chapter=6, title="Control Scheme",
            status="ready" if step16_params else "pending",
            sections=["6.1 Control architecture overview",
                      "6.2 Plant analysis — critical frequencies, RHP zero",
                      "6.3 FAN9672 pin configuration — pin map and operating envelope",
                      "6.4 Current loop design — Type-II compensator",
                      "6.5 Voltage loop design — Type-II/III compensator",
                      "6.6 Stability scorecard — all 9 operating points",
                      "6.7 Soft-start and protection",
                      "6.8 Control network bill of materials"],
            missing=["step16_params — complete Step 16 Control Design"] if not step16_params else [],
            note="Control design data present" if step16_params else "Complete Step 16 first",
        ))

        return chapters

    @staticmethod
    def _chapter_dict(c: ChapterStatus) -> dict:
        return {
            "chapter": c.chapter, "title": c.title, "status": c.status,
            "sections": c.sections, "missing": c.missing, "note": c.note,
        }
