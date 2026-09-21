from getpass import getpass

from auth import hash_password
from database import get_connection


def main():
    print("=== Create Admin User ===")
    username = input("Username: ").strip()
    if len(username) < 3:
        print("Username must be at least 3 characters.")
        return

    password = getpass("Password (hidden): ")
    if len(password) < 6:
        print("Password must be at least 6 characters.")
        return

    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, hash_password(password)),
            )
            connection.commit()
            print(f"\n✅ User '{username}' created successfully.")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    main()