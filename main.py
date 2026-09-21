from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database import get_connection
import mysql.connector

app = FastAPI()

# ---------- HTML Template for the Dashboard ----------
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
    </style>
</head>
<body>

    <nav class="navbar navbar-dark bg-dark">
        <div class="container-fluid">
            <span class="navbar-brand"><i class="fas fa-server me-2"></i>Home Server Health</span>
            <span class="navbar-text text-light" id="live-status"><i class="fas fa-circle text-success"></i> Live</span>
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

    <!-- Floating Add Button (opens modal) -->
    <button class="btn btn-primary btn-lg rounded-circle add-btn" data-bs-toggle="modal" data-bs-target="#addServerModal">
        <i class="fas fa-plus"></i>
    </button>

    <!-- Add Server Modal -->
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
        // ----- Helper: Generate mock metrics (replace later with real SSH data) -----
        function generateMetrics() {
            return {
                cpu: Math.round(Math.random() * 100),
                ram: Math.round(Math.random() * 100),
                disk: Math.round(Math.random() * 100)
            };
        }

        // ----- Thresholds (from sprint plan) -----
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

        // ----- Load and render servers -----
        async function loadDashboard() {
            try {
                const response = await fetch('/servers');
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
                                <div class="card-header d-flex justify-content-between">
                                    <span><i class="fas fa-hdd me-2"></i>${server.name}</span>
                                    <span class="badge ${isOnline ? 'bg-success' : 'bg-danger'} status-badge">${statusBadge.toUpperCase()}</span>
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

                // Global alert summary
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

        // ----- Add Server via Modal (uses your existing POST /servers) -----
        document.getElementById('addServerForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const name = document.getElementById('inputName').value.trim();
            const hostname = document.getElementById('inputHostname').value.trim();
            const ssh_port = parseInt(document.getElementById('inputPort').value) || 22;

            const feedback = document.getElementById('formFeedback');
            feedback.innerHTML = '';

            // Validate (simple frontend check)
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

                // Read as text first, then try to parse as JSON.
                // This prevents the "Unexpected token 'I'" error when the
                // backend returns a plain-text 500 page instead of JSON.
                const raw = await response.text();
                let result;
                try {
                    result = JSON.parse(raw);
                } catch {
                    result = { detail: raw.slice(0, 300) || 'Server returned a non-JSON response.' };
                }

                if (response.ok) {
                    feedback.innerHTML = '<div class="text-success">Server added successfully!</div>';
                    // Close modal after short delay
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('addServerModal'));
                        modal.hide();
                        loadDashboard(); // refresh
                    }, 1000);
                } else {
                    feedback.innerHTML = `<div class="text-danger">Error ${response.status}: ${result.detail || 'Unknown error'}</div>`;
                }
            } catch (err) {
                feedback.innerHTML = `<div class="text-danger">Network error: ${err.message}</div>`;
            }
        });

        // Load on page load
        document.addEventListener('DOMContentLoaded', loadDashboard);
    </script>
</body>
</html>
"""

# ---------- Existing API Endpoints ----------
@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}

@app.get("/servers")
def get_servers():
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            # Aliases make the JSON keys lowercase so they match what
            # the dashboard JavaScript expects (server.name, server.status).
            cursor.execute("""
                SELECT
                    id,
                    NAME       AS name,
                    hostname,
                    ssh_port,
                    os_type,
                    os_version,
                    STATUS     AS status
                FROM servers
            """)
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
    # Backend validation (mirrors the frontend checks)
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
        # Column names must match the MySQL schema (NAME / STATUS uppercase).
        sql = """
            INSERT INTO servers (NAME, hostname, ssh_port, STATUS)
            VALUES (%s, %s, %s, %s)
        """
        values = (server.name, server.hostname, server.ssh_port, "Unknown")
        cursor.execute(sql, values)
        connection.commit()
        return {
            "message": "Server added successfully!",
            "id": cursor.lastrowid
        }

    except mysql.connector.Error as db_err:
        # Return the real MySQL error as JSON so the frontend can display it
        raise HTTPException(status_code=500, detail=f"Database error: {db_err.msg}")

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

# ---------- Dashboard Frontend Endpoint ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return HTML_TEMPLATE
