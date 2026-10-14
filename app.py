
import os
import sqlite3
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = "smart-student-management-local-key"


# =====================================================
# DATABASE HELPERS
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn, table, column, definition):
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def valid_course_type(value):
    value = (value or "").strip().upper()
    return value if value in ("UG", "PG") else ""


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

    # Add missing columns without deleting existing data.
    ensure_column(conn, "students", "course_type", "TEXT DEFAULT 'UG'")
    ensure_column(conn, "subjects", "student_name", "TEXT")
    ensure_column(conn, "subjects", "subject_code", "TEXT")
    ensure_column(conn, "subjects", "course_type", "TEXT DEFAULT 'UG'")
    ensure_column(conn, "marks", "course_type", "TEXT")

    # Normalize course types in existing records.
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

    # Recover missing course types on old marks using the student's
    # name and their subject assignment.
    conn.execute("""
        UPDATE marks
        SET course_type = (
            SELECT UPPER(TRIM(s.course_type))
            FROM subjects s
            WHERE LOWER(TRIM(s.student_name)) =
                  LOWER(TRIM(marks.student_name))
              AND LOWER(TRIM(s.subject_name)) =
                  LOWER(TRIM(marks.subject_name))
            ORDER BY s.id DESC
            LIMIT 1
        )
        WHERE course_type IS NULL
           OR TRIM(course_type) = ''
    """)

    conn.commit()
    conn.close()


initialize_database()


# =====================================================
# LOGIN AND DASHBOARD
# =====================================================

@app.route("/")
def login():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    conn = get_db()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_subjects = conn.execute(
        "SELECT COUNT(*) FROM subjects"
    ).fetchone()[0]

    total_attendance = conn.execute(
        "SELECT COUNT(*) FROM attendance"
    ).fetchone()[0]

    present_count = conn.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE LOWER(TRIM(COALESCE(status, ''))) = 'present'
    """).fetchone()[0]

    attendance_percentage = (
        round(present_count * 100 / total_attendance, 1)
        if total_attendance else 0
    )

    average = conn.execute("""
        SELECT AVG(marks) FROM marks WHERE marks IS NOT NULL
    """).fetchone()[0]

    avg_marks = round(average, 1) if average is not None else 0

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_subjects=total_subjects,
        attendance_percentage=attendance_percentage,
        avg_marks=avg_marks
    )


# =====================================================
# STUDENTS
# =====================================================

@app.route("/students", methods=["GET", "POST"])
def students():
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()
        course_type = valid_course_type(request.form.get("course_type"))

        if not name or not course_type:
            conn.close()
            flash("Enter the student name and select UG or PG.", "error")
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
    return render_template("students.html", students=students_data)


@app.route("/delete/<int:id>", methods=["GET", "POST"])
def delete_student(id):
    conn = get_db()
    conn.execute("DELETE FROM students WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Student deleted successfully.", "success")
    return redirect(url_for("students"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()
        course_type = valid_course_type(request.form.get("course_type"))

        if not name or not course_type:
            conn.close()
            flash("Enter the student name and select UG or PG.", "error")
            return redirect(url_for("edit_student", id=id))

        conn.execute("""
            UPDATE students
            SET name=?, email=?, course=?, semester=?, course_type=?
            WHERE id=?
        """, (name, email, course, semester, course_type, id))

        conn.commit()
        conn.close()

        flash("Student updated successfully.", "success")
        return redirect(url_for("students"))

    student = conn.execute(
        "SELECT * FROM students WHERE id=?", (id,)
    ).fetchone()

    conn.close()

    if student is None:
        return "Student not found", 404

    return render_template("edit_student.html", student=student)


# =====================================================
# SUBJECTS
# =====================================================

@app.route("/subjects", methods=["GET", "POST"])
def subjects():
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        course_type = valid_course_type(request.form.get("course_type"))
        subject_name = request.form.get("subject_name", "").strip()
        subject_code = request.form.get("subject_code", "").strip()

        if not all([student_name, course_type, subject_name]):
            conn.close()
            flash("Select a student, course type and subject.", "error")
            return redirect(url_for("subjects"))

        student = conn.execute("""
            SELECT id FROM students
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
            LIMIT 1
        """, (student_name,)).fetchone()

        if not student:
            conn.close()
            flash("Selected student was not found.", "error")
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

    course_filter = valid_course_type(request.args.get("course_type"))

    if course_filter:
        subjects_data = conn.execute("""
            SELECT * FROM subjects
            WHERE UPPER(TRIM(COALESCE(course_type, ''))) = ?
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
    conn.execute("DELETE FROM subjects WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Subject deleted successfully.", "success")
    return redirect(url_for("subjects"))


