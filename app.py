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

# ---------------- PDF TEXT ----------------

def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            if p.extract_text():
                text += p.extract_text() + "\n"
    return text

# ---------------- STUDENT DETAILS ----------------

def extract_student_details(text):
    name = "Student Name"
    reg = "Register No"

    name_match = re.search(
        r"Name of the Candidate\s+([A-Z ]+?)(?:\s+Month|\s+Date|\n)",
        text,
        re.IGNORECASE
    )

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

# ---------------- SEMESTER DETECTION ----------------

def extract_semester(text):
    # Explicit semester column
    m = re.search(r"\bSEMESTER\s+(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # Fallback from subject code (23CS101 → 1, 23CS201 → 2)
    m = re.search(r"\b\d{2}[A-Z]{2}(\d)\d{2}\b", text)
    if m:
        return int(m.group(1))

    return None

# ---------------- SUBJECT EXTRACTION ----------------

def extract_subjects(text):
    pattern = r"([A-Z0-9]{5,7})\s+([A-Za-z0-9 +().,:/\-]+?)\s+(\d)\s+([OABC][+]?)"
    matches = re.findall(pattern, text)

    subjects = []
    for code, name, credit, grade in matches:
        subjects.append({
            "code": code[-5:],     # AS101 / CS101 etc
            "name": name.strip(),
            "credit": int(credit),
            "grade": grade
        })
    return subjects

# ---------------- SGPA CALCULATION ----------------

def calculate_sgpa(subjects):
    total_points = 0
    total_credits = 0

    for s in subjects:
        # 🔥 Ignore credit = 0 subjects
        if s["credit"] == 0:
            continue

        gp = GRADE_POINTS.get(s["grade"], 0)
        total_points += gp * s["credit"]
        total_credits += s["credit"]

    sgpa = round(total_points / total_credits, 2) if total_credits else 0
    return sgpa, total_credits, total_points

# ---------------- CERTIFICATE PDF ----------------

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

    # Header
    elements.append(Paragraph("CGPA CERTIFICATE", styles["CenterTitle"]))
    elements.append(Paragraph(f"<b>Name:</b> {data['name']}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Register No:</b> {data['reg']}", styles["Normal"]))
    elements.append(Spacer(1, 18))

    # Semester tables
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

    # Final certification text
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
    elements.append(Paragraph(f"<b>{data['cgpa']}</b>", styles["CenterTitle"]))

    doc.build(elements)
    return output

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    files = request.files.getlist("pdfs")

    semester_map = {}
    student_name = "Student Name"
    reg_no = "Register No"

    for f in files:
        path = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(path)

        text = extract_text(path)
        student_name, reg_no = extract_student_details(text)
        semester = extract_semester(text)

        if semester is None:
            continue

        subjects = extract_subjects(text)
        sgpa, credits, points = calculate_sgpa(subjects)

        semester_map[semester] = {
            "no": semester,
            "sgpa": sgpa,
            "subjects": subjects,
            "credits": credits,
            "points": points
        }

    # Sort semesters
    semesters = sorted(semester_map.values(), key=lambda x: x["no"])

    # 🔥 TRUE OG CGPA (subject-level weighted)
    grand_points = sum(s["points"] for s in semesters)
    grand_credits = sum(s["credits"] for s in semesters)
    cgpa = round(grand_points / grand_credits, 2) if grand_credits else 0

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
    app.run()
