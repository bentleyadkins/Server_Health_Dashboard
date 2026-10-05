import base64
import hashlib
import hmac
import secrets


PBKDF2_ITERATIONS = 200_000


def generate_salt(num_bytes: int = 16) -> str:
    """Generate a cryptographically secure random salt."""
    salt = secrets.token_bytes(num_bytes)
    return base64.b64encode(salt).decode("utf-8")


def hash_password(password: str, salt_b64: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    salt = base64.b64decode(salt_b64.encode("utf-8"))

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return base64.b64encode(derived_key).decode("utf-8")


def verify_password(
    password: str,
    salt_b64: str,
    stored_hash_b64: str
) -> bool:
    """Verify an entered password against the stored password hash."""
    try:
        entered_hash = hash_password(password, salt_b64)

        return hmac.compare_digest(
            entered_hash,
            stored_hash_b64
        )

    except (ValueError, TypeError):
        return False