@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):
    conn = get_db()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        course_type = valid_course_type(request.form.get("course_type"))
        subject_name = request.form.get("subject_name", "").strip()
        subject_code = request.form.get("subject_code", "").strip()

        if not student_name or not course_type or not subject_name:
            conn.close()
            flash("Please fill in all required subject details.", "error")
            return redirect(url_for("edit_subject", id=id))

        conn.execute("""
            UPDATE subjects
            SET student_name=?, subject_name=?, subject_code=?, course_type=?
            WHERE id=?
        """, (student_name, subject_name, subject_code, course_type, id))

        conn.commit()
        conn.close()

        flash("Subject updated successfully.", "success")
        return redirect(url_for("subjects"))

    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=?", (id,)
    ).fetchone()

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    conn.close()

    if subject is None:
        return "Subject not found", 404

    return render_template(
        "edit_subject.html",
        subject=subject,
        students=students_data
    )


# =====================================================
# MARKS MANAGEMENT
# =====================================================

@app.route("/marks", methods=["GET", "POST"])
def marks():
    conn = get_db()

    course_type = valid_course_type(
        request.form.get("course_type") or request.args.get("course_type")
    )

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        subject_id = request.form.get("subject_id", "").strip()
        marks_text = request.form.get("marks", "").strip()

        if not course_type or not student_id or not subject_id:
            conn.close()
            flash("Select course type, student and subject.", "error")
            return redirect(url_for("marks", course_type=course_type))

        try:
            marks_value = int(marks_text)
            if not 0 <= marks_value <= 100:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            flash("Enter marks between 0 and 100.", "error")
            return redirect(url_for("marks", course_type=course_type))

        # Student is selected from the existing Students table.
        student = conn.execute("""
            SELECT id, name
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        # Subject must be an existing subject for this course type
        # and must be assigned to the selected student.
        subject = conn.execute("""
            SELECT id, subject_name
            FROM subjects
            WHERE id = ?
              AND UPPER(TRIM(COALESCE(course_type, ''))) = ?
              AND LOWER(TRIM(COALESCE(student_name, ''))) =
                  LOWER(TRIM(?))
        """, (subject_id, course_type, student["name"] if student else "")).fetchone()

        if not student:
            conn.close()
            flash("Selected student was not found.", "error")
            return redirect(url_for("marks", course_type=course_type))

        if not subject:
            conn.close()
            flash(
                "Select a subject assigned to this student in Subject Management.",
                "error"
            )
            return redirect(url_for("marks", course_type=course_type))

        # Prevent duplicate marks for the same student and subject.
        existing = conn.execute("""
            SELECT id FROM marks
            WHERE LOWER(TRIM(student_name)) = LOWER(TRIM(?))
              AND LOWER(TRIM(subject_name)) = LOWER(TRIM(?))
        """, (student["name"], subject["subject_name"])).fetchone()

        if existing:
            conn.close()
            flash(
                "Marks already exist for this student and subject. Use Edit to update them.",
                "error"
            )
            return redirect(url_for("marks", course_type=course_type))

        try:
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

        except sqlite3.Error as error:
            conn.rollback()
            conn.close()
            app.logger.exception("Unable to save marks: %s", error)
            flash("Marks could not be saved. Please try again.", "error")
            return redirect(url_for("marks", course_type=course_type))

        conn.close()
        flash("Marks added successfully.", "success")
        return redirect(url_for("marks", course_type=course_type))

    if course_type:
        # Students appear when they have a subject assigned for
        # the selected UG/PG type, even if their course_type column
        # was not populated correctly when they were first added.
        students_data = conn.execute("""
            SELECT DISTINCT st.id, st.name
            FROM students st
            INNER JOIN subjects sub
                ON LOWER(TRIM(st.name)) =
                   LOWER(TRIM(sub.student_name))
            WHERE UPPER(TRIM(COALESCE(sub.course_type, ''))) = ?
            ORDER BY st.name
        """, (course_type,)).fetchall()

        subjects_data = conn.execute("""
            SELECT id, subject_name, subject_code, student_name
            FROM subjects
            WHERE UPPER(TRIM(COALESCE(course_type, ''))) = ?
            ORDER BY subject_name
        """, (course_type,)).fetchall()

        # Include older marks whose course type was not saved,
        # matching their subject to the existing subject assignments.
        marks_data = conn.execute("""
            SELECT
                m.id,
                m.student_name,
                m.subject_name,
                m.marks,
                COALESCE(
                    NULLIF(UPPER(TRIM(m.course_type)), ''),
                    (
                        SELECT UPPER(TRIM(s.course_type))
                        FROM subjects s
                        WHERE LOWER(TRIM(s.student_name)) =
                              LOWER(TRIM(m.student_name))
                          AND LOWER(TRIM(s.subject_name)) =
                              LOWER(TRIM(m.subject_name))
                        ORDER BY s.id DESC
                        LIMIT 1
                    ),
                    ''
                ) AS display_course_type
            FROM marks m
            WHERE COALESCE(
                NULLIF(UPPER(TRIM(m.course_type)), ''),
                (
                    SELECT UPPER(TRIM(s.course_type))
                    FROM subjects s
                    WHERE LOWER(TRIM(s.student_name)) =
                          LOWER(TRIM(m.student_name))
                      AND LOWER(TRIM(s.subject_name)) =
                          LOWER(TRIM(m.subject_name))
                    ORDER BY s.id DESC
                    LIMIT 1
                ),
                ''
            ) = ?
            ORDER BY m.id DESC
        """, (course_type,)).fetchall()

    else:
        students_data = []
        subjects_data = []
        marks_data = conn.execute("""
            SELECT id, student_name, subject_name, marks,
                   COALESCE(UPPER(TRIM(course_type)), '') AS display_course_type
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

    mark = conn.execute(
        "SELECT * FROM marks WHERE id=?", (id,)
    ).fetchone()

    if mark is None:
        conn.close()
        return "Marks record not found", 404

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        subject_name = request.form.get("subject_name", "").strip()
        course_type = valid_course_type(request.form.get("course_type"))

        try:
            marks_value = int(request.form.get("marks", ""))
            if not 0 <= marks_value <= 100:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            flash("Enter marks between 0 and 100.", "error")
            return redirect(url_for("edit_mark", id=id))

        if not student_name or not subject_name or not course_type:
            conn.close()
            flash("Enter all marks details.", "error")
            return redirect(url_for("edit_mark", id=id))

        conn.execute("""
            UPDATE marks
            SET student_name=?, subject_name=?, marks=?, course_type=?
            WHERE id=?
        """, (student_name, subject_name, marks_value, course_type, id))

        conn.commit()
        conn.close()

        flash("Marks updated successfully.", "success")
        return redirect(url_for("marks", course_type=course_type))

    conn.close()
    return render_template("edit_mark.html", mark=mark)


@app.route("/delete_mark/<int:id>", methods=["GET", "POST"])
def delete_mark(id):
    conn = get_db()

    mark = conn.execute(
        "SELECT course_type FROM marks WHERE id=?", (id,)
    ).fetchone()

    course_type = valid_course_type(mark["course_type"]) if mark else ""

    conn.execute("DELETE FROM marks WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Marks deleted successfully.", "success")

    if course_type:
        return redirect(url_for("marks", course_type=course_type))
    return redirect(url_for("marks"))


# =====================================================
# ATTENDANCE
# =====================================================

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    conn = get_db()
    today = date.today().isoformat()

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        date_value = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip().capitalize()

        try:
            selected_date = date.fromisoformat(date_value)
        except ValueError:
            selected_date = None

        if not student_name or not selected_date:
            conn.close()
            flash("Select a student and valid date.", "error")
            return redirect(url_for("attendance"))

        if selected_date > date.today():
            conn.close()
            flash("Future attendance dates are not allowed.", "error")
            return redirect(url_for("attendance"))

        if status not in ("Present", "Absent"):
            conn.close()
            flash("Select Present or Absent.", "error")
            return redirect(url_for("attendance"))

        conn.execute("""
            INSERT INTO attendance (student_name, date, status)
            VALUES (?, ?, ?)
        """, (student_name, date_value, status))

        conn.commit()
        conn.close()

        flash("Attendance added successfully.", "success")
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
        attendance_data=attendance_data,
        today=today
    )


