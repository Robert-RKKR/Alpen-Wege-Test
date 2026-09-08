# Third-party
from passlib.context import CryptContext

# Shared password hashing context: uses bcrypt and auto-marks older schemes as
# deprecated.
_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    # Hash a plaintext password for storage.
    # Params:
    #   plain: the user-supplied plaintext password.
    # Returns: the bcrypt hash string (salt embedded) safe to persist.
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    # Check a plaintext password against a stored hash.
    # Params:
    #   plain: the plaintext password to verify.
    #   hashed: the previously stored bcrypt hash.
    # Returns: True if the password matches the hash, otherwise False.
    return _ctx.verify(plain, hashed)
