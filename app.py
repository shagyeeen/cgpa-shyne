from flask import Flask, request, send_file, render_template
import pdfplumber, os, re
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

GRADE_POINTS = {
    "O": 10, "A+": 9, "A": 8,
    "B+": 7, "B": 6, "C": 5, "U": 0
}

# ---------- PDF EXTRACTION ----------

def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            if p.extract_text():
                text += p.extract_text() + "\n"
    return text

def extract_student_details(text):
    name = "Student Name"
    reg = "Register No"

    # Name extraction (cut before 'Month' or 'Date')
    name_match = re.search(
        r"Name of the Candidate\s+([A-Z ]+?)(?:\s+Month|\s+Date|\n)",
        text,
        re.IGNORECASE
    )

    # Register number extraction
    reg_match = re.search(
        r"Register No\s+([A-Z0-9]+)",
        text,
        re.IGNORECASE
    )

    if name_match:
        name = name_match.group(1).strip()

    if reg_match:
        reg = reg_match.group(1).strip()

    return name, reg

def extract_subjects(text):
    pattern = r"([A-Z]{2}\d{3})\s+([A-Za-z0-9 &()\-]+?)\s+(\d)\s+([OABC][+]?)"
    matches = re.findall(pattern, text)

    subjects = []
    for code, name, credit, grade in matches:
        subjects.append({
            "code": code,
            "name": name.strip(),
            "credit": int(credit),
            "grade": grade
        })
    return subjects


def calculate_sgpa(subjects):
    total_points = total_credits = 0
    for s in subjects:
        gp = GRADE_POINTS.get(s["grade"], 0)
        total_points += gp * s["credit"]
        total_credits += s["credit"]
    return (round(total_points / total_credits, 2), total_credits) if total_credits else (0, 0)

# ---------- CERTIFICATE GENERATION ----------

def generate_certificate(data):
    output = "CGPA_Certificate.pdf"

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CenterTitle",
        alignment=TA_CENTER,
        fontSize=18,
        spaceAfter=20
    ))

    styles.add(ParagraphStyle(
        name="CenterBig",
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=12
    ))

    elements = []

    # ---- HEADER ----
    elements.append(Paragraph("CGPA CERTIFICATE", styles["CenterTitle"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"<b>Name:</b> {data['name']}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Register No:</b> {data['reg']}", styles["Normal"]))
    elements.append(Spacer(1, 18))

    # ---- SEMESTER DETAILS ----
    for sem in data["semesters"]:
        elements.append(
            Paragraph(
                f"<b>Semester {sem['no']} — SGPA: {sem['sgpa']}</b>",
                styles["Heading3"]
            )
        )
        elements.append(Spacer(1, 6))

        table_data = [["Code", "Subject Name", "Credit", "Grade"]]
        for s in sem["subjects"]:
            table_data.append([s["code"], s["name"], s["credit"], s["grade"]])

        table = Table(table_data, colWidths=[70, 260, 60, 60])
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.8, colors.black),
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("ALIGN", (2,1), (-1,-1), "CENTER"),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 16))

    # ---- FINAL CERTIFICATION TEXT (YOUR EXACT REQUIREMENT) ----
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("This is to certify that", styles["CenterBig"]))
    elements.append(Paragraph(f"<b>{data['name']}</b>", styles["CenterBig"]))
    elements.append(Paragraph(
        f"Register Number : <b>{data['reg']}</b>",
        styles["CenterBig"]
    ))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(
        f"has completed {len(data['semesters'])} semesters",
        styles["CenterBig"]
    ))
    elements.append(Paragraph(
        "and secured a Cumulative Grade Point Average (CGPA) of",
        styles["CenterBig"]
    ))
    elements.append(Spacer(1, 10))

    elements.append(
        Paragraph(
            f"<b>{data['cgpa']}</b>",
            styles["CenterTitle"]
        )
    )

    doc.build(elements)
    return output

# ---------- ROUTES ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    files = request.files.getlist("pdfs")

    semesters = []
    total_points = total_credits = 0
    student_name = "Student Name"
    reg_no = "Register No"

    for i, f in enumerate(files, start=1):
        path = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(path)

        text = extract_text(path)
        student_name, reg_no = extract_student_details(text)

        subjects = extract_subjects(text)
        sgpa, credits = calculate_sgpa(subjects)

        semesters.append({
            "no": i,
            "sgpa": sgpa,
            "subjects": subjects
        })

        total_points += sgpa * credits
        total_credits += credits

    cgpa = round(total_points / total_credits, 2) if total_credits else 0

    pdf_path = generate_certificate({
        "name": student_name,
        "reg": reg_no,
        "cgpa": cgpa,
        "semesters": semesters
    })

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="CGPA_Certificate.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)
