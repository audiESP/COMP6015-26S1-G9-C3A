import psycopg

url = "postgresql://neondb_owner:npg_vNQ4dpUYzT9S@ep-purple-surf-apo7wfbi-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
conn = psycopg.connect(url)
cur = conn.cursor()

print("=== visits -> patient_id (what the app actually sends) ===")
cur.execute("""
    select v.id, v.status, v.patient_id, p.first_name, p.last_name
    from c3a_app_visits v
    left join c3a_synthea_patients p on p.id = v.patient_id
    order by v.scheduled_at
""")
for r in cur.fetchall():
    print(f"  visit={str(r[0])[:8]} status={r[1]:12} patient_id={r[2]} synthea_match={r[3]} {r[4]}")

print("\n=== do those patient_ids have clinical data? ===")
cur.execute("select patient_id from c3a_app_visits")
for (pid,) in cur.fetchall():
    cur.execute("select count(*) from c3a_synthea_conditions where patient_id=%s", (pid,))
    conds = cur.fetchone()[0]
    cur.execute("select count(*) from c3a_synthea_patients where id=%s", (pid,))
    pat = cur.fetchone()[0]
    print(f"  {pid}: patient_row={pat} conditions={conds}")

conn.close()
