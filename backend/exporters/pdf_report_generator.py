from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def generate_pdf_report(state, markdown_report: str, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("Final PFC Design Report", styles["Title"]), Spacer(1,12)]
    for para in markdown_report.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.replace("\n","<br/>"), styles["BodyText"]))
            story.append(Spacer(1,6))
    doc.build(story)
    return output_path
