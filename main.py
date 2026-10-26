from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from auth import verify_password


from database import *
import os
from fastapi import Form
import psutil
from ssh_monitor import get_remote_health, SSHMonitorError
import asyncio
from login import router as login_router
import mysql.connector

# IMPORTANT: replace this with your own random 64-char hex string.
# Generate one with: py -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "6a6e34449fec654e25d4e03954a4c542ff7cfe1bb592ca95a1f319de4863011b"


# ---------- HTML Template: Login Page ----------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Health Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            max-width: 400px;
            width: 100%;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            border: none;
        }
        .login-logo {
            font-size: 2.5rem;
            color: #0d6efd;
        }
    </style>
</head>
<body>
    <div class="login-card card p-4">
        <div class="text-center mb-3">
            <i class="fas fa-server login-logo"></i>
            <h4 class="mt-2 mb-0">Home Server Health</h4>
            <p class="text-muted small">Sign in to continue</p>
        </div>
        %%ERROR%%
        <form method="POST" action="/login">
            <div class="mb-3">
                <label class="form-label">Username</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="fas fa-user"></i></span>
                    <input type="text" class="form-control" name="username" required autofocus>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Password</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="fas fa-lock"></i></span>
                    <input type="password" class="form-control" name="password" required>
                </div>
            </div>
            <button type="submit" class="btn btn-primary w-100">
                <i class="fas fa-sign-in-alt me-2"></i>Sign In
            </button>
        </form>
    </div>
