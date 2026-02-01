import os
import json
import requests
import re
from datetime import datetime
from tqdm import tqdm
from time import sleep

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

STOKEN = os.getenv("QUARK_STOKEN")
if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN")
    exit(1)

# 清理旧文件
print("清理旧文件...")
for file in os.listdir():
    if file.endswith((".apk", ".txt")):
        os.remove(file)
        print(f"已删除旧文件: {file}")

# ===== 工具函数 =====
def fetch_page(pdir_fid, page=1):
    try:
        r = requests.post(WORKER_URL, json={
            "pwd_id": PWD_ID,
            "pdir_fid": pdir_fid,
            "_page": page,
            "_size": PAGE_SIZE,
            "ver": 2,
            "pr": "ucpro",
            "fr": "h5",
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {e}")
        return []

def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        page_data = fetch_page(fid, page)
        if not page_data:
            break
        files.extend(page_data)
        if len(page_data) < PAGE_SIZE:
            break
        page += 1
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("file_name", "").endswith(".apk")]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt")]
    print(f"目录 {fid[:8]} → APK {len(apks)} / TXT {len(txts)}")
    return apks, txts

def download_file(url, name):
    try:
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            with open(name, 'wb') as f, tqdm(desc=name, total=total, unit='B', unit_scale=True) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        print(f"下载完成: {name}")
        return True
    except Exception as e:
        print(f"下载失败 {name}: {e}")
        return False

def rename_file(name):
    for pattern, new_name in PRO_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    for pattern, new_name in OK_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    return name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"

# ===== 主逻辑 =====
all_files = []
downloaded_files = []

for fid in TARGET_DIRS:
    apks, txts = get_apks_in_dir(fid)
    for f in txts + apks:
        file_name = f.get("file_name", "?")
        download_url = f.get("download_url")  # Worker 返回的数据里必须包含 download_url
        if not download_url:
            print(f"❌ 没有下载链接 {file_name}")
            continue
        is_apk = file_name.endswith(".apk")
        final_name = rename_file(file_name) if is_apk else f"Version-{file_name}.txt"
        success = download_file(download_url, final_name)
        if success:
            downloaded_files.append(final_name)
        all_files.append({
            "name": file_name,
            "url": download_url,
            "saved_as": final_name
        })

# 保存列表 JSON
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
    json.dump(all_files, f, ensure_ascii=False, indent=2)
print(f"\n已保存下载列表 downloads_{ts}.json")
print("已下载文件:", downloaded_files)
