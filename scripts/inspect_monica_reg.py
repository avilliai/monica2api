with open("register/monica_register.py", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Let's inspect register_single_account and error handling
idx = text.find("async def register_single_account")
print(text[idx:idx+2500])