</body>
</html>
"""


# ---------- HTML Template: Dashboard ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Health Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: #f4f6f9; }
        .card { border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .metric-value { font-size: 1.6rem; font-weight: bold; }
        .progress { height: 8px; }
        .offline-card { opacity: 0.6; }
        .status-badge { font-size: 0.75rem; }
        .add-btn { position: fixed; bottom: 30px; right: 30px; z-index: 1000; }
        .alert-box { padding: 8px 12px; border-radius: 6px; }
        .delete-btn { padding: 2px 8px; font-size: 0.75rem; }
    </style>
</head>
<body>

    <nav class="navbar navbar-dark bg-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><i class="fas fa-server me-2"></i>Home Server Health</span>
            <div class="d-flex align-items-center gap-2">
                <span class="navbar-text text-light small">
                    <i class="fas fa-circle text-success me-1"></i>Live
                </span>
                <form method="POST" action="/logout" class="d-inline mb-0">
                    <button type="submit" class="btn btn-outline-light btn-sm">
                        <i class="fas fa-sign-out-alt me-1"></i>Logout
                    </button>
                </form>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div id="global-alerts" class="mb-3"></div>
        <div class="row" id="server-grid">
            <div class="col-12 text-center text-muted">
                <i class="fas fa-spinner fa-spin fa-2x"></i><br>Loading servers...
            </div>
        </div>
    </div>

    <button class="btn btn-primary btn-lg rounded-circle add-btn" data-bs-toggle="modal" data-bs-target="#addServerModal">
        <i class="fas fa-plus"></i>
    </button>

    <div class="modal fade" id="addServerModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header bg-primary text-white">
                    <h5><i class="fas fa-plus-circle me-2"></i>Add New Server</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="addServerForm">
                        <div class="mb-3">
                            <label class="form-label">Server Name *</label>
                            <input type="text" class="form-control" id="inputName" required minlength="3">
                            <div class="invalid-feedback">Name must be at least 3 characters.</div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Hostname / IP *</label>
                            <input type="text" class="form-control" id="inputHostname" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">SSH Port</label>
                            <input type="number" class="form-control" id="inputPort" value="22" min="1" max="65535">
                        </div>
                        <button type="submit" class="btn btn-primary" id="submitServerBtn">Add Server</button>
                    </form>
                    <div id="formFeedback" class="mt-2"></div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function generateMetrics() {
            return {
                cpu: Math.round(Math.random() * 100),
                ram: Math.round(Math.random() * 100),
                disk: Math.round(Math.random() * 100)
            };
        }

        const THRESHOLDS = {
            cpu_warning: 80,
            cpu_critical: 95,
            ram_warning: 85,
            ram_critical: 95,
            disk_warning: 80,
            disk_critical: 90
        };

        function checkMetrics(cpu, ram, disk) {
            let alerts = [];
            if (cpu >= THRESHOLDS.cpu_critical) alerts.push(`CRITICAL: CPU ${cpu}%`);
            else if (cpu >= THRESHOLDS.cpu_warning) alerts.push(`WARNING: CPU ${cpu}%`);
            if (ram >= THRESHOLDS.ram_critical) alerts.push(`CRITICAL: RAM ${ram}%`);
            else if (ram >= THRESHOLDS.ram_warning) alerts.push(`WARNING: RAM ${ram}%`);
            if (disk >= THRESHOLDS.disk_critical) alerts.push(`CRITICAL: Disk ${disk}%`);
            else if (disk >= THRESHOLDS.disk_warning) alerts.push(`WARNING: Disk ${disk}%`);
            return alerts;
        }

        async function loadDashboard() {
            try {
                const response = await fetch('/servers');
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                if (!response.ok) throw new Error('Failed to fetch servers');
                const servers = await response.json();

                const grid = document.getElementById('server-grid');
                if (!servers || servers.length === 0) {
                    grid.innerHTML = `<div class="col-12 text-center text-muted">No servers registered. Click the + button to add one.</div>`;
                    document.getElementById('global-alerts').innerHTML =
                        `<div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>No servers registered yet.</div>`;
                    return;
                }

                let cardsHtml = '';
                let allAlerts = [];

                servers.forEach(server => {
                    const metrics = generateMetrics();
                    const alerts = checkMetrics(metrics.cpu, metrics.ram, metrics.disk);
                    if (alerts.length > 0) allAlerts.push(...alerts);

                    const statusClass = server.status && server.status.toLowerCase() === 'offline' ? 'offline-card' : '';
                    const statusBadge = server.status || 'Unknown';
                    const isOnline = statusBadge.toLowerCase() === 'online';

                    cardsHtml += `
                        <div class="col-md-4 mb-3">
                            <div class="card ${statusClass}">
                                <div class="card-header d-flex justify-content-between align-items-center">
                                    <span><i class="fas fa-hdd me-2"></i>${server.name}</span>
                                    <div class="d-flex align-items-center gap-2">
                                        <span class="badge ${isOnline ? 'bg-success' : 'bg-danger'} status-badge">${statusBadge.toUpperCase()}</span>
                                        <button class="btn btn-outline-danger delete-btn"
                                                data-id="${server.id}"
                                                data-name="${server.name}"
                                                title="Delete server">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="card-body">
                                    <p><i class="fas fa-microchip"></i> ${server.hostname} (port ${server.ssh_port})</p>
                                    <div class="row text-center">
                                        <div class="col-4">
                                            <div class="metric-value">${metrics.cpu}%</div>
                                            <div>CPU</div>
                                            <div class="progress"><div class="progress-bar ${metrics.cpu >= THRESHOLDS.cpu_warning ? 'bg-warning' : ''} ${metrics.cpu >= THRESHOLDS.cpu_critical ? 'bg-danger' : ''}" style="width:${metrics.cpu}%"></div></div>
                                        </div>
                                        <div class="col-4">
                                            <div class="metric-value">${metrics.ram}%</div>
                                            <div>RAM</div>
                                            <div class="progress"><div class="progress-bar ${metrics.ram >= THRESHOLDS.ram_warning ? 'bg-warning' : ''} ${metrics.ram >= THRESHOLDS.ram_critical ? 'bg-danger' : ''}" style="width:${metrics.ram}%"></div></div>
                                        </div>
                                        <div class="col-4">
                                            <div class="metric-value">${metrics.disk}%</div>
                                            <div>Disk</div>
                                            <div class="progress"><div class="progress-bar ${metrics.disk >= THRESHOLDS.disk_warning ? 'bg-warning' : ''} ${metrics.disk >= THRESHOLDS.disk_critical ? 'bg-danger' : ''}" style="width:${metrics.disk}%"></div></div>
                                        </div>
                                    </div>
                                    <div class="mt-2">
                                        ${alerts.length ? `<div class="alert alert-danger alert-box py-1"><i class="fas fa-exclamation-triangle me-1"></i>${alerts.join('; ')}</div>` : `<span class="text-success"><i class="fas fa-check-circle"></i> No alerts</span>`}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });

                grid.innerHTML = cardsHtml;

                const globalDiv = document.getElementById('global-alerts');
                if (allAlerts.length) {
                    globalDiv.innerHTML = `<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2"></i>${allAlerts.length} alert(s) detected.</div>`;
                } else {
                    globalDiv.innerHTML = `<div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>All systems healthy.</div>`;
                }
            } catch (error) {
                document.getElementById('server-grid').innerHTML = `<div class="col-12 text-center text-danger">Failed to load servers: ${error.message}</div>`;
            }
        }

        document.getElementById('addServerForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const name = document.getElementById('inputName').value.trim();
            const hostname = document.getElementById('inputHostname').value.trim();
            const ssh_port = parseInt(document.getElementById('inputPort').value) || 22;

            const feedback = document.getElementById('formFeedback');
            feedback.innerHTML = '';

            if (name.length < 3) {
                feedback.innerHTML = '<div class="text-danger">Name must be at least 3 characters.</div>';
                return;
            }
            if (!hostname) {
                feedback.innerHTML = '<div class="text-danger">Hostname is required.</div>';
                return;
            }

            try {
                const response = await fetch('/servers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, hostname, ssh_port })
                });

                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                const raw = await response.text();
                let result;
                try {
                    result = JSON.parse(raw);
                } catch {
                    result = { detail: raw.slice(0, 300) || 'Server returned a non-JSON response.' };
                }

                if (response.ok) {
                    feedback.innerHTML = '<div class="text-success">Server added successfully!</div>';
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('addServerModal'));
                        modal.hide();
                        loadDashboard();
                    }, 1000);
                } else {
                    feedback.innerHTML = `<div class="text-danger">Error ${response.status}: ${result.detail || 'Unknown error'}</div>`;
                }
            } catch (err) {
                feedback.innerHTML = `<div class="text-danger">Network error: ${err.message}</div>`;
            }
        });

        // ----- Delete server handler (event delegation) -----
        document.addEventListener('click', async function(e) {
            const btn = e.target.closest('.delete-btn');
            if (!btn) return;

            const id = btn.dataset.id;
            const name = btn.dataset.name;

            if (!confirm(`Delete server "${name}"? This cannot be undone.`)) {
                return;
            }

            try {
                const response = await fetch(`/servers/${id}`, { method: 'DELETE' });

                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                const raw = await response.text();
                let result;
                try {
                    result = JSON.parse(raw);
                } catch {
                    result = { detail: raw.slice(0, 300) || 'Server returned a non-JSON response.' };
                }

                if (response.ok) {
                    loadDashboard();
                } else {
                    alert(`Error ${response.status}: ${result.detail || 'Unknown error'}`);
                }
            } catch (err) {
                alert(`Network error: ${err.message}`);
            }
        });

        document.addEventListener('DOMContentLoaded', loadDashboard);
    </script>
</body>
</html>
"""


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
#app.include_router(login_router)

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
    return LOGIN_TEMPLATE.replace("%%ERROR%%", "")


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    connection = get_connection()
    user_row = None
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, username, password_hash, salt FROM users WHERE username = %s",
                (username,),
            )
            user_row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if user_row and verify_password(
    password,
    user_row["salt"],
    user_row["password_hash"]
    ):
        request.session["user"] = user_row["username"]
        return RedirectResponse(url="/dashboard", status_code=303)

    error_html = (
        '<div class="alert alert-danger mb-3">'
        '<i class="fas fa-exclamation-triangle me-2"></i>'
        "Invalid username or password."
        "</div>"
    )
    return HTMLResponse(LOGIN_TEMPLATE.replace("%%ERROR%%", error_html), status_code=401)


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

@app.get("/remote-health")
def get_remote_system_health(request: Request):
    require_login(request)

    hostname = os.environ.get("SSH_HOST")
    username = os.environ.get("SSH_USER")
    port = int(os.environ.get("SSH_PORT", "22"))

    if not hostname or not username:
        raise HTTPException(
            status_code=500,
            detail="SSH_HOST and SSH_USER are not configured"
        )

    try:
        return get_remote_health(
            hostname=hostname,
            username=username,
            port=port
        )
    except SSHMonitorError as e:
        print(f"Remote monitoring error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Unable to collect remote server metrics"
        )

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
    return HTML_TEMPLATE
