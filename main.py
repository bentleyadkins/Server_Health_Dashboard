from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import get_connection
from alerts import get_system_health

app = FastAPI()


class ServerCreate(BaseModel):
    name: str
    hostname: str
    ssh_port: int = 22


# Check that the API is running
@app.get("/")
def home():
    return {"message": "Health Dashboard API is running"}


# View all saved servers
@app.get("/servers")
def get_servers():
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM servers")
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()


# Add a server
@app.post("/servers", status_code=201)
def add_server(server: ServerCreate):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            sql = """
                INSERT INTO servers (name, hostname, ssh_port, status)
                VALUES (%s, %s, %s, %s)
            """

            values = (
                server.name,
                server.hostname,
                server.ssh_port,
                "Unknown"
            )

            cursor.execute(sql, values)
            connection.commit()

            return {
                "message": "Server added successfully!",
                "id": cursor.lastrowid
            }
        finally:
            cursor.close()
    finally:
        connection.close()


# Delete a server by its ID
@app.delete("/servers/{server_id}")
def delete_server(server_id: int):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM servers WHERE id = %s",
                (server_id,)
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Server not found"
                )

            connection.commit()

            return {
                "message": "Server deleted successfully!",
                "id": server_id
            }
        finally:
            cursor.close()
    finally:
        connection.close()


# View health readings from the computer running FastAPI
@app.get("/health")
def health():
    return get_system_health()
