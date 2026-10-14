import os
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = "sms-local-development-key"

# ==========================================
# DATABASE PATH
# Always use the database in this project folder
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# DATABASE MIGRATION
# Does not delete existing records
# ==========================================
def ensure_column(conn, table, column, definition):
    columns = [
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def initialize_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            course TEXT,
            semester TEXT,
            course_type TEXT DEFAULT 'UG'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            subject_name TEXT NOT NULL,
            subject_code TEXT,
            course_type TEXT DEFAULT 'UG'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            subject_name TEXT,
            marks INTEGER,
            course_type TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            date TEXT,
            status TEXT
        )
    """)

    ensure_column(conn, "students", "course_type", "TEXT DEFAULT 'UG'")
    ensure_column(conn, "subjects", "course_type", "TEXT DEFAULT 'UG'")
    ensure_column(conn, "marks", "course_type", "TEXT")

    # Classify existing students by their degree name.
    conn.execute("""
        UPDATE students
        SET course_type = CASE
            WHEN UPPER(TRIM(course)) IN (
                'MCA', 'MBA', 'MSC', 'M.SC', 'M.COM', 'MCOM',
                'MA', 'M.TECH', 'MTECH'
            ) THEN 'PG'
            WHEN UPPER(TRIM(course)) IN (
                'BCA', 'BBA', 'BSC', 'B.SC', 'BA',
                'B.COM', 'BCOM', 'BE', 'BTECH', 'B.TECH'
            ) THEN 'UG'
            ELSE course_type
        END
        WHERE course IS NOT NULL AND TRIM(course) != ''
    """)

    conn.execute("""
        UPDATE students
        SET course_type = UPPER(TRIM(course_type))
        WHERE course_type IS NOT NULL
    """)

    conn.execute("""
        UPDATE subjects
        SET course_type = UPPER(TRIM(course_type))
        WHERE course_type IS NOT NULL
    """)

    conn.commit()
    conn.close()


initialize_database()


# ==========================================
# HELPERS
# ==========================================
def infer_course_type(course):
    course = (course or "").strip().upper()

    pg_courses = {
        "MCA", "MBA", "MSC", "M.SC", "M.COM",
        "MCOM", "MA", "M.TECH", "MTECH"
    }

    ug_courses = {
        "BCA", "BBA", "BSC", "B.SC", "BA",
        "B.COM", "BCOM", "BE", "BTECH", "B.TECH"
    }

    if course in pg_courses:
        return "PG"

    if course in ug_courses:
        return "UG"

    return ""


# ==========================================
# LOGIN PAGE
# ==========================================
@app.route("/")
def login():
    return render_template("login.html")


# ==========================================
# DASHBOARD
# Dynamic values from database
# ==========================================
@app.route("/dashboard")
def dashboard():
    conn = get_db()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_subjects = conn.execute(
        "SELECT COUNT(*) FROM subjects"
    ).fetchone()[0]

    total_attendance = conn.execute("""
        SELECT COUNT(*) FROM attendance
    """).fetchone()[0]

    present_count = conn.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE LOWER(TRIM(status)) = 'present'
    """).fetchone()[0]

    attendance_percentage = round(
        present_count * 100 / total_attendance, 1
    ) if total_attendance else 0

    avg_marks = conn.execute("""
        SELECT AVG(marks) FROM marks
        WHERE marks IS NOT NULL
    """).fetchone()[0]

    avg_marks = round(avg_marks, 1) if avg_marks is not None else 0

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_subjects=total_subjects,
        attendance_percentage=attendance_percentage,
        avg_marks=avg_marks
    )


