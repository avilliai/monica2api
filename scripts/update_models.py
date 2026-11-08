import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

client_file = Path("app/services/monica_client.py")
text = client_file.read_text(encoding="utf-8")

new_models_map = """
    # 2026 Latest Free Models
    "gemini-3-flash": "gemini-3-flash",
    "gpt-6-luna": "gpt-6-luna",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "deepseek-v4-1-flash": "deepseek-v4.1-flash",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3-5-flash-lite": "gemini-3.5-flash-lite",
    "qwen3.8-flash": "qwen3.8-flash",
    "qwen-3.8-flash": "qwen3.8-flash",
    "glm-5.3-flash": "glm-5.3-flash",
    "glm-5-3-flash": "glm-5.3-flash",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3-1-flash-lite": "gemini-3.1-flash-lite",
"""

new_chat_models_map = """
    # 2026 Latest Free Models internal chat_model
    "gemini-3-flash": "gemini_3_flash",
    "gpt-6-luna": "gpt_6_luna_chat",
    "deepseek-v4.1-flash": "deepseek_v4_1_flash",
    "deepseek-v4-1-flash": "deepseek_v4_1_flash",
    "gemini-3.5-flash-lite": "gemini_3_5_flash_lite",
    "gemini-3-5-flash-lite": "gemini_3_5_flash_lite",
    "qwen3.8-flash": "qwen_3_8_flash",
    "qwen-3.8-flash": "qwen_3_8_flash",
    "glm-5.3-flash": "glm_5_3_flash",
    "glm-5-3-flash": "glm_5_3_flash",
    "gemini-3.1-flash-lite": "gemini_3_1_flash_lite",
    "gemini-3-1-flash-lite": "gemini_3_1_flash_lite",
"""

text = text.replace('"grok-3-beta": "grok_3_beta", "grok-4": "grok_4",', '"grok-3-beta": "grok_3_beta", "grok-4": "grok_4",' + new_models_map)
text = text.replace('"gpt-4o": "gpt_4_o_chat", "gpt-4o-mini": "gpt_4_o_mini_chat",', '"gpt-4o": "gpt_4_o_chat", "gpt-4o-mini": "gpt_4_o_mini_chat",' + new_chat_models_map)

client_file.write_text(text, encoding="utf-8")
print("Updated app/services/monica_client.py")

# 更新 app/core/config.py
config_file = Path("app/core/config.py")
cfg_text = config_file.read_text(encoding="utf-8")

cfg_models_insert = """
    "gpt-6-luna",
    "deepseek-v4.1-flash",
    "gemini-3.5-flash-lite",
    "qwen3.8-flash",
    "glm-5.3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash",
"""

cfg_text = cfg_text.replace('DEFAULT_MODELS = [', 'DEFAULT_MODELS = [' + cfg_models_insert)
config_file.write_text(cfg_text, encoding="utf-8")
print("Updated app/core/config.py")
