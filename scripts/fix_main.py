from pathlib import Path
reg_file = Path("register/monica_register.py")
text = reg_file.read_text(encoding="utf-8")
if 'if __name__ == "__main__":' not in text:
    text = text.rstrip() + '\n\nif __name__ == "__main__":\n    main()\n'
    reg_file.write_text(text, encoding="utf-8")
    print("Added if __name__ == '__main__': main()")
else:
    print("Already exists")
