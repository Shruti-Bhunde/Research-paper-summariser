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
        return mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            port=os.getenv("DB_PORT")
        )

