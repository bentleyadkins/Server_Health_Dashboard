import socket
import mysql.connector
from mysql.connector import Error, IntegrityError

def get_connection():
    """
    Make connection to Health_Dashboard database
    """
    return mysql.connector.connect(
        host="localhost", # Change back to 127.0.0.1 when testing/debugging   (HAD TO REMOVE DOCKER LINE BC IS WAS CAUSING ISSUES WITH MYSQL CONNECTOR)
        user="root",
        password="",
        database="health dashboard"
    )

def create_tables():
    """
    Create the two tables needed for running 
    the dashboard if they do not already exist.
    """
    
    connection = get_connection() # Make connection
    cursor = connection.cursor()  # Executes SQL Statements
    
    try:
        create_server_table = """
            CREATE TABLE IF NOT EXISTS `servers` (
                `id` int(11) NOT NULL AUTO_INCREMENT,
                `NAME` varchar(100) NOT NULL,
                `hostname` varchar(255) NOT NULL,
                `ssh_port` int(11) DEFAULT 22,
                `os_type` varchar(50) DEFAULT NULL,
                `os_version` varchar(100) DEFAULT NULL,
                `STATUS` varchar(30) DEFAULT NULL,
                PRIMARY KEY (`id`)
            ) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
        """

        create_hdlog_table = """
        CREATE TABLE IF NOT EXISTS `server_health_log` (
            `server_id` int NOT NULL,
            `cpu_percent` float NOT NULL,
            `ram_percent` float NOT NULL,
            `disk_percent` float NOT NULL,
            `logged_at` timestamp DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT `fk_server_id` FOREIGN KEY (`server_id`) REFERENCES `servers`(`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
        """
        
        cursor.execute(create_server_table)
        cursor.execute(create_hdlog_table)
        
        connection.commit() # Publish the changes to the database
        print("Schemas created successfully.")
        
    except mysql.connector.Error as e:
        print(f"Failed to create schema: {e}") # Prompts error if failed to create schema

    # Disconnectes the cursor and connection for mysql.connector
    finally:
        if connection and connection.is_connected(): 
            cursor.close()
            connection.close()

def get_or_create_main_server():
    """
    Return the database ID for this server, creating its 
    server row once initialize.
    """
    hostname = socket.gethostname() # Bentley's Laptop
    ipaddress = socket.gethostbyname(hostname) # IP Address of hostname server
    print(ipaddress) # TODO: Implement IP Address into database function
    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Returns the host if one was created. Only allow 1
        cursor.execute(
            "SELECT id FROM servers WHERE hostname = %s LIMIT 1",
            (hostname,)
        )
        server = cursor.fetchone()

        if server is None:
            # If the host server has been created yet, insert into servers table
            cursor.execute(
                """
                INSERT INTO servers (name, hostname, ssh_port, status)
                VALUES (%s, %s, %s, %s)
                """,
                ("Server", hostname, 0, "Online") 
                # TODO: Arbitary Values, need to pull variables in place
            )
            connection.commit()
            return cursor.lastrowid

        return server[0] # Return server at row 1
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    create_tables() # Gets imported into main