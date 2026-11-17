# Server Health Dashboard

UTC Senior Capstone Project - A dashboard application that monitors the health meterics of servers using XAMPP, Docker, and Python FastAPI package.

## Prerequistes

1. Download XAMPP for hosting the mySQL server on your local machine. If you already have a database you will need to change the parameters in database.py to make the connection.

[XAMPP Download](https://www.apachefriends.org/download.html)

2. Download Docker Desktop for your machine to host the Docker container.

[Docker (Windows Download)](https://docs.docker.com/desktop/setup/install/windows-install/)

[Docker (Linux Download)](https://docs.docker.com/desktop/setup/install/linux/)

## Quickstart/Docker Build

The quickstart steps will take you through building up the docker container and running the FastAPI application. 

1. Navigate to the Dockerfile Repo and build up the container
```
docker build -t server_heath_dashboard .
```

2. Run the container and expose port 8000 with the FastAPI application
```
docker run -d --name server_health_dashboard -p 8000:8000 server_health_dashboard
```

3. This creates a docker service image spinning up the mysql database
```
docker compose up -d
```

## Development, Testing, Debugging

### Windows Setup (Command Prompt)

1. Install python 3.12.10
```
py install 3.12.10
```

2. Create the .venv
```
py -3.12 -m venv .venv
```

3. Activate .venv
```
.venv\Scripts\activate
```

4. Run requirements.txt for packages
```
pip install -r requirements.txt
```

5. Start the FastAPI application in reload so FastAPI changes happen immediately
```
py -m uvicorn main:app --reload
```

6. Navigate to a browser and open the FastAPI. NOTE -> Ensure 127.0.0.1 is the host connection for the database when debugging
```
http://127.0.0.1:8000/
```

### Local and Remote Server Health Collection

The dashboard uses `psutil` to collect CPU, RAM, and root-disk usage for this
machine when a registered hostname resolves to the machine running FastAPI.
Add it from the dashboard as `localhost`, its computer name, or one of its
local IP addresses. The SSH port is ignored for local collection, and no SSH
environment variables are required when monitoring only this machine.

Other registered Linux servers are monitored over SSH. Before starting
FastAPI, configure the SSH username and, when needed, the private-key path in
the same shell. The configured SSH username is used for every remote server:

```powershell
$env:SSH_USER = "seed"
$env:SSH_KEY_FILE = "$HOME\.ssh\id_ed25519"
$env:HEALTH_POLL_INTERVAL = "3"
py -m uvicorn main:app --reload
```

Health collection and dashboard refresh both default to every 3 seconds. Set
`HEALTH_POLL_INTERVAL` to another number of seconds before starting the app to
change both intervals. A collection that takes longer than the interval starts
the next collection as soon as the current one finishes.

`SSH_KEY_FILE` is optional when SSH agent or default-key authentication is
available. Paramiko verifies host keys using the app user's SSH `known_hosts`
file; add each remote server's host key before collection. Register servers
from the dashboard using their reachable hostname/IP and SSH port. A newly
registered server shows unavailable metrics until its first successful sample.
The dashboard marks readings older than two minutes offline.

When running the app in Docker, the container must be able to reach the remote
servers and access the SSH key and `known_hosts` file securely. Do not copy
private keys into the image. Local metrics collected in Docker describe the
container environment, not necessarily the physical host.

The dashboard's Admin view lets you change CPU, RAM, and disk alert thresholds,
configure a notification email address, and view a server's recent metric
history. Thresholds and the notification address are held in memory and reset
when the app restarts. Email delivery is not configured; saving an address does
not send email.

All dashboard and history timestamps are displayed in fixed Eastern Standard
Time (EST, UTC-05:00), year-round. MySQL connections use UTC for timestamp
storage and comparisons; API timestamps are converted to EST before display.

<!-- Paramiko Setup -->
1. Configure VirtualBox Adapter 2
- Shut down Ubuntu VM.
- VirtualBox → Settings → Network → Adapter 2
- Check Enable Network Adapter.
- Attached to: Host-only Adapter
- Name: VirtualBox Host-Only Ethernet Adapter
- Click OK and start Ubuntu.
2. Find IP addresses
Ubuntu:
hostname -I


Windows PowerShell:
ipconfig


Look for the VirtualBox Host-Only adapter. My Example:
- Windows: 192.168.56.1
- Ubuntu: 192.168.56.101
3. Enable SSH on Ubuntu
sudo apt install openssh-server
sudo systemctl enable --now ssh


4. Generate SSH key on Windows
ssh-keygen -t ed25519 -f "$HOME\.ssh\id_ed25519"
Get-Content "$HOME\.ssh\id_ed25519.pub"


5. Authorize key on Ubuntu
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys


Paste the Windows public key, save, then:
chmod 600 ~/.ssh/authorized_keys


6. Test SSH from Windows
ssh seed@192.168.56.101


Replace the username and IP as needed.
7. Run project in Windows PowerShell
python -m pip install paramiko
docker compose up -d
$env:SSH_HOST="192.168.56.101"
$env:SSH_USER="seed"
python ssh_monitor.py
python -m uvicorn main:app --reload