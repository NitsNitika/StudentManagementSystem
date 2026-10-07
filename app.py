from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

@app.route("/")
def login():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    total_students = cur.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_subjects = cur.execute(
        "SELECT COUNT(*) FROM subjects"
    ).fetchone()[0]

    attendance = cur.execute("""
        SELECT
        COUNT(*),
        SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END)
        FROM attendance
    """).fetchone()

    total_classes = attendance[0] or 0
    present_classes = attendance[1] or 0

    attendance_percentage = (
        round((present_classes / total_classes) * 100, 1)
        if total_classes > 0 else 0
    )

    avg_marks = cur.execute(
        "SELECT AVG(marks) FROM marks"
    ).fetchone()[0]

    avg_marks = round(avg_marks, 1) if avg_marks else 0

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_subjects=total_subjects,
        attendance_percentage=attendance_percentage,
        avg_marks=avg_marks
    )


@app.route("/students", methods=["GET", "POST"])
def students():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        course = request.form["course"]
        semester = request.form["semester"]

        cursor.execute(
            """
            INSERT INTO students
            (name,email,course,semester)
            VALUES (?,?,?,?)
            """,
            (name, email, course, semester)
        )

        conn.commit()

    cursor.execute("SELECT * FROM students")
    students_data = cursor.fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students_data
    )


@app.route("/delete/<int:id>")
def delete_student(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM students WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/students")
@app.route("/delete_subject/<int:id>")
def delete_subject(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM subjects WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/subjects")
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        course = request.form["course"]
        semester = request.form["semester"]

        cursor.execute(
            """
            UPDATE students
            SET name=?,
                email=?,
                course=?,
                semester=?
            WHERE id=?
            """,
            (name, email, course, semester, id)
        )

        conn.commit()
        conn.close()

        return redirect("/students")

    cursor.execute(
        "SELECT * FROM students WHERE id=?",
        (id,)
    )

    student = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_student.html",
        student=student
    )
@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        subject_name = request.form["subject_name"]
        subject_code = request.form["subject_code"]

        cursor.execute(
            """
            UPDATE subjects
            SET subject_name=?,
                subject_code=?
            WHERE id=?
            """,
            (subject_name, subject_code, id)
        )

        conn.commit()
        conn.close()

        return redirect("/subjects")

    cursor.execute(
        "SELECT * FROM subjects WHERE id=?",
        (id,)
    )

    subject = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_subject.html",
        subject=subject
    )
@app.route('/subjects', methods=['GET','POST'])
def subjects():

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    if request.method == 'POST':

        student_name = request.form['student_name']
        subject_name = request.form['subject_name']
        subject_code = request.form['subject_code']

        cur.execute("""
        INSERT INTO subjects
        (student_name, subject_name, subject_code)
        VALUES (?,?,?)
        """,
        (student_name, subject_name, subject_code))

        conn.commit()

    cur.execute("SELECT * FROM students")
    students = cur.fetchall()

    cur.execute("SELECT * FROM subjects")
    subjects = cur.fetchall()

    conn.close()

    return render_template(
        'subjects.html',
        students=students,
        subjects=subjects
    )

@app.route("/marks", methods=["GET", "POST"])
def marks():

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # Get students
    students = cur.execute(
        "SELECT name FROM students"
    ).fetchall()

    # Get subjects
    subjects = cur.execute(
        "SELECT DISTINCT subject_name FROM subjects"
    ).fetchall()

    if request.method == "POST":

        student_name = request.form["student_name"]

        subject_name = request.form["subject_name"]

        # If Other selected
        if subject_name == "Other":
            subject_name = request.form["custom_subject"]

        marks = request.form["marks"]

        cur.execute("""
            INSERT INTO marks
            (student_name, subject_name, marks)
            VALUES (?, ?, ?)
        """, (
            student_name,
            subject_name,
            marks
        ))

        conn.commit()

    marks_data = cur.execute("""
        SELECT *
        FROM marks
    """).fetchall()

    conn.close()

    return render_template(
        "marks.html",
        students=students,
        subjects=subjects,
        marks_data=marks_data
    )
@app.route("/edit_mark/<int:id>", methods=["GET", "POST"])
def edit_mark(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        student_name = request.form["student_name"]
        subject_name = request.form["subject_name"]
        marks = request.form["marks"]

        cursor.execute(
            """
            UPDATE marks
            SET student_name=?,
                subject_name=?,
                marks=?
            WHERE id=?
            """,
            (student_name, subject_name, marks, id)
        )

        conn.commit()
        conn.close()

        return redirect("/marks")

    cursor.execute(
        "SELECT * FROM marks WHERE id=?",
        (id,)
    )

    mark = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_mark.html",
        mark=mark
    )
@app.route("/delete_mark/<int:id>")
def delete_mark(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM marks WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/marks")

@app.route("/attendance", methods=["GET", "POST"])
def attendance():

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    students = cur.execute(
        "SELECT name FROM students"
    ).fetchall()

    if request.method == "POST":

        student_name = request.form["student_name"]
        date = request.form["date"]
        status = request.form["status"]

        cur.execute("""
            INSERT INTO attendance
            (student_name, date, status)
            VALUES (?, ?, ?)
        """, (student_name, date, status))

        conn.commit()

    attendance_data = cur.execute(
        "SELECT * FROM attendance"
    ).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        students=students,
        attendance_data=attendance_data
    )
@app.route("/delete_attendance/<int:id>")
def delete_attendance(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM attendance WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/attendance")
@app.route("/edit_attendance/<int:id>", methods=["GET", "POST"])
def edit_attendance(id):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        student_name = request.form["student_name"]
        date = request.form["date"]
        status = request.form["status"]

        cursor.execute(
            """
            UPDATE attendance
            SET student_name=?,
                date=?,
                status=?
            WHERE id=?
            """,
            (student_name, date, status, id)
        )

        conn.commit()
        conn.close()

        return redirect("/attendance")

    cursor.execute(
        "SELECT * FROM attendance WHERE id=?",
        (id,)
    )

    attendance = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_attendance.html",
        attendance=attendance
    )

@app.route('/performance', methods=['GET', 'POST'])
def performance():

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    students = cur.execute(
        "SELECT * FROM students"
    ).fetchall()

    performance = None

    if request.method == "POST":

        student_id = request.form['student_id']

        # Get student name
        student = cur.execute(
            "SELECT name FROM students WHERE id=?",
            (student_id,)
        ).fetchone()

        student_name = student[0]

        # Marks
        marks = cur.execute(
            """
            SELECT subject_name, marks
            FROM marks
            WHERE student_name=?
            """,
            (student_name,)
        ).fetchall()

        total = 0
        subjects = []

        for subject, mark in marks:
            total += mark

            subjects.append({
                "name": subject,
                "marks": mark
            })

        avg_marks = round(total / len(marks), 1) if marks else 0

        # Grade
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

        # Attendance
        attendance = cur.execute(
            """
            SELECT status
            FROM attendance
            WHERE student_name=?
            """,
            (student_name,)
        ).fetchall()

        total_classes = len(attendance)

        attended = len(
            [a for a in attendance if a[0] == "Present"]
        )

        missed = total_classes - attended

        attendance_percentage = round(
            (attended / total_classes) * 100, 1
        ) if total_classes > 0 else 0

        performance = {
            "student_name": student_name,
            "subjects": subjects,
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
        students=students,
        performance=performance
    )


@app.route("/reports")
def reports():
    return render_template("reports.html")


if __name__ == "__main__":
    app.run(debug=True)