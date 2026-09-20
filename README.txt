========================================================================
 HOME SERVER HEALTH DASHBOARD
 README.txt
========================================================================

 A centralized monitoring dashboard for tracking resource utilization
 (CPU, memory, disk) across local servers and containers, with a
 rule-based alerting system and a web-based user interface.

 Built with: Python, FastAPI, MySQL (XAMPP), Bootstrap 5
========================================================================


------------------------------------------------------------------------
 1. PROJECT OVERVIEW
------------------------------------------------------------------------

The Health Dashboard is a web-based tool that:

  - Connects to a MySQL database of registered servers.
  - Displays each server as a card in a live dashboard.
  - Shows CPU, RAM, and Disk usage with visual progress bars.
  - Automatically flags WARNING and CRITICAL alerts when metrics
    exceed predefined thresholds.
  - Allows users to add new servers through a validated form.

This is the frontend + API foundation. SSH monitoring, container
management, and LLM diagnosis will be layered on top in later sprints.


------------------------------------------------------------------------
 2. PREREQUISITES
------------------------------------------------------------------------

Before running this project, make sure you have:

  [1] Python 3.8 or newer
      - Download from https://www.python.org/downloads/
      - IMPORTANT: Check "Add Python to PATH" during installation.

  [2] XAMPP (for MySQL)
      - Download from https://www.apachefriends.org/
      - Only the MySQL module is required.

  [3] PyCharm (recommended IDE)
      - Download from https://www.jetbrains.com/pycharm/

  [4] Required Python packages:
      - fastapi
      - uvicorn
      - mysql-connector-python


------------------------------------------------------------------------
 3. SETUP INSTRUCTIONS
------------------------------------------------------------------------

--- STEP 1: Start MySQL in XAMPP ----------------------------------------

  - Open the XAMPP Control Panel.
  - Click "Start" next to the MySQL module.
  - (Optional) Click "Admin" next to MySQL to open phpMyAdmin at
    http://localhost/phpmyadmin

--- STEP 2: Create the Database -----------------------------------------

  In phpMyAdmin:

    1. Click "New" in the left sidebar.
    2. Name the database:  Health Dashboard
    3. Click "Create".

--- STEP 3: Create the servers Table ------------------------------------

  Select the "Health Dashboard" database, then click the "SQL" tab
  and run the following:

    CREATE TABLE `servers` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `NAME` varchar(100) NOT NULL,
      `hostname` varchar(255) NOT NULL,
      `ssh_port` int(11) DEFAULT 22,
      `os_type` varchar(50) DEFAULT NULL,
      `os_version` varchar(100) DEFAULT NULL,
      `STATUS` varchar(30) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_general_ci;

--- STEP 4: Install Python Packages -------------------------------------

  Open the Terminal in PyCharm (bottom of the window) and run:

      py -m pip install fastapi uvicorn mysql-connector-python

  If "py" is not recognized, use:

      python -m pip install fastapi uvicorn mysql-connector-python

  Alternatively, use PyCharm's built-in installer:
      File -> Settings -> Project -> Python Interpreter -> "+" button
      Search for and install each package individually.


------------------------------------------------------------------------
 4. PROJECT FILES
------------------------------------------------------------------------

  HealthDashboard/
  |
  |-- main.py          The FastAPI application (API + dashboard HTML)
  |-- database.py      MySQL connection helper
  |-- README.txt       This file
  |
  |-- venv/            Python virtual environment (auto-generated)


------------------------------------------------------------------------
 5. HOW TO RUN
