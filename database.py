import paramiko
import socket
import mysql.connector
from mysql.connector import Error, IntegrityError

def get_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="Health_Dashboard"
    )

def create_tables():
    """
    Create the two tables needed for running 
    the dashboard if they do not already exist.
    """
    connection = get_connection() # Assuming this is defined elsewhere
    cursor = connection.cursor()
    
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
        
        # Explicitly commit the changes (though DDL statements usually auto-commit)
        connection.commit() 
        print("Schemas created successfully.")
        
    except mysql.connector.Error as e:
        print(f"Failed to create schema: {e}")
        
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def get_or_create_main_server():
    """Return the database ID for this laptop, creating its server row once."""
    hostname = socket.gethostname()
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT id FROM servers WHERE hostname = %s LIMIT 1",
            (hostname,)
        )
        server = cursor.fetchone()

        if server is None:
            cursor.execute(
                """
                INSERT INTO servers (name, hostname, ssh_port, status)
                VALUES (%s, %s, %s, %s)
                """,
                ("Laptop", hostname, 0, "Online")
            )
            connection.commit()
            return cursor.lastrowid

        return server[0]
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    create_tables()