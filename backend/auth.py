
import os
import bcrypt
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from database import client

router = APIRouter()

SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

if not SECRET:
    raise RuntimeError("JWT_SECRET is missing. Check your backend .env file.")

security = HTTPBearer(auto_error=False)


# -------------------------------
# PASSWORD UTILITIES
# -------------------------------

def hash_pw(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def make_initials(name: str) -> str:
    parts = name.strip().split()

    if not parts:
        return "U"

    if len(parts) > 1:
        return (parts[0][0] + parts[-1][0]).upper()

    return parts[0][:2].upper()


# -------------------------------
# JWT TOKEN
# -------------------------------

def make_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }

    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# -------------------------------
# AUTHENTICATION
# -------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET,
            algorithms=[ALGORITHM]
        )

        email = payload.get("sub")

        if not email:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token"
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    result = client.execute(
        """
        SELECT id, name, email, initials, role
        FROM users
        WHERE email = ?
        """,
        [email]
    )

    if not result.rows:
        raise HTTPException(
            status_code=401,
            detail="User account not found"
        )

    user_id, name, email, initials, role = result.rows[0]

    return {
        "id": user_id,
        "name": name,
        "email": email,
        "initials": initials,
        "role": role
    }


# -------------------------------
# ADMIN AUTHORIZATION
# -------------------------------

def require_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required"
        )

    return current_user


# -------------------------------
# REGISTER
# -------------------------------

@router.post("/api/register")
def register(name: str, email: str, password: str):

    name = name.strip()
    email = email.strip().lower()

    if not name:
        raise HTTPException(400, "Name is required")

    if not email or "@" not in email:
        raise HTTPException(400, "Enter a valid email address")

    if len(password) < 8:
        raise HTTPException(
            400,
            "Password must contain at least 8 characters"
        )

    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            400,
            "Password must not exceed 72 bytes"
        )

    existing = client.execute(
        "SELECT id FROM users WHERE email = ?",
        [email]
    )

    if existing.rows:
        raise HTTPException(400, "Email already registered")

    initials = make_initials(name)

    client.execute(
        """
        INSERT INTO users (
            name, email, password_hash, initials, role
        )
        VALUES (?, ?, ?, ?, 'user')
        """,
        [name, email, hash_pw(password), initials]
    )

    return {
        "token": make_token(email),
        "name": name,
        "email": email,
        "initials": initials,
        "role": "user"
    }


# -------------------------------
# LOGIN
# -------------------------------

@router.post("/api/login")
def login(email: str, password: str):

    email = email.strip().lower()

    result = client.execute(
        """
        SELECT name, password_hash, initials, role
        FROM users
        WHERE email = ?
        """,
        [email]
    )

    if not result.rows:
        raise HTTPException(401, "Invalid credentials")

    name, password_hash, initials, role = result.rows[0]

    if not verify_pw(password, password_hash):
        raise HTTPException(401, "Invalid credentials")

    return {
        "token": make_token(email),
        "name": name,
        "email": email,
        "initials": initials,
        "role": role
    }


# -------------------------------
# PROTECTED PROFILE
# -------------------------------

@router.get("/api/profile")
def profile(
    current_user: dict = Depends(get_current_user)
):
    return current_user
