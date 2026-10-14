"""
Run all of Task 6.2 on ONE laptop for testing, before deploying to VMs.
Uses SQLite files instead of MySQL (no database install needed).

  product-service -> http://localhost:5001   (productdb.db)
  cart-service    -> http://localhost:5002   (cartdb.db)
  order-service   -> http://localhost:5003   (orderdb.db)
  gateway         -> http://localhost:5000   <- open this

Run:   python run_local.py        Stop: Ctrl + C
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
P, C, O = "http://localhost:5001", "http://localhost:5002", "http://localhost:5003"
SERVICES = [
    ("product-service", 5001, {"DB_NAME": "productdb", "SYNC_SUBSCRIBERS": f"{C},{O}"}),
    ("cart-service", 5002, {"DB_NAME": "cartdb", "PRODUCT_SERVICE_URL": P}),
    ("order-service", 5003, {"DB_NAME": "orderdb", "PRODUCT_SERVICE_URL": P, "CART_SERVICE_URL": C}),
    ("gateway", 5000, {"PRODUCT_SERVICE_URL": P, "CART_SERVICE_URL": C, "ORDER_SERVICE_URL": O}),
]

procs = []
try:
    for name, port, env in SERVICES:
        print(f"Starting {name:<16} on http://localhost:{port}")
        procs.append(subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(BASE, name),
                                      env={**os.environ, "DB_TYPE": "sqlite", "PORT": str(port), **env}))
        time.sleep(1)
    print("\nAll running. Open http://localhost:5000  (Ctrl + C to stop)\n")
    while all(p.poll() is None for p in procs):
        time.sleep(1)
    print("A service stopped - shutting down.")
except KeyboardInterrupt:
    pass
finally:
    for p in procs:
        p.terminate()
