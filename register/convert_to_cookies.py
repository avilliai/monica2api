"""将已验证账号合并到 Monica2API Cookie 池。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REGISTER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = REGISTER_DIR.parent


def convert_accounts_to_cookies(
    input_file: str | Path = REGISTER_DIR / "monica_accounts.json",
    output_file: str | Path = PROJECT_ROOT / "data" / "cookies.json",
    *,
    merge: bool = True,
) -> dict[str, int]:
    input_path = Path(input_file).expanduser().resolve()
    output_path = Path(output_file).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    accounts = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(accounts, list):
        raise ValueError("账号文件顶层结构必须是数组")

    converted = []
    invalid = 0
    for account in accounts:
        if not isinstance(account, dict):
            invalid += 1
            continue
        email = str(account.get("email") or "").strip()
        cookie = str(account.get("cookie") or "").strip()
        if not email or not cookie:
            invalid += 1
            continue
        converted.append(
            {
                "email": email,
                "password": str(account.get("password") or ""),
                "cookie": cookie,
                "disabled": bool(account.get("disabled", False)),
            }
        )

    existing = []
    if merge and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise ValueError("目标 Cookie 文件顶层结构必须是数组")

    seen = {
        str(item.get("email") or "").strip().casefold()
        for item in existing
        if isinstance(item, dict)
    }
    added_items = []
    for item in converted:
        key = item["email"].casefold()
        if key in seen:
            continue
        seen.add(key)
        added_items.append(item)

    result = existing + added_items if merge else added_items
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, output_path)
    return {"added": len(added_items), "invalid": invalid, "total": len(result)}


def main() -> int:
    parser = argparse.ArgumentParser(description="将 Monica 注册账号导入 Cookie 池")
    parser.add_argument("input", nargs="?", default=str(REGISTER_DIR / "monica_accounts.json"))
    parser.add_argument("output", nargs="?", default=str(PROJECT_ROOT / "data" / "cookies.json"))
    parser.add_argument("--replace", action="store_true", help="覆盖目标文件而不是按邮箱合并")
    args = parser.parse_args()
    stats = convert_accounts_to_cookies(args.input, args.output, merge=not args.replace)
    print(f"导入完成: 新增={stats['added']} 无效={stats['invalid']} 总数={stats['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
