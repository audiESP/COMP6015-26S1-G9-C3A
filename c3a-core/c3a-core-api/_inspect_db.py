"""Ad-hoc DB inspector: list tables and row counts for the C3A Neon database."""
import os
import psycopg

url = None
with open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("DATABASE_URL="):
            url = line.strip().split("=", 1)[1]
            break

conn = psycopg.connect(url)
cur = conn.cursor()

cur.execute(
    "select table_name from information_schema.tables "
    "where table_schema='public' order by table_name"
)
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES (%d) ===" % len(tables))
for t in tables:
    print("  " + t)

print("\n=== ROW COUNTS ===")
for t in tables:
    try:
        cur.execute(f'select count(*) from "{t}"')
        print(f"  {t}: {cur.fetchone()[0]}")
    except Exception as e:
        print(f"  {t}: ERROR {e}")
        conn.rollback()

conn.close()
