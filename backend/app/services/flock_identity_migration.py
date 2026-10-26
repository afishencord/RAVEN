"""Non-destructive SQLite upgrade for atomic Flock identity uniqueness."""
from sqlalchemy import inspect, text

from app.services.flock_identity import identity_key


def migrate_flock_agent_identities(engine) -> None:
    with engine.begin() as connection:
        # Serialize concurrent backend/broker startups, including preflight.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        rows = connection.execute(text("SELECT id, name, hostname FROM flock_agents")).mappings().all()
        seen_names: dict[str, int] = {}
        seen_hosts: dict[str, int] = {}
        keys = []
        for row in rows:
            try:
                name = identity_key(row["name"])
                host = identity_key(row["hostname"], hostname=True)
            except ValueError as exc:
                raise RuntimeError(f"Invalid Flock identity for row {row['id']}; resolve it before restarting") from exc
            for key, seen, label in ((name, seen_names, "name"), (host, seen_hosts, "hostname")):
                if key in seen:
                    raise RuntimeError(
                        f"Conflicting Flock {label} identities at rows {seen[key]} and {row['id']}; "
                        "back up the database and explicitly reconcile these records before restarting. "
                        "No agent identity or token has been replaced."
                    )
                seen[key] = row["id"]
            keys.append({"id": row["id"], "name_key": name, "hostname_key": host})
        columns = {column["name"] for column in inspect(connection).get_columns("flock_agents")}
        for column in ("name_key", "hostname_key"):
            if column not in columns:
                connection.execute(text(f"ALTER TABLE flock_agents ADD COLUMN {column} VARCHAR(512) NOT NULL DEFAULT ''"))
        if keys:
            connection.execute(text("UPDATE flock_agents SET name_key=:name_key, hostname_key=:hostname_key WHERE id=:id"), keys)
        for column in ("name_key", "hostname_key"):
            connection.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_flock_agents_{column} ON flock_agents ({column})"))
