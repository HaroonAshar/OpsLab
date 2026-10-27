import os
import psycopg

try:
    with psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        connect_timeout=5,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            database, user = cur.fetchone()

            print(f"Connected to database: {database}")
            print(f"Connected as user: {user}")

            cur.execute(
                "SELECT id, title, completed FROM tasks ORDER BY id"
            )
            for task in cur.fetchall():
                print(task)

except Exception as exc:
    print(f"Database connection failed: {exc}")
    raise SystemExit(1)
