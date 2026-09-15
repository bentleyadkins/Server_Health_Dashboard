from pydantic import BaseModel
from fastapi import FastAPI
from database import *
import os
import psutil
import asyncio

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}

@app.get("/servers")
def get_servers():
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


@app.get("/health")
def get_system_health():
    cpu_percent = psutil.cpu_percent(interval=1)
    ram_percent = psutil.virtual_memory().percent
    user = psutil.users()
    net_if_addrs = psutil.net_if_addrs()
    disk_path = os.path.abspath(os.sep)
    disk_percent = psutil.disk_usage(disk_path).percent

    return {
        "user": user[0].name if user else "System",
        "net_if_stats": net_if_addrs,
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "disk_percent": disk_percent
    }

# --- 1. Completed POST Endpoint ---
class HealthLogCreate(BaseModel):
    server_id: int
    cpu_percent: float
    ram_percent: float
    disk_percent: float

@app.post("/health")
def post_system_health(log_data: HealthLogCreate):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        sql = """
            INSERT INTO server_health_log (server_id, cpu_percent, ram_percent, disk_percent)
            VALUES (%s, %s, %s, %s)
        """
        values = (log_data.server_id, log_data.cpu_percent, log_data.ram_percent, log_data.disk_percent)
        cursor.execute(sql, values)
        connection.commit()
        return {"message": "Health metrics saved"}
    except mysql.connector.Error as e:
        print(f"Error: {e}")
        return {"error": "Failed to log health data"}
    finally:
        if 'cursor' in locals():
            cursor.close()
        connection.close()

# --- 2. The 5-Second Background Loop ---
async def log_health(server_id: int):
    """Runs in the background, logging laptop stats every 5 seconds."""
    while True:
        try:
            # Gather laptop stats
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk_path = os.path.abspath(os.sep)
            disk = psutil.disk_usage(disk_path).percent
            
            # Insert directly into DB (Assuming your laptop is server_id = 1)
            connection = get_connection()
            cursor = connection.cursor()
            
            sql = """
                INSERT INTO server_health_log (server_id, cpu_percent, ram_percent, disk_percent)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (server_id, cpu, ram, disk))
            connection.commit()
            
            cursor.close()
            connection.close()
            print(f"Server ID: {server_id}, CPU {cpu}%, RAM {ram}%")
            
        except Exception as e:
            print(f"Background logging error: {e}")
            
        # Wait 5 seconds without blocking FastAPI
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    """Starts the background task when FastAPI boots up."""
    create_tables()
    laptop_server_id = get_or_create_main_server()
    asyncio.create_task(log_health(laptop_server_id))