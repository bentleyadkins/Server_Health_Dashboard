from datetime import datetime, timedelta, timezone
from pathlib import Path
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from auth import verify_password


from database import *
import os
import ipaddress
import socket
from fastapi import Form
import psutil
from ssh_monitor import get_remote_health, SSHMonitorError
import asyncio
from login import router as login_router
import mysql.connector
import logging
from contextlib import suppress

# IMPORTANT: replace this with your own random 64-char hex string.
# Generate one with: py -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "6a6e34449fec654e25d4e03954a4c542ff7cfe1bb592ca95a1f319de4863011b"
logger = logging.getLogger(__name__)
HEALTH_POLL_INTERVAL = int(os.environ.get("HEALTH_POLL_INTERVAL", "3"))
THRESHOLDS = {
    "cpu_warning": 80,
    "cpu_critical": 95,
    "ram_warning": 85,
    "ram_critical": 95,
    "disk_warning": 80,
    "disk_critical": 90,
}
NOTIFICATION_SETTINGS = {"notification_email": ""}
EASTERN_STANDARD_TIME = timezone(timedelta(hours=-5), "EST")


def format_est_timestamp(value: datetime | None) -> str | None:
    """Serialize a database UTC timestamp as fixed Eastern Standard Time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(EASTERN_STANDARD_TIME).isoformat()


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
    <link rel="icon" type="image/png" href="/static/hivemind-logo.png">
    <style>
        body { background: radial-gradient(circle at 50% 20%, #32145a 0, #150d2b 45%, #080d1b 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; color: #f8fafc; font-family: system-ui, sans-serif; }
        .login-card {
            max-width: 450px;
            width: 100%;
            margin: 1rem;
            border-radius: 18px;
            background: rgba(18, 19, 42, .94);
            border: 1px solid rgba(192, 132, 252, .25);
            box-shadow: 0 20px 70px rgba(0, 0, 0, .45);
        }
        .login-logo { display: block; width: 190px; height: 190px; margin: 0 auto; object-fit: contain; border-radius: 12px; box-shadow: 0 0 30px rgba(168, 85, 247, .25); }
        .login-card .form-label { color: #cbd5e1; }
        .login-card .form-control { color: #fff; background: #10152a; border-color: #343253; }
        .login-card .form-control:focus { border-color: #a855f7; box-shadow: 0 0 0 .2rem rgba(168, 85, 247, .2); }
        .login-card .input-group-text { color: #c084fc; background: #10152a; border-color: #343253; }
        .login-card .btn-primary { color: #160d2b; background: #c084fc; border: 0; font-weight: 700; }
    </style>
</head>
<body>
    <div class="login-card card p-4 p-md-5">
        <div class="text-center mb-4">
            <img class="login-logo" src="/static/hivemind-logo.png" alt="HiveMind Metrics logo">
            <p class="text-secondary small mt-3">Helping all of your servers think alike.</p>
        </div>
        %%ERROR%%
        <form method="POST" action="/login">
            <div class="mb-3">
                <label class="form-label small">Username</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="fas fa-user"></i></span>
                    <input type="text" class="form-control" name="username" required autofocus>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label small">Password</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="fas fa-lock"></i></span>
                    <input type="password" class="form-control" name="password" required>
                </div>
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
    <link rel="icon" type="image/png" href="/static/hivemind-logo.png">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {
            --bg-main: #0b1020;
            --bg-panel: #11172a;
            --bg-card: rgba(18, 22, 43, .94);
            --accent: #a855f7;
            --accent-bright: #c084fc;
            --teal: #2dd4bf;
            --muted: #9aa5bd;
            --line: rgba(190, 170, 255, .16);
        }
        * { box-sizing: border-box; }
        body {
            min-height: 100vh;
            margin: 0;
            color: #f8fafc;
            background: radial-gradient(ellipse at 60% 20%, rgba(83, 30, 130, .2), transparent 50%), var(--bg-main);
            font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
        }
        .sidebar {
            width: 250px;
            height: 100vh;
            position: fixed;
            inset: 0 auto 0 0;
            z-index: 1000;
            overflow: hidden;
            padding: 28px 14px;
            background:
                radial-gradient(ellipse at 50% 25%, rgba(168, 85, 247, .36), transparent 48%),
                radial-gradient(ellipse at 10% 85%, rgba(92, 40, 155, .25), transparent 40%),
                linear-gradient(180deg, #21103e 0%, #15132d 56%, #0c1122 100%);
            border-right: 1px solid var(--line);
        }
        .sidebar::after {
            content: "";
            position: absolute;
            width: 280px;
            height: 280px;
            left: -100px;
            bottom: -70px;
            border: 1px solid rgba(192, 132, 252, .12);
            border-radius: 50%;
            box-shadow: 0 0 0 24px rgba(192, 132, 252, .025), 0 0 0 48px rgba(192, 132, 252, .02);
            pointer-events: none;
        }
        .sidebar-brand {
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 10px 12px 24px;
            margin-bottom: 24px;
            color: #fff;
            text-align: center;
            border-bottom: 1px solid rgba(255,255,255,.1);
        }
        .brand-emblem {
            display: block;
            width: 190px;
            height: 190px;
            margin-bottom: 10px;
            object-fit: contain;
            filter: drop-shadow(0 0 18px rgba(168, 85, 247, .35));
        }
        .sidebar-brand h1 { margin: 0; font: 700 1.12rem Georgia, serif; letter-spacing: 1.5px; }
        .sidebar-brand p { margin: 5px 0 0; color: #c4b5fd; font-size: .62rem; letter-spacing: 4px; text-transform: uppercase; }
        .sidebar .nav { position: relative; z-index: 1; }
        .sidebar .nav-link {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 11px 14px;
            margin: 4px 0;
            color: var(--muted);
            font-size: .9rem;
            border-radius: 9px;
            transition: background .18s ease, color .18s ease;
        }
        .sidebar .nav-link:hover { color: #fff; background: rgba(255,255,255,.07); }
        .sidebar .nav-link.active { color: #fff; background: linear-gradient(100deg, #7c22cf, #5214a1); box-shadow: 0 5px 20px rgba(111, 35, 197, .28); }
        .sidebar .nav-link.logout { margin-top: 20px; color: #fda4af; }
        .main-content { min-height: 100vh; margin-left: 250px; padding: 34px clamp(22px, 4vw, 58px) 90px; }
        .page-heading { margin: 0; font-size: clamp(1.5rem, 2.4vw, 2rem); font-weight: 750; letter-spacing: -.03em; }
        .overview-top { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 23px; }
        .status-row, .filter-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
        .status-row { margin: 0 0 20px; }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            min-height: 34px;
            padding: 6px 15px;
            color: var(--muted);
            font-size: .76rem;
            font-weight: 600;
            border: 1px solid var(--line);
            border-radius: 999px;
            background: rgba(13, 18, 35, .72);
        }
        .pill-online { color: var(--teal); border-color: rgba(45, 212, 191, .65); }
        .pill-warning { color: #fbbf24; border-color: rgba(245, 158, 11, .65); }
        .filter-row { margin-bottom: 16px; }
        .filter-btn {
            padding: 6px 17px;
            color: #aeb8cc;
            font-size: .76rem;
            background: rgba(13, 18, 35, .72);
            border: 1px solid var(--line);
            border-radius: 999px;
            transition: all .18s ease;
        }
        .filter-btn:hover, .filter-btn.active { color: var(--teal); border-color: var(--teal); box-shadow: 0 0 14px rgba(45, 212, 191, .12); }
        #global-alerts:empty { display: none; }
        #global-alerts .alert { color: #f8fafc; background: rgba(245, 158, 11, .1); border-color: rgba(245, 158, 11, .3); }
        #server-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 410px), 1fr)); gap: 13px; }
        .server-card {
            position: relative;
            min-width: 0;
            padding: 15px 17px 13px;
            overflow: hidden;
            background: linear-gradient(135deg, rgba(20, 24, 46, .98), rgba(13, 18, 34, .98));
            border: 1px solid var(--line);
            border-radius: 12px;
            box-shadow: 0 8px 28px rgba(0, 0, 0, .22);
        }
        .server-card::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--teal); }
        .server-card-warning::before { background: #fbbf24; }
        .server-card-critical::before, .server-card-offline::before { background: #f43f70; }
        .server-card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 11px; }
        .server-name { margin: 0; color: #f8fafc; font-size: .98rem; font-weight: 700; }
        .server-address { display: block; margin-top: 3px; color: var(--muted); font-size: .72rem; }
        .server-actions { display: flex; align-items: center; gap: 8px; }
        .server-state { display: inline-flex; align-items: center; gap: 5px; font-size: .72rem; font-weight: 650; white-space: nowrap; }
        .state-healthy { color: var(--teal); }
        .state-warning { color: #fbbf24; }
        .state-critical, .state-offline { color: #fb7185; }
        .icon-btn { display: grid; place-items: center; width: 29px; height: 29px; padding: 0; color: #aeb8cc; background: transparent; border: 1px solid transparent; border-radius: 7px; }
        .icon-btn:hover { color: #fff; background: rgba(255,255,255,.07); border-color: var(--line); }
        .icon-btn.delete-btn:hover { color: #fb7185; border-color: rgba(251, 113, 133, .4); }
        .metric-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 15px; }
        .metric { min-width: 0; }
        .metric-top { display: flex; align-items: baseline; gap: 8px; }
        .metric-value { color: #f8fafc; font-size: 1.22rem; font-weight: 720; line-height: 1; }
        .metric-label { color: #aab4ca; font-size: .66rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
        .metric-empty { color: #7d879e; font-size: 1rem; }
        .sparkline { display: block; width: 100%; height: 22px; margin-top: 7px; overflow: visible; }
        .server-footer { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 10px; color: #7e8aa3; font-size: .66rem; }
        .empty-state { grid-column: 1 / -1; padding: 42px 20px; color: var(--muted); text-align: center; background: rgba(18, 22, 43, .65); border: 1px dashed var(--line); border-radius: 12px; }
        .add-btn { position: fixed; right: 28px; bottom: 25px; z-index: 1001; display: grid; place-items: center; width: 54px; height: 54px; padding: 0; color: #072321; background: var(--teal); border: 0; border-radius: 50%; box-shadow: 0 7px 25px rgba(45, 212, 191, .28); }
        .add-btn:hover { color: #072321; background: #5eead4; transform: translateY(-2px); }
        .admin-title { margin-bottom: 22px; }
        .admin-tabs { display: flex; flex-wrap: wrap; gap: 9px; margin-bottom: 16px; }
        .admin-tab { padding: 8px 17px; color: var(--muted); background: transparent; border: 1px solid var(--line); border-radius: 999px; }
        .admin-tab.active, .admin-tab:hover { color: var(--teal); border-color: var(--teal); }
        .admin-card { padding: clamp(18px, 3vw, 28px); background: var(--bg-card); border: 1px solid var(--line); border-radius: 13px; box-shadow: 0 8px 28px rgba(0,0,0,.2); }
        .admin-card h4 { margin: 0 0 20px; font-size: 1.05rem; }
        .admin-card .form-label { color: #d6dced; font-size: .84rem; }
        .admin-card .form-control { color: #f8fafc; background: #0d1325; border-color: #343253; }
        .admin-card .form-control:focus { background: #0d1325; color: #fff; border-color: var(--accent-bright); box-shadow: 0 0 0 .2rem rgba(168, 85, 247, .18); }
        .admin-note { color: var(--muted); font-size: .82rem; }
        .modal-content { color: #f8fafc; background: #12172a; border: 1px solid var(--line); border-radius: 14px; }
        .modal-header, .modal-footer { border-color: var(--line); }
        .modal .form-label { color: #d6dced; }
        .modal .form-control { color: #fff; background: #0d1325; border-color: #343253; }
        .modal .form-control:focus { color: #fff; background: #0d1325; border-color: var(--accent-bright); box-shadow: none; }
        .modal .form-text { color: var(--muted); }
        .btn-primary { color: #fff; background: #812bd0; border-color: #812bd0; }
        .btn-primary:hover { color: #fff; background: #9a45e8; border-color: #9a45e8; }
        .btn-teal { color: #082321; background: var(--teal); border: 0; font-weight: 700; }
        .btn-teal:hover { color: #082321; background: #5eead4; }
        .btn-close-white { filter: invert(1) grayscale(100%) brightness(200%); }
        .feedback-success { color: var(--teal); }
        .feedback-error { color: #fb7185; }
        #historyChart { max-height: 390px; }
        @media (max-width: 760px) {
            .sidebar { width: 76px; padding: 18px 8px; }
            .sidebar-brand { padding: 5px 0 15px; }
            .brand-emblem { width: 58px; height: 58px; margin-bottom: 10px; object-fit: cover; object-position: center 35%; }
            .sidebar-brand h1, .sidebar-brand p { display: none; }
            .sidebar .nav-link { justify-content: center; padding: 12px 4px; font-size: 0; }
            .sidebar .nav-link i { margin: 0 !important; font-size: 1rem; }
            .main-content { margin-left: 76px; padding: 24px 16px 85px; }
            .overview-top { align-items: flex-start; }
            .status-row { gap: 7px; }
            .status-pill { padding: 6px 10px; font-size: .68rem; }
        }
        @media (max-width: 420px) {
            .metric-row { gap: 8px; }
            .metric-top { display: block; }
            .metric-label { display: block; margin-top: 4px; }
            .metric-value { font-size: 1.05rem; }
            .server-card { padding: 13px 12px; }
        }
    </style>
</head>
<body>

    <aside class="sidebar">
        <div class="sidebar-brand">
            <img class="brand-emblem" src="/static/hivemind-logo.png" alt="HiveMind Metrics">
        </div>
        <nav class="nav flex-column" aria-label="Main navigation">
            <a class="nav-link active" href="#" id="nav-dashboard" onclick="showView('dashboard'); return false;">
                <i class="fas fa-th-large" aria-hidden="true"></i> Dashboard
            </a>
            <a class="nav-link" href="#" id="nav-admin" onclick="showView('admin'); return false;">
                <i class="fas fa-user-cog" aria-hidden="true"></i> Admin
            </a>
            <form id="logoutForm" method="POST" action="/logout">
                <button class="nav-link logout w-100 border-0 bg-transparent text-start" type="submit">
                    <i class="fas fa-sign-out-alt" aria-hidden="true"></i> Log out
                </button>
            </form>
        </nav>
    </aside>

    <main class="main-content">
        <section id="dashboard-view">
            <div class="overview-top">
                <h2 class="page-heading">Overview</h2>
                <span class="status-pill pill-updated"><i class="fas fa-sync-alt" aria-hidden="true"></i><span id="stat-updated">Updated just now</span></span>
            </div>
            <div class="status-row">
                <span class="status-pill pill-online"><i class="fas fa-circle" aria-hidden="true"></i><span id="stat-online">Loading...</span></span>
                <span class="status-pill pill-warning"><i class="fas fa-exclamation-triangle" aria-hidden="true"></i><span id="stat-warning">Loading...</span></span>
            </div>
            <div class="filter-row" role="group" aria-label="Filter servers">
                <button class="filter-btn active" type="button" data-server-filter="all">All</button>
                <button class="filter-btn" type="button" data-server-filter="alerts">Alerts</button>
                <button class="filter-btn" type="button" data-server-filter="offline">Offline</button>
            </div>
            <div id="global-alerts" role="status" aria-live="polite"></div>
            <div id="server-grid">
                <div class="empty-state"><i class="fas fa-spinner fa-spin me-2" aria-hidden="true"></i>Loading servers...</div>
            </div>
        </section>

        <section id="admin-view" style="display: none;">
            <h2 class="page-heading admin-title">Admin Settings</h2>
            <div class="admin-tabs" role="tablist">
                <button class="admin-tab active" data-admin-tab="thresholds" type="button">Alert thresholds</button>
                <button class="admin-tab" data-admin-tab="notifications" type="button">Notifications</button>
                <button class="admin-tab" data-admin-tab="users" type="button">Users</button>
            </div>
            <section class="admin-card" id="tab-thresholds">
                <h4>Alert thresholds (%)</h4>
                <form id="thresholdForm" class="row g-3">
                    <div class="col-md-4"><label class="form-label" for="cpuWarning">CPU warning</label><input class="form-control" id="cpuWarning" type="number" min="0" max="100" required></div>
                    <div class="col-md-4"><label class="form-label" for="cpuCritical">CPU critical</label><input class="form-control" id="cpuCritical" type="number" min="0" max="100" required></div>
                    <div class="col-md-4"><label class="form-label" for="ramWarning">RAM warning</label><input class="form-control" id="ramWarning" type="number" min="0" max="100" required></div>
                    <div class="col-md-4"><label class="form-label" for="ramCritical">RAM critical</label><input class="form-control" id="ramCritical" type="number" min="0" max="100" required></div>
                    <div class="col-md-4"><label class="form-label" for="diskWarning">Disk warning</label><input class="form-control" id="diskWarning" type="number" min="0" max="100" required></div>
                    <div class="col-md-4"><label class="form-label" for="diskCritical">Disk critical</label><input class="form-control" id="diskCritical" type="number" min="0" max="100" required></div>
                    <div class="col-12"><button class="btn btn-teal px-4 py-2 rounded-3" type="submit">Save thresholds</button><span id="thresholdFeedback" class="ms-3 small"></span></div>
                </form>
            </section>
            <section class="admin-card" id="tab-notifications" style="display: none;">
                <h4>External notifications</h4>
                <p class="admin-note mb-4">Configure a notification email address. Email delivery is not configured by this app.</p>
                <form id="notificationForm" class="row g-3">
                    <div class="col-md-6"><label class="form-label" for="inputNotifyEmail">Notification email address</label><input class="form-control" id="inputNotifyEmail" type="email" placeholder="admin@example.com"></div>
                    <div class="col-12"><button class="btn btn-teal px-4 py-2 rounded-3" type="submit">Save settings</button><span id="notifyFeedback" class="ms-3 small"></span></div>
                </form>
            </section>
            <section class="admin-card" id="tab-users" style="display: none;">
                <h4>Users</h4>
                <p class="admin-note mb-0">Create dashboard accounts with the project's user setup utility.</p>
            </section>
        </section>
    </main>

    <button class="btn add-btn" data-bs-toggle="modal" data-bs-target="#addServerModal" aria-label="Add server" title="Add server">
        <i class="fas fa-plus fa-lg" aria-hidden="true"></i>
    </button>

    <div class="modal fade" id="addServerModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-plus-circle me-2"></i>Add server</h5>
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
                            <div class="form-text">For this machine, use localhost or its hostname; SSH is not used.</div>
                        </div>
                        <button type="submit" class="btn btn-primary" id="submitServerBtn">Add Server</button>
                    </form>
                    <div id="formFeedback" class="mt-2"></div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="historyModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">History: <span id="historyServerName"></span></h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="historyLoading" class="text-center text-muted py-4">Loading history...</div>
                    <div id="historyError" class="alert alert-danger d-none"></div>
                    <div id="historyEmpty" class="alert alert-secondary d-none">No historical data yet.</div>
                    <div id="historyChartWrapper" class="d-none"><canvas id="historyChart" height="120"></canvas></div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let THRESHOLDS = { cpu_warning: 80, cpu_critical: 95, ram_warning: 85, ram_critical: 95, disk_warning: 80, disk_critical: 90 };
        let currentChart = null;
        let historyRefreshTimer = null;
        const EST_TIME_ZONE = 'Etc/GMT+5';

        function formatEstTime(value = new Date()) {
            const time = new Intl.DateTimeFormat('en-US', {
                timeZone: EST_TIME_ZONE,
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit'
            }).format(new Date(value));
            return `${time} EST`;
        }

        function showView(view) {
            document.getElementById('dashboard-view').style.display = view === 'dashboard' ? 'block' : 'none';
            document.getElementById('admin-view').style.display = view === 'admin' ? 'block' : 'none';
            document.getElementById('nav-dashboard').classList.toggle('active', view === 'dashboard');
            document.getElementById('nav-admin').classList.toggle('active', view === 'admin');
        }

        function switchAdminTab(tab) {
            document.querySelectorAll('[data-admin-tab]').forEach(button => {
                button.classList.toggle('active', button.dataset.adminTab === tab);
            });
            ['thresholds', 'notifications', 'users'].forEach(name => {
                document.getElementById(`tab-${name}`).style.display = name === tab ? 'block' : 'none';
            });
        }

        function showFeedback(elementId, message, isError = false) {
            const element = document.getElementById(elementId);
            element.textContent = message;
            element.className = `ms-3 small ${isError ? 'text-danger' : 'text-success'}`;
        }

        async function loadAdminSettings() {
            const response = await fetch('/admin/settings');
            if (response.status === 401) {
                window.location.href = '/login';
                return;
            }
            if (!response.ok) throw new Error('Failed to load admin settings');
            const settings = await response.json();
            THRESHOLDS = settings.thresholds;
            document.getElementById('inputNotifyEmail').value = settings.notification_email;
            Object.entries({
                cpu_warning: 'cpuWarning', cpu_critical: 'cpuCritical',
                ram_warning: 'ramWarning', ram_critical: 'ramCritical',
                disk_warning: 'diskWarning', disk_critical: 'diskCritical'
            }).forEach(([key, id]) => { document.getElementById(id).value = THRESHOLDS[key]; });
        }

        document.querySelectorAll('[data-admin-tab]').forEach(button => {
            button.addEventListener('click', () => switchAdminTab(button.dataset.adminTab));
        });

        let serverFilter = 'all';
        const metricSamples = new Map();
        document.querySelectorAll('[data-server-filter]').forEach(button => {
            button.addEventListener('click', () => {
                serverFilter = button.dataset.serverFilter;
                document.querySelectorAll('[data-server-filter]').forEach(filterButton => {
                    filterButton.classList.toggle('active', filterButton === button);
                });
                loadDashboard();
            });
        });

        document.getElementById('thresholdForm').addEventListener('submit', async event => {
            event.preventDefault();
            const thresholds = {
                cpu_warning: Number(document.getElementById('cpuWarning').value),
                cpu_critical: Number(document.getElementById('cpuCritical').value),
                ram_warning: Number(document.getElementById('ramWarning').value),
                ram_critical: Number(document.getElementById('ramCritical').value),
                disk_warning: Number(document.getElementById('diskWarning').value),
                disk_critical: Number(document.getElementById('diskCritical').value)
            };
            try {
                const response = await fetch('/admin/settings/thresholds', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(thresholds)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save thresholds');
                THRESHOLDS = result.thresholds;
                showFeedback('thresholdFeedback', 'Thresholds saved.');
                loadDashboard();
            } catch (error) {
                showFeedback('thresholdFeedback', error.message, true);
            }
        });

        document.getElementById('notificationForm').addEventListener('submit', async event => {
            event.preventDefault();
            try {
                const response = await fetch('/admin/settings/email', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: document.getElementById('inputNotifyEmail').value })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save notification settings');
                showFeedback('notifyFeedback', 'Settings saved.');
            } catch (error) {
                showFeedback('notifyFeedback', error.message, true);
            }
        });

        function checkMetrics(cpu, ram, disk) {
            let alerts = [];
            if (Number.isFinite(cpu)) {
                if (cpu >= THRESHOLDS.cpu_critical) alerts.push(`CRITICAL: CPU ${cpu}%`);
                else if (cpu >= THRESHOLDS.cpu_warning) alerts.push(`WARNING: CPU ${cpu}%`);
            }
            if (Number.isFinite(ram)) {
                if (ram >= THRESHOLDS.ram_critical) alerts.push(`CRITICAL: RAM ${ram}%`);
                else if (ram >= THRESHOLDS.ram_warning) alerts.push(`WARNING: RAM ${ram}%`);
            }
            if (Number.isFinite(disk)) {
                if (disk >= THRESHOLDS.disk_critical) alerts.push(`CRITICAL: Disk ${disk}%`);
                else if (disk >= THRESHOLDS.disk_warning) alerts.push(`WARNING: Disk ${disk}%`);
            }
            return alerts;
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, character => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            })[character]);
        }

        function renderMetric(serverId, label, value, warning, critical) {
            if (!Number.isFinite(value)) {
                return `<div class="metric">
                            <div class="metric-top"><span class="metric-value metric-empty">--</span><span class="metric-label">${label}</span></div>
                            <div class="metric-label mt-2">No data</div>
                        </div>`;
            }

            const percent = Math.max(0, Math.min(100, value));
            const color = percent >= critical ? '#fb7185' : percent >= warning ? '#fbbf24' : '#2dd4bf';
            const key = `${serverId}:${label}`;
            const samples = metricSamples.get(key) || [];
            samples.push(percent);
            if (samples.length > 24) samples.shift();
            metricSamples.set(key, samples);
            const points = samples.map((sample, index) => {
                const x = samples.length === 1 ? 120 : index * 120 / (samples.length - 1);
                const y = 27 - sample * 0.24;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(' ');

            return `<div class="metric">
                        <div class="metric-top"><span class="metric-value">${percent.toFixed(0)}%</span><span class="metric-label">${label}</span></div>
                        <svg class="sparkline" viewBox="0 0 120 30" preserveAspectRatio="none" aria-hidden="true">
                            <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>
                        </svg>
                    </div>`;
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
                    grid.innerHTML = `<div class="empty-state"><i class="fas fa-server mb-2" aria-hidden="true"></i><br>No servers registered yet. Use the + button to add one.</div>`;
                    document.getElementById('stat-online').textContent = '0 online';
                    document.getElementById('stat-warning').textContent = '0 need attention';
                    document.getElementById('stat-updated').textContent = 'Updated just now';
                    document.getElementById('global-alerts').textContent = '';
                    return;
                }

                let cardsHtml = '';
                let onlineCount = 0;
                let warningCount = 0;
                const cards = [];

                        const results = await Promise.all(
            servers.map(async server => {
                try {
                    const response = await fetch(
                        `/servers/${server.id}/health`
                    );

                    if (!response.ok) {
                        throw new Error("Health request failed");
                    }

                    return {
                        ...server,
                        health: await response.json()
                    };
                } catch {
                    return {
                        ...server,
                        health: { status: "offline" }
                    };
                }
            })
        );

        results.forEach(server => {
            const health = server.health;

            const metrics = {
                cpu: health.cpu_percent ?? 0,
                ram: health.ram_percent ?? 0,
                disk: health.disk_percent ?? 0
            };

            server.status = health.status;
                    const alerts = checkMetrics(metrics.cpu, metrics.ram, metrics.disk);
                    const isOffline = server.status !== 'online';
                    const hasMetrics = Number.isFinite(metrics.cpu) || Number.isFinite(metrics.ram) || Number.isFinite(metrics.disk);
                    const needsAttention = isOffline || alerts.length > 0;
                    const isCritical = isOffline || alerts.some(alert => alert.includes('CRITICAL'));
                    const cardState = isOffline ? 'offline' : isCritical ? 'critical' : alerts.length ? 'warning' : 'healthy';
                    if (server.status === 'online') onlineCount += 1;
                    if (needsAttention) warningCount += 1;

                    cardsHtml += `
                        <article class="server-card server-card-${cardState}" data-server-state="${cardState}">
                            <div class="server-card-top">
                                <div>
                                    <h3 class="server-name">${escapeHtml(server.name)}</h3>
                                    <span class="server-address">${escapeHtml(server.hostname)} : ${escapeHtml(server.ssh_port)}</span>
                                </div>
                                <div class="server-actions">
                                    <span class="server-state state-${cardState}"><i class="fas fa-circle" aria-hidden="true"></i>${cardState}</span>
                                    <button class="icon-btn history-btn" data-id="${server.id}" data-name="${escapeHtml(server.name)}" title="View history" aria-label="View history for ${escapeHtml(server.name)}">
                                        <i class="fas fa-chart-line" aria-hidden="true"></i>
                                    </button>
                                    <button class="icon-btn delete-btn" data-id="${server.id}" data-name="${escapeHtml(server.name)}" title="Delete server" aria-label="Delete ${escapeHtml(server.name)}">
                                        <i class="fas fa-trash" aria-hidden="true"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="metric-row">
                                ${renderMetric(server.id, 'CPU', metrics.cpu, THRESHOLDS.cpu_warning, THRESHOLDS.cpu_critical)}
                                ${renderMetric(server.id, 'RAM', metrics.ram, THRESHOLDS.ram_warning, THRESHOLDS.ram_critical)}
                                ${renderMetric(server.id, 'Disk', metrics.disk, THRESHOLDS.disk_warning, THRESHOLDS.disk_critical)}
                            </div>
                            <div class="server-footer">
                                <span>${hasMetrics ? (alerts.length ? escapeHtml(alerts[0]) : 'All metrics within thresholds') : 'Waiting for first health sample'}</span>
                                <span>${server.logged_at ? `Updated ${formatEstTime(server.logged_at)}` : 'No sample yet'}</span>
                            </div>
                        </article>
                    `;
                    cards.push({
                        html: cardsHtml,
                        state: cardState,
                        needsAttention,
                        isOffline
                    });
                    cardsHtml = '';
                });

                grid.innerHTML = cards
                    .filter(card => serverFilter === 'all'
                        || (serverFilter === 'alerts' && card.needsAttention)
                        || (serverFilter === 'offline' && card.isOffline))
                    .map(card => card.html)
                    .join('') || `<div class="empty-state">No servers match this filter.</div>`;

                document.getElementById('stat-online').textContent = `${onlineCount} online`;
                document.getElementById('stat-warning').textContent = `${warningCount} need attention`;
                document.getElementById('stat-updated').textContent = `Updated ${formatEstTime()}`;
                document.getElementById('global-alerts').textContent = '';
            } catch (error) {
                document.getElementById('server-grid').innerHTML = `<div class="empty-state text-danger">Failed to load servers: ${escapeHtml(error.message)}</div>`;
                document.getElementById('global-alerts').textContent = 'Could not refresh server health. Check the connection and try again.';
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

            document.addEventListener('DOMContentLoaded', () => {
        loadDashboard();

        setInterval(loadDashboard, 5000);
    });
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
    health_task = asyncio.create_task(collect_health())
    try:
        yield
    finally:
        health_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_task

# Pass the lifespan function to your FastAPI app instance
app = FastAPI(lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
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


class EmailSettings(BaseModel):
    email: str


class ThresholdSettings(BaseModel):
    cpu_warning: int = Field(ge=0, le=100)
    cpu_critical: int = Field(ge=0, le=100)
    ram_warning: int = Field(ge=0, le=100)
    ram_critical: int = Field(ge=0, le=100)
    disk_warning: int = Field(ge=0, le=100)
    disk_critical: int = Field(ge=0, le=100)


@app.get("/admin/settings")
def get_admin_settings(request: Request):
    require_login(request)
    return {
        "notification_email": NOTIFICATION_SETTINGS["notification_email"],
        "thresholds": THRESHOLDS,
    }


@app.post("/admin/settings/email")
def update_email_settings(settings: EmailSettings, request: Request):
    require_login(request)
    email = settings.email.strip()
    if email and (len(email) > 254 or "@" not in email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    NOTIFICATION_SETTINGS["notification_email"] = email
    return {"message": "Settings updated", "email": email}


@app.post("/admin/settings/thresholds")
def update_threshold_settings(settings: ThresholdSettings, request: Request):
    require_login(request)
    values = settings.model_dump()
    for metric in ("cpu", "ram", "disk"):
        if values[f"{metric}_warning"] >= values[f"{metric}_critical"]:
            raise HTTPException(
                status_code=400,
                detail=f"{metric.upper()} critical threshold must be higher than its warning threshold.",
            )
    THRESHOLDS.update(values)
    return {"message": "Thresholds updated", "thresholds": THRESHOLDS}


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

@app.get("/servers/{server_id}/health")
def get_server_health(server_id: int, request: Request):
    require_login(request)

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, name, hostname, ssh_port "
                "FROM servers WHERE id = %s",
                (server_id,)
            )
            server = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if not server:
        raise HTTPException(404, "Server not found")

    # Windows host: collect local metrics
    import socket

    if server["hostname"].lower() == socket.gethostname().lower():
        return {
            "status": "online",
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(
                os.path.abspath(os.sep)
            ).percent
        }

    # Ubuntu VM: collect remote metrics through SSH
    try:
        # Select SSH username based on the remote server
                # SSH usernames for each remote server
        ssh_usernames = {
            "192.168.56.101": "seed",
            "192.168.56.10": "kali"
        }

        ssh_username = ssh_usernames.get(
            server["hostname"]
        )

        if not ssh_username:
            raise SSHMonitorError(
                f"No SSH username configured for {server['hostname']}"
            )

        metrics = get_remote_health(
            hostname=server["hostname"],
            username=ssh_username,
            port=server["ssh_port"]
        )

        return {"status": "online", **metrics}

    except (SSHMonitorError, KeyError):
        return {
            "status": "offline",
            "cpu_percent": None,
            "ram_percent": None,
            "disk_percent": None
        }
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
        cursor.execute(
            """
            SELECT
                s.id,
                s.name,
                s.hostname,
                s.ssh_port,
                h.cpu_percent,
                h.ram_percent,
                h.disk_percent,
                h.logged_at,
                CASE
                    WHEN h.logged_at IS NULL THEN 'unknown'
                    WHEN h.logged_at < NOW() - INTERVAL 2 MINUTE THEN 'offline'
                    ELSE 'online'
                END AS status
            FROM servers AS s
            LEFT JOIN server_health_log AS h
                ON h.server_id = s.id
                AND h.logged_at = (
                    SELECT MAX(h2.logged_at)
                    FROM server_health_log AS h2
                    WHERE h2.server_id = s.id
                )
            ORDER BY s.id
            """
        )
        servers = cursor.fetchall()
        for server in servers:
            server["logged_at"] = format_est_timestamp(server["logged_at"])
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


@app.get("/servers/{server_id}/metrics")
def get_server_metrics(server_id: int, request: Request):
    """Return the most recently collected metrics in the dashboard's legacy shape."""
    require_login(request)
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT s.name, s.hostname, s.ssh_port, h.cpu_percent, h.ram_percent,
                   h.disk_percent, h.logged_at
            FROM servers AS s
            LEFT JOIN server_health_log AS h
                ON h.server_id = s.id
                AND h.logged_at = (
                    SELECT MAX(h2.logged_at)
                    FROM server_health_log AS h2
                    WHERE h2.server_id = s.id
                )
            WHERE s.id = %s
            """,
            (server_id,),
        )
        server = cursor.fetchone()
        if server is None:
            raise HTTPException(status_code=404, detail="Server not found.")

        cpu = server["cpu_percent"]
        ram = server["ram_percent"]
        disk = server["disk_percent"]
        alerts = []
        if cpu is not None:
            if cpu >= THRESHOLDS["cpu_critical"]:
                alerts.append(f"CRITICAL: CPU {cpu}%")
            elif cpu >= THRESHOLDS["cpu_warning"]:
                alerts.append(f"WARNING: CPU {cpu}%")
        if ram is not None:
            if ram >= THRESHOLDS["ram_critical"]:
                alerts.append(f"CRITICAL: RAM {ram}%")
            elif ram >= THRESHOLDS["ram_warning"]:
                alerts.append(f"WARNING: RAM {ram}%")
        if disk is not None:
            if disk >= THRESHOLDS["disk_critical"]:
                alerts.append(f"CRITICAL: Disk / {disk}%")
            elif disk >= THRESHOLDS["disk_warning"]:
                alerts.append(f"WARNING: Disk / {disk}%")

        return {
            "hostname": server["hostname"],
            "ssh_port": server["ssh_port"],
            "cpu": cpu,
            "ram": ram,
            "cpu_percent": cpu,
            "ram_percent": ram,
            "disk_percent": disk,
            "disks": [] if disk is None else [{"mount": "/", "percent": disk}],
            "alerts": alerts,
            "logged_at": format_est_timestamp(server["logged_at"]),
        }
    except mysql.connector.Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err.msg}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.get("/health/history/{server_id}")
def get_health_history(server_id: int, request: Request, limit: int = 120):
    require_login(request)
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 500.")

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cpu_percent, ram_percent, disk_percent, logged_at
            FROM server_health_log
            WHERE server_id = %s
            ORDER BY logged_at DESC
            LIMIT %s
            """,
            (server_id, limit),
        )
        rows = cursor.fetchall()
        rows.reverse()
        for row in rows:
            row["logged_at"] = format_est_timestamp(row["logged_at"])
        return rows
    except mysql.connector.Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err.msg}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

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

