import os
import json
import requests
from datetime import datetime
import re
from tqdm import tqdm

WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.* - 模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE") or ""

HEADERS = {
    "User-Agent": "Mozilla/5.0 quark-cloud-drive",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

def rename_file(name):
    for pattern, new_name in PRO_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    for pattern, new_name in OK_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    return name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"

def fetch_page(pdir_fid, page=1):
    try:
        r = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": PAGE_SIZE,
                "stoken": STOKEN,
                "ver": 2,
                "pr": "ucpro",
                "fr": "h5",
            },
            headers=HEADERS,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {e}")
        return []

def get_apks_in_dir(fid):
    files, page = [], 1
    while True:
        page_data = fetch_page(fid, page)
        if not page_data:
            break
        files.extend(page_data)
        if len(page_data) < PAGE_SIZE:
            break
        page += 1
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("download_url")]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt") and f.get("download_url")]
    print(f"目录 {fid[:8]} → APK {len(apks)} / TXT {len(txts)}")
    return apks, txts

def download_file(url, filename):
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=300)
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        with open(filename, "wb") as f, tqdm(desc=filename, total=total_size, unit="B", unit_scale=True) as pbar:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        print(f"✅ 下载完成 {filename}")
        return True
    except Exception as e:
        print(f"❌ 下载失败 {filename}: {e}")
        return False

def main():
    # 清理旧文件
    for f in os.listdir():
        if f.endswith((".apk", ".txt")):
            os.remove(f)

    downloaded_files = []
    for idx, fid in enumerate(TARGET_DIRS):
        print(f"\n=== {'OK Pro版' if idx==0 else 'OK 标准版'} ===")
        apks, txts = get_apks_in_dir(fid)
        for f in txts + apks:
            name = f.get("file_name")
            url = f.get("download_url")
            if not url:
                print(f"❌ 没有下载链接 {name}")
                continue
            final_name = rename_file(name)
            if download_file(url, final_name):
                downloaded_files.append(final_name)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(downloaded_files, f, ensure_ascii=False, indent=2)
    print(f"\n已下载文件: {downloaded_files}")

if __name__ == "__main__":
    main()
