from fastapi import APIRouter
from pydantic import BaseModel

from auth import verify_password
from database import get_connection


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(login_data: LoginRequest):
    """
    Verify a user's username and password.

    The stored password hash and salt are retrieved from the
    users table. The entered password is hashed using the
    stored salt and compared with the stored password hash.
    """

    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT username, password_hash, salt
            FROM users
            WHERE username = %s
            LIMIT 1
            """,
            (login_data.username,)
        )

        user = cursor.fetchone()

        # Do not reveal whether the username or password was wrong.
        if user is None:
            return {
                "success": False,
                "message": "Invalid username or password"
            }

        password_is_valid = verify_password(
            login_data.password,
            user["salt"],
            user["password_hash"]
        )

        if not password_is_valid:
            return {
                "success": False,
                "message": "Invalid username or password"
            }

        return {
            "success": True,
            "message": "Login successful",
            "username": user["username"]
        }

    finally:
        if cursor is not None:
            cursor.close()

        if connection.is_connected():
            connection.close()