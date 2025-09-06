#!/usr/bin/env python3
import argparse
import glob
import os
import subprocess
import sys
import uuid
from urllib.parse import urlparse, urlunparse

import psycopg

KNOWN_MIGRATION_TABLES = [
    "alembic_version",
    "django_migrations",
    "schema_migrations",
    "flyway_schema_history",
    "knex_migrations",
    "knex_migrations_lock",
    "goose_db_version",
    "drizzle__migrations",
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Squash SQL migrations into a single initial schema (PostgreSQL).",
    )
    p.add_argument(
        "--migrations-dir",
        required=True,
        help="Directory with SQL migration files (applied in sorted order).",
    )
    p.add_argument(
        "--db-url",
        required=True,
        help="Postgres connection URI to a *control* database where a temp DB can be created, e.g. "
        "postgresql://user:pass@localhost:5432/postgres",
    )
    p.add_argument(
        "--outfile",
        default="initial_schema.sql",
        help="Path to write the resulting schema SQL.",
    )
    p.add_argument(
        "--include-data",
        action="store_true",
        help="Include data as well (defaults to schema only). Not recommended for a pure initial schema.",
    )
    p.add_argument(
        "--extra-drop",
        action="append",
        default=[],
        help="Extra table names to drop before dump (can repeat).",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not drop the temp database (for debugging).",
    )
    return p.parse_args()


def _db_url_with_dbname(db_url: str, new_dbname: str) -> str:
    """Return db_url but with database path replaced by /new_dbname."""
    parts = urlparse(db_url)
    return urlunparse(parts._replace(path="/" + new_dbname))


def _create_temp_db(control_url: str) -> str:
    temp_dbname = "squash_" + uuid.uuid4().hex[:12]
    with psycopg.connect(control_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE {psycopg.sql.Identifier(temp_dbname).as_string(cur)} TEMPLATE template0 ENCODING 'UTF8';",
            )
    return temp_dbname


def _drop_temp_db(control_url: str, dbname: str):
    # Must disconnect all clients first
    with psycopg.connect(control_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid();
            """,
                (dbname,),
            )
            cur.execute(
                f"DROP DATABASE IF EXISTS {psycopg.sql.Identifier(dbname).as_string(cur)};",
            )


def _apply_sql_files(db_url: str, migrations_dir: str):
    files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    if not files:
        raise SystemExit(f"No .sql files found in: {migrations_dir}")

    # Autocommit True to allow files that contain their own BEGIN/COMMIT or CONCURRENT operations.
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for fpath in files:
                sys.stdout.write(f"Applying {os.path.basename(fpath)} ... ")
                sys.stdout.flush()
                sql = open(fpath, encoding="utf-8").read()
                try:
                    cur.execute(sql)
                    print("OK")
                except Exception as e:
                    print("FAILED")
                    raise RuntimeError(f"Error applying {fpath}: {e}") from e


def _prune_migration_tables(db_url: str, extra_drop: list[str]):
    to_drop = list(KNOWN_MIGRATION_TABLES) + list(extra_drop)
    if not to_drop:
        return
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for t in to_drop:
                cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE;')


def _pg_dump_to_file(db_url: str, outfile: str, include_data: bool):
    args = ["pg_dump", db_url, "--file", outfile, "--no-owner", "--no-privileges"]
    if not include_data:
        args.append("--schema-only")
    # Add these for more deterministic output (optional):
    args += ["--quote-all-identifiers", "--if-exists"]
    # Execute
    env = os.environ.copy()
    # pg_dump can read credentials from the URI; if you rely on PGPASSWORD, keep it in env.
    subprocess.run(args, check=True, env=env)


def main():
    args = parse_args()
    # Create temp DB
    temp_dbname = _create_temp_db(args.db_url)
    temp_db_url = _db_url_with_dbname(args.db_url, temp_dbname)
    try:
        _apply_sql_files(temp_db_url, args.migrations_dir)
        _prune_migration_tables(temp_db_url, args.extra_drop)
        _pg_dump_to_file(temp_db_url, args.outfile, args.include_data)
        print(f"\n✅ Wrote squashed schema to: {args.outfile}")
    finally:
        if args.no_cleanup:
            print(f"⚠️ Temp database kept for debugging: {temp_dbname}")
        else:
            _drop_temp_db(args.db_url, temp_dbname)


if __name__ == "__main__":
    main()
