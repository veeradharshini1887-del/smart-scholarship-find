"""
ai_recommendation.py
====================
Scholarship recommendation + career guidance engine.

HOW THE "AI" WORKS (explain this in your viva)
----------------------------------------------
This is a transparent, rule-based weighted scoring system (a simple
content-based matching / expert-system approach). It is NOT a trained
neural network, and the project does not claim it is.

For every scholarship, six criteria are checked against the student's profile.
Each criterion that is satisfied earns points:

    CGPA        20 points   student CGPA   >= scholarship minimum CGPA
    Income      25 points   family income  <= scholarship maximum income
    Degree      15 points   student degree is in the scholarship's degree list
    Community   20 points   student community is in the scholarship's list
    Gender      10 points   scholarship gender matches (or is open to all)
    State       10 points   student state is in the scholarship's state list
    ----------------------------------------------------------------------
    Total      100 points   -> Match percentage

A criterion left open by the scholarship ("ALL", 0) counts as satisfied.

Status:
    Eligible            all six criteria satisfied and deadline not passed
    Partially Eligible  match score >= 60 but at least one criterion failed
    Not Eligible        match score < 60
    Closed              last date is before today

Scholarships are sorted by match score (highest first), then by amount.
"""

import re
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------
# Choice lists (used by forms and by validation)
# ---------------------------------------------------------------------
COMMUNITIES = ["General", "OBC", "BC", "MBC", "DNC", "SC", "ST", "Minority"]
GENDERS = ["Male", "Female", "Other"]
SCHOLARSHIP_GENDERS = ["All"] + GENDERS
UG_DEGREES = ["B.E.", "B.Tech", "B.Sc.", "B.Com.", "B.A.", "BBA", "BCA", "Diploma"]
PG_DEGREES = ["M.E.", "M.Tech", "M.Sc.", "M.Com.", "M.A.", "MBA", "MCA"]
DEGREES = UG_DEGREES + PG_DEGREES
STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

# Document columns in the `document` table
DOC_FIELDS = ["aadhaar", "income_certificate", "marksheet", "community_certificate"]
DOC_LABELS = {
    "aadhaar": "Aadhaar",
    "income_certificate": "Income Certificate",
    "marksheet": "Marksheet",
    "community_certificate": "Community Certificate",
}
_DOC_KEYWORDS = [
    ("aadhaar", "aadhaar"), ("aadhar", "aadhaar"),
    ("income", "income_certificate"),
    ("mark", "marksheet"),
    ("community", "community_certificate"), ("caste", "community_certificate"),
]

WEIGHTS = {"cgpa": 20, "income": 25, "degree": 15, "community": 20, "gender": 10, "state": 10}
CRITERIA_LABELS = {
    "cgpa": "CGPA", "income": "Family income", "degree": "Degree",
    "community": "Community", "gender": "Gender", "state": "State",
}
PARTIAL_THRESHOLD = 60


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _tokens(value):
    """'B.E., B.Tech' -> {'b.e.', 'b.tech'}.  Empty / 'ALL' -> empty set (= open to all)."""
    if value is None:
        return set()
    text = str(value).strip()
    if not text or text.lower() in ("all", "any"):
        return set()
    return {t.strip().lower() for t in text.split(",") if t.strip()}


