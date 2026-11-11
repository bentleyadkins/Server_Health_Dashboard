import asyncio
import os
import psutil
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from auth import verify_password
from database import *
from ssh_monitor import get_remote_health, SSHMonitorError

# IMPORTANT: replace this with your own random 64-char hex string.
# Generate one with: py -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "6a6e34449fec654e25d4e03954a4c542ff7cfe1bb592ca95a1f319de4863011b"



# --- NOTIFICATION SETTINGS ---
# In the future, these should be saved in your database so they persist on restart!
# For now, we store them in memory.
SETTINGS = {
    "notification_email": "admin@example.com",
    "smtp_user": "your_email@gmail.com",
    "smtp_password": "your_app_password"  # Use a Gmail App Password, not your real password
}

# ---------- HTML Template: Login Page ----------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - HiveMind Metrics</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="icon" type="image/png" href="/static/egg_logo.png">
    <style>
        body {
            background: linear-gradient(135deg, #1a0b2e 0%, #0f172a 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-family: 'Inter', sans-serif;
        }
        .login-card {
            max-width: 450px;
            width: 100%;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.6);
            padding: 3rem 2.5rem;
        }
        .brand-title { font-family: serif; font-weight: 700; letter-spacing: 2px; }
        .tagline { color: #a78bfa; letter-spacing: 5px; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 2rem; }
        .form-control {
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            color: #ffffff !important;
        }
        .form-control::placeholder { color: #64748b; }
        .form-control:focus {
            background: rgba(0,0,0,0.5);
            color: #fff;
            border-color: #a78bfa;
            box-shadow: 0 0 0 0.25rem rgba(167, 139, 250, 0.25);
        }
        .btn-primary {
            background: #a78bfa;
            border: none;
            color: #1a0b2e;
            font-weight: 600;
            padding: 0.6rem;
        }
        .btn-primary:hover { background: #c4b5fd; color: #1a0b2e; }
        .form-label { color: #e2e8f0 !important; }
        .text-muted { color: #cbd5e1 !important; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="text-center mb-4">
            <img src="/static/egg_logo.png" alt="HiveMind Logo" style="width: 140px; height: 140px; border-radius: 50%; object-fit: cover; border: 2px solid #a78bfa; box-shadow: 0 0 20px rgba(167, 139, 250, 0.5); margin-bottom: 15px;">
            <h2 class="brand-title">HIVE MIND</h2>
            <p class="tagline">Metrics</p>
        </div>

        <p class="text-center text-muted small mb-4">Helping all of your servers think alike.</p>

        %%ERROR%%

        <form method="POST" action="/login">
            <div class="mb-3">
                <label class="form-label small text-muted">Username</label>
                <input type="text" class="form-control" name="username" required autofocus>
            </div>
            <div class="mb-4">
                <label class="form-label small text-muted">Password</label>
                <input type="password" class="form-control" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary w-100 rounded-3">Sign in</button>
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
    <title>Dashboard - HiveMind Metrics</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="icon" type="image/png" href="/static/egg_logo.png">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {
            --bg-main: #0f172a;
            --bg-sidebar: #1e1b4b;
            --accent: #a855f7;
            --accent-hover: #c084fc;
            --teal: #2dd4bf;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body { background: var(--bg-main); color: var(--text-main); font-family: 'Inter', sans-serif; overflow-x: hidden; }

        /* Sidebar Layout with Background Image */
        .sidebar {
            width: 260px;
            height: 100vh;
            position: fixed;
            top: 0; left: 0;
            background: linear-gradient(180deg, rgba(26, 11, 46, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%), url('/static/egg_logo.png') center top / cover no-repeat;
            border-right: 1px solid rgba(255,255,255,0.05);
            padding-top: 30px;
            z-index: 1000;
        }
        .sidebar-brand {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 0 20px 20px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05); 
            margin-bottom: 20px;
            color: #fff; 
        }
        .nav-link {
            color: var(--text-muted); padding: 12px 20px; font-weight: 500;
            transition: all 0.2s; margin: 4px 15px; border-radius: 8px;
        }
        .nav-link:hover { color: #fff; background: rgba(255,255,255,0.05); }
        .nav-link.active { color: #fff; background: var(--accent); box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4); }

        /* Main Content */
        .main-content { margin-left: 260px; padding: 30px; transition: 0.3s; }

        /* Top Status Bar Pills */
        .status-pill {
            background: transparent; border-radius: 50px; padding: 8px 20px;
            font-size: 0.85rem; font-weight: 600; border: 1px solid;
        }
        .pill-online { border-color: var(--teal); color: var(--teal); }
        .pill-warning { border-color: #f59e0b; color: #f59e0b; }
        .pill-updated { border-color: rgba(255,255,255,0.1); color: var(--text-muted); }

        /* Cards */
        .card {
            background: var(--card-bg); border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px; color: var(--text-main); margin-bottom: 20px;
        }
        .server-card-critical { border-left: 4px solid #ef4444; }
        .server-card-warning { border-left: 4px solid #f59e0b; }
        .server-card-healthy { border-left: 4px solid var(--teal); }

        .card-header { border-bottom: 1px solid rgba(255,255,255,0.05); background: transparent; }
        .metric-value { font-size: 1.8rem; font-weight: 700; color: #fff; }
        .metric-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
        .progress { height: 6px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-top: 8px; }
        .progress-bar { border-radius: 4px; }

        /* Buttons */
        .btn-primary { background: var(--accent); border: none; color: #fff; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-teal { background: var(--teal); border: none; color: #0f172a; font-weight: 600; }
        .btn-teal:hover { background: #5eead4; }
        .add-btn { position: fixed; bottom: 30px; right: 30px; z-index: 1000; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4); }

        /* Modals & Forms */
        .modal-content { background: var(--card-bg); color: #fff; border: 1px solid rgba(255,255,255,0.1); }
        .modal-header { border-bottom: 1px solid rgba(255,255,255,0.05); }
        .modal-footer { border-top: 1px solid rgba(255,255,255,0.05); }
        .form-control, .form-select { background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); color: #fff; }
        .form-control:focus { background: rgba(0,0,0,0.3); color: #fff; border-color: var(--accent); box-shadow: none; }
        .modal .form-label { color: #e2e8f0 !important; font-weight: 500; }
        .form-control::placeholder { color: #94a3b8; opacity: 1; }

        /* Admin Tabs */
        .admin-tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .admin-tab { background: transparent; border: 1px solid rgba(255,255,255,0.1); color: var(--text-muted); border-radius: 20px; padding: 8px 20px; font-size: 0.9rem; cursor: pointer; }
        .admin-tab.active { border-color: var(--teal); color: var(--teal); }
    </style>
</head>
<body>

    <!-- Sidebar -->
    <div class="sidebar">
        <div class="sidebar-brand">
            <img src="/static/egg_logo.png" alt="HiveMind Logo" style="width: 110px; height: 110px; border-radius: 50%; object-fit: cover; border: 2px solid var(--accent); box-shadow: 0 0 20px rgba(168, 85, 247, 0.5); margin-bottom: 15px;">
            <h3 style="font-family: serif; font-size: 1.3rem; letter-spacing: 1px; margin-bottom: 0;">HIVE MIND</h3>
            <p style="font-size: 0.6rem; letter-spacing: 4px; color: var(--text-muted); text-transform: uppercase;">Metrics</p>
        </div>
        <nav class="nav flex-column">
            <a class="nav-link active" href="#" id="nav-dashboard" onclick="showView('dashboard')"><i class="fas fa-th-large me-2"></i> Dashboard</a>
            <a class="nav-link" href="#" id="nav-admin" onclick="showView('admin')"><i class="fas fa-user-cog me-2"></i> Admin</a>
            <a class="nav-link mt-4 text-danger" href="#" onclick="document.getElementById('logoutForm').submit()"><i class="fas fa-sign-out-alt me-2"></i> Log out</a>
        </nav>
        <form id="logoutForm" method="POST" action="/logout" class="d-none"></form>
    </div>

    <!-- Main Content Area -->
    <div class="main-content">

        <!-- DASHBOARD VIEW -->
        <div id="view-dashboard">
            <h3 class="mb-4 fw-bold">Overview</h3>

            <!-- Top Status Pills -->
            <div class="d-flex gap-3 mb-4">
                <div class="status-pill pill-online">
                    <span id="stat-online">Loading...</span>
                </div>
                <div class="status-pill pill-warning">
                    <span id="stat-warning">Loading...</span>
                </div>
                <div class="status-pill pill-updated">
                    <span id="stat-updated">Updated just now <i class="fas fa-sync-alt ms-1"></i></span>
                </div>
            </div>

            <div class="row">
                <div class="col-lg-12">
                    <div class="row" id="server-grid">
                        <div class="col-12 text-center text-muted py-5">
                            <i class="fas fa-spinner fa-spin fa-2x mb-3 text-accent"></i><br>Loading servers...
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- ADMIN VIEW -->
        <div id="view-admin" style="display: none;">
            <h3 class="mb-4 fw-bold">Admin Settings</h3>

            <div class="admin-tabs">
                <div class="admin-tab active" onclick="switchAdminTab('thresholds', this)">Alert Thresholds</div>
                <div class="admin-tab" onclick="switchAdminTab('notifications', this)">Notifications</div>
                <div class="admin-tab" onclick="switchAdminTab('users', this)">Users</div>
            </div>

            <!-- Alert Thresholds -->
            <div id="tab-thresholds" class="card p-4">
                <h5 class="mb-4">Alert thresholds</h5>
                <div class="row mb-4">
                    <div class="col-md-6">
                        <p class="text-warning small mb-1">Warning</p>
                        <div class="d-flex align-items-center mb-3">
                            <span class="me-3" style="width: 50px;">CPU</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="80">
                            <span class="ms-3 text-muted">80%</span>
                        </div>
                        <div class="d-flex align-items-center mb-3">
                            <span class="me-3" style="width: 50px;">RAM</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="85">
                            <span class="ms-3 text-muted">85%</span>
                        </div>
                        <div class="d-flex align-items-center">
                            <span class="me-3" style="width: 50px;">Disk</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="80">
                            <span class="ms-3 text-muted">80%</span>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <p class="text-danger small mb-1">Critical</p>
                        <div class="d-flex align-items-center mb-3">
                            <span class="me-3" style="width: 50px;">CPU</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="95">
                            <span class="ms-3 text-muted">95%</span>
                        </div>
                        <div class="d-flex align-items-center mb-3">
                            <span class="me-3" style="width: 50px;">RAM</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="95">
                            <span class="ms-3 text-muted">95%</span>
                        </div>
                        <div class="d-flex align-items-center">
                            <span class="me-3" style="width: 50px;">Disk</span>
                            <input type="range" class="form-range flex-grow-1" min="0" max="100" value="90">
                            <span class="ms-3 text-muted">90%</span>
                        </div>
                    </div>
                </div>
                <button class="btn btn-teal px-4 py-2 rounded-3" style="width: fit-content;">Save thresholds</button>
            </div>

            <!-- Notifications Tab -->
            <div id="tab-notifications" class="card p-4" style="display: none;">
                <h5 class="mb-4">External Notifications</h5>
                <p class="text-muted small mb-4">Configure where to send alerts when a server hits a critical threshold.</p>

                <div class="mb-4" style="max-width: 400px;">
                    <label class="form-label small">Notification Email Address</label>
                    <input type="email" class="form-control" id="inputNotifyEmail" placeholder="admin@example.com" value="admin@example.com">
                </div>

                <button class="btn btn-teal px-4 py-2 rounded-3" onclick="saveNotificationSettings()">Save Settings</button>
                <div id="notifyFeedback" class="mt-3 small text-success"></div>
            </div>

            <!-- Users Tab -->
            <div id="tab-users" class="card p-4" style="display: none;">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5>Users</h5>
                    <button class="btn btn-outline-light btn-sm">Add user</button>
                </div>
                <table class="table table-dark table-borderless">
                    <thead><tr class="text-muted"><th>Username</th><th>Created</th><th class="text-end">Actions</th></tr></thead>
                    <tbody>
                        <tr><td>admin</td><td>Sep 30</td><td class="text-end text-muted">Reset password</td></tr>
                    </tbody>
                </table>
            </div>

        </div>

    </div>

    <!-- Add Server Button -->
    <button class="btn btn-primary btn-lg rounded-circle add-btn p-3" data-bs-toggle="modal" data-bs-target="#addServerModal">
        <i class="fas fa-plus fa-lg"></i>
    </button>

    <!-- Add Server Modal -->
    <div class="modal fade" id="addServerModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Add server</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="addServerForm">
                        <div class="mb-3">
                            <label class="form-label small">Name</label>
                            <input type="text" class="form-control" id="inputName" placeholder="Pi-345" required minlength="3">
                        </div>
                        <div class="mb-3">
                            <label class="form-label small">Hostname or IP</label>
                            <input type="text" class="form-control" id="inputHostname" placeholder="192.168.1.30" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label small">SSH port</label>
                            <input type="number" class="form-control" id="inputPort" value="22" min="1" max="65535">
                        </div>
                        <div class="d-flex justify-content-between align-items-center mt-4">
                            <button type="button" class="btn btn-outline-light btn-sm px-3">Test connection</button>
                            <button type="submit" class="btn btn-primary px-4" id="submitServerBtn">Add server</button>
                        </div>
                    </form>
                    <div id="formFeedback" class="mt-3 small"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- History Modal -->
    <div class="modal fade" id="historyModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-chart-line me-2 text-accent"></i>History: <span id="historyServerName"></span></h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="historyLoading" class="text-center text-muted py-4">
                        <i class="fas fa-spinner fa-spin fa-2x"></i><br>Loading history...
                    </div>
                    <div id="historyError" class="alert alert-danger d-none"></div>
                    <div id="historyEmpty" class="alert alert-dark d-none border-secondary text-muted">
                        No historical data yet. Metrics are logged every 30 seconds.
                    </div>
                    <div id="historyChartWrapper" class="d-none">
                        <canvas id="historyChart" height="120"></canvas>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Navigation Logic
        function showView(view) {
            document.getElementById('view-dashboard').style.display = view === 'dashboard' ? 'block' : 'none';
            document.getElementById('view-admin').style.display = view === 'admin' ? 'block' : 'none';

            document.getElementById('nav-dashboard').classList.toggle('active', view === 'dashboard');
            document.getElementById('nav-admin').classList.toggle('active', view === 'admin');
        }

        function switchAdminTab(tab, el) {
            document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            document.getElementById('tab-thresholds').style.display = tab === 'thresholds' ? 'block' : 'none';
            document.getElementById('tab-notifications').style.display = tab === 'notifications' ? 'block' : 'none';
            document.getElementById('tab-users').style.display = tab === 'users' ? 'block' : 'none';
        }

        async function saveNotificationSettings() {
            const email = document.getElementById('inputNotifyEmail').value;
            try {
                await fetch('/admin/settings/email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email })
                });
                document.getElementById('notifyFeedback').textContent = 'Settings saved successfully!';
                setTimeout(() => document.getElementById('notifyFeedback').textContent = '', 3000);
            } catch(e) {
                alert("Error saving settings");
            }
        }

        // Dashboard Logic
        const THRESHOLDS = { cpu_warning: 80, cpu_critical: 95, ram_warning: 85, ram_critical: 95, disk_warning: 80, disk_critical: 90 };

        async function loadDashboard() {
            try {
                const response = await fetch('/servers');
                if (response.status === 401) { window.location.href = '/login'; return; }
                const servers = await response.json();

                const grid = document.getElementById('server-grid');
                if (!servers || servers.length === 0) {
                    grid.innerHTML = `<div class="col-12 text-center text-muted">No servers registered. Click the + button to add one.</div>`;
                    return;
                }

                let cardsHtml = '';
                let onlineCount = 0;
                let warningCount = 0;

                for (const server of servers) {
                    let m = { cpu: 0, ram: 0, disks: [], alerts: [] };
                    let isOffline = false;

                    try {
                        const metricRes = await fetch(`/servers/${server.id}/metrics`);
                        if (metricRes.ok) {
                            m = await metricRes.json();

                            // Fallback: If teammate hasn't updated ssh_monitor.py yet, handle old single disk format
                            if (!m.disks && m.disk_percent !== undefined) {
                                m.disks = [{ mount: "/", percent: m.disk_percent }];
                            }
                        } else {
                            isOffline = true;
                        }
                    } catch (e) {
                        isOffline = true;
                    }

                    // Use alerts returned by the backend!
                    const alerts = m.alerts || [];
                    let cardStatusClass = 'server-card-healthy';

                    if (isOffline) {
                        warningCount++;
                        cardStatusClass = 'server-card-critical';
                    } else if (alerts.length > 0) {
                        warningCount++;
                        cardStatusClass = alerts[0].includes('CRITICAL') ? 'server-card-critical' : 'server-card-warning';
                    } else {
                        onlineCount++;
                    }

                    // Build the Disk HTML dynamically
                    let diskHtml = '';
                    if (m.disks && m.disks.length > 0) {
                        m.disks.forEach(d => {
                            const color = d.percent >= THRESHOLDS.disk_critical ? 'bg-danger' : (d.percent >= THRESHOLDS.disk_warning ? 'bg-warning' : 'bg-info');
                            diskHtml += `
                                <div class="col-4 mt-2">
                                    <div class="metric-value">${isOffline ? '--' : d.percent + '%'}</div>
                                    <div class="metric-label">${d.mount}</div>
                                    <div class="progress"><div class="progress-bar ${color}" style="width:${isOffline ? 0 : d.percent}%"></div></div>
                                </div>
                            `;
                        });
                    }

                    const cpuColor = m.cpu >= THRESHOLDS.cpu_critical ? 'bg-danger' : (m.cpu >= THRESHOLDS.cpu_warning ? 'bg-warning' : 'bg-info');
                    const ramColor = m.ram >= THRESHOLDS.ram_critical ? 'bg-danger' : (m.ram >= THRESHOLDS.ram_warning ? 'bg-warning' : 'bg-info');

                    cardsHtml += `
                        <div class="col-md-12 mb-3">
                            <div class="card p-3 ${cardStatusClass}">
                                <div class="d-flex justify-content-between align-items-center mb-3">
                                    <div>
                                        <h5 class="mb-0 fw-bold">${server.name}</h5>
                                        <span class="text-muted small">${server.hostname} : ${server.ssh_port}</span>
                                    </div>
                                    <div class="d-flex align-items-center gap-3">
                                        <span class="small ${isOffline ? 'text-danger' : (alerts.length ? 'text-warning' : 'text-success')}">
                                            <i class="fas fa-circle me-1" style="font-size: 0.6rem;"></i> 
                                            ${isOffline ? 'offline' : (alerts.length ? (alerts[0].includes('CRITICAL') ? 'critical' : 'warning') : 'healthy')}
                                        </span>
                                        <button class="btn btn-outline-info btn-sm history-btn" data-id="${server.id}" data-name="${server.name}" title="History">
                                            <i class="fas fa-chart-line"></i>
                                        </button>
                                        <button class="btn btn-outline-danger btn-sm delete-btn" data-id="${server.id}" data-name="${server.name}" title="Delete">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>

                                <div class="row text-center mt-2">
                                    <!-- CPU & RAM -->
                                    <div class="col-4">
                                        <div class="metric-value">${isOffline ? '--' : m.cpu + '%'}</div>
                                        <div class="metric-label">CPU</div>
                                        <div class="progress"><div class="progress-bar ${cpuColor}" style="width:${isOffline ? 0 : m.cpu}%"></div></div>
                                    </div>
                                    <div class="col-4">
                                        <div class="metric-value">${isOffline ? '--' : m.ram + '%'}</div>
                                        <div class="metric-label">RAM</div>
                                        <div class="progress"><div class="progress-bar ${ramColor}" style="width:${isOffline ? 0 : m.ram}%"></div></div>
                                    </div>

                                    <!-- Dynamically Generated Disks -->
                                    ${diskHtml}
                                </div>
                            </div>
                        </div>
                    `;
                }

                grid.innerHTML = cardsHtml;

                document.getElementById('stat-online').textContent = `${onlineCount} online`;
                document.getElementById('stat-warning').textContent = `${warningCount} need attention`;
                document.getElementById('stat-updated').innerHTML = `Updated just now <i class="fas fa-sync-alt ms-1"></i>`;

            } catch (error) {
                document.getElementById('server-grid').innerHTML = `<div class="col-12 text-center text-danger">Failed to load servers</div>`;
            }
        }

        // Add Server Form
        document.getElementById('addServerForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const name = document.getElementById('inputName').value.trim();
            const hostname = document.getElementById('inputHostname').value.trim();
            const ssh_port = parseInt(document.getElementById('inputPort').value) || 22;
            const feedback = document.getElementById('formFeedback');
            feedback.innerHTML = '';

            try {
                const response = await fetch('/servers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, hostname, ssh_port })
                });
                if (response.ok) {
                    feedback.innerHTML = '<span class="text-success">Server added successfully!</span>';
                    setTimeout(() => { document.querySelector('#addServerModal .btn-close').click(); loadDashboard(); }, 1000);
                } else {
                    feedback.innerHTML = `<span class="text-danger">Error adding server</span>`;
                }
            } catch (err) { feedback.innerHTML = `<span class="text-danger">Network error</span>`; }
        });

        // Delete Server
        document.addEventListener('click', async function(e) {
            const btn = e.target.closest('.delete-btn');
            if (!btn) return;
            if (!confirm(`Delete server "${btn.dataset.name}"?`)) return;
            await fetch(`/servers/${btn.dataset.id}`, { method: 'DELETE' });
            loadDashboard();
        });

        // History Graph
        let currentChart = null;
        let historyRefreshTimer = null;

        document.addEventListener('click', async function(e) {
            const btn = e.target.closest('.history-btn');
            if (!btn) return;

            const id = btn.dataset.id;
            document.getElementById('historyServerName').textContent = btn.dataset.name;
            document.getElementById('historyLoading').classList.remove('d-none');
            document.getElementById('historyError').classList.add('d-none');
            document.getElementById('historyEmpty').classList.add('d-none');
            document.getElementById('historyChartWrapper').classList.add('d-none');

            const modalEl = document.getElementById('historyModal');
            new bootstrap.Modal(modalEl).show();

            async function fetchAndRender() {
                try {
                    const response = await fetch(`/health/history/${id}?limit=120`);
                    const rows = await response.json();

                    document.getElementById('historyLoading').classList.add('d-none');

                    if (!rows || rows.length === 0) {
                        document.getElementById('historyEmpty').classList.remove('d-none');
                        document.getElementById('historyChartWrapper').classList.add('d-none');
                        return;
                    }

                    document.getElementById('historyEmpty').classList.add('d-none');
                    document.getElementById('historyChartWrapper').classList.remove('d-none');

                    const labels = rows.map(r => new Date(r.logged_at).toLocaleTimeString());
                    const cpuData = rows.map(r => r.cpu_percent);
                    const ramData = rows.map(r => r.ram_percent);
                    const diskData = rows.map(r => r.disk_percent); // Note: this only graphs root disk for now

                    if (currentChart) {
                        currentChart.data.labels = labels;
                        currentChart.data.datasets[0].data = cpuData;
                        currentChart.data.datasets[1].data = ramData;
                        currentChart.data.datasets[2].data = diskData;
                        currentChart.update('none');
                        return;
                    }

                    const ctx = document.getElementById('historyChart').getContext('2d');
                    currentChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [
                                { label: 'CPU %', data: cpuData, borderColor: '#a855f7', backgroundColor: 'rgba(168, 85, 247, 0.1)', tension: 0.3, fill: true, pointRadius: 0 },
                                { label: 'RAM %', data: ramData, borderColor: '#2dd4bf', backgroundColor: 'rgba(45, 212, 191, 0.1)', tension: 0.3, fill: true, pointRadius: 0 },
                                { label: 'Disk %', data: diskData, borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', tension: 0.3, fill: true, pointRadius: 0 }
                            ]
                        },
                        options: {
                            responsive: true, animation: false, interaction: { mode: 'index', intersect: false },
                            plugins: { legend: { labels: { color: '#fff' } } },
                            scales: {
                                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                                x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 8 } }
                            }
                        }
                    });
                } catch (err) { console.error(err); }
            }

            await fetchAndRender();
            historyRefreshTimer = setInterval(fetchAndRender, 30_000);

            modalEl.addEventListener('hidden.bs.modal', function cleanup() {
                if (historyRefreshTimer) clearInterval(historyRefreshTimer);
                if (currentChart) { currentChart.destroy(); currentChart = null; }
                modalEl.removeEventListener('hidden.bs.modal', cleanup);
            }, { once: true });
        });

        document.addEventListener('DOMContentLoaded', loadDashboard);
        setInterval(loadDashboard, 30000);
    </script>
</body>
</html>
"""


# ---------- Backend Logic ----------

async def send_alert_email(server_name, alert_message):
    """
    Stub function to send an email.
    To make this work for real, set smtp_user and smtp_password in SETTINGS.
    (Google requires you to generate an "App Password" for this to work).
    """
    recipient = SETTINGS.get("notification_email")
    if not recipient:
        return

    subject = f"🚨 HiveMind Alert: {server_name}"
    body = f"Critical threshold reached on {server_name}:\n\n{alert_message}"

    print(f"\n--- 📧 EMAIL PREPARED ---")
    print(f"To: {recipient}")
    print(f"Subject: {subject}")
    print(f"Body: {body}")
    print(f"-------------------------\n")

    # Uncomment below to actually send the email (requires valid SMTP credentials)
    """
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = SETTINGS["smtp_user"]
        msg['To'] = recipient

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SETTINGS["smtp_user"], SETTINGS["smtp_password"])
            smtp.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")
    """


def check_backend_thresholds(cpu, ram, disks):
    """Evaluates metrics on the server so it can trigger emails."""
    alerts = []
    if cpu >= 95:
        alerts.append(f"CRITICAL: CPU {cpu}%")
    elif cpu >= 80:
        alerts.append(f"WARNING: CPU {cpu}%")

    if ram >= 95:
        alerts.append(f"CRITICAL: RAM {ram}%")
    elif ram >= 85:
        alerts.append(f"WARNING: RAM {ram}%")

    for d in disks:
        if d["percent"] >= 90:
            alerts.append(f"CRITICAL: Disk {d['mount']} {d['percent']}%")
        elif d["percent"] >= 80:
            alerts.append(f"WARNING: Disk {d['mount']} {d['percent']}%")

    return alerts


async def lifespan(app: FastAPI):
    create_tables()
    server_id = get_or_create_main_server()
    health_task = asyncio.create_task(log_health(server_id))
    yield
    health_task.cancel()

# noinspection PyTypeChecker
app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------- Admin Settings Routes ----------
class EmailSettings(BaseModel):
    email: str


@app.post("/admin/settings/email")
def update_email_settings(settings: EmailSettings, request: Request):
    require_login(request)
    SETTINGS["notification_email"] = settings.email
    return {"message": "Settings updated"}


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
            cursor.execute("SELECT id, username, password_hash, salt FROM users WHERE username = %s", (username,))
            user_row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if user_row and verify_password(password, user_row["salt"], user_row["password_hash"]):
        request.session["user"] = user_row["username"]
        return RedirectResponse(url="/dashboard", status_code=303)

    error_html = '<div class="alert alert-danger mb-3 py-2 small"><i class="fas fa-exclamation-triangle me-2"></i>Invalid username or password.</div>'
    return HTMLResponse(LOGIN_TEMPLATE.replace("%%ERROR%%", error_html), status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# ---------- Server Routes ----------
class ServerCreate(BaseModel):
    name: str
    hostname: str
    ssh_port: int = 22


@app.post("/servers", status_code=201)
def add_server(request: Request, server: ServerCreate):
    require_login(request)
    if len(server.name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Name too short")

    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("INSERT INTO servers (NAME, hostname, ssh_port) VALUES (%s, %s, %s)",
                       (server.name, server.hostname, server.ssh_port))
        connection.commit()
        return {"message": "Server added successfully!", "id": cursor.lastrowid}
    finally:
        cursor.close()
        connection.close()


@app.get("/servers")
def get_servers(request: Request):
    require_login(request)
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name, hostname, ssh_port FROM servers")
        servers = cursor.fetchall()
        for s in servers:
            if "status" not in s or not s["status"]: s["status"] = "online"
        return servers
    finally:
        cursor.close()
        connection.close()


@app.delete("/servers/{server_id}")
def delete_server(server_id: int, request: Request):
    require_login(request)
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM servers WHERE id = %s", (server_id,))
        connection.commit()
        return {"message": f"Server {server_id} deleted."}
    finally:
        cursor.close()
        connection.close()


# ---------- Metric Routes ----------
@app.get("/servers/{server_id}/metrics")
async def get_server_metrics(server_id: int, request: Request):
    require_login(request)

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT hostname, ssh_port FROM servers WHERE id = %s", (server_id,))
        server = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    username = os.environ.get("SSH_USER", "seed")
    port = server["ssh_port"] or 22

    try:
        # Fetch from teammate's ssh_monitor.py
        metrics = get_remote_health(hostname=server["hostname"], username=username, port=port)

        # --- MODULAR DISK FALLBACK ---
        # If teammate hasn't updated ssh_monitor.py yet, convert single disk to list
        if "disks" not in metrics and "disk_percent" in metrics:
            metrics["disks"] = [{"mount": "/", "percent": metrics["disk_percent"]}]

        # Evaluate alerts on the backend so we can email them!
        backend_alerts = check_backend_thresholds(metrics.get("cpu_percent", 0), metrics.get("ram_percent", 0),
                                                  metrics.get("disks", []))
        metrics["alerts"] = backend_alerts

        # If there are alerts, trigger the email stub
        if backend_alerts:
            await send_alert_email(server["name"], backend_alerts[0])

        return metrics

    except SSHMonitorError as e:
        print(f"🚨 SSH ERROR FOR {server['hostname']}: {e}")
        raise HTTPException(status_code=503, detail="Failed to connect to server")


@app.get("/health/history/{server_id}")
def get_health_history(server_id: int, request: Request, limit: int = 120):
    require_login(request)
    if limit < 1 or limit > 500: limit = 120

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT cpu_percent, ram_percent, disk_percent, logged_at
            FROM server_health_log WHERE server_id = %s
            ORDER BY logged_at DESC LIMIT %s
        """, (server_id, limit))
        rows = cursor.fetchall()
        rows.reverse()
        return rows
    finally:
        cursor.close()
        connection.close()


# ---------- Background Logging ----------
async def log_health(server_id: int):
    while True:
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage(os.path.abspath(os.sep)).percent

            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO server_health_log (server_id, cpu_percent, ram_percent, disk_percent) VALUES (%s, %s, %s, %s)",
                (server_id, cpu, ram, disk)
            )
            connection.commit()
            cursor.close()
            connection.close()
        except Exception as e:
            print(f"Logging error: {e}")
        await asyncio.sleep(30)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=302)
    return HTML_TEMPLATE
