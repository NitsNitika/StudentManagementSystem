"""
Database Management add-on for SSMS.

Displays Students, Subjects, Marks, Attendance
and registered Teachers from the existing database.
"""

import os
import sqlite3

from flask import Blueprint, current_app, render_template, request


database_management_bp = Blueprint(
    "database_management",
    __name__,
    template_folder="templates_database",
    url_prefix="/database"
)


def get_database_connection():
    """Connect to the existing project's SQLite database."""

    database_path = current_app.config.get(
        "DATABASE",
        os.path.join(current_app.root_path, "database.db")
    )

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    return connection


@database_management_bp.route("/", methods=["GET"])
def database_management():

    active_table = request.args.get(
        "table", "students"
    ).strip().lower()

    allowed_tables = {
        "students",
        "subjects",
        "marks",
        "attendance",
        "teachers"
    }

    if active_table not in allowed_tables:
        active_table = "students"

    search_term = request.args.get("q", "").strip()
    search_pattern = f"%{search_term}%"

    queries = {

        "students": """
            SELECT
                id,
                student_code,
                name,
                email,
                course,
                semester,
                course_type
            FROM students
            WHERE CAST(id AS TEXT) LIKE ?
               OR COALESCE(student_code, '') LIKE ?
               OR COALESCE(name, '') LIKE ?
               OR COALESCE(email, '') LIKE ?
               OR COALESCE(course, '') LIKE ?
               OR COALESCE(semester, '') LIKE ?
               OR COALESCE(course_type, '') LIKE ?
            ORDER BY id DESC
        """,

        "subjects": """
            SELECT
                id,
                student_name,
                subject_name,
                subject_code,
                course_type
            FROM subjects
            WHERE CAST(id AS TEXT) LIKE ?
               OR COALESCE(student_name, '') LIKE ?
               OR COALESCE(subject_name, '') LIKE ?
               OR COALESCE(subject_code, '') LIKE ?
               OR COALESCE(course_type, '') LIKE ?
            ORDER BY id DESC
        """,

        "marks": """
            SELECT
                id,
                student_name,
                subject_name,
                marks,
                course_type
            FROM marks
            WHERE CAST(id AS TEXT) LIKE ?
               OR COALESCE(student_name, '') LIKE ?
               OR COALESCE(subject_name, '') LIKE ?
               OR CAST(COALESCE(marks, '') AS TEXT) LIKE ?
               OR COALESCE(course_type, '') LIKE ?
            ORDER BY id DESC
        """,

        "attendance": """
            SELECT
                id,
                student_name,
                date,
                status
            FROM attendance
            WHERE CAST(id AS TEXT) LIKE ?
               OR COALESCE(student_name, '') LIKE ?
               OR COALESCE(date, '') LIKE ?
               OR COALESCE(status, '') LIKE ?
            ORDER BY id DESC
        """,

        "teachers": """
            SELECT
                id,
                username,
                role
            FROM users
            WHERE CAST(id AS TEXT) LIKE ?
               OR COALESCE(username, '') LIKE ?
               OR COALESCE(role, '') LIKE ?
            ORDER BY id DESC
        """
    }

    parameter_counts = {
        "students": 7,
        "subjects": 5,
        "marks": 5,
        "attendance": 4,
        "teachers": 3
    }

    connection = get_database_connection()

    try:

        # Count records from all five tables.

        counts = {}

        table_mapping = {
            "students": "students",
            "subjects": "subjects",
            "marks": "marks",
            "attendance": "attendance",
            "teachers": "users"
        }

        for display_name, table_name in table_mapping.items():

            counts[display_name] = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]

        # Fetch records from the selected table.

        sql = queries[active_table]

        parameters = [
            search_pattern
        ] * parameter_counts[active_table]

        records = connection.execute(
            sql,
            parameters
        ).fetchall()

        return render_template(
            "database.html",
            active_table=active_table,
            records=records,
            counts=counts,
            search_term=search_term
        )

    except sqlite3.Error:

        current_app.logger.exception(
            "Database Management page could not load."
        )

        return (
            "Unable to read the existing database. "
            "Check that the required database tables exist. "
            "Check the application terminal for details.",
            500
        )

    finally:
        connection.close()