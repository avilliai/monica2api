import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("register/monica_register.py", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Let's see what solve_recaptcha_audio does
idx = text.find("async def solve_recaptcha_audio")
print(text[idx:idx+2500])