@app.route("/delete_attendance/<int:id>", methods=["GET", "POST"])
def delete_attendance(id):
    conn = get_db()
    conn.execute("DELETE FROM attendance WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Attendance deleted successfully.", "success")
    return redirect(url_for("attendance"))


@app.route("/edit_attendance/<int:id>", methods=["GET", "POST"])
def edit_attendance(id):
    conn = get_db()
    today = date.today().isoformat()

    attendance_record = conn.execute(
        "SELECT * FROM attendance WHERE id=?", (id,)
    ).fetchone()

    if attendance_record is None:
        conn.close()
        return "Attendance record not found", 404

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        date_value = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip().capitalize()

        try:
            selected_date = date.fromisoformat(date_value)
        except ValueError:
            selected_date = None

        if not student_name or not selected_date:
            conn.close()
            flash("Select a student and valid date.", "error")
            return redirect(url_for("edit_attendance", id=id))

        if selected_date > date.today():
            conn.close()
            flash("Future attendance dates are not allowed.", "error")
            return redirect(url_for("edit_attendance", id=id))

        if status not in ("Present", "Absent"):
            conn.close()
            flash("Select Present or Absent.", "error")
            return redirect(url_for("edit_attendance", id=id))

        conn.execute("""
            UPDATE attendance
            SET student_name=?, date=?, status=?
            WHERE id=?
        """, (student_name, date_value, status, id))

        conn.commit()
        conn.close()

        flash("Attendance updated successfully.", "success")
        return redirect(url_for("attendance"))

    students_data = conn.execute("""
        SELECT name FROM students ORDER BY name
    """).fetchall()

    conn.close()

    return render_template(
        "edit_attendance.html",
        attendance=attendance_record,
        students=students_data,
        today=today
    )


