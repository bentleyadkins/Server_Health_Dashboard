import asyncio
import os

import psutil
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from auth import verify_password
from database import *
from ssh_monitor import get_remote_health, SSHMonitorError

# IMPORTANT: replace this with your own random 64-char hex string.
SECRET_KEY = "6a6e34449fec654e25d4e03954a4c542ff7cfe1bb592ca95a1f319de4863011b"

# ---------- HTML Template: Login Page (Slide 5) ----------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Server Health Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {
            background: linear-gradient(135deg, #2b1055 0%, #1a0b2e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-family: 'Inter', sans-serif;
        }
        .login-card {
            max-width: 400px;
            width: 100%;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            padding: 2.5rem;
        }
        .brand-title { font-weight: 700; letter-spacing: -0.5px; }
        .tagline { color: #a78bfa; font-size: 0.9rem; margin-bottom: 2rem; }
        .form-control {
            background: rgba(0,0,0,0.2);
            border: 1px solid rgba(255,255,255,0.1);
            color: #ffffff !important; /* Forces typed text to be white */
        }
        .form-control::placeholder {
            color: #a78bfa; /* Makes placeholder text visible */
        }
        /* Fixes Chrome's annoying autofill background color */
        .form-control:-webkit-autofill {
            -webkit-text-fill-color: #fff !important;
            -webkit-box-shadow: 0 0 0px 1000px #2b1055 inset !important;
        }
        .form-control:focus {
            background: rgba(0,0,0,0.3);
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
        .btn-primary:hover {
            background: #c4b5fd;
            color: #1a0b2e;
        }
        /* Forces the labels to be a visible light color */
        .form-label {
            color: #e2e8f0 !important;
        }
        .text-muted {
            color: #cbd5e1 !important; /* Overrides the dark gray bootstrap text-muted */
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="text-center mb-4">
            <h2 class="brand-title">Server Health Dashboard</h2>
            <p class="tagline">A+ service for your servers.</p>
        </div>

        <p class="text-center text-muted small mb-3">CPU, memory and disk for every machine in your lab, in one place.</p>

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

# ---------- HTML Template: Dashboard (Slides 6-8) ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Server Health</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
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

        /* Sidebar Layout */
        .sidebar {
            width: 250px;
            height: 100vh;
            position: fixed;
            top: 0; left: 0;
            background: linear-gradient(180deg, var(--bg-sidebar) 0%, #0f172a 100%);
            border-right: 1px solid rgba(255,255,255,0.05);
            padding-top: 20px;
            z-index: 1000;
        }
        .sidebar-brand {
            font-size: 1.2rem; font-weight: 700; padding: 0 20px 20px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom: 20px;
            color: #fff; display: flex; align-items: center; gap: 10px;
        }
        .sidebar-brand i { color: var(--accent); }
        .nav-link {
            color: var(--text-muted); padding: 12px 20px; font-weight: 500;
            transition: all 0.2s; margin: 4px 10px; border-radius: 8px;
        }
        .nav-link:hover { color: #fff; background: rgba(255,255,255,0.05); }
        .nav-link.active { color: #fff; background: var(--accent); box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4); }

        /* Main Content */
        .main-content { margin-left: 250px; padding: 30px; transition: 0.3s; }

        /* Top Bar (Slide 6) */
        .top-bar {
            background: var(--card-bg); border-radius: 12px; padding: 15px 25px;
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 30px; border: 1px solid rgba(255,255,255,0.05);
            font-size: 0.9rem;
        }
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .status-online { background: var(--teal); box-shadow: 0 0 10px var(--teal); }
        .status-warning { background: #f59e0b; box-shadow: 0 0 10px #f59e0b; }

        /* Cards */
        .card {
            background: var(--card-bg); border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px; color: var(--text-main); margin-bottom: 20px;
        }
        .card-header { border-bottom: 1px solid rgba(255,255,255,0.05); background: transparent; }
        .metric-value { font-size: 1.5rem; font-weight: 700; color: #fff; }
        .progress { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; }
        .progress-bar { border-radius: 4px; }

        /* Buttons */
        .btn-primary { background: var(--accent); border: none; color: #fff; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-teal { background: var(--teal); border: none; color: #0f172a; font-weight: 600; }
        .btn-teal:hover { background: #5eead4; }
        .add-btn { position: fixed; bottom: 30px; right: 30px; z-index: 1000; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4); }

        /* Modals */
        .modal-content { background: var(--card-bg); color: #fff; border: 1px solid rgba(255,255,255,0.1); }
        .modal-header { border-bottom: 1px solid rgba(255,255,255,0.05); }
        .modal-footer { border-top: 1px solid rgba(255,255,255,0.05); }
        .form-control, .form-select { background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); color: #fff; }
        .form-control:focus { background: rgba(0,0,0,0.3); color: #fff; border-color: var(--accent); box-shadow: none; }

        /* Admin Tabs */
        .admin-tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .admin-tab { background: transparent; border: 1px solid rgba(255,255,255,0.1); color: var(--text-muted); border-radius: 20px; padding: 8px 20px; font-size: 0.9rem; cursor: pointer; }
        .admin-tab.active { border-color: var(--teal); color: var(--teal); }
        
        /* Make form labels readable in dark mode */
        .modal .form-label {
            color: #e2e8f0 !important; /* Light gray/white */
            font-weight: 500;
            }
            
            /* Make the placeholder text inside the input boxes a bit brighter too */
            .form-control::placeholder {
                color: #94a3b8; 
                opacity: 1:
            }
            
    </style>
</head>
<body>

    <!-- Sidebar -->
    <div class="sidebar">
        <div class="sidebar-brand">
            <i class="fas fa-server"></i> Server Health
        </div>
        <nav class="nav flex-column">
            <a class="nav-link active" href="#" id="nav-dashboard" onclick="showView('dashboard')"><i class="fas fa-tachometer-alt me-2"></i> Dashboard</a>
            <a class="nav-link" href="#" id="nav-admin" onclick="showView('admin')"><i class="fas fa-shield-alt me-2"></i> Admin</a>
            <a class="nav-link mt-4 text-danger" href="#" onclick="document.getElementById('logoutForm').submit()"><i class="fas fa-sign-out-alt me-2"></i> Log out</a>
        </nav>
        <form id="logoutForm" method="POST" action="/logout" class="d-none"></form>
    </div>

    <!-- Main Content Area -->
    <div class="main-content">

        <!-- DASHBOARD VIEW -->
        <div id="view-dashboard">
            <!-- Top Status Bar -->
            <div class="top-bar">
                <div>
                    <span class="status-dot status-online"></span> <span id="stat-online" class="me-3">Loading...</span>
                    <span class="status-dot status-warning"></span> <span id="stat-warning" class="text-muted">Loading...</span>
                </div>
                <div class="text-muted small" id="stat-updated">Updated just now</div>
            </div>

            <div id="global-alerts" class="mb-3"></div>

            <div class="row" id="server-grid">
                <div class="col-12 text-center text-muted py-5">
                    <i class="fas fa-spinner fa-spin fa-2x mb-3 text-accent"></i><br>Loading servers...
                </div>
            </div>
        </div>

        <!-- ADMIN VIEW (Slide 8) -->
        <div id="view-admin" style="display: none;">
            <h3 class="mb-4">Admin Settings</h3>

            <div class="admin-tabs">
                <div class="admin-tab active" onclick="switchAdminTab('thresholds', this)">Alert thresholds</div>
                <div class="admin-tab" onclick="switchAdminTab('users', this)">Users</div>
                <div class="admin-tab" onclick="switchAdminTab('servers', this)">Servers</div>
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

            <!-- Users Tab (Skeleton) -->
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

            <!-- Servers Tab (Skeleton) -->
            <div id="tab-servers" class="card p-4" style="display: none;">
                <h5>Servers Management</h5>
                <p class="text-muted mt-2">Edit and delete servers here in a future update.</p>
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
                            <label class="form-label text-muted small">Name</label>
                            <input type="text" class="form-control" id="inputName" placeholder="Pi-345" required minlength="3">
                        </div>
                        <div class="mb-3">
                            <label class="form-label text-muted small">Hostname or IP</label>
                            <input type="text" class="form-control" id="inputHostname" placeholder="192.168.1.30" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label text-muted small">SSH port</label>
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
            document.getElementById('tab-users').style.display = tab === 'users' ? 'block' : 'none';
            document.getElementById('tab-servers').style.display = tab === 'servers' ? 'block' : 'none';
        }

        // Dashboard Logic
        const THRESHOLDS = { cpu_warning: 80, cpu_critical: 95, ram_warning: 85, ram_critical: 95, disk_warning: 80, disk_critical: 90 };

        function generateMetrics() {
            return { cpu: Math.round(Math.random() * 100), ram: Math.round(Math.random() * 100), disk: Math.round(Math.random() * 100) };
        }

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
                if (response.status === 401) { window.location.href = '/login'; return; }
                const servers = await response.json();

                const grid = document.getElementById('server-grid');
                if (!servers || servers.length === 0) {
                    grid.innerHTML = `<div class="col-12 text-center text-muted">No servers registered. Click the + button to add one.</div>`;
                    return;
                }

                let cardsHtml = '';
                let allAlerts = [];
                let onlineCount = 0;
                let warningCount = 0;

                servers.forEach(server => {
                    const m = generateMetrics();
                    const alerts = checkMetrics(m.cpu, m.ram, m.disk);
                    if (alerts.length > 0) { allAlerts.push(...alerts); warningCount++; } else { onlineCount++; }

                    const statusClass = server.status && server.status.toLowerCase() === 'offline' ? 'opacity-50' : '';

                    // Determine colors based on thresholds
                    const cpuColor = m.cpu >= THRESHOLDS.cpu_critical ? 'bg-danger' : (m.cpu >= THRESHOLDS.cpu_warning ? 'bg-warning' : 'bg-info');
                    const ramColor = m.ram >= THRESHOLDS.ram_critical ? 'bg-danger' : (m.ram >= THRESHOLDS.ram_warning ? 'bg-warning' : 'bg-info');
                    const diskColor = m.disk >= THRESHOLDS.disk_critical ? 'bg-danger' : (m.disk >= THRESHOLDS.disk_warning ? 'bg-warning' : 'bg-info');

                    cardsHtml += `
                        <div class="col-md-4 mb-4">
                            <div class="card h-100 ${statusClass}">
                                <div class="card-header d-flex justify-content-between align-items-center py-3">
                                    <span class="fw-bold"><i class="fas fa-server me-2 text-muted"></i>${server.name}</span>
                                    <div class="d-flex gap-2">
                                        <button class="btn btn-outline-info btn-sm history-btn" data-id="${server.id}" data-name="${server.name}" title="History">
                                            <i class="fas fa-chart-line"></i>
                                        </button>
                                        <button class="btn btn-outline-danger btn-sm delete-btn" data-id="${server.id}" data-name="${server.name}" title="Delete">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="card-body">
                                    <p class="text-muted small mb-4">${server.hostname} : ${server.ssh_port}</p>

                                    <div class="row text-center mb-3">
                                        <div class="col-4">
                                            <div class="metric-value">${m.cpu}%</div>
                                            <div class="text-muted small mb-2">CPU</div>
                                            <div class="progress"><div class="progress-bar ${cpuColor}" style="width:${m.cpu}%"></div></div>
                                        </div>
                                        <div class="col-4">
                                            <div class="metric-value">${m.ram}%</div>
                                            <div class="text-muted small mb-2">RAM</div>
                                            <div class="progress"><div class="progress-bar ${ramColor}" style="width:${m.ram}%"></div></div>
                                        </div>
                                        <div class="col-4">
                                            <div class="metric-value">${m.disk}%</div>
                                            <div class="text-muted small mb-2">Disk</div>
                                            <div class="progress"><div class="progress-bar ${diskColor}" style="width:${m.disk}%"></div></div>
                                        </div>
                                    </div>
                                    <div class="mt-4 pt-3 border-top border-secondary border-opacity-25">
                                        ${alerts.length ? `<span class="text-danger small"><i class="fas fa-exclamation-triangle me-1"></i>${alerts[0]}</span>` : `<span class="text-success small"><i class="fas fa-check-circle me-1"></i> No alerts</span>`}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });

                grid.innerHTML = cardsHtml;

                // Update Top Status Bar
                document.getElementById('stat-online').textContent = `${onlineCount} online`;
                document.getElementById('stat-warning').textContent = `${warningCount} need attention`;
                document.getElementById('stat-updated').textContent = `Updated ${Math.floor(Math.random() * 5) + 1}s ago`;

            } catch (error) {
                document.getElementById('server-grid').innerHTML = `<div class="col-12 text-center text-danger">Failed to load servers</div>`;
            }
        }

        // Add/Delete/History logic remains the same...
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

        document.addEventListener('click', async function(e) {
            const btn = e.target.closest('.delete-btn');
            if (!btn) return;
            if (!confirm(`Delete server "${btn.dataset.name}"?`)) return;
            await fetch(`/servers/${btn.dataset.id}`, { method: 'DELETE' });
            loadDashboard();
        });

        // History Graph Logic
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
                    const diskData = rows.map(r => r.disk_percent);

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
        // Auto update stats every 15 seconds
        setInterval(loadDashboard, 15000);
    </script>
</body>
</html>
"""


async def lifespan(app: FastAPI):
    app = FastAPI(lifespan=lifespan)
    create_tables()
    server_id = get_or_create_main_server()
    health_task = asyncio.create_task(log_health(server_id))
    yield
    health_task.cancel()


app = FastAPI(lifespan=lifespan)
# app.include_router(login_router) # Still commented out based on your last version

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


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


@app.get("/health")
def get_system_health():
    disk_path = os.path.abspath(os.sep)
    user = psutil.users()
    return {
        "user": user[0].name if user else "System",
        "net_if_stats": psutil.net_if_addrs(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage(disk_path).percent
    }


@app.get("/remote-health")
def get_remote_system_health(request: Request):
    require_login(request)
    hostname = os.environ.get("SSH_HOST")
    username = os.environ.get("SSH_USER")
    port = int(os.environ.get("SSH_PORT", "22"))

    if not hostname or not username:
        raise HTTPException(status_code=500, detail="SSH_HOST and SSH_USER are not configured")

    try:
        return get_remote_health(hostname=hostname, username=username, port=port)
    except SSHMonitorError as e:
        raise HTTPException(status_code=503, detail="Unable to collect remote server metrics")


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
