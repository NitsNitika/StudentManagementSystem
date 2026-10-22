
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
            course_type TEXT DEFAULT 'UG',
            student_code TEXT
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
    ensure_column(conn, "students", "student_code", "TEXT")
    ensure_column(conn, "subjects", "student_name", "TEXT")
    ensure_column(conn, "subjects", "subject_code", "TEXT")
    ensure_column(conn, "subjects", "course_type", "TEXT DEFAULT 'UG'")
    ensure_column(conn, "marks", "course_type", "TEXT")

    # Normalize course types without blindly changing PG to UG.
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

    # Recover student type from existing register numbers.
    conn.execute("""
        UPDATE students
        SET course_type = 'PG'
        WHERE UPPER(TRIM(COALESCE(student_code, ''))) LIKE 'MC26MC%'
    """)

    conn.execute("""
        UPDATE students
        SET course_type = 'UG'
        WHERE UPPER(TRIM(COALESCE(student_code, ''))) LIKE 'MS2353%'
    """)

    # Recover missing course types from subjects linked by student name.
    # Use this only when the student has no reliable register-number prefix.
    conn.execute("""
        UPDATE students
        SET course_type = (
            SELECT UPPER(TRIM(s.course_type))
            FROM subjects s
            WHERE LOWER(TRIM(COALESCE(s.student_name, ''))) =
                  LOWER(TRIM(students.name))
              AND UPPER(TRIM(COALESCE(s.course_type, ''))) IN ('UG', 'PG')
            ORDER BY s.id DESC
            LIMIT 1
        )
        WHERE (
            course_type IS NULL
            OR TRIM(course_type) = ''
            OR UPPER(TRIM(course_type)) NOT IN ('UG', 'PG')
        )
        AND UPPER(TRIM(COALESCE(student_code, ''))) NOT LIKE 'MC26MC%'
        AND UPPER(TRIM(COALESCE(student_code, ''))) NOT LIKE 'MS2353%'
        AND EXISTS (
            SELECT 1
            FROM subjects s
            WHERE LOWER(TRIM(COALESCE(s.student_name, ''))) =
                  LOWER(TRIM(students.name))
              AND UPPER(TRIM(COALESCE(s.course_type, ''))) IN ('UG', 'PG')
        )
    """)

    # Recover missing course types from recognizable course names.
    # Do not overwrite a valid UG/PG value.
    students = conn.execute("""
        SELECT id, course, course_type, student_code
        FROM students
    """).fetchall()

    pg_courses = {
        "MCA", "MBA", "MSC", "M.SC", "MCOM",
        "M.COM", "MA", "MTECH", "M.TECH"
    }

    ug_courses = {
        "BCA", "BBA", "BSC", "B.SC", "BCOM",
        "B.COM", "BA", "BE", "BTECH", "B.TECH"
    }

    for student in students:
        current_type = (
            student["course_type"] or ""
        ).strip().upper()

        code = (student["student_code"] or "").strip().upper()
        course = (
            (student["course"] or "")
            .strip()
            .upper()
            .replace(" ", "")
        )

        # A recognized register-number prefix takes priority.
        if code.startswith("MC26MC"):
            current_type = "PG"
        elif code.startswith("MS2353"):
            current_type = "UG"
        elif current_type not in ("UG", "PG"):
            if course in pg_courses:
                current_type = "PG"
            elif course in ug_courses:
                current_type = "UG"

        # Leave the value untouched if it cannot be identified reliably.
        if current_type in ("UG", "PG"):
            conn.execute("""
                UPDATE students
                SET course_type = ?
                WHERE id = ?
            """, (current_type, student["id"]))

    # Recover missing course types on old marks.
    conn.execute("""
        UPDATE marks
        SET course_type = (
            SELECT UPPER(TRIM(s.course_type))
            FROM subjects s
            WHERE LOWER(TRIM(COALESCE(s.student_name, ''))) =
                  LOWER(TRIM(COALESCE(marks.student_name, '')))
              AND LOWER(TRIM(COALESCE(s.subject_name, ''))) =
                  LOWER(TRIM(COALESCE(marks.subject_name, '')))
              AND UPPER(TRIM(COALESCE(s.course_type, ''))) IN ('UG', 'PG')
            ORDER BY s.id DESC
            LIMIT 1
        )
        WHERE course_type IS NULL OR TRIM(course_type) = ''
    """)

    # Assign register numbers to existing students without one.
    # Keep all existing register numbers unchanged.
    for course_type, prefix in (
        ("UG", "MS2353"),
        ("PG", "MC26MC")
    ):
        existing_codes = conn.execute("""
            SELECT student_code
            FROM students
            WHERE UPPER(TRIM(COALESCE(student_code, ''))) LIKE ?
        """, (prefix + "%",)).fetchall()

        numbers = []

        for row in existing_codes:
            code = (row["student_code"] or "").strip().upper()
            suffix = code[len(prefix):]

            if suffix.isdigit():
                numbers.append(int(suffix))

        next_number = max(numbers, default=0) + 1

        missing_students = conn.execute("""
            SELECT id
            FROM students
            WHERE (
                student_code IS NULL
                OR TRIM(student_code) = ''
            )
            AND UPPER(TRIM(COALESCE(course_type, ''))) = ?
            ORDER BY id ASC
        """, (course_type,)).fetchall()

        for student in missing_students:
            new_code = f"{prefix}{next_number:02d}"

            conn.execute("""
                UPDATE students
                SET student_code = ?
                WHERE id = ?
            """, (new_code, student["id"]))

            next_number += 1

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

