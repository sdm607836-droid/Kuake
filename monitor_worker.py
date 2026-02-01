import os
import json
import requests
import time
from datetime import datetime
import threading
import re
from tqdm import tqdm

# ===== Fongmi 配置（改成你的 ID） =====
FONGMI_ID = "335400"  # ← 这里填你授权后得到的 ID
FONGMI_BASE = "https://t4a.fongmi.leuse.top/auth/quark"

# ===== 获取最新 stoken（优先 Fongmi，fallback 到 Secrets） =====
def get_latest_stoken():
    print("正在从 Fongmi 获取最新 stoken...")
    try:
        url = f"{FONGMI_BASE}?id={FONGMI_ID}&act=get"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                stoken = data.get("data", {}).get("stoken")
                cookie = data.get("data", {}).get("cookie")
                if stoken:
                    print(f"从 Fongmi 获取 stoken 成功: {stoken[:10]}...")
                    # 可选：更新 COOKIE（如果 Fongmi 返回了新 cookie）
                    if cookie:
                        global COOKIE
                        COOKIE = cookie
                        print("同时更新 COOKIE")
                    return stoken
            else:
                print("Fongmi 返回错误:", data.get("msg"))
        else:
            print("Fongmi 请求失败:", r.status_code)
    except Exception as e:
        print("Fongmi 获取失败:", str(e))

    # fallback 到 Secrets
    stoken = os.getenv("QUARK_STOKEN")
    if stoken:
        print("使用 GitHub Secrets 的 stoken")
        return stoken
    print("❌ 所有方式都无法获取 stoken")
    return None

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版
]

# 重命名映射（Pro版）
PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.* - 模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

# 重命名映射（标准版）
OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# 调试信息
print("=== 调试信息 ===")
STOKEN = get_latest_stoken()  # ← 使用 Fongmi 优先获取
COOKIE = os.getenv("QUARK_COOKIE")
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
if COOKIE:
    print(f"QUARK_COOKIE 长度: {len(COOKIE)}")
    print(f"QUARK_COOKIE 前20字符: {COOKIE[:20]}...")
print("=== 调试结束 ===\n")

if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN，无法继续")
    exit(1)

if not COOKIE:
    print("⚠️ 缺少 QUARK_COOKIE → 只能扫描列表，无法转存和获取下载链接")

# 其余代码保持不变（FILES_CACHE、HEADERS、test_personal_drive 等）
# ...（你的原代码从这里继续）

# 在 main() 前加一行刷新 stoken 的逻辑（可选，每天运行一次刷新）
def refresh_stoken():
    try:
        url = f"{FONGMI_BASE}?id={FONGMI_ID}&act=refresh"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                new_stoken = data.get("data", {}).get("stoken")
                if new_stoken:
                    print(f"stoken 刷新成功: {new_stoken[:10]}...")
                    global STOKEN
                    STOKEN = new_stoken
                    return True
    except Exception as e:
        print("stoken 刷新失败:", str(e))
    return False

# 在 main() 开头调用一次刷新
def main():
    refresh_stoken()  # 尝试刷新 stoken
    test_personal_drive()
    # ... 你的原 main 逻辑
