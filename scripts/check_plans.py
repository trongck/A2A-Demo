import sqlite3, json, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("data/memory.sqlite")
c = conn.cursor()
c.execute("SELECT plan_id, session_id, plan_json FROM plans ORDER BY created_at DESC LIMIT 5")
rows = c.fetchall()
for r in rows:
    print(f"\n=== RECORD: {r[0]} (Session: {r[1]}) ===")
    plans = json.loads(r[2])
    if isinstance(plans, dict):
        plans = [plans]
    for p in plans:
        print(f"Plan: {p.get('plan_id')} - {p.get('title')}")
        for idx, leg in enumerate(p.get("legs", [])):
            print(f"  Leg {idx+1}: {leg.get('service_name')} | lat={leg.get('lat')}, lng={leg.get('lng')}")
