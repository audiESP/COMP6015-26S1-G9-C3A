import json
import urllib.request

for pid, name in [
    ("96779f23-e1c7-9b86-f7b5-bfae61b7eaec", "Flor (in_progress)"),
    ("8b9f8dea-94be-df0d-4eff-b79f01091f3d", "Tyesha (in_progress)"),
]:
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/patients/{pid}/summary", method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            b = json.load(r)
            print(f"{name}: HTTP {r.status} chars={len(b.get('summary',''))}")
    except urllib.error.HTTPError as e:
        print(f"{name}: HTTP {e.code} {e.read().decode()[:120]}")