# =====================================================
# PERFORMANCE
# =====================================================

@app.route("/performance", methods=["GET", "POST"])
def performance():
    conn = get_db()

    students_data = conn.execute("""
        SELECT * FROM students ORDER BY name
    """).fetchall()

    performance_data = None

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()

        student = conn.execute("""
            SELECT id, name, course_type
            FROM students WHERE id=?
        """, (student_id,)).fetchone()

        if student:
            student_name = student["name"]

            marks_rows = conn.execute("""
                SELECT subject_name, marks
                FROM marks
                WHERE LOWER(TRIM(student_name)) =
                      LOWER(TRIM(?))
                ORDER BY subject_name
            """, (student_name,)).fetchall()

            subject_list = [
                {
                    "name": row["subject_name"],
                    "marks": row["marks"] if row["marks"] is not None else 0
                }
                for row in marks_rows
            ]

            values = [item["marks"] for item in subject_list]
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

            result = (
                "PASS" if values and avg_marks >= 40
                else "FAIL" if values
                else "NO MARKS"
            )

            attendance_rows = conn.execute("""
                SELECT status FROM attendance
                WHERE LOWER(TRIM(student_name)) =
                      LOWER(TRIM(?))
            """, (student_name,)).fetchall()

            total_classes = len(attendance_rows)
            attended = sum(
                1 for row in attendance_rows
                if (row["status"] or "").strip().lower() == "present"
            )

            missed = total_classes - attended
            attendance_percentage = (
                round(attended * 100 / total_classes, 1)
                if total_classes else 0
            )

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


# =====================================================
# REPORTS
# =====================================================

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


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(debug=True)
