import mysql.connector
import os

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )

# def create_user(user):
#     conn = get_connection()
#     cursor = conn.cursor()

#     cursor.execute("""
#         INSERT IGNORE INTO users
#         (google_sub,email,name,picture)
#         VALUES (%s,%s,%s,%s)
#     """,(
#         user["sub"],
#         user["email"],
#         user["name"],
#         user["picture"]
#     ))

#     conn.commit()
#     conn.close()

# def get_user_papers(google_sub):
#     conn = get_connection()
#     cursor = conn.cursor(dictionary=True)

#     cursor.execute("""
#         SELECT *
#         FROM papers
#         WHERE google_sub=%s
#         ORDER BY updated_at DESC
#     """,(google_sub,))

#     rows = cursor.fetchall()

#     conn.close()

#     return rows


# from dotenv import load_dotenv
# from pathlib import Path
# import os
# # database.py

# import mysql.connector

# env_path = Path(__file__).resolve().parent / ".env"

# print("Looking for:", env_path)
# print("Exists:", env_path.exists())

# load_dotenv(dotenv_path=env_path)

# print("HOST =", os.getenv("MYSQL_HOST"))
# print("USER =", os.getenv("MYSQL_USER"))
# print("DATABASE =", os.getenv("MYSQL_DATABASE"))