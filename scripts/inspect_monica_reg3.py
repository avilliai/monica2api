with open("register/monica_register.py", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

idx = text.find("async def register_single_account")
print(text[idx+4000:idx+6500])