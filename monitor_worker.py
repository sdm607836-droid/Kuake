import os
import json
import requests
import time
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
    r"OK影视Pro-手机版-.*模拟器.*\.apk": "mobile-arm64_v7a-pro.apk",
}

# 重命名映射（标准版）
OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# ===== 环境变量 =====
print("=== 调试信息 ===")
STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")

print(f"QUARK_STOKEN 是否存在: {'是' if STOKEN else '否'}")
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
print("=== 调试结束 ===\n")

if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN")
    exit(1)

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE or "",
}

# ===== 基础函数 =====
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
        print("列表获取失败:", e)
        return []

def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        data = fetch_page(fid, page)
        if not data:
            break
        files.extend(data)
        if len(data) < PAGE_SIZE:
            break
        page += 1

    apks = [
        f for f in files
        if not f.get("dir")
        and f.get("file_type") == 1
        and f.get("file_name", "").endswith(".apk")
    ]
    txts = [
        f for f in files
        if not f.get("dir")
        and f.get("file_name", "").endswith(".txt")
    ]
    return apks, txts

def get_latest_subfolder(fid):
    files = fetch_page(fid, 1)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None

    def sort_key(f):
        digits = "".join(c for c in f.get("file_name", "") if c.isdigit())
        return int(digits) if digits else 0

    return max(folders, key=sort_key)

def rename_apk(name):
    for p, n in PRO_RENAME_MAP.items():
        if re.search(p, name):
            return n
    for p, n in OK_RENAME_MAP.items():
        if re.search(p, name):
            return n
    return name.replace(" ", "_")

def download_file(url, filename, cookies):
    headers = {"Cookie": cookies}
    r = requests.get(url, headers=headers, stream=True, timeout=600)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))

    with open(filename, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, desc=filename
    ) as bar:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))

def get_original_download(fid, name, is_txt=False):
    if not COOKIE:
        return

    r = requests.post(
        "https://drive-pc.quark.cn/1/clouddrive/file/download",
        json={"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN},
        headers=HEADERS,
        timeout=30,
    )
    if r.status_code != 200:
        return

    data = r.json().get("data", [])
    if not data:
        return

    url = data[0].get("download_url")
    if not url:
        return

    cookies = "; ".join(f"{k}={v}" for k, v in r.cookies.items())

    if is_txt:
        filename = "Version.txt"
    else:
        filename = rename_apk(name)

    print("下载:", filename)
    download_file(url, filename, cookies)

# ===== 主流程 =====
def main():
    # 清理旧文件
    for f in os.listdir():
        if f.endswith((".apk", ".txt")):
            os.remove(f)

    # ===== 目录1：Pro =====
    print("=== 扫描 OK Pro ===")
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])

    for f in txts1:
        get_original_download(f["fid"], f["file_name"], is_txt=True)

    if apks1:
        smallest = min(apks1, key=lambda x: x.get("size", 0))
        get_original_download(smallest["fid"], smallest["file_name"])

    # ===== 目录2：标准版 =====
    print("=== 扫描 OK 标准版 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        apks2, txts2 = get_apks_in_dir(latest["fid"])
        for f in txts2:
            get_original_download(f["fid"], f["file_name"], is_txt=True)
        for f in apks2:
            get_original_download(f["fid"], f["file_name"])

    print("=== 完成 ===")

if __name__ == "__main__":
    main()
