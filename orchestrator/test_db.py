import sys
sys.path.insert(0, '.')
from db.connection import get_conn, release_conn

conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
release_conn(conn)
print("Connected! Tables found:")
for t in tables:
    print(" ", t)
