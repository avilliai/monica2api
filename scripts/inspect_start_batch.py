with open("app/templates/dashboard.html", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("".join(lines[1620:1670]))