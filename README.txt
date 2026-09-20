SETUP PHASE

Download python and xampp for MySQL

Create the Health Dashboard database and its tables using a SQL setup file

Create database.py and main.py and copy the files over

install "py -m pip install fastapi uvicorn mysql-connector-python" in cmd

install psutil if not already (run "py -m pip install psutil")



START THE BACKEND

start the backend with "py -m uvicorn main:app --reload"

Open http://127.0.0.1:8000/docs in your browser (placeholder for dashboard website)

http://127.0.0.1:8000/servers   to show server query


		UPDATES 9/19/26

now have delete and viewing function added into main.py as of 9/19 (operational as of my testing)

to delete you need a valid server id

press try it out and input server id

should be gone in viewing panel and get a terminal notification

should also get 404 error if trying to delete an already gone or nonexistent server

		9/20/26

separated monitoring from main.py

renamed monitoring to alerts.py

updated main.py to call newfound alerts.py

added new health function into main.py 

checked and operational as of 9/20/26








phpMyAdmin url 
http://localhost/phpmyadmin/