------------------------------------------------------------------------

  [1] Make sure XAMPP's MySQL module is running.

  [2] In the PyCharm terminal, from the project root, run:

          py -m uvicorn main:app --reload

      (Use "python -m uvicorn" if "py" doesn't work.)

  [3] If successful, you will see output like:

          INFO:     Uvicorn running on http://127.0.0.1:8000
          INFO:     Application startup complete.

  [4] Open your browser and go to:

          http://127.0.0.1:8000/dashboard

      You should now see the Health Dashboard.

  NOTE: Keep the terminal open while using the dashboard. Closing it
        stops the server. Press CTRL+C to stop the server manually.


------------------------------------------------------------------------
 6. HOW THE CODE WORKS
------------------------------------------------------------------------

--- database.py --------------------------------------------------------

  Provides a single function, get_connection(), which returns a live
  MySQL connection using the mysql-connector-python library. Every
  API route that touches the database calls this function, uses the
  connection, and closes it when done.

  Connection settings:
      host:     127.0.0.1
      user:     root
      password: (empty - default for XAMPP)
      database: Health Dashboard

--- main.py ------------------------------------------------------------

  This file contains the entire application: the FastAPI backend and
  the HTML/JavaScript frontend served as a single string.

  A) API ENDPOINTS
  ----------------

     GET  /               Health check.
                          Returns: {"message": "Health Dashboard API
                          is running"}

     GET  /servers        Returns all servers from the database as
                          JSON. Used by the dashboard to build the
                          server cards.

     POST /servers        Adds a new server.
                          Request body (JSON):
                              {
                                "name": "web-server-01",
                                "hostname": "192.168.1.10",
                                "ssh_port": 22
                              }
                          Inserts a row into the servers table with
                          status = "Unknown".

     GET  /dashboard      Returns the full dashboard HTML page.

  B) THE DASHBOARD (HTML_TEMPLATE)
  --------------------------------

     The dashboard is a Bootstrap 5 page with three main parts:

       1. NAVBAR
          The dark bar at the top with the app name and a "Live"
          indicator.

       2. GLOBAL ALERT SUMMARY
          A colored banner below the navbar that says either
          "All systems healthy" or "N alert(s) detected".

       3. SERVER GRID
          A responsive grid of cards, one per server. Each card
          shows:
            - Server name and status badge (ONLINE/OFFLINE)
            - Hostname and SSH port
            - CPU / RAM / Disk percentages with progress bars
            - Per-card alerts (if any)

       4. FLOATING "+" BUTTON
          Opens a modal to add a new server.

  C) JAVASCRIPT LOGIC
  -------------------

     generateMetrics()
         Simulates CPU/RAM/Disk values with random numbers.
         -> This is a placeholder. In a later sprint, this will be
            replaced with real metrics pulled from the SSH backend.

     checkMetrics(cpu, ram, disk)
         Compares values against THRESHOLDS and returns an array of
         alert strings. Thresholds:

             CPU  warning: 80%   critical: 95%
             RAM  warning: 85%   critical: 95%
             Disk warning: 80%   critical: 90%

     loadDashboard()
         Fetches /servers, builds one HTML card per server, injects
         them into the grid, and updates the global alert banner.

     Add Server Form Handler
         When the user submits the "Add Server" modal:
           1. Validates the form client-side (name >= 3 chars,
              hostname required, port 1-65535).
           2. Sends a POST request to /servers with JSON data.
           3. On success: closes the modal and refreshes the
              dashboard so the new server appears.
           4. On failure: shows the error message inside the modal.


------------------------------------------------------------------------
 7. HOW ALERTS WORK
------------------------------------------------------------------------

  Alerts are generated in two places:

    FRONTEND (JavaScript)
        Each time the dashboard loads, mock metrics are generated
        and compared to the THRESHOLDS object. Any value above a
        warning or critical threshold triggers an alert.

    FUTURE (BACKEND)
        In later sprints, alerts will be computed server-side based
        on real SSH-collected metrics and stored in the database for
        historical review.

  Alert Levels:
      HEALTHY    ->  All metrics below warning thresholds
      WARNING    ->  A metric crossed its warning threshold
      CRITICAL   ->  A metric crossed its critical threshold

  Alerts appear:
      - Individually on the affected server's card.
      - Collected in the global summary banner at the top.


------------------------------------------------------------------------
 8. TROUBLESHOOTING
------------------------------------------------------------------------

  ERROR: "pip is not recognized"
    FIX: Use "py -m pip install ..." instead of "pip install ...".

  ERROR: "python was not found"
    FIX: Use "py" instead of "python", or reinstall Python and check
         "Add Python to PATH".

  ERROR: "uvicorn is not recognized"
    FIX: Use "py -m uvicorn main:app --reload" instead of
         "uvicorn main:app --reload".

  ERROR: "ModuleNotFoundError: No module named 'fastapi'"
    FIX: The package isn't installed in the active environment.
         Run: py -m pip install fastapi uvicorn mysql-connector-python

  ERROR: "ModuleNotFoundError: No module named 'database'"
    FIX: Make sure database.py exists in the same folder as main.py.

  ERROR: "Can't connect to MySQL server on '127.0.0.1:3306'"
    FIX: XAMPP's MySQL module is not running. Start it from the XAMPP
         Control Panel.

  ERROR: "Access denied for user 'root'@'localhost'"
    FIX: Your XAMPP MySQL password may not be empty. Update the
         password in database.py.

  ERROR (Browser): "127.0.0.1 refused to connect" / ERR_CONNECTION_REFUSED
    FIX: The FastAPI server is not running. Start it with
         "py -m uvicorn main:app --reload" and leave the terminal open.

  ERROR: "Unknown database 'Health Dashboard'"
    FIX: The database wasn't created. Follow Step 2 in the setup
         section above.


------------------------------------------------------------------------
 9. NEXT STEPS (FUTURE SPRINTS)
------------------------------------------------------------------------

  - Replace mock metrics with real SSH-collected data.
  - Add container discovery and start/stop/restart controls.
  - Store historical metrics in MySQL and add time-range graphs.
  - Expand the alert system with backend thresholds and event logs.
  - Integrate an LLM for automated problem diagnosis.


========================================================================
 END OF README
========================================================================