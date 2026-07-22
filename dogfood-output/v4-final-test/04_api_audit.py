#!/usr/bin/env python3
"""
API endpoint audit for packaged CScode desktop app
"""
import json
from pathlib import Path
import requests

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v4-final-test")
BASE_URL = "http://127.0.0.1:8080"

endpoints = [
    ("GET", "/api/health"),
    ("GET", "/api/version"),
    ("GET", "/api/config"),
    ("GET", "/api/tools"),
    ("GET", "/api/sessions"),
    ("POST", "/api/sessions"),
    ("GET", "/api/share"),
    ("POST", "/api/share"),
    ("GET", "/api/workspaces"),
    ("POST", "/api/workspaces"),
    ("GET", "/api/credentials"),
    ("GET", "/api/application-tools"),
]

results = []

for method, path in endpoints:
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json={}, timeout=5)
        
        body_preview = ""
        try:
            body = r.json()
            body_preview = json.dumps(body)[:100]
        except Exception:
            body_preview = r.text[:100]
        
        results.append({
            "method": method,
            "path": path,
            "status": r.status_code,
            "body_preview": body_preview
        })
        print(f"[{method}] {path} -> {r.status_code}: {body_preview}")
    except Exception as e:
        results.append({
            "method": method,
            "path": path,
            "status": -1,
            "error": str(e)
        })
        print(f"[{method}] {path} -> ERROR: {e}")

# Check OpenAPI / docs
for doc_path in ["/docs", "/openapi.json", "/redoc"]:
    try:
        r = requests.get(f"{BASE_URL}{doc_path}", timeout=5)
        results.append({"method": "GET", "path": doc_path, "status": r.status_code, "body_preview": r.text[:80]})
        print(f"[GET] {doc_path} -> {r.status_code}")
    except Exception as e:
        print(f"[GET] {doc_path} -> ERROR: {e}")

with open(OUTPUT_DIR / "api_audit.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n📁 API audit saved to {OUTPUT_DIR / 'api_audit.json'}")