# ==========================================
# STUDENTS
# ==========================================
@app.route("/students", methods=["GET", "POST"])
def students():
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()

        course_type = (
            request.form.get("course_type")
            or infer_course_type(course)
        ).strip().upper()

        if not name:
            conn.close()
            flash("Student name is required.", "error")
            return redirect(url_for("students"))

        if course_type not in ("UG", "PG"):
            conn.close()
            flash(
                "Please select UG or PG, or enter a recognized course.",
                "error"
            )
            return redirect(url_for("students"))

        conn.execute("""
            INSERT INTO students
                (name, email, course, semester, course_type)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, course, semester, course_type))

        conn.commit()
        conn.close()

        flash("Student added successfully.", "success")
        return redirect(url_for("students"))

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students_data
    )


@app.route("/delete/<int:id>", methods=["GET", "POST"])
def delete_student(id):
    conn = get_db()
    conn.execute("DELETE FROM students WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("students"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()

        course_type = (
            request.form.get("course_type")
            or infer_course_type(course)
        ).strip().upper()

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Please select a valid course type.", "error")
            return redirect(url_for("edit_student", id=id))

        conn.execute("""
            UPDATE students
            SET name = ?, email = ?, course = ?,
                semester = ?, course_type = ?
            WHERE id = ?
        """, (name, email, course, semester, course_type, id))

        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?", (id,)
    ).fetchone()

    conn.close()

    if student is None:
        return "Student not found", 404

    return render_template("edit_student.html", student=student)


# ==========================================
# SUBJECT MANAGEMENT - UG / PG
# ==========================================
@app.route("/subjects", methods=["GET", "POST"])
def subjects():
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        course_type = request.form.get("course_type", "").strip().upper()
        subject_name = request.form.get("subject_name", "").strip()
        subject_code = request.form.get("subject_code", "").strip()

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Select UG or PG.", "error")
            return redirect(url_for("subjects"))

        if not student_name or not subject_name:
            conn.close()
            flash("Select a student and subject.", "error")
            return redirect(url_for("subjects"))

        student = conn.execute("""
            SELECT id FROM students
            WHERE name = ? AND UPPER(course_type) = ?
            LIMIT 1
        """, (student_name, course_type)).fetchone()

        if not student:
            conn.close()
            flash(
                "The selected student does not belong to this course type.",
                "error"
            )
            return redirect(url_for("subjects"))

        conn.execute("""
            INSERT INTO subjects
                (student_name, subject_name, subject_code, course_type)
            VALUES (?, ?, ?, ?)
        """, (student_name, subject_name, subject_code, course_type))

        conn.commit()
        conn.close()

        flash("Subject added successfully.", "success")
        return redirect(url_for("subjects"))

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    course_filter = request.args.get("course_type", "").strip().upper()

    if course_filter in ("UG", "PG"):
        subjects_data = conn.execute("""
            SELECT * FROM subjects
            WHERE UPPER(course_type) = ?
            ORDER BY id DESC
        """, (course_filter,)).fetchall()
    else:
        subjects_data = conn.execute("""
            SELECT * FROM subjects ORDER BY id DESC
        """).fetchall()

    conn.close()

    return render_template(
        "subjects.html",
        students=students_data,
        subjects=subjects_data,
        course_filter=course_filter
    )


@app.route("/delete_subject/<int:id>", methods=["GET", "POST"])
def delete_subject(id):
    conn = get_db()
    conn.execute("DELETE FROM subjects WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("subjects"))


@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        course_type = request.form.get("course_type", "").strip().upper()
        subject_name = request.form.get("subject_name", "").strip()
        subject_code = request.form.get("subject_code", "").strip()

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Select UG or PG.", "error")
            return redirect(url_for("edit_subject", id=id))

        conn.execute("""
            UPDATE subjects
            SET student_name = ?, course_type = ?,
                subject_name = ?, subject_code = ?
            WHERE id = ?
        """, (student_name, course_type, subject_name, subject_code, id))

        conn.commit()
        conn.close()

        return redirect(url_for("subjects"))

    subject = conn.execute(
        "SELECT * FROM subjects WHERE id = ?", (id,)
    ).fetchone()

    students_data = conn.execute(
        "SELECT * FROM students ORDER BY name"
    ).fetchall()

    conn.close()

    if subject is None:
        return "Subject not found", 404

    return render_template(
        "edit_subject.html",
        subject=subject,
        students=students_data
    )


# ==========================================
# MARKS MANAGEMENT - UG / PG
# ==========================================
@app.route("/marks", methods=["GET", "POST"])
def marks():
    conn = get_db()

    course_type = (
        request.form.get("course_type")
        or request.args.get("course_type")
        or ""
    ).strip().upper()

    if course_type not in ("UG", "PG"):
        course_type = ""

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        subject_id = request.form.get("subject_id", "").strip()
        marks_value = request.form.get("marks", "").strip()

        if not course_type or not student_id or not subject_id:
            conn.close()
            flash("Select course type, student and subject.", "error")
            return redirect(url_for("marks"))

        try:
            marks_value = int(marks_value)
            if not 0 <= marks_value <= 100:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            flash("Marks must be between 0 and 100.", "error")
            return redirect(url_for("marks", course_type=course_type))

        student = conn.execute("""
            SELECT id, name
            FROM students
            WHERE id = ? AND UPPER(course_type) = ?
        """, (student_id, course_type)).fetchone()

        subject = conn.execute("""
            SELECT id, subject_name
            FROM subjects
            WHERE id = ? AND UPPER(course_type) = ?
        """, (subject_id, course_type)).fetchone()

        if not student or not subject:
            conn.close()
            flash(
                "Student and subject must belong to the selected UG/PG type.",
                "error"
            )
            return redirect(url_for("marks", course_type=course_type))

        conn.execute("""
            INSERT INTO marks
                (student_name, subject_name, marks, course_type)
            VALUES (?, ?, ?, ?)
        """, (
            student["name"],
            subject["subject_name"],
            marks_value,
            course_type
        ))

        conn.commit()
        conn.close()

        flash("Marks added successfully.", "success")
        return redirect(url_for("marks", course_type=course_type))

    if course_type:
        students_data = conn.execute("""
            SELECT id, name
            FROM students
            WHERE UPPER(course_type) = ?
            ORDER BY name
        """, (course_type,)).fetchall()

        subjects_data = conn.execute("""
            SELECT id, subject_name, subject_code
            FROM subjects
            WHERE UPPER(course_type) = ?
            ORDER BY subject_name
        """, (course_type,)).fetchall()

        marks_data = conn.execute("""
            SELECT id, student_name, subject_name, marks, course_type
            FROM marks
            WHERE UPPER(course_type) = ?
            ORDER BY id DESC
        """, (course_type,)).fetchall()
    else:
        students_data = []
        subjects_data = []

        marks_data = conn.execute("""
            SELECT id, student_name, subject_name, marks, course_type
            FROM marks
            ORDER BY id DESC
        """).fetchall()

    conn.close()

    return render_template(
        "marks.html",
        students=students_data,
        subjects=subjects_data,
        marks_data=marks_data,
        course_type=course_type
    )


@app.route("/edit_mark/<int:id>", methods=["GET", "POST"])
def edit_mark(id):
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        subject_name = request.form.get("subject_name", "").strip()
        course_type = request.form.get("course_type", "").strip().upper()

        try:
            marks_value = int(request.form.get("marks", ""))
            if not 0 <= marks_value <= 100:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            flash("Marks must be between 0 and 100.", "error")
            return redirect(url_for("edit_mark", id=id))

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Select UG or PG.", "error")
            return redirect(url_for("edit_mark", id=id))

        conn.execute("""
            UPDATE marks
            SET student_name = ?, subject_name = ?,
                marks = ?, course_type = ?
            WHERE id = ?
        """, (student_name, subject_name, marks_value, course_type, id))

        conn.commit()
        conn.close()

        return redirect(url_for("marks", course_type=course_type))

    mark = conn.execute(
        "SELECT * FROM marks WHERE id = ?", (id,)
    ).fetchone()

    conn.close()

    if mark is None:
        return "Marks record not found", 404

    return render_template("edit_mark.html", mark=mark)


@app.route("/delete_mark/<int:id>", methods=["GET", "POST"])
def delete_mark(id):
    conn = get_db()

    mark = conn.execute(
        "SELECT course_type FROM marks WHERE id = ?", (id,)
    ).fetchone()

    course_type = mark["course_type"] if mark else ""

    conn.execute("DELETE FROM marks WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    if course_type in ("UG", "PG"):
        return redirect(url_for("marks", course_type=course_type))

    return redirect(url_for("marks"))


# ==========================================
# ATTENDANCE MANAGEMENT
# ==========================================
@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        date = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip()

        if status not in ("Present", "Absent"):
            conn.close()
            flash("Select Present or Absent.", "error")
            return redirect(url_for("attendance"))

        conn.execute("""
            INSERT INTO attendance (student_name, date, status)
            VALUES (?, ?, ?)
        """, (student_name, date, status))

        conn.commit()
        conn.close()

        return redirect(url_for("attendance"))

    students_data = conn.execute("""
        SELECT name FROM students ORDER BY name
    """).fetchall()

    attendance_data = conn.execute("""
        SELECT * FROM attendance ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        students=students_data,
        attendance_data=attendance_data
    )


