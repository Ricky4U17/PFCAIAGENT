"""
generate_combined_report.py
Orchestrates the full Steps 1–14 combined PDF:
  1. Calls existing generate-report endpoint to get Steps 1-12 PDF bytes
  2. Generates Steps 13-14 PDF via generate_steps13_14.py
  3. Merges both with pypdf and returns combined bytes

Called from the /mode-b/generate-full-report endpoint.
"""
from __future__ import annotations
import io
from pypdf import PdfWriter, PdfReader
from app.mode_b.generate_steps13_14 import generate_steps13_14_pdf


def generate_combined_report(
    state: dict,
    approved_design: dict,
    steps1_12_pdf_bytes: bytes,
    step15_result: dict | None = None,
    step16_params: dict | None = None,
) -> bytes:
    """
    Parameters
    ----------
    state               : confirmed Mode A state
    approved_design     : serialised DesignResult from step7/run-sizing
    steps1_12_pdf_bytes : raw PDF bytes from /mode-b/generate-report

    Returns
    -------
    bytes : merged PDF covering Steps 1–14
    """
    # 1. Generate Steps 13-14
    pdf_13_14 = generate_steps13_14_pdf(approved_design, state)

    # 2. Merge
    writer = PdfWriter()

    r1 = PdfReader(io.BytesIO(steps1_12_pdf_bytes))
    for page in r1.pages:
        writer.add_page(page)

    r2 = PdfReader(io.BytesIO(pdf_13_14))
    for page in r2.pages:
        writer.add_page(page)

    # Step 3 (optional): append Step 15 pages if step15_result is provided
    if step15_result:
        from app.mode_b.generate_step15 import generate_step15_section
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.units import mm

        buf15   = io.BytesIO()
        doc15   = SimpleDocTemplate(buf15, pagesize=A4,
                      leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=26*mm, bottomMargin=26*mm,
                      title='Step 15 — Vout Capacitor Design',
                      author='PFC AI Design Agent')
        story15 = generate_step15_section(step15_result)
        doc15.build(story15)
        r15 = PdfReader(io.BytesIO(buf15.getvalue()))
        for page in r15.pages:
            writer.add_page(page)

    # Step 4 (optional): append Step 16 control-loop design section
    if step16_params:
        try:
            from app.mode_b.step16_control_design import design_control_loops
            from app.mode_b.generate_step16 import generate_step16_section
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate
            from reportlab.lib.units import mm

            ctrl = design_control_loops(**step16_params)

            buf16  = io.BytesIO()
            doc16  = SimpleDocTemplate(buf16, pagesize=A4,
                         leftMargin=20*mm, rightMargin=20*mm,
                         topMargin=22*mm, bottomMargin=18*mm,
                         title='Step 16 — PFC Control Loop Design',
                         author='PFC AI Design Agent')
            story16 = generate_step16_section(ctrl)
            doc16.build(story16)
            r16 = PdfReader(io.BytesIO(buf16.getvalue()))
            for page in r16.pages:
                writer.add_page(page)
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning('Step 16 generation failed: %s', _e)

    project_id  = state.get("project_id", "design")
    if step16_params:
        steps_label = "1–16"
    elif step15_result:
        steps_label = "1–15"
    else:
        steps_label = "1–14"

    writer.add_metadata({
        "/Title":   f"PFC Design Report — Steps {steps_label} — {project_id}",
        "/Author":  "PFC AI Design Agent",
        "/Subject": "Full PFC Power-Stage Design Calculation Record",
    })

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
