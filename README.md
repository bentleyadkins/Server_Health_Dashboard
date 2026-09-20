# Server_Health_Dashboard

UTC Senior Capstone Project - A dashboard application that monitors the health meterics of servers using XAMPP, Docker, and FastAPI.

## Prerequistes

1. Download XAMPP for hosting the mySQL server on your local machine. If you already have a database you will need to change the parameters in database.py to make the connection.

2. Download Docker Desktop for your machine to host the Docker container.

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

6. Navigate to a browser and open the FastAPI. NOTE -> Ensure 127.0.0.1 is the host connection when debugging
```
http://127.0.0.1:8000/
```

### Linux Setup (Terminal)

<!-- Add setup once VM's installed -->

