"""SQLite connection and transaction management for Continuum Code Brain.

Guarantees directory provisioning, WAL concurrency, foreign key integrity,
and atomic commit boundaries.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from backend.app.core.exceptions import CodeBrainException
from backend.app.core.logging import get_logger
from backend.app.code_brain.models import CREATE_TABLES_SQL, SCHEMA_VERSION

logger = get_logger("continuum.code_brain.database")


class CodeBrainDatabase:
    """Manages SQLite connection lifecycle and schema provisioning for symbols.db."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._ensure_directory_provisioned()
        self._connection: Optional[sqlite3.Connection] = None

    def _ensure_directory_provisioned(self) -> None:
        """Idempotently provision the parent directory before opening SQLite."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise CodeBrainException(
                f"Failed to provision Code Brain directory '{self.db_path.parent}': {err}",
                details={"db_path": self.db_path.as_posix(), "error": str(err)},
            )

    def get_connection(self) -> sqlite3.Connection:
        """Get or establish SQLite connection with required PRAGMAs."""
        if self._connection is None:
            self._ensure_directory_provisioned()
            try:
                # isolation_level=None allows explicit BEGIN / COMMIT transaction control
                conn = sqlite3.connect(
                    self.db_path.as_posix(),
                    timeout=10.0,
                    isolation_level=None,
                    check_same_thread=False,
                )
                conn.row_factory = sqlite3.Row

                # Configure high-performance concurrency PRAGMAs
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.execute("PRAGMA busy_timeout=5000;")

                self._connection = conn
            except sqlite3.Error as err:
                raise CodeBrainException(
                    f"Failed to connect to Code Brain database at '{self.db_path}': {err}",
                    details={"db_path": self.db_path.as_posix(), "error": str(err)},
                )
        return self._connection

    def initialize_schema(self) -> None:
        """Apply schema tables, indexes, and version metadata."""
        conn = self.get_connection()
        try:
            conn.executescript(CREATE_TABLES_SQL)
            with self.transaction():
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?);",
                    ("schema_version", SCHEMA_VERSION),
                )
        except sqlite3.Error as err:
            raise CodeBrainException(
                f"Failed to initialize Code Brain schema: {err}",
                details={"db_path": self.db_path.as_posix(), "error": str(err)},
            )

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing atomic transaction boundary."""
        conn = self.get_connection()
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception as err:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
            except sqlite3.Error:
                pass
            if isinstance(err, CodeBrainException):
                raise
            raise CodeBrainException(
                f"Transaction failed and was rolled back: {err}",
                details={"error": str(err)},
            ) from err

    def close(self) -> None:
        """Close active database connection."""
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
            finally:
                self._connection = None
