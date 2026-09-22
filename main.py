from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from database import *
import os
import psutil
import asyncio

async def lifespan(app: FastAPI):
    """
    This code starts as soon as FastAPI gets booted up. This will
    create the tables for the database and 
    """

    create_tables() # Create tables on startup
    server_id = get_or_create_main_server() # "return server[0]"
    
    # TODO: Assigned as a variable for now for host server, will need to take multiple servers
    health_task = asyncio.create_task(log_health(server_id))
    yield  # FastAPI running
    
    # When app stops running, pause the logging meteric
    health_task.cancel()

# Pass the lifespan function to your FastAPI app instance
app = FastAPI(lifespan=lifespan)

app = FastAPI()


class ServerCreate(BaseModel):
    name: str
    hostname: str
    ssh_port: int = 22


# Check that the API is running
@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}


# View all saved servers
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


# Add a server
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

# Delete a server by its ID
@app.delete("/servers/{server_id}")
def delete_server(server_id: int):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM servers WHERE id = %s",
                (server_id,)
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Server not found"
                )

            connection.commit()

            return {
                "message": "Server deleted successfully!",
                "id": server_id
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
    """
    Pydantic uses a class as a way to know which variables need to be logged into
    the health meterics table.
    TODO: Add more meterics here to boost the performance of the LLM and data logged
    """
    server_id: int
    cpu_percent: float
    ram_percent: float
    disk_percent: float

@app.post("/health")
def post_system_health(log_data: HealthLogCreate):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM servers WHERE id = %s",
                (server_id,)
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Server not found"
                )

            connection.commit()

            return {
                "message": "Server deleted successfully!",
                "id": server_id
            }
        finally:
            cursor.close()
    finally:
        connection.close()


# View health readings from the computer running FastAPI
@app.get("/health")
def health():
    return get_system_health()