def format_inr(value):
    """25000 -> 'Rs 25,000' style with Indian digit grouping (uses the rupee sign)."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        digits = head + "," + tail
    return ("-" if n < 0 else "") + "\u20b9" + digits


def days_left(last_date, today=None):
    today = today or date.today()
    return (_to_date(last_date) - today).days


def deadline_text(last_date, today=None):
    d = days_left(last_date, today)
    if d < 0:
        return "Closed"
    if d == 0:
        return "Last day today"
    if d == 1:
        return "1 day left"
    return f"{d} days left"


# ---------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------
def evaluate(student, scholarship, today=None):
    """Compare one student with one scholarship. Returns a dict with score and reasons."""
    today = today or date.today()
    criteria = []

    def add(key, passed, detail):
        criteria.append({
            "key": key,
            "label": CRITERIA_LABELS[key],
            "points": WEIGHTS[key],
            "passed": bool(passed),
            "earned": WEIGHTS[key] if passed else 0,
            "detail": detail,
        })

    # 1. CGPA
    min_cgpa = _num(scholarship.get("minimum_cgpa"))
    s_cgpa = _num(student.get("cgpa"))
    if min_cgpa <= 0:
        add("cgpa", True, "No minimum CGPA")
    else:
        add("cgpa", s_cgpa >= min_cgpa, f"Needs {min_cgpa:.2f} or above; you have {s_cgpa:.2f}")

    # 2. Family income
    max_income = _num(scholarship.get("maximum_income"))
    s_income = _num(student.get("family_income"))
    if max_income <= 0:
        add("income", True, "No income limit")
    else:
        add("income", s_income <= max_income,
            f"Limit {format_inr(max_income)}; your family income is {format_inr(s_income)}")

    # 3-5. Degree, community, state (comma separated lists)
    for key, field in (("degree", "degree"), ("community", "community"), ("state", "state")):
        allowed = _tokens(scholarship.get(field))
        mine = str(student.get(field) or "").strip()
        if not allowed:
            add(key, True, "Open to all")
        else:
            shown = ", ".join(x.strip() for x in str(scholarship.get(field)).split(","))
            add(key, mine.lower() in allowed, f"Accepted: {shown}; yours: {mine or 'not set'}")

    # 6. Gender
    g_allowed = str(scholarship.get("gender") or "All").strip().lower()
    g_mine = str(student.get("gender") or "").strip().lower()
    if g_allowed in ("all", "any", ""):
        add("gender", True, "Open to all genders")
    else:
        add("gender", g_mine == g_allowed, f"For {scholarship.get('gender')} students; yours: {student.get('gender') or 'not set'}")

    order = ["cgpa", "income", "degree", "community", "gender", "state"]
    criteria.sort(key=lambda c: order.index(c["key"]))

    score = sum(c["earned"] for c in criteria)
    all_passed = all(c["passed"] for c in criteria)
    left = days_left(scholarship["last_date"], today)
    is_closed = left < 0

    if is_closed:
        status, css = "Closed", "closed"
    elif all_passed:
        status, css = "Eligible", "eligible"
    elif score >= PARTIAL_THRESHOLD:
        status, css = "Partially Eligible", "partial"
    else:
        status, css = "Not Eligible", "not-eligible"

    return {
        "score": score,
        "percentage": int(round(score * 100 / sum(WEIGHTS.values()))),
        "criteria": criteria,
        "failed": [c["label"] for c in criteria if not c["passed"]],
        "all_criteria_met": all_passed,
        "is_eligible": all_passed and not is_closed,
        "is_closed": is_closed,
        "status": status,
        "status_class": css,
        "days_left": left,
    }


def recommend(student, scholarships, today=None, include_closed=False, min_percentage=0):
    """Return [{'s': scholarship, 'm': match}] sorted by highest match first."""
    today = today or date.today()
    results = []
    for s in scholarships:
        m = evaluate(student, s, today)
        if m["is_closed"] and not include_closed:
            continue
        if m["percentage"] < min_percentage:
            continue
        results.append({"s": s, "m": m})
    results.sort(key=lambda r: (-r["m"]["percentage"], -_num(r["s"].get("amount")),
                                _to_date(r["s"]["last_date"])))
    return results


def upcoming_deadlines(scholarships, today=None, within_days=30):
    """Scholarships whose last date is today or within the next `within_days` days."""
    today = today or date.today()
    out = []
    for s in scholarships:
        d = days_left(s["last_date"], today)
        if 0 <= d <= within_days:
            out.append({"s": s, "days_left": d, "urgent": d <= 7})
    out.sort(key=lambda r: r["days_left"])
    return out


# ---------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------
def required_document_fields(required_text):
    """'Aadhaar, Income Certificate' -> ['aadhaar', 'income_certificate']"""
    fields = []
    for token in str(required_text or "").split(","):
        t = token.strip().lower()
        for key, field in _DOC_KEYWORDS:
            if key in t and field not in fields:
                fields.append(field)
                break
    return fields


def document_status(required_text, uploaded):
    """List of {'field','label','uploaded'} for the documents a scholarship needs."""
    return [{"field": f, "label": DOC_LABELS[f], "uploaded": bool((uploaded or {}).get(f))}
            for f in required_document_fields(required_text)]


# ---------------------------------------------------------------------
# Admin-side validation helpers
# ---------------------------------------------------------------------
def normalize_choice_list(text, allowed, label):
    """Validate a comma separated list against allowed values. Returns canonical text."""
    text = (text or "").strip()
    if not text or text.lower() in ("all", "any"):
        return "ALL"
    lookup = {a.lower(): a for a in allowed}
    result = []
    for token in text.split(","):
        t = token.strip()
        if not t:
            continue
        if t.lower() not in lookup:
            raise ValueError(f"{label}: '{t}' is not a valid value")
        if lookup[t.lower()] not in result:
            result.append(lookup[t.lower()])
    return ",".join(result) if result else "ALL"


# ---------------------------------------------------------------------
# Career guidance
# ---------------------------------------------------------------------
DEGREE_INTERESTS = {
    "B.E.": ["Software Development", "Data Science & AI", "Cyber Security", "Electronics & Embedded Systems",
             "Mechanical & Manufacturing", "Civil & Structural", "Electrical & Power"],
    "B.Tech": ["Software Development", "Data Science & AI", "Cyber Security", "Electronics & Embedded Systems",
               "Mechanical & Manufacturing", "Civil & Structural", "Electrical & Power"],
    "B.Sc.": ["Data Science & AI", "Life Sciences & Healthcare", "Teaching, Research & Government Exams"],
    "B.Com.": ["Commerce, Finance & Accounting", "Business & Management", "Teaching, Research & Government Exams"],
    "B.A.": ["Teaching, Research & Government Exams", "Design & Creative", "Business & Management"],
    "BBA": ["Business & Management", "Commerce, Finance & Accounting", "Data Science & AI"],
    "BCA": ["Software Development", "Data Science & AI", "Cyber Security"],
    "Diploma": ["Mechanical & Manufacturing", "Electrical & Power", "Civil & Structural", "Electronics & Embedded Systems"],
    "M.E.": ["Software Development", "Electronics & Embedded Systems", "Mechanical & Manufacturing", "Civil & Structural"],
    "M.Tech": ["Software Development", "Data Science & AI", "Cyber Security", "Electronics & Embedded Systems"],
    "M.Sc.": ["Data Science & AI", "Life Sciences & Healthcare", "Teaching, Research & Government Exams"],
    "M.Com.": ["Commerce, Finance & Accounting", "Business & Management", "Teaching, Research & Government Exams"],
    "M.A.": ["Teaching, Research & Government Exams", "Design & Creative", "Business & Management"],
    "MBA": ["Business & Management", "Commerce, Finance & Accounting", "Data Science & AI"],
    "MCA": ["Software Development", "Data Science & AI", "Cyber Security"],
}

CAREER_PATHS = {
    "Data Science & AI": {
        "summary": "Use data and machine learning to find patterns and support decisions.",
        "higher_studies": {
            "UG": ["M.Sc. Data Science", "M.Tech in AI & Machine Learning", "MBA in Business Analytics", "MS in Data Science (abroad)"],
            "PG": ["PhD in Machine Learning / AI", "Research fellowship in a data lab", "Professional ML engineering certification"]},
        "courses": ["Python for Data Science", "Statistics and Probability", "Machine Learning", "Deep Learning", "SQL and Databases", "Data Visualization"],
        "jobs": ["Data Analyst", "Business Intelligence Developer", "Data Scientist", "Machine Learning Engineer"],
        "skills": ["Python", "Statistics", "SQL", "Data visualization", "Problem solving", "Communication"],
        "technologies": ["Python", "Pandas / NumPy", "scikit-learn", "TensorFlow / PyTorch", "Power BI / Tableau", "MySQL"],
        "roadmap": {"UG": ["M.Sc. Data Science", "Data Analyst", "Data Scientist"],
                    "PG": ["Junior Data Scientist", "Data Scientist", "Senior Data Scientist"]}},
    "Software Development": {
        "summary": "Design, build and maintain software, websites and mobile apps.",
        "higher_studies": {
            "UG": ["M.Tech Computer Science", "MCA", "MS in Computer Science (abroad)", "MBA in IT Management"],
            "PG": ["PhD in Computer Science", "Research programs in systems / software engineering"]},
        "courses": ["Data Structures and Algorithms", "Web Development", "Database Management", "Software Engineering", "Cloud Computing", "System Design"],
        "jobs": ["Software Developer", "Full Stack Developer", "Backend Engineer", "DevOps Engineer"],
        "skills": ["Programming", "Problem solving", "Version control (Git)", "Databases", "Teamwork", "Debugging"],
        "technologies": ["Python / Java", "Flask / Spring Boot", "React", "MySQL / MongoDB", "Git and GitHub", "Docker"],
        "roadmap": {"UG": ["Internships and projects", "Junior Software Developer", "Software Engineer", "Senior Engineer / Tech Lead"],
                    "PG": ["Software Engineer", "Senior Software Engineer", "Tech Lead / Architect"]}},
    "Cyber Security": {
        "summary": "Protect systems, networks and data from attacks.",
        "higher_studies": {
            "UG": ["M.Tech Cyber Security", "M.Sc. Cyber Forensics", "MS in Information Security (abroad)"],
            "PG": ["PhD in Cryptography / Security", "Security research programs"]},
        "courses": ["Computer Networks", "Ethical Hacking", "Cryptography", "Digital Forensics", "Cloud Security"],
        "jobs": ["Security Analyst", "Penetration Tester", "SOC Analyst", "Security Engineer"],
        "skills": ["Networking", "Linux", "Risk analysis", "Scripting", "Attention to detail"],
        "technologies": ["Kali Linux", "Wireshark", "Nmap", "Burp Suite", "Python", "SIEM tools"],
        "roadmap": {"UG": ["M.Tech / M.Sc. Cyber Security", "Security Analyst", "Penetration Tester", "Security Architect"],
                    "PG": ["Security Analyst", "Security Engineer", "Security Architect"]}},
    "Electronics & Embedded Systems": {
        "summary": "Work on circuits, microcontrollers, IoT devices and communication systems.",
        "higher_studies": {
            "UG": ["M.E./M.Tech VLSI Design", "M.Tech Embedded Systems", "M.Tech Communication Systems", "MS in Electrical Engineering (abroad)"],
            "PG": ["PhD in VLSI / Embedded Systems", "Research at national labs"]},
        "courses": ["Digital Electronics", "Microcontrollers", "Embedded C", "VLSI Design", "IoT Fundamentals"],
        "jobs": ["Embedded Engineer", "VLSI Design Engineer", "IoT Developer", "Test Engineer"],
        "skills": ["Circuit analysis", "Embedded C", "Debugging hardware", "Communication protocols"],
        "technologies": ["Arduino / Raspberry Pi", "ARM Cortex", "Verilog / VHDL", "MATLAB", "RTOS"],
        "roadmap": {"UG": ["M.Tech VLSI / Embedded", "Embedded Engineer", "Senior Embedded Engineer", "System Architect"],
                    "PG": ["Embedded / VLSI Engineer", "Senior Engineer", "Design Lead"]}},
    "Mechanical & Manufacturing": {
        "summary": "Design machines and improve how products are made.",
        "higher_studies": {
            "UG": ["M.Tech Thermal / Design / Manufacturing", "MBA in Operations", "MS in Mechanical Engineering (abroad)"],
            "PG": ["PhD in Mechanical Engineering", "Research and development programs"]},
        "courses": ["CAD/CAM", "Thermodynamics", "Manufacturing Processes", "Finite Element Analysis", "Industrial Automation"],
        "jobs": ["Design Engineer", "Production Engineer", "Quality Engineer", "Maintenance Engineer"],
        "skills": ["Engineering drawing", "Analysis", "Problem solving", "Safety and quality standards"],
        "technologies": ["AutoCAD", "SolidWorks", "ANSYS", "CATIA", "PLC basics"],
        "roadmap": {"UG": ["M.Tech / GATE preparation", "Graduate Engineer Trainee", "Design / Production Engineer", "Manager"],
                    "PG": ["R&D Engineer", "Senior Engineer", "Engineering Manager"]}},
    "Civil & Structural": {
        "summary": "Plan, design and supervise buildings, roads and infrastructure.",
        "higher_studies": {
            "UG": ["M.Tech Structural Engineering", "M.Tech Construction Management", "MBA in Infrastructure", "MS in Civil Engineering (abroad)"],
            "PG": ["PhD in Structural / Geotechnical Engineering", "Consultancy and research roles"]},
        "courses": ["Structural Analysis", "Concrete Technology", "Surveying", "Construction Management", "Environmental Engineering"],
        "jobs": ["Site Engineer", "Structural Designer", "Quantity Surveyor", "Project Engineer"],
        "skills": ["Structural analysis", "Site supervision", "Estimation", "Reading drawings"],
        "technologies": ["AutoCAD", "STAAD.Pro", "Revit", "Primavera", "Total station"],
        "roadmap": {"UG": ["M.Tech Structural / Construction", "Site Engineer", "Project Engineer", "Project Manager"],
                    "PG": ["Structural Designer", "Senior Engineer", "Project Manager"]}},
    "Electrical & Power": {
        "summary": "Work on power generation, distribution, control and electric vehicles.",
        "higher_studies": {
            "UG": ["M.Tech Power Systems", "M.Tech Power Electronics", "M.Tech Control Systems", "MS in Electrical Engineering (abroad)"],
            "PG": ["PhD in Power Systems / Renewable Energy", "Research at energy institutes"]},
        "courses": ["Power Systems", "Electrical Machines", "Power Electronics", "Renewable Energy", "PLC and SCADA"],
        "jobs": ["Electrical Engineer", "Power Systems Engineer", "Automation Engineer", "EV Engineer"],
        "skills": ["Circuit analysis", "Power system knowledge", "Safety standards", "Control systems"],
        "technologies": ["MATLAB / Simulink", "ETAP", "PLC / SCADA", "AutoCAD Electrical"],
        "roadmap": {"UG": ["M.Tech Power Systems", "Graduate Engineer Trainee", "Electrical Engineer", "Senior Engineer"],
                    "PG": ["Power Systems Engineer", "Senior Engineer", "Engineering Manager"]}},
    "Business & Management": {
        "summary": "Lead teams, run operations and grow organisations.",
        "higher_studies": {
            "UG": ["MBA (CAT / MAT / XAT / TANCET)", "PGDM", "MS in Management (abroad)"],
            "PG": ["PhD in Management", "Executive certifications (PMP, Six Sigma)"]},
        "courses": ["Marketing Management", "Human Resource Management", "Operations", "Business Analytics", "Entrepreneurship"],
        "jobs": ["Business Analyst", "Marketing Executive", "HR Executive", "Operations Manager"],
        "skills": ["Communication", "Leadership", "Analytical thinking", "Negotiation", "Excel"],
        "technologies": ["Excel", "Power BI", "CRM tools (Salesforce)", "Google Analytics", "Project tools (Jira, Trello)"],
        "roadmap": {"UG": ["MBA", "Management Trainee", "Manager", "Senior Manager"],
                    "PG": ["Management Trainee / Analyst", "Manager", "Senior Manager / Director"]}},
    "Commerce, Finance & Accounting": {
        "summary": "Handle accounts, taxation, banking, audit and investments.",
        "higher_studies": {
            "UG": ["M.Com.", "CA / CMA / CS", "MBA in Finance", "CFA"],
            "PG": ["PhD in Commerce / Finance", "CA / CMA / CFA (if not done)"]},
        "courses": ["Financial Accounting", "Taxation (GST and Income Tax)", "Auditing", "Financial Markets", "Business Law"],
        "jobs": ["Accountant", "Auditor", "Financial Analyst", "Bank Officer"],
        "skills": ["Accounting", "Excel", "Attention to detail", "Regulatory knowledge"],
        "technologies": ["Tally", "Excel", "SAP FICO", "Zoho Books", "Power BI"],
        "roadmap": {"UG": ["CA / M.Com. / MBA Finance", "Junior Accountant / Analyst", "Senior Accountant / Auditor", "Finance Manager"],
                    "PG": ["Financial Analyst", "Senior Analyst / Auditor", "Finance Manager"]}},
    "Life Sciences & Healthcare": {
        "summary": "Work in biology, biotechnology, pharma research or healthcare support.",
        "higher_studies": {
            "UG": ["M.Sc. Biotechnology / Microbiology", "M.Sc. Bioinformatics", "MPH (Public Health)", "MS in Life Sciences (abroad)"],
            "PG": ["PhD in Life Sciences", "Research fellowship (CSIR-UGC NET JRF)"]},
        "courses": ["Molecular Biology", "Bioinformatics", "Clinical Research", "Biostatistics", "Quality Control"],
        "jobs": ["Research Assistant", "Lab Technician", "Clinical Research Associate", "Quality Analyst"],
        "skills": ["Laboratory techniques", "Data analysis", "Scientific writing", "Attention to detail"],
        "technologies": ["PCR and lab instruments", "R / Python", "BLAST", "SPSS", "LIMS software"],
        "roadmap": {"UG": ["M.Sc. Life Sciences", "Research Assistant", "Scientist / Clinical Research Associate", "Senior Scientist"],
                    "PG": ["Research Associate", "Scientist", "Senior Scientist"]}},
    "Teaching, Research & Government Exams": {
        "summary": "Become a teacher, lecturer, researcher or civil servant.",
        "higher_studies": {
            "UG": ["Master's degree in your subject", "B.Ed.", "M.Phil. / integrated PhD", "UPSC / TNPSC / SSC coaching"],
            "PG": ["PhD", "UGC-NET / SET for lecturer eligibility", "Post-doctoral research"]},
        "courses": ["Subject specialisation", "Teaching methodology", "Research methods", "General studies and aptitude"],
        "jobs": ["School Teacher", "Assistant Professor", "Research Scholar", "Government Officer"],
        "skills": ["Subject knowledge", "Communication", "Writing", "Time management"],
        "technologies": ["MS Office / Google Workspace", "LaTeX", "Zotero / Mendeley", "SPSS / R (for research)"],
        "roadmap": {"UG": ["Master's degree", "NET / SET / B.Ed. / Civil Services exam", "Lecturer / Government Officer", "Professor / Senior Officer"],
                    "PG": ["NET / SET / PhD", "Assistant Professor", "Associate Professor / Senior Officer"]}},
    "Design & Creative": {
        "summary": "Create user interfaces, visuals, content and media.",
        "higher_studies": {
            "UG": ["M.Des. (UI/UX, Communication Design)", "MA in Mass Communication", "PG Diploma in Animation / Multimedia"],
            "PG": ["PhD in Design / Media Studies", "Advanced UX research programs"]},
        "courses": ["UI/UX Design", "Graphic Design", "Video Editing", "Content Writing", "Digital Marketing"],
        "jobs": ["UI/UX Designer", "Graphic Designer", "Content Creator", "Video Editor"],
        "skills": ["Visual design", "Creativity", "User research", "Storytelling", "Portfolio building"],
        "technologies": ["Figma", "Adobe Photoshop / Illustrator", "Premiere Pro", "Canva", "HTML/CSS basics"],
        "roadmap": {"UG": ["Portfolio and internships", "Junior Designer", "UI/UX Designer", "Senior Designer / Design Lead"],
                    "PG": ["UI/UX Designer", "Senior Designer", "Design Lead / Creative Director"]}},
}


def suggested_interests(degree):
    return DEGREE_INTERESTS.get(degree, list(CAREER_PATHS.keys()))


def build_career_plan(degree, interest):
    """Return the guidance dictionary for a degree + interest, or None if unknown."""
    path = CAREER_PATHS.get(interest)
    if not path:
        return None
    level = "PG" if degree in PG_DEGREES else "UG"
    return {
        "degree": degree,
        "interest": interest,
        "level": level,
        "summary": path["summary"],
        "higher_studies": path["higher_studies"][level],
        "courses": path["courses"],
        "jobs": path["jobs"],
        "skills": path["skills"],
        "technologies": path["technologies"],
        "roadmap": [degree] + path["roadmap"][level],
    }
