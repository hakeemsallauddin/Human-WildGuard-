
import os
import libsql_client
from dotenv import load_dotenv

# Load environment variables from backend/.env
load_dotenv()

# Connect to Turso database
database_url = os.getenv("TURSO_DATABASE_URL")
database_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not database_token:
    raise RuntimeError(
        "TURSO_DATABASE_URL or TURSO_AUTH_TOKEN is missing from .env"
    )

client = libsql_client.create_client_sync(
    url=database_url.replace("libsql://", "https://"),
    auth_token=database_token
)


def init_db():
    # Create users table if it does not exist
    client.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        initials TEXT
    )""")

    # Add role only if it does not already exist
    user_columns = client.execute(
        "PRAGMA table_info(users)"
    ).rows

    column_names = [column[1] for column in user_columns]

    if "role" not in column_names:
        client.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
        )

    # Create reports table if it does not exist
    client.execute("""CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        species TEXT,
        confidence REAL,
        image_path TEXT,
        reported_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
