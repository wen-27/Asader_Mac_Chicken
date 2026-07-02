"""Small Alembic entrypoint used by README/Makefile so migrations run the same way across environments."""

from __future__ import annotations

from alembic import command
from alembic.config import Config


def main() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()