def _is_local_server(hostname: str) -> bool:
    """Return whether a server address identifies this app's machine."""
    normalized_hostname = hostname.strip().strip("[]").rstrip(".").casefold()
    local_hostnames = {
        "localhost",
        "localhost.localdomain",
        socket.gethostname().rstrip(".").casefold(),
        socket.getfqdn().rstrip(".").casefold(),
    }
    if normalized_hostname in local_hostnames:
        return True

    local_addresses = {"127.0.0.1", "::1"}
    for interface_addresses in psutil.net_if_addrs().values():
        for address in interface_addresses:
            value = address.address.split("%", 1)[0]
            try:
                local_addresses.add(ipaddress.ip_address(value).compressed)
            except ValueError:
                continue

    try:
        target_address = ipaddress.ip_address(normalized_hostname).compressed
    except ValueError:
        try:
            resolved_addresses = socket.getaddrinfo(
                normalized_hostname, None, type=socket.SOCK_STREAM
            )
        except socket.gaierror:
            return False
        target_addresses = {
            ipaddress.ip_address(result[4][0].split("%", 1)[0]).compressed
            for result in resolved_addresses
        }
    else:
        target_addresses = {target_address}

    return bool(target_addresses & local_addresses)


def get_local_health() -> dict:
    """Collect CPU, memory, and root-disk usage from the app's own machine."""
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
    return {
        "cpu_percent": round(cpu, 2),
        "ram_percent": round(ram, 2),
        "disk_percent": round(disk, 2),
    }


