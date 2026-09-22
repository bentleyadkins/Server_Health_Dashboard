========================================================================
 HOME SERVER HEALTH DASHBOARD
 README.txt
========================================================================

 A centralized monitoring dashboard for tracking resource utilization
 (CPU, memory, disk) across local servers, with a rule-based alerting
 system, user authentication, and a web-based user interface.

 Built with: Python, FastAPI, MySQL (XAMPP), Bootstrap 5
========================================================================


------------------------------------------------------------------------
 1. PROJECT OVERVIEW
------------------------------------------------------------------------

The Health Dashboard is a web-based tool that:

  - Requires login before any dashboard or API access.
  - Connects to a MySQL database of registered servers.
  - Displays each server as a card in a live dashboard.
  - Shows CPU, RAM, and Disk usage with visual progress bars.
  - Automatically flags WARNING and CRITICAL alerts when metrics
    exceed predefined thresholds.
  - Allows adding new servers through a validated form.
  - Allows deleting servers with a confirmation prompt.

This is the frontend + API + auth foundation. SSH monitoring,
container management, and LLM diagnosis will be layered on top in
later sprints.


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
      - bcrypt                (password hashing)
      - itsdangerous          (session cookie signing)
      - python-multipart      (form handling for login)


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
    2. Name the database:  health_dashboard
    3. Collation: utf8mb4_general_ci
    4. Click "Create".

  NOTE: The database name must match what's in database.py.

