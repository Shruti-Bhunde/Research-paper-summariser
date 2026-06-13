import mysql.connector
import os

def get_connection():
    if os.getenv("ENV") == "production":
        return mysql.connector.connect(
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            unix_socket=os.getenv("CLOUD_SQL_SOCKET")
        )
    else:
        # Using .get() with a default fallback "3306" ensures it is NEVER None
        db_port = os.getenv("DB_PORT", "3306")
        return mysql.connector.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=int(db_port)
        )

