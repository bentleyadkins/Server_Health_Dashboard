from contextlib import asynccontextmanager, suppress
from pathlib import Path

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from auth import verify_password

from database import *
import os
import psutil
import asyncio
import mysql.connector

# IMPORTANT: replace this with your own random 64-char hex string.
# Generate one with: py -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "6a6e34449fec654e25d4e03954a4c542ff7cfe1bb592ca95a1f319de4863011b"


# Read HTML relative to main.py, regardless of the terminal directory.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def read_page(filename: str) -> str:
    return (TEMPLATES_DIR / filename).read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    This code starts as soon as FastAPI gets booted up. This will
    create the tables for the database and 
    """

    create_tables() # Create tables on startup
    server_id = get_or_create_main_server() # "return server[0]"
    
    # TODO: Assigned as a variable for now for host server, will need to take multiple servers
    health_task = asyncio.create_task(log_health(server_id))
    try:
        yield  # FastAPI running
    finally:
        health_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_task

# Pass the lifespan function to your FastAPI app instance
app = FastAPI(lifespan=lifespan)

# Creation of the Secret key 
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}

# ---------- Auth helper ----------
def require_login(request: Request):
    """Raise a redirect if the user isn't logged in. Returns the username otherwise."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ---------- Auth Routes ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return read_page("login.html").replace("%%ERROR%%", "")


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    connection = get_connection()
    user_row = None
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            user_row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if user_row and verify_password(password, user_row["password_hash"]):
        request.session["user"] = user_row["username"]
        return RedirectResponse(url="/dashboard", status_code=302)

    error_html = (
        '<div class="alert alert-danger mb-3">'
        '<i class="fas fa-exclamation-triangle me-2"></i>'
        "Invalid username or password."
        "</div>"
    )
    return HTMLResponse(read_page("login.html").replace("%%ERROR%%", error_html), status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

class ServerCreate(BaseModel):
    name: str
    hostname: str
    ssh_port: int = 22

@app.post("/servers", status_code=201)
def add_server(request: Request, server: ServerCreate):
    require_login(request)

    if len(server.name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Name must be at least 3 characters.")
    if not server.hostname.strip():
        raise HTTPException(status_code=400, detail="Hostname is required.")
    if not (1 <= server.ssh_port <= 65535):
        raise HTTPException(status_code=400, detail="SSH port must be between 1 and 65535.")

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        sql = """
            INSERT INTO servers (NAME, hostname, ssh_port)
            VALUES (%s, %s, %s)
        """
        values = (server.name, server.hostname, server.ssh_port)
        cursor.execute(sql, values)
        connection.commit()
        return {"message": "Server added successfully!", "id": cursor.lastrowid}
    except mysql.connector.Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err.msg}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

@app.put("/servers/{server_id}")
def edit_server(server_id: int, request: Request, server: ServerCreate):
    """Edit a saved server while keeping its ID and health history."""
    require_login(request)

    if len(server.name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Name must be at least 3 characters.")
    if not server.hostname.strip():
        raise HTTPException(status_code=400, detail="Hostname is required.")
    if not (1 <= server.ssh_port <= 65535):
        raise HTTPException(status_code=400, detail="SSH port must be between 1 and 65535.")

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        # An unchanged record should also count as a successful edit.
        cursor.execute("SELECT id FROM servers WHERE id = %s FOR UPDATE", (server_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Server not found.")
        cursor.execute(
            "UPDATE servers SET NAME = %s, hostname = %s, ssh_port = %s WHERE id = %s",
            (server.name, server.hostname, server.ssh_port, server_id),
        )
        connection.commit()
        return {"message": "Server updated successfully!", "id": server_id}
    except mysql.connector.Error as db_err:
        if connection is not None:
            connection.rollback()
        raise HTTPException(status_code=500, detail="Failed to update server.") from db_err
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.get("/servers")
def get_servers(request: Request):
    """Fetch all registered servers for the dashboard."""
    require_login(request)
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, hostname, ssh_port FROM servers")
        servers = cursor.fetchall()
        for server in servers:
            if "status" not in server or not server["status"]:
                server["status"] = "online"
        return servers
    except mysql.connector.Error as db_err:
        raise HTTPException(
            status_code=500, detail=f"Database error: {db_err.msg}"
        )
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
            
# @app.post("/servers", status_code=201)
# def add_server(server: ServerCreate):
#     connection = get_connection()
#     try:
#         cursor = connection.cursor()
#         try:
#             sql = """
#                 INSERT INTO servers (name, hostname, ssh_port)
#                 VALUES (%s, %s, %s)
#             """

#             values = (
#                 server.name,
#                 server.hostname,
#                 server.ssh_port,
#             )

#             cursor.execute(sql, values)
#             connection.commit()

#             return {
#                 "message": "Server added successfully!",
#                 "id": cursor.lastrowid
#             }
#         finally:
#             cursor.close()
#     finally:
#         connection.close()

@app.delete("/servers/{server_id}")
def delete_server(server_id: int, request: Request):
    require_login(request)

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM servers WHERE id = %s", (server_id,))
        connection.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Server not found.")

        return {"message": f"Server {server_id} deleted."}
    except mysql.connector.Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err.msg}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
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

async def log_health(server_id: int):
    """Background task logging server health metrics every 5 seconds."""
    while True:
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk_path = os.path.abspath(os.sep)
            disk = psutil.disk_usage(disk_path).percent

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

        await asyncio.sleep(5)


# ---------- Protected Dashboard Page ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=302)
    return read_page("dashboard.html")
