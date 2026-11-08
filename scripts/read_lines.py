import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
print("Reading app/services/monica_client.py header...")
lines = Path("app/services/monica_client.py").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(lines[:60]):
    print(f"{i+1}: {l}")