# =====================================================
# STUDENT MANAGEMENT
# =====================================================


# =========================================================
# STUDENT MANAGEMENT
# =========================================================

def generate_student_code(conn, course_type):
    course_type = valid_course_type(course_type)

    if course_type == "UG":
        prefix = "MS2353"
    elif course_type == "PG":
        prefix = "MC26MC"
    else:
        raise ValueError("Please select UG or PG.")

    # Find the highest number for this course type only
    rows = conn.execute("""
        SELECT student_code
        FROM students
        WHERE student_code LIKE ?
    """, (prefix + "%",)).fetchall()

    numbers = []

    for row in rows:
        code = row["student_code"] or ""

        if code.startswith(prefix):
            suffix = code[len(prefix):]

            if suffix.isdigit():
                numbers.append(int(suffix))

    next_number = max(numbers, default=0) + 1

    return f"{prefix}{next_number:02d}"



@app.route("/students", methods=["GET", "POST"])
def students():
    conn = get_db()

    # -----------------------------------------------------
    # ADD STUDENT
    # -----------------------------------------------------
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()

        course_type = valid_course_type(
            request.form.get("course_type")
        )

        if not name:
            conn.close()
            flash("Please enter the student name.", "error")
            return redirect(url_for("students"))

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Please select UG or PG.", "error")
            return redirect(url_for("students"))

        try:
            # Generate a permanent register number
            student_code = generate_student_code(
                conn, course_type
            )

            conn.execute("""
                INSERT INTO students
                    (name, email, course, semester,
                     course_type, student_code)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                course,
                semester,
                course_type,
                student_code
            ))

            conn.commit()

        except Exception:
            conn.rollback()
            conn.close()
            raise

        conn.close()

        flash("Student added successfully!", "success")
        return redirect(url_for("students"))

    # -----------------------------------------------------
    # FILTER: ALL / UG / PG
    # Use the student's saved course_type.
    # Do not infer it from subjects.
    # -----------------------------------------------------
    course_filter = request.args.get(
        "course_type", ""
    ).strip().upper()

    if course_filter not in ("UG", "PG"):
        course_filter = ""

    students_data = conn.execute("""
        SELECT
            s.*,
            UPPER(TRIM(COALESCE(s.course_type, '')))
                AS display_course_type
        FROM students s
        ORDER BY s.id DESC
    """).fetchall()

    conn.close()

    # Filter by the student's own saved course type
    if course_filter:
        students_data = [
            student
            for student in students_data
            if (
                student["display_course_type"] or ""
            ) == course_filter
        ]

    return render_template(
        "students.html",
        students=students_data,
        course_filter=course_filter
    )


# =========================================================
# DELETE STUDENT
# =========================================================


@app.route("/delete/<int:id>", methods=["GET", "POST"])
def delete_student(id):
    conn = get_db()

    try:
        student = conn.execute(
            "SELECT id, name FROM students WHERE id = ?",
            (id,)
        ).fetchone()

        if student is None:
            flash("Student not found.", "error")
            return redirect(url_for("students"))

        student_name = student["name"]

        # Delete related subject records
        conn.execute("""
            DELETE FROM subjects
            WHERE LOWER(TRIM(COALESCE(student_name, ''))) =
                  LOWER(TRIM(?))
        """, (student_name,))

        # Delete related marks records
        conn.execute("""
            DELETE FROM marks
            WHERE LOWER(TRIM(COALESCE(student_name, ''))) =
                  LOWER(TRIM(?))
        """, (student_name,))

        # Delete related attendance records
        conn.execute("""
            DELETE FROM attendance
            WHERE LOWER(TRIM(COALESCE(student_name, ''))) =
                  LOWER(TRIM(?))
        """, (student_name,))

        # Delete the student record
        conn.execute(
            "DELETE FROM students WHERE id = ?",
            (id,)
        )

        conn.commit()
        flash(
            "Student and related records deleted successfully!",
            "success"
        )

    except Exception:
        conn.rollback()
        app.logger.exception("Failed to delete student and related records")
        flash("Could not delete the student. Please try again.", "error")

    finally:
        conn.close()

    return redirect(url_for("students"))

# =========================================================
# EDIT STUDENT
# =========================================================

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (id,)
    ).fetchone()

    if student is None:
        conn.close()
        return "Student not found", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()
        course_type = valid_course_type(
            request.form.get("course_type")
        )

        if not name:
            conn.close()
            flash("Please enter the student name.", "error")
            return redirect(url_for("edit_student", id=id))

        if course_type not in ("UG", "PG"):
            conn.close()
            flash("Please select UG or PG.", "error")
            return redirect(url_for("edit_student", id=id))

        conn.execute("""
            UPDATE students
            SET name = ?,
                email = ?,
                course = ?,
                semester = ?,
                course_type = ?
            WHERE id = ?
        """, (
            name,
            email,
            course,
            semester,
            course_type,
            id
        ))

        conn.commit()
        conn.close()

        flash("Student updated successfully!", "success")
        return redirect(url_for("students"))

    conn.close()

    return render_template(
        "edit_student.html",
        student=student
    )


# ==========================================
# SUBJECT MANAGEMENT
# ==========================================

@app.route("/subjects", methods=["GET", "POST"])
def subjects():
    conn = get_db()

    try:
        # ------------------------------------------
        # ADD SUBJECT
        # ------------------------------------------
        if request.method == "POST":
            student_name = request.form.get(
                "student_name", ""
            ).strip()

            course_type = valid_course_type(
                request.form.get("course_type")
            )

            subject_name = request.form.get(
                "subject_name", ""
            ).strip()

            subject_code = request.form.get(
                "subject_code", ""
            ).strip()

            # Support the Other subject option.
            if subject_name == "Other":
                subject_name = request.form.get(
                    "custom_subject", ""
                ).strip()

            if not student_name or not course_type or not subject_name:
                flash(
                    "Please select a student, course type and subject.",
                    "error"
                )
                return redirect(url_for("subjects"))

            # Find the student using both name and course type.
            student = conn.execute("""
                SELECT id, name, course_type, student_code
                FROM students
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                  AND UPPER(TRIM(COALESCE(course_type, 'UG'))) = ?
                ORDER BY id DESC
                LIMIT 1
            """, (student_name, course_type)).fetchone()

            if not student:
                flash(
                    "Student not found for the selected course type.",
                    "error"
                )
                return redirect(url_for("subjects"))

            # Use the actual student's name from the database.
            student_name = student["name"]

            conn.execute("""
                INSERT INTO subjects (
                    student_name,
                    subject_name,
                    subject_code,
                    course_type
                )
                VALUES (?, ?, ?, ?)
            """, (
                student_name,
                subject_name,
                subject_code,
                course_type
            ))

            conn.commit()

            flash("Subject added successfully.", "success")
            return redirect(url_for("subjects"))

        # ------------------------------------------
        # FETCH STUDENTS FOR THE ADD SUBJECT FORM
        # ------------------------------------------
        students_data = conn.execute("""
            SELECT
                id,
                name,
                email,
                course,
                semester,
                UPPER(TRIM(COALESCE(course_type, 'UG'))) AS course_type,
                student_code
            FROM students
            ORDER BY name
        """).fetchall()

        # ------------------------------------------
        # FETCH SUBJECT LIST WITH REGISTER NUMBERS
        # ------------------------------------------
        course_filter = valid_course_type(
            request.args.get("course_type")
        )

        if course_filter:
            subjects_data = conn.execute("""
                SELECT
                    sub.id,
                    sub.student_name,
                    sub.subject_name,
                    sub.subject_code,
                    UPPER(TRIM(COALESCE(sub.course_type, 'UG')))
                        AS course_type,
                    s.student_code
                FROM subjects AS sub
                LEFT JOIN students AS s
                    ON LOWER(TRIM(s.name)) =
                       LOWER(TRIM(sub.student_name))
                   AND UPPER(TRIM(COALESCE(s.course_type, 'UG'))) =
                       UPPER(TRIM(COALESCE(sub.course_type, 'UG')))
                WHERE UPPER(TRIM(COALESCE(sub.course_type, 'UG'))) = ?
                ORDER BY sub.id DESC
            """, (course_filter,)).fetchall()

        else:
            subjects_data = conn.execute("""
                SELECT
                    sub.id,
                    sub.student_name,
                    sub.subject_name,
                    sub.subject_code,
                    UPPER(TRIM(COALESCE(sub.course_type, 'UG')))
                        AS course_type,
                    s.student_code
                FROM subjects AS sub
                LEFT JOIN students AS s
                    ON LOWER(TRIM(s.name)) =
                       LOWER(TRIM(sub.student_name))
                   AND UPPER(TRIM(COALESCE(s.course_type, 'UG'))) =
                       UPPER(TRIM(COALESCE(sub.course_type, 'UG')))
                ORDER BY sub.id DESC
            """).fetchall()

        return render_template(
            "subjects.html",
            students=students_data,
            subjects=subjects_data,
            course_filter=course_filter
        )

    except Exception:
        conn.rollback()
        app.logger.exception("Error loading or saving subjects")
        flash(
            "Unable to process the subject request. Please check the application logs.",
            "error"
        )
        return redirect(url_for("subjects"))

    finally:
        conn.close()


# ==========================================
# DELETE SUBJECT
# ==========================================

@app.route("/delete_subject/<int:id>", methods=["GET", "POST"])
def delete_subject(id):
    conn = get_db()

    try:
        subject = conn.execute("""
            SELECT id, subject_name
            FROM subjects
            WHERE id = ?
        """, (id,)).fetchone()

        if subject is None:
            flash("Subject not found.", "error")
            return redirect(url_for("subjects"))

        conn.execute("""
            DELETE FROM subjects
            WHERE id = ?
        """, (id,))

        conn.commit()

        flash("Subject deleted successfully.", "success")
        return redirect(url_for("subjects"))

    except Exception:
        conn.rollback()
        app.logger.exception("Error deleting subject")
        flash("Unable to delete the subject.", "error")
        return redirect(url_for("subjects"))

    finally:
        conn.close()


# ==========================================
# EDIT SUBJECT
# ==========================================

@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):
    conn = get_db()

    try:
        subject = conn.execute("""
            SELECT *
            FROM subjects
            WHERE id = ?
        """, (id,)).fetchone()

        if subject is None:
            flash("Subject not found.", "error")
            return redirect(url_for("subjects"))

        if request.method == "POST":
            student_name = request.form.get(
                "student_name", ""
            ).strip()

            course_type = valid_course_type(
                request.form.get("course_type")
            )

            subject_name = request.form.get(
                "subject_name", ""
            ).strip()

            subject_code = request.form.get(
                "subject_code", ""
            ).strip()

            if subject_name == "Other":
                subject_name = request.form.get(
                    "custom_subject", ""
                ).strip()

            if not student_name or not course_type or not subject_name:
                flash(
                    "Please fill in all required subject details.",
                    "error"
                )
                return redirect(
                    url_for("edit_subject", id=id)
                )

            # Verify that the selected student belongs to the chosen type.
            student = conn.execute("""
                SELECT id, name
                FROM students
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                  AND UPPER(TRIM(COALESCE(course_type, 'UG'))) = ?
                ORDER BY id DESC
                LIMIT 1
            """, (student_name, course_type)).fetchone()

            if not student:
                flash(
                    "Selected student was not found for that course type.",
                    "error"
                )
                return redirect(
                    url_for("edit_subject", id=id)
                )

            conn.execute("""
                UPDATE subjects
                SET student_name = ?,
                    subject_name = ?,
                    subject_code = ?,
                    course_type = ?
                WHERE id = ?
            """, (
                student["name"],
                subject_name,
                subject_code,
                course_type,
                id
            ))

            conn.commit()

            flash("Subject updated successfully.", "success")
            return redirect(url_for("subjects"))

        # Students available in the edit form.
        students_data = conn.execute("""
            SELECT
                id,
                name,
                email,
                course,
                semester,
                UPPER(TRIM(COALESCE(course_type, 'UG'))) AS course_type,
                student_code
            FROM students
            ORDER BY name
        """).fetchall()

        # Register number for the selected subject's student.
        subject_with_student = conn.execute("""
            SELECT
                sub.*,
                s.student_code
            FROM subjects AS sub
            LEFT JOIN students AS s
                ON LOWER(TRIM(s.name)) =
                   LOWER(TRIM(sub.student_name))
               AND UPPER(TRIM(COALESCE(s.course_type, 'UG'))) =
                   UPPER(TRIM(COALESCE(sub.course_type, 'UG')))
            WHERE sub.id = ?
        """, (id,)).fetchone()

        return render_template(
            "edit_subject.html",
            subject=subject_with_student,
            students=students_data
        )

    except Exception:
        conn.rollback()
        app.logger.exception("Error editing subject")
        flash("Unable to process the subject edit.", "error")
        return redirect(url_for("subjects"))

    finally:
        conn.close()



# =====================================================
# MARKS MANAGEMENT
# =====================================================


@app.route("/marks", methods=["GET", "POST"])
def marks():
    conn = get_db()

    course_type = valid_course_type(
        request.form.get("course_type") or
        request.args.get("course_type")
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

        # Get the selected student and their existing register number.
        student = conn.execute("""
            SELECT id, name, course_type, student_code
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        if not student:
            conn.close()
            flash("Selected student was not found.", "error")
            return redirect(url_for("marks", course_type=course_type))

        # Check that the selected student belongs to the chosen UG/PG type.
        student_type = (
            (student["course_type"] or "UG").strip().upper()
        )

        if student_type != course_type:
            conn.close()
            flash(
                "The selected student does not belong to this course type.",
                "error"
            )
            return redirect(url_for("marks", course_type=course_type))

        # Subject must belong to the selected course type and student.
        subject = conn.execute("""
            SELECT id, subject_name
            FROM subjects
            WHERE id = ?
              AND UPPER(TRIM(COALESCE(course_type, ''))) = ?
              AND LOWER(TRIM(COALESCE(student_name, ''))) =
                  LOWER(TRIM(?))
        """, (
            subject_id,
            course_type,
            student["name"]
        )).fetchone()

        if not subject:
            conn.close()
            flash(
                "Select a subject assigned to this student in Subject Management.",
                "error"
            )
            return redirect(url_for("marks", course_type=course_type))

        # Prevent duplicate marks for the same student, subject and course type.
        existing = conn.execute("""
            SELECT id
            FROM marks
            WHERE LOWER(TRIM(student_name)) = LOWER(TRIM(?))
              AND LOWER(TRIM(subject_name)) = LOWER(TRIM(?))
              AND UPPER(TRIM(COALESCE(course_type, ''))) = ?
        """, (
            student["name"],
            subject["subject_name"],
            course_type
        )).fetchone()

        if existing:
            conn.close()
            flash(
                "Marks already exist for this student and subject. "
                "Use Edit to update them.",
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

        except sqlite3.Error:
            conn.rollback()
            conn.close()
            app.logger.exception("Unable to save marks")
            flash("Marks could not be saved. Please try again.", "error")
            return redirect(url_for("marks", course_type=course_type))

        conn.close()
        flash("Marks added successfully.", "success")
        return redirect(url_for("marks", course_type=course_type))

    # Load students and subjects for the selected UG/PG type.
    if course_type:
        students_data = conn.execute("""
            SELECT id, name, course_type, student_code
            FROM students
            WHERE UPPER(TRIM(COALESCE(course_type, 'UG'))) = ?
            ORDER BY name
        """, (course_type,)).fetchall()

        subjects_data = conn.execute("""
            SELECT id, subject_name, subject_code, student_name
            FROM subjects
            WHERE UPPER(TRIM(COALESCE(course_type, ''))) = ?
            ORDER BY subject_name
        """, (course_type,)).fetchall()

    else:
        students_data = []
        subjects_data = []

    # Infer the course type for older marks that have no saved course type.
    # Then match the mark to the student's existing register number.
    marks_query = """
        WITH mark_rows AS (
            SELECT
                m.id,
                m.student_name,
                m.subject_name,
                m.marks,
                m.course_type,
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
        )
        SELECT
            mr.id,
            mr.student_name,
            mr.subject_name,
            mr.marks,
            mr.course_type,
            mr.display_course_type,
            st.student_code
        FROM mark_rows mr
        LEFT JOIN students st
            ON LOWER(TRIM(st.name)) =
               LOWER(TRIM(mr.student_name))
           AND UPPER(TRIM(COALESCE(st.course_type, 'UG'))) =
               mr.display_course_type
    """

    if course_type:
        marks_data = conn.execute(
            marks_query + """
                WHERE mr.display_course_type = ?
                ORDER BY mr.id DESC
            """,
            (course_type,)
        ).fetchall()
    else:
        marks_data = conn.execute(
            marks_query + """
                ORDER BY mr.id DESC
            """
        ).fetchall()

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
        except (ValueError, TypeError):
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

        # Confirm the student exists.
        student = conn.execute("""
            SELECT id, name
            FROM students
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
            ORDER BY id DESC
            LIMIT 1
        """, (student_name,)).fetchone()

        if not student:
            conn.close()
            flash("Selected student was not found.", "error")
            return redirect(url_for("attendance"))

        # Prevent duplicate attendance for the same student and date.
        existing = conn.execute("""
            SELECT id
            FROM attendance
            WHERE LOWER(TRIM(student_name)) = LOWER(TRIM(?))
              AND date = ?
        """, (student["name"], date_value)).fetchone()

        if existing:
            conn.close()
            flash(
                "Attendance for this student and date already exists.",
                "error"
            )
            return redirect(url_for("attendance"))

        conn.execute("""
            INSERT INTO attendance (student_name, date, status)
            VALUES (?, ?, ?)
        """, (student["name"], date_value, status))

        conn.commit()
        conn.close()

        flash("Attendance added successfully.", "success")
        return redirect(url_for("attendance"))

    students_data = conn.execute("""
        SELECT id, name, student_code, course_type
        FROM students
        ORDER BY name
    """).fetchall()

    # Display the student's register number instead of attendance ID.
    attendance_data = conn.execute("""
        SELECT
            a.id,
            a.student_name,
            a.date,
            a.status,
            COALESCE(
                (
                    SELECT s.student_code
                    FROM students s
                    WHERE LOWER(TRIM(s.name)) =
                          LOWER(TRIM(a.student_name))
                    ORDER BY s.id DESC
                    LIMIT 1
                ),
                'Not assigned'
            ) AS student_code
        FROM attendance a
        ORDER BY a.id DESC
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

    conn.execute(
        "DELETE FROM attendance WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    flash("Attendance deleted successfully.", "success")
    return redirect(url_for("attendance"))


@app.route("/edit_attendance/<int:id>", methods=["GET", "POST"])
def edit_attendance(id):
    conn = get_db()
    today = date.today().isoformat()

    attendance_record = conn.execute("""
        SELECT *
        FROM attendance
        WHERE id = ?
    """, (id,)).fetchone()

    if attendance_record is None:
        conn.close()
        return "Attendance record not found", 404

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        date_value = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip().capitalize()

        try:
            selected_date = date.fromisoformat(date_value)
        except (ValueError, TypeError):
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

        student = conn.execute("""
            SELECT name
            FROM students
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
            ORDER BY id DESC
            LIMIT 1
        """, (student_name,)).fetchone()

        if not student:
            conn.close()
            flash("Selected student was not found.", "error")
            return redirect(url_for("edit_attendance", id=id))

        conn.execute("""
            UPDATE attendance
            SET student_name = ?, date = ?, status = ?
            WHERE id = ?
        """, (
            student["name"],
            date_value,
            status,
            id
        ))

        conn.commit()
        conn.close()

        flash("Attendance updated successfully.", "success")
        return redirect(url_for("attendance"))

    students_data = conn.execute("""
        SELECT id, name, student_code, course_type
        FROM students
        ORDER BY name
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

    try:
        students_data = conn.execute("""
            SELECT *
            FROM students
            ORDER BY name
        """).fetchall()

        marks_data = conn.execute("""
            SELECT *
            FROM marks
            ORDER BY id DESC
        """).fetchall()

        attendance_data = conn.execute("""
            SELECT *
            FROM attendance
            ORDER BY id DESC
        """).fetchall()

        return render_template(
            "reports.html",
            students=[dict(row) for row in students_data],
            marks_data=[dict(row) for row in marks_data],
            attendance_data=[
                dict(row) for row in attendance_data
            ]
        )

    finally:
        conn.close()



# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(debug=True)
