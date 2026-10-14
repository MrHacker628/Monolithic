"""
Starts all 5 parts of the microservices app, each as its own separate process:

  product-service  -> http://localhost:5001
  cart-service     -> http://localhost:5002
  order-service    -> http://localhost:5003
  payment-service  -> http://localhost:5004
  frontend         -> http://localhost:5000   (open this in your browser)

Run:   python run_all.py
Stop:  Ctrl + C
"""
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES = [
    ("product-service", 5001),
    ("cart-service", 5002),
    ("order-service", 5003),
    ("payment-service", 5004),
    ("frontend", 5000),
]

processes = []
try:
    for name, port in SERVICES:
        print(f"Starting {name:<16} on http://localhost:{port}")
        processes.append(subprocess.Popen(
            [sys.executable, "app.py"], cwd=os.path.join(BASE_DIR, name),
            env={**os.environ, "PORT": str(port)}))
        time.sleep(1)
    print("\nAll services started. Open http://localhost:5000 (Ctrl + C to stop)\n")
    while True:
        for (name, _), p in zip(SERVICES, processes):
            if p.poll() is not None:
                print(f"{name} stopped (exit code {p.returncode}).")
                raise KeyboardInterrupt
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping all services...")
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
