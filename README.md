# Smart Scholarship Finder & Career Guidance System

A Flask + MySQL web application that recommends scholarships to college students,
checks eligibility, manages documents and applications, and gives career guidance.

## 1. What is included

| File / folder | Purpose |
|---|---|
| `app.py` | Flask routes, validation, security, admin API |
| `database.py` | MySQL connection pool and query helpers |
| `ai_recommendation.py` | Scholarship scoring algorithm + career guidance data |
| `database/schema.sql` | Creates the database, 5 tables and demo scholarships |
| `setup_database.py` | Runs `schema.sql` for you using the `.env` details |
| `templates/` | HTML pages (Jinja2 + Bootstrap 5) |
| `static/css/style.css`, `static/js/script.js` | Styling, form checks, admin dashboard logic |
| `uploads/` | Uploaded documents (created per student, random file names) |
| `tests/test_recommendation.py` | Unit tests for the matching algorithm (no database needed) |
| `.env` | Database password, secret key, admin login (edit before running) |

## 2. Setup (Windows / macOS / Linux)

1. **Install Python 3.10+** from python.org. Tick "Add Python to PATH" on Windows.
2. **Install MySQL 8** (MySQL Community Server or XAMPP/MariaDB). Remember the root password.
3. **Install packages** (a virtual environment is recommended). In a terminal in the project folder:
   ```
   python -m venv venv
   venv\Scripts\activate          # Windows      |   source venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```
4. **Edit `.env`**: set `DB_PASSWORD` to your MySQL password. Change `ADMIN_PASSWORD`.
   `SECRET_KEY` is already a random value; keep it private.
5. **Create the database and tables** (runs `database/schema.sql` using your `.env` details):
   ```
   python setup_database.py
   ```
   Alternatives: in MySQL Workbench open `database/schema.sql` and run it, or on macOS/Linux/CMD use
   `mysql -u root -p < database/schema.sql` (this `<` form does not work in Windows PowerShell).
6. **Start the server:**
   ```
   python app.py
   ```
7. **Open Chrome** at <http://127.0.0.1:5000/>

The admin account is created automatically from `.env` when the server starts.
Admin login page: <http://127.0.0.1:5000/admin/login>

> The pages load Bootstrap and Google Fonts from a CDN, so the computer needs an internet
> connection to look its best. Everything still works offline, only plainer.

## 3. Quick demo script (for viva)

1. Home page: note the deadline reminder box.
2. Register, then fill the Student Profile (for example B.E., CGPA 7.8, income 210000, SC, Female, Tamil Nadu).
3. Recommendations: scholarships sorted by match %. Hover over the tick/cross chips to see the reason.
4. Open **View Details** to see the point-by-point eligibility table.
5. Click **Apply Now** before uploading documents: it is blocked and tells you what is missing.
6. Upload documents, apply again: status **Submitted** appears under My Applications.
7. Admin: log in, change the status to **Under Review** or **Approved**, then refresh the student page.
8. Admin: add a scholarship, edit one, delete one, or remove all demo data.
9. Career Guidance: choose a degree and interest to see the roadmap.

## 4. How the recommendation works

It is a transparent **rule-based weighted scoring** system (not a trained ML model, and it does
not pretend to be one). Each scholarship is compared with the student's profile:

| Criterion | Points | Rule |
|---|---|---|
| CGPA | 20 | student CGPA >= scholarship minimum |
| Family income | 25 | student income <= scholarship maximum |
| Degree | 15 | student degree is in the scholarship's degree list |
| Community | 20 | student community is in the scholarship's list |
| Gender | 10 | matches, or scholarship is open to all |
| State | 10 | student state is in the scholarship's list |

A criterion the scholarship leaves open (`ALL`, or 0 for CGPA/income) counts as met.
Match % = points earned. Status: **Eligible** (all met), **Partially Eligible** (>= 60% but something
failed), **Not Eligible**, or **Closed** (last date passed). Results are sorted by score, then amount.
Applying is only allowed for **Eligible** scholarships, and the server checks this again on submit.

Possible future improvement: learn the weights from past approved applications using logistic regression.

## 5. Database tables

`student`, `scholarship`, `application`, `document` as specified, plus `admin`.
Extra columns: `student.email` and `password_hash` (login), `scholarship.is_demo` and `official_link`,
`document.updated_at`. `application` has a unique key on (student, scholarship) so nobody can apply twice.

## 6. Security summary

Password hashing (Werkzeug), session login, CSRF tokens on every form and API call,
parameterised SQL only, server-side validation, uploads limited to PDF/JPG/PNG up to 2 MB with a
file-signature check and random file names, admin-only routes, credentials in `.env`, friendly error pages.

## 7. Demo data

All scholarships inserted by `schema.sql` are **fictional demo records** (marked "Demo data" in the UI).
Their deadlines are set relative to the day you run the SQL so reminders always show.
Replace them in **Admin dashboard > Scholarships**: edit a record and untick "demo data" once verified,
or click **Remove all demo data** and add real scholarships from official sources.

## 8. Troubleshooting

* *"Cannot reach the database"*: MySQL not running, wrong `DB_PASSWORD`, or `schema.sql` not imported.
* *`Access denied for user`*: check `DB_USER` / `DB_PASSWORD` in `.env`.
* *`setup_database.py` cannot connect*: MySQL is not running or `.env` credentials are wrong.
* *`ModuleNotFoundError`*: activate the virtual environment and run `pip install -r requirements.txt`.
* *Admin login fails*: the password comes from `.env`; restart `python app.py` after changing it.
* Run the algorithm tests any time: `python -m unittest discover tests`