def collect_health_once():
    """Collect and store one health sample for every registered server."""
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, hostname, ssh_port FROM servers")
            servers = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    if not servers:
        return

    username = os.environ.get("SSH_USER")
    key_filename = os.environ.get("SSH_KEY_FILE") or None

    for server in servers:
        try:
            if _is_local_server(server["hostname"]):
                metrics = get_local_health()
            elif not username:
                logger.error(
                    "Set SSH_USER to collect remote server %s",
                    server["hostname"],
                )
                continue
            else:
                metrics = get_remote_health(
                    hostname=server["hostname"],
                    username=username,
                    port=server["ssh_port"],
                    key_filename=key_filename,
                )
        except (SSHMonitorError, OSError, ValueError) as exc:
            logger.warning(
                "Health collection failed for %s: %s",
                server["hostname"],
                exc,
            )
            continue

        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO server_health_log
                        (server_id, cpu_percent, ram_percent, disk_percent)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        server["id"],
                        metrics["cpu_percent"],
                        metrics["ram_percent"],
                        metrics["disk_percent"],
                    ),
                )
                connection.commit()
            finally:
                cursor.close()
        finally:
            connection.close()


async def collect_health():
    """Periodically collect health metrics for all configured servers."""
    while True:
        loop = asyncio.get_running_loop()
        collection_started = loop.time()
        try:
            await asyncio.to_thread(collect_health_once)
        except mysql.connector.Error:
            logger.exception("Health collection database error")
        elapsed = loop.time() - collection_started
        await asyncio.sleep(max(0, HEALTH_POLL_INTERVAL - elapsed))


# ---------- Protected Dashboard Page ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=302)
    return HTML_TEMPLATE.replace(
        "%%HEALTH_REFRESH_INTERVAL_MS%%",
        str(HEALTH_POLL_INTERVAL * 1000),
    )
