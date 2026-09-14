from pydantic import BaseModel
from fastapi import FastAPI
from database import *
import os
import psutil

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}

@app.get("/servers")
def get_servers():
    create_tables()
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM servers")
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

class ServerCreate(BaseModel):
    name: str
    hostname: str
    ssh_port: int = 22


@app.post("/servers", status_code=201)
def add_server(server: ServerCreate):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            sql = """
                INSERT INTO servers (name, hostname, ssh_port, status)
                VALUES (%s, %s, %s, %s)
            """

            values = (
                server.name,
                server.hostname,
                server.ssh_port,
                "Unknown"
            )

            cursor.execute(sql, values)
            connection.commit()

            return {
                "message": "Server added successfully!",
                "id": cursor.lastrowid
            }
        finally:
            cursor.close()
    finally:
        connection.close()


# System Health Metrics
@app.get("/health")
def get_system_health():
    cpu_percent = psutil.cpu_percent(interval=1)
    ram_percent = psutil.virtual_memory().percent
    user = psutil.users()
    username = user[0].name if user else "System"
    net_if_addrs = psutil.net_if_addrs()

    disk_path = os.path.abspath(os.sep)
    disk_percent = psutil.disk_usage(disk_path).percent

    return {
        "user": user[0].name,
        "net_if_stats": net_if_addrs,
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "disk_percent": disk_percent
    }

@app.post("/health")
def post_system_health():
    connection = get_connection()
    try:
        cursor = connection.cursor()


    except mysql.connector.Error as e:
        print(f"Error: {e}")
