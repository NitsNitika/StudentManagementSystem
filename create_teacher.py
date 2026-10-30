
import os
import sqlite3
from getpass import getpass
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

username = input("Teacher username: ").strip()
password = getpass("Teacher password: ")

if not username or not password:
    raise SystemExit("Username and password are required.")

conn = sqlite3.connect(DB_PATH)

try:
    conn.execute("""
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, 'teacher')
    """, (username, generate_password_hash(password)))

    conn.commit()
    print("Teacher account created successfully!")

except sqlite3.IntegrityError:
    print("This username already exists. Please use another username.")

finally:
    check = conn.execute("""
        SELECT id, username, role FROM users
    """).fetchall()

    print("\nRegistered teachers:")
    for teacher in check:
        print(teacher)

    conn.close()

# python create_teacher.py
