from pathlib import Path

# 1. Patch register/monica_register.py
reg_path = Path("register/monica_register.py")
content = reg_path.read_text(encoding="utf-8")
old_cfg = """@dataclass
class RegisterConfig:
    headless: bool = True"""
new_cfg = """@dataclass
class RegisterConfig:
    browser_backend: str = "camoufox"
    headless: bool = True"""
if old_cfg in content:
    content = content.replace(old_cfg, new_cfg, 1)
reg_path.write_text(content, encoding="utf-8")
print("Added browser_backend to RegisterConfig")

# 2. Patch app/services/register.py
svc_path = Path("app/services/register.py")
scontent = svc_path.read_text(encoding="utf-8")
old_changes = """        if changes:
            config = replace(config, **changes)"""
new_changes = """        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(config)}
        filtered_changes = {k: v for k, v in changes.items() if k in valid_keys}
        if filtered_changes:
            config = replace(config, **filtered_changes)"""
if old_changes in scontent:
    scontent = scontent.replace(old_changes, new_changes, 1)
svc_path.write_text(scontent, encoding="utf-8")
print("Safeguarded replace(config) in app/services/register.py")
