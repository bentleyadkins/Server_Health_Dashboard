import paramiko
import socket
import mysql.connector
from mysql.connector import Error

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
                `id` int(11) NOT NULL AUTO_INCREMENT,
                `log_time` timestamp DEFAULT CURRENT_TIMESTAMP,
                `username` varchar(100) DEFAULT NULL,
                `cpu_percent` float NOT NULL,
                `ram_percent` float NOT NULL,
                `disk_percent` float NOT NULL,
                `net_if_stats` json DEFAULT NULL,
                PRIMARY KEY (`id`)
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

if __name__ == "__main__":
    create_tables()