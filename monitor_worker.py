import os
import json
import requests
from datetime import datetime
import threading
import re
from tqdm import tqdm

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版目录
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版目录
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

# ===== 调试信息 =====
print("=== 调试信息 ===")
STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")

print(f"QUARK_STOKEN 是否存在: {'是' if STOKEN else '否'}")
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
print("=== 调试结束 ===\n")

if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN，无法继续")
    exit(1)

if not COOKIE:
    print("⚠️ 缺少 QUARK_COOKIE → 只能扫描列表，无法下载")

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE or "",
}

# ===== 功能函数 =====

def test_personal_drive():
    url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_fetch_total=1&_size=10"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"个人网盘访问状态: {r.status_code}")
    except Exception as e:
        print(f"测试失败: {e}")

def fetch_page(pdir_fid, page=1):
    try:
        r = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": STOKEN,
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": PAGE_SIZE,
                "ver": 2,
                "pr": "ucpro",
                "fr": "h5",
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"列表请求失败: {e}")
        return []

def get_apks_in_dir(fid):
    files, page = [], 1
    while True:
        data = fetch_page(fid, page)
        if not data:
            break
        files.extend(data)
        if len(data) < PAGE_SIZE:
            break
        page += 1

    apks = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".apk")]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt")]
    return apks, txts

def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None

    def key(f):
        digits = "".join(c for c in f.get("file_name", "") if c.isdigit())
        return int(digits) if digits else -1

    return max(folders, key=key)

# ===== 安全占位函数（关键）=====

def copy_file(fid, share_fid_token=""):
    return None

def get_original_download(fid, share_fid_token="", name="", size=0, is_txt=False):
    print(f" [跳过下载] {name}")
    return [], None

def cleanup_transferred_files():
    print(" 转存清理：跳过")

# ===== 主流程 =====

def main():
    test_personal_drive()

    all_apks = []
    download_results = []
    downloaded_files = []

    print("\n清空旧文件...")
    for f in os.listdir():
        if f.endswith((".apk", ".txt")):
            try:
                os.remove(f)
            except:
                pass

    print("\n=== 扫描 OK Pro ===")
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])

    for f in apks1:
        all_apks.append(f)
        get_original_download(f["fid"], f.get("share_fid_token", ""), f["file_name"], f.get("size", 0))

    print("\n=== 扫描 OK 标准版 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        apks2, txts2 = get_apks_in_dir(latest["fid"])
        for f in apks2:
            all_apks.append(f)
            get_original_download(f["fid"], f.get("share_fid_token", ""), f["file_name"], f.get("size", 0))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)

    cleanup_transferred_files()
    print("\n✅ 脚本执行完成")

if __name__ == "__main__":
    main()
