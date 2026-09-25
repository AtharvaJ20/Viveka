# Only expose Base here. Session factories are imported explicitly by callers:
#   from app.db.session import get_db, AsyncSessionLocal, SyncSessionLocal
# Importing session.py at package level would try to validate the asyncpg URL
# scheme at import time, blocking Alembic offline mode and unit tests.
from app.db.base import Base

__all__ = ["Base"]
