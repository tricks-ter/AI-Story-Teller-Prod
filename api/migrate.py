import os
import sys
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")

def get_url():
    url = os.getenv("DATABASE_URL")
    if url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}sslmode=require"
    return url

def main():
    url = get_url()
    if not url:
        print("[migrate] ERROR: DATABASE_URL not set")
        return 1

    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "filename VARCHAR(255) PRIMARY KEY, "
                "applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {r[0] for r in cur.fetchall()}

        files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
        pending = [f for f in files if os.path.basename(f) not in applied]

        if not pending:
            print("[migrate] Up to date. Nothing to apply.")
            return 0

        for path in pending:
            name = os.path.basename(path)
            print(f"[migrate] Applying {name} ...")
            with open(path, "r") as fh:
                sql = fh.read()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT (filename) DO NOTHING",
                        (name,))
                conn.commit()
                print(f"[migrate] OK {name}")
            except Exception as e:
                conn.rollback()
                print(f"[migrate] FAILED {name}: {e}")
                return 1

        print("[migrate] All migrations applied.")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(main())