@app.route("/delete_attendance/<int:id>", methods=["GET", "POST"])
def delete_attendance(id):
    conn = get_db()
    conn.execute("DELETE FROM attendance WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("attendance"))


@app.route("/edit_attendance/<int:id>", methods=["GET", "POST"])
def edit_attendance(id):
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        date = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip()

        if status not in ("Present", "Absent"):
            conn.close()
            flash("Select Present or Absent.", "error")
            return redirect(url_for("edit_attendance", id=id))

        conn.execute("""
            UPDATE attendance
            SET student_name = ?, date = ?, status = ?
            WHERE id = ?
        """, (student_name, date, status, id))

        conn.commit()
        conn.close()

        return redirect(url_for("attendance"))

    attendance_record = conn.execute(
        "SELECT * FROM attendance WHERE id = ?", (id,)
    ).fetchone()

    students_data = conn.execute(
        "SELECT name FROM students ORDER BY name"
    ).fetchall()

    conn.close()

    if attendance_record is None:
        return "Attendance record not found", 404

    return render_template(
        "edit_attendance.html",
        attendance=attendance_record,
        students=students_data
    )


# ==========================================
# PERFORMANCE ANALYSIS
# ==========================================
@app.route("/performance", methods=["GET", "POST"])
def performance():
    conn = get_db()

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    performance_data = None

    if request.method == "POST":
        student_id = request.form.get("student_id")

        student = conn.execute("""
            SELECT id, name, course_type
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        if student:
            student_name = student["name"]

            marks_rows = conn.execute("""
                SELECT subject_name, marks
                FROM marks
                WHERE student_name = ?
                ORDER BY subject_name
            """, (student_name,)).fetchall()

            subject_list = [
                {
                    "name": row["subject_name"],
                    "marks": row["marks"] or 0
                }
                for row in marks_rows
            ]

            values = [row["marks"] or 0 for row in marks_rows]
            avg_marks = round(sum(values) / len(values), 1) if values else 0

            if avg_marks >= 90:
                grade = "A+"
            elif avg_marks >= 80:
                grade = "A"
            elif avg_marks >= 70:
                grade = "B"
            elif avg_marks >= 60:
                grade = "C"
            elif avg_marks >= 50:
                grade = "D"
            else:
                grade = "F"

            result = "PASS" if avg_marks >= 40 else "FAIL"

            attendance_rows = conn.execute("""
                SELECT status
                FROM attendance
                WHERE student_name = ?
            """, (student_name,)).fetchall()

            total_classes = len(attendance_rows)

            attended = sum(
                1 for row in attendance_rows
                if (row["status"] or "").strip().lower() == "present"
            )

            missed = total_classes - attended

            attendance_percentage = round(
                attended * 100 / total_classes, 1
            ) if total_classes else 0

            performance_data = {
                "student_name": student_name,
                "subjects": subject_list,
                "avg_marks": avg_marks,
                "grade": grade,
                "result": result,
                "attendance_percentage": attendance_percentage,
                "total_classes": total_classes,
                "attended": attended,
                "missed": missed
            }

    conn.close()

    return render_template(
        "performance.html",
        students=students_data,
        performance=performance_data
    )


# ==========================================
# REPORTS
# ==========================================
@app.route("/reports")
def reports():
    conn = get_db()

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    marks_data = conn.execute("""
        SELECT * FROM marks ORDER BY id DESC
    """).fetchall()

    attendance_data = conn.execute("""
        SELECT * FROM attendance ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        students=students_data,
        marks_data=marks_data,
        attendance_data=attendance_data
    )


# ==========================================
# RUN APPLICATION
# ==========================================
if __name__ == "__main__":
    app.run(debug=True)
