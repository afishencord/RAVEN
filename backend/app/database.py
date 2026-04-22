from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def migrate_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "nodes" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("nodes")}
        additions = {
            "execution_mode": "ALTER TABLE nodes ADD COLUMN execution_mode VARCHAR(32) DEFAULT 'runner'",
            "context_text": "ALTER TABLE nodes ADD COLUMN context_text TEXT",
            "approved_command_policy": "ALTER TABLE nodes ADD COLUMN approved_command_policy TEXT",
            "credential_id": "ALTER TABLE nodes ADD COLUMN credential_id INTEGER",
        }
        with engine.begin() as connection:
            for column, statement in additions.items():
                if column not in existing:
                    connection.execute(text(statement))

    if "execution_tasks" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("execution_tasks")}
        additions = {
            "proposal_id": "ALTER TABLE execution_tasks ADD COLUMN proposal_id VARCHAR(128)",
            "proposal_title": "ALTER TABLE execution_tasks ADD COLUMN proposal_title VARCHAR(255)",
            "execution_mode": "ALTER TABLE execution_tasks ADD COLUMN execution_mode VARCHAR(32) DEFAULT 'runner'",
            "approved_command": "ALTER TABLE execution_tasks ADD COLUMN approved_command TEXT",
        }
        with engine.begin() as connection:
            for column, statement in additions.items():
                if column not in existing:
                    connection.execute(text(statement))
