import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("register/monica_register.py", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

idx = text.find("async def solve_recaptcha_audio")
print(text[idx+2000:idx+4500])