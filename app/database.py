"""Database setup for the order service.

The service owns its database (database-per-service pattern). The connection
string comes from DATABASE_URL so the same code runs on SQLite for local
development and on PostgreSQL inside Kubernetes.
"""
import logging
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger("order-service")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orders.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db(attempts: int = 15, delay_seconds: float = 2.0) -> None:
    """Create the tables, waiting for the database to accept connections.

    In Kubernetes the database pod may start after the service pod, and two
    replicas may try to create the tables at the same moment, so a failure
    here is retried instead of crashing the pod.
    """
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            log.info("database ready")
            return
        except SQLAlchemyError as exc:
            log.warning("database not ready (attempt %s/%s): %s", attempt, attempts, exc.__class__.__name__)
            time.sleep(delay_seconds)
    raise RuntimeError("database did not become ready")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
