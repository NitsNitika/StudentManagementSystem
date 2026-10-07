import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Students Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS students(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    course TEXT,
    semester TEXT
)
""")

# Subjects Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS subjects(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT,
    subject_name TEXT,
    subject_code TEXT
)
""")

# Marks Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS marks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT,
    subject_name TEXT,
    marks INTEGER
)
""")

# Attendance Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT,
    date TEXT,
    status TEXT
)
""")

conn.commit()
conn.close()

print("Database Checked Successfully")