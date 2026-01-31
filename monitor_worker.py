# monitor_worker.py （只保留列表功能，暂时不要下载尝试）

import os
import json
import requests
from datetime import datetime

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

STOKEN = os.getenv("QUARK_STOKEN")
if not STOKEN:
    print("❌ 请设置 QUARK_STOKEN")
    exit(1)

def fetch_page(pdir_fid, page=1):
    try:
        resp = requests.post(
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
            timeout=60
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"❌ 请求目录 {pdir_fid[:8]}... 失败: {e}")
        return []

def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        page_files = fetch_page(fid, page)
        if not page_files:
            break
        files.extend(page_files)
        if len(page_files) < PAGE_SIZE:
            break
        page += 1
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1]
    return apks

def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None

    def key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else -999999

    return max(folders, key=key)

def main():
    all_apks = []

    print("\n=== 目录 1 ===")
    dir1 = TARGET_DIRS[0]
    apks1 = get_apks_in_dir(dir1)
    print(f"找到 {len(apks1)} 个 APK 文件")
    for f in apks1:
        name = f.get("file_name", "unknown.apk")
        size = f.get("size", 0)
        print(f"  • {name:<50} {size:>12,} bytes")
        all_apks.append(f)

    print("\n=== 目录 2 - 最新子文件夹 ===")
    dir2 = TARGET_DIRS[1]
    latest = get_latest_subfolder(dir2)
    if latest:
        folder_name = latest.get("file_name", "??")
        fid_latest = latest["fid"]
        print(f"最新文件夹：{folder_name}")

        apks2 = get_apks_in_dir(fid_latest)
        print(f"找到 {len(apks2)} 个 APK 文件")
        for f in apks2:
            name = f.get("file_name", "unknown.apk")
            size = f.get("size", 0)
            print(f"  • {name:<50} {size:>12,} bytes")
            all_apks.append(f)
    else:
        print("  没有找到子文件夹")

    # 保存
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"quark_apks_{ts}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 {filename}")

if __name__ == "__main__":
    main()