--- STEP 3: Create the Tables -------------------------------------------

  Select the "health_dashboard" database, then click the "SQL" tab
  and run the following statements one at a time.

  --- servers table ---

    CREATE TABLE `servers` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `NAME` varchar(100) NOT NULL,
      `hostname` varchar(255) NOT NULL,
      `ssh_port` int(11) DEFAULT 22,
      `os_type` varchar(50) DEFAULT NULL,
      `os_version` varchar(100) DEFAULT NULL,
      `STATUS` varchar(30) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_general_ci;

  --- users table ---

    CREATE TABLE `users` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `username` varchar(50) NOT NULL UNIQUE,
      `password_hash` varchar(255) NOT NULL,
      `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COLLATE=utf8mb4_general_ci;

--- STEP 4: Install Python Packages -------------------------------------

  Open the Terminal in PyCharm (bottom of the window) and run:

      py -m pip install fastapi uvicorn mysql-connector-python bcrypt itsdangerous python-multipart

  If "py" is not recognized, use:

      python -m pip install fastapi uvicorn mysql-connector-python bcrypt itsdangerous python-multipart

  Alternatively, use PyCharm's built-in installer:
      File -> Settings -> Project -> Python Interpreter -> "+" button

--- STEP 5: Create the Admin User ---------------------------------------

  The dashboard requires a login. Create one admin user by running:

      py create_user.py

  You'll be prompted for a username and password.

  NOTE: The password field hides characters as you type (this is
  normal). Just type the password, press Enter, then type it again to
  confirm.

  If the prompt appears frozen in PyCharm, run the script from a
  regular Windows Command Prompt instead:

      cd C:\Users\<you>\PycharmProjects\PythonProjects\HealthDashboard
      py create_user.py

  The password is hashed with bcrypt before being stored. It is never
  saved in plain text.

--- STEP 6: Configure the Secret Key ------------------------------------

  Open main.py and find the line:

      SECRET_KEY = "CHANGE-ME-REPLACE-WITH-YOUR-OWN-RANDOM-HEX-STRING"

  Generate your own random key by running this once in a terminal:

      py -c "import secrets; print(secrets.token_hex(32))"

  Copy the output and paste it in place of the placeholder. This key
  signs the session cookie. Keep it private.


------------------------------------------------------------------------
 4. PROJECT FILES
------------------------------------------------------------------------

  HealthDashboard/
  |
  |-- main.py          FastAPI app (API + dashboard + login HTML)
  |-- database.py      MySQL connection helper
  |-- auth.py          Password hashing and verification
  |-- create_user.py   One-time admin user creation script
  |-- README.txt       This file
  |
  |-- venv/            Python virtual environment (not committed)


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

          http://127.0.0.1:8000/login

      Log in with the admin user you created in Step 5. You'll be
      redirected to the dashboard.

  NOTE: Keep the terminal open while using the dashboard. Closing it
        stops the server. Press CTRL+C to stop the server manually.


------------------------------------------------------------------------
 6. HOW THE CODE WORKS
------------------------------------------------------------------------

--- database.py --------------------------------------------------------

  Provides get_connection(), which returns a live MySQL connection.
  Every route that touches the database calls this function, uses
  the connection, and closes it when done.

  Connection settings:
      host:     127.0.0.1
      user:     root
      password: (empty - default for XAMPP)
      database: health_dashboard

--- auth.py ------------------------------------------------------------

  Two helper functions:

    hash_password(password)
        Turns a plain-text password into a bcrypt hash. Used by
        create_user.py when setting up the admin account.

    verify_password(password, password_hash)
        Returns True if the plain-text password matches the stored
        hash. Used by POST /login to check credentials.

  Passwords are never stored or logged in plain text.

--- create_user.py -----------------------------------------------------

  A one-time script that:

    1. Prompts for a username and password (password hidden).
    2. Hashes the password with bcrypt.
    3. Inserts a new row into the users table.

  Run this once to create your admin account. Do not commit real
  credentials to the repository.

--- main.py ------------------------------------------------------------

  This file contains the entire application: FastAPI backend routes
  and the HTML/JavaScript frontend served as strings.

  A) SESSION MIDDLEWARE
  ---------------------

     SessionMiddleware signs the session cookie using SECRET_KEY.
     This prevents users from tampering with their own session.

  B) API ENDPOINTS
  ----------------

     GET  /                Health check.
                           Returns: {"message": "Health Dashboard API
                           is running"}

     GET  /servers         Returns all servers from the database as
                           JSON. Requires login.

     POST /servers         Adds a new server. Requires login.
                           Request body (JSON):
                               {
                                 "name": "web-server-01",
                                 "hostname": "192.168.1.10",
                                 "ssh_port": 22
                               }

     DELETE /servers/{id}  Deletes a server by ID. Requires login.
                           Returns 404 if the ID doesn't exist.

  C) AUTH ENDPOINTS
  -----------------

     GET  /login           Shows the login page.
                           Redirects to /dashboard if already logged in.

     POST /login           Validates credentials against the users
                           table. On success, sets a session cookie
                           and redirects to /dashboard. On failure,
                           shows a generic error.

     POST /logout          Clears the session and redirects to /login.

     GET  /dashboard       Protected. Redirects to /login if not
                           authenticated. Otherwise returns the full
                           dashboard HTML.

  D) THE LOGIN PAGE (LOGIN_TEMPLATE)
  ----------------------------------

     A centered Bootstrap card with username and password fields
     on a dark gradient background. Errors are inserted into the
     %%ERROR%% placeholder.

  E) THE DASHBOARD (HTML_TEMPLATE)
  --------------------------------

     A Bootstrap 5 page with:

       1. NAVBAR
          App name, "Live" indicator, and a Logout button.

       2. GLOBAL ALERT SUMMARY
          Colored banner showing "All systems healthy" or
          "N alert(s) detected".

       3. SERVER GRID
          One card per server, each showing:
            - Server name and status badge (ONLINE/OFFLINE)
            - Hostname and SSH port
            - CPU / RAM / Disk percentages with progress bars
            - Per-card alerts
            - A trash icon to delete the server

       4. FLOATING "+" BUTTON
          Opens a modal to add a new server.

  F) JAVASCRIPT LOGIC
  -------------------

     generateMetrics()
         Simulates CPU/RAM/Disk values with random numbers.
         -> Placeholder. Will be replaced with real SSH metrics in
            a later sprint.

     checkMetrics(cpu, ram, disk)
         Compares values against THRESHOLDS and returns an array of
         alert strings. Thresholds:

             CPU  warning: 80%   critical: 95%
             RAM  warning: 85%   critical: 95%
             Disk warning: 80%   critical: 90%

     loadDashboard()
         Fetches /servers, builds one HTML card per server, injects
         them into the grid, and updates the global alert banner.
         Redirects to /login if the session has expired.

     Add Server Form Handler
         Validates the form client-side, POSTs to /servers, and
         refreshes the dashboard on success.

     Delete Server Handler
         Uses event delegation (so it survives card re-renders).
         Clicking the trash icon shows a confirmation dialog,
         then sends DELETE /servers/{id} and refreshes.

     All fetch() calls read the response as text first, then try
     to parse it as JSON. This prevents cryptic "Unexpected token"
     errors when the backend returns a plain-text 500 page.


------------------------------------------------------------------------
 7. HOW ALERTS WORK
------------------------------------------------------------------------

  Alerts are generated client-side based on the mock metrics.

  Alert Levels:
      HEALTHY    ->  All metrics below warning thresholds
      WARNING    ->  A metric crossed its warning threshold
      CRITICAL   ->  A metric crossed its critical threshold

  Alerts appear:
      - Individually on the affected server's card.
      - Collected in the global summary banner at the top.

  In a later sprint, alerts will be computed server-side based on
  real SSH-collected metrics and stored in the database for
  historical review.


------------------------------------------------------------------------
 8. HOW AUTHENTICATION WORKS
------------------------------------------------------------------------

  Login flow:

    1. User submits username and password to POST /login.
    2. Server looks up the username in the users table.
    3. If found, verify_password() checks the bcrypt hash.
    4. On success, the username is stored in the signed session
       cookie (request.session["user"]).
    5. Browser sends this cookie on every subsequent request.
    6. Protected routes call require_login(request) which raises
       a 401 if the session is missing.
    7. /dashboard checks the session directly and redirects to
       /login if the user isn't authenticated.

  Security notes:

    - Passwords are hashed with bcrypt, never stored in plain text.
    - The session cookie is signed to prevent tampering.
    - Login errors are generic ("Invalid username or password") so
      attackers can't tell whether a username exists.

  Known limitations (intentional scope for this capstone):

    - HTTP only (no HTTPS). Fine for localhost, would need TLS in
      production.
    - No rate limiting on the login endpoint.
    - No registration page, no roles, no password reset.
    - One admin user is sufficient.


------------------------------------------------------------------------
 9. TROUBLESHOOTING
------------------------------------------------------------------------

  ERROR: "pip is not recognized"
    FIX: Use "py -m pip install ..." instead of "pip install ...".

  ERROR: "python was not found"
    FIX: Use "py" instead of "python", or reinstall Python and check
         "Add Python to PATH".

  ERROR: "uvicorn is not recognized"
    FIX: Use "py -m uvicorn main:app --reload" instead of
         "uvicorn main:app --reload".

  ERROR: "ModuleNotFoundError: No module named 'auth'"
    FIX: Make sure auth.py is in the same folder as main.py.

  ERROR: "ModuleNotFoundError: No module named 'bcrypt'"
    FIX: Run: py -m pip install bcrypt itsdangerous python-multipart

  ERROR: "RuntimeError: Form data requires 'python-multipart'"
    FIX: Run: py -m pip install python-multipart

  ERROR: "Can't connect to MySQL server on '127.0.0.1:3306'"
    FIX: XAMPP's MySQL module is not running. Start it from the XAMPP
         Control Panel.

  ERROR: "Unknown database 'health_dashboard'"
    FIX: The database wasn't created. Follow Step 2 in the setup
         section above.

  ERROR: "Table 'health_dashboard.servers' doesn't exist"
    FIX: Open phpMyAdmin, select health_dashboard, and run the
         CREATE TABLE statements from Step 3.

  ERROR: "Table 'health_dashboard.users' doesn't exist"
    FIX: Same as above - run the CREATE TABLE for users.

  ERROR (Browser): "127.0.0.1 refused to connect" / ERR_CONNECTION_REFUSED
    FIX: The FastAPI server is not running. Start it with
         "py -m uvicorn main:app --reload" and leave the terminal open.

  ERROR: Password prompt in create_user.py seems frozen
    FIX: getpass hides input by design - type the password and press
         Enter. If the terminal is genuinely stuck, run the script
         from a Windows Command Prompt instead of PyCharm's terminal.

  ERROR: Login always fails with the correct password
    FIX: Re-run create_user.py to create the user. Check phpMyAdmin's
         users table for the row.

  ERROR (Modal): "Unexpected token 'I', "Internal S"..."
    FIX: The backend returned a 500 error page instead of JSON. Check
         the uvicorn terminal for the traceback. This is prevented in
         the current code by reading responses as text first.

  ERROR: "Not authenticated" (401) in the browser
    FIX: Session expired or missing. Refresh the page, it will
         redirect to /login.

  ERROR: Stuck logged in even after logout
    FIX: Clear cookies for 127.0.0.1:8000 in the browser.


------------------------------------------------------------------------
 10. NEXT STEPS (FUTURE SPRINTS)
------------------------------------------------------------------------

  - Replace mock metrics with real SSH-collected data.
  - Add container discovery and start/stop/restart controls.
  - Store historical metrics in MySQL and add time-range graphs.
  - Expand the alert system with backend thresholds and event logs.
  - Integrate an LLM for automated problem diagnosis.


------------------------------------------------------------------------
 11. QUICK COMMAND REFERENCE
------------------------------------------------------------------------

  Install packages:      py -m pip install fastapi uvicorn mysql-connector-python bcrypt itsdangerous python-multipart

  Create admin user:     py create_user.py

  Generate secret key:   py -c "import secrets; print(secrets.token_hex(32))"

  Run the server:        py -m uvicorn main:app --reload

  Open login page:       http://127.0.0.1:8000/login

  Open API docs:         http://127.0.0.1:8000/docs

  Open phpMyAdmin:       http://localhost/phpmyadmin


========================================================================
 END OF README
========================================================================
