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
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版
]

# ===== 重命名规则 =====
PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# ===== 环境变量 =====
COOKIE = os.getenv("QUARK_COOKIE")
STOKEN = os.getenv("QUARK_STOKEN")  # 仅用于转存 / 下载

print("=== 调试信息 ===")
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
print(f"QUARK_STOKEN 是否存在: {'是' if STOKEN else '否'}")
print("==================\n")

HEADERS = {
    "User-Agent": "Mozilla/5.0 quark-cloud-drive",
    "Content-Type": "application/json",
    "Cookie": COOKIE or "",
}

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

# ======================================================
# Worker 列表接口（核心）
# ======================================================
def fetch_page(pdir_fid, page=1):
    print(f"请求列表: pdir_fid={pdir_fid[:8]}, page={page}")
    try:
        r = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "pdir_fid": pdir_fid,
                "page": page,
                "size": PAGE_SIZE,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        lst = data.get("data", {}).get("detail_info", {}).get("list", [])
        print(f" 返回 {len(lst)} 条数据")
        return lst
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {e}")
        return []

# ======================================================
def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        part = fetch_page(fid, page)
        if not part:
            break
        files.extend(part)
        if len(part) < PAGE_SIZE:
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

    print(f"目录 {fid[:8]} → APK {len(apks)} / TXT {len(txts)}")
    return apks, txts

# ======================================================
def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None

    def key(f):
        digits = "".join(c for c in f.get("file_name", "") if c.isdigit())
        return int(digits) if digits else -1

    latest = max(folders, key=key)
    print(f"最新子文件夹: {latest.get('file_name')}")
    return latest

# ======================================================
# 以下：个人盘操作（仍然需要 STOKEN）
# ======================================================
def get_original_download(fid, name="", size=0, is_txt=False):
    if not COOKIE or not STOKEN:
        print("缺少 COOKIE 或 STOKEN，跳过下载")
        return

    url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    payload = {"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN}

    r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
    if r.status_code != 200:
        print(f"下载失败 {fid[:8]}")
        return

    data = r.json()
    if not data.get("data"):
        return

    file_url = data["data"][0]["download_url"]
    filename = name

    for m in (PRO_RENAME_MAP, OK_RENAME_MAP):
        for pat, new in m.items():
            if re.search(pat, name):
                filename = new
                break

    print(f"下载 {filename}")
    dl = requests.get(file_url, stream=True, timeout=600)
    dl.raise_for_status()

    total = int(dl.headers.get("content-length", 0))
    with open(filename, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, desc=filename
    ) as bar:
        for chunk in dl.iter_content(8192):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))

# ======================================================
def main():
    print("清理旧文件...")
    for f in os.listdir():
        if f.endswith((".apk", ".txt")):
            try:
                os.remove(f)
            except:
                pass

    print("\n=== OK Pro版 ===")
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])
    for f in txts1:
        get_original_download(f["fid"], f["file_name"], f.get("size", 0), True)
    for f in apks1:
        get_original_download(f["fid"], f["file_name"], f.get("size", 0))

    print("\n=== OK 标准版 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        apks2, txts2 = get_apks_in_dir(latest["fid"])
        for f in txts2:
            get_original_download(f["fid"], f["file_name"], f.get("size", 0), True)
        for f in apks2:
            get_original_download(f["fid"], f["file_name"], f.get("size", 0))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"done_{ts}.txt", "w") as f:
        f.write("完成")

if __name__ == "__main__":
    main()
