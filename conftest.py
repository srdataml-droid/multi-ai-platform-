"""Root pytest config: exposes the shared Postgres fixtures to every package."""

pytest_plugins = ["novaxis_db.testing"]
