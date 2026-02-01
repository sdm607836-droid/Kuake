import os
import json
import requests
import time
from datetime import datetime
from tqdm import tqdm
import re

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

# ===== 环境变量 =====
COOKIE = os.getenv("QUARK_COOKIE")
STOKEN = os.getenv("QUARK_STOKEN")  # 这个可以不用，因为 Worker 会生成 stoken

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
}

# ===== 工具函数 =====
def rename_file(name):
    for pattern, new_name in PRO_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    for pattern, new_name in OK_RENAME_MAP.items():
        if re.search(pattern, name):
            return new_name
    return name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"

def fetch_files_from_worker(pdir_fid, page=1):
    """调用 Worker 获取文件列表，包括 share_fid_token"""
    try:
        r = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "pdir_fid": pdir_fid,
                "page": page,
                "size": PAGE_SIZE,
            },
            headers=HEADERS,
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        files = data.get("files", [])
        return files
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {e}")
        return []

def get_all_files(fid):
    """分页获取目录内所有文件"""
    all_files = []
    page = 1
    while True:
        files = fetch_files_from_worker(fid, page)
        if not files:
            break
        all_files.extend(files)
        if len(files) < PAGE_SIZE:
            break
        page += 1
    apks = [f for f in all_files if f["file_type"] == 1 and f["file_name"].endswith(".apk")]
    txts = [f for f in all_files if f["file_type"] == 1 and f["file_name"].endswith(".txt")]
    print(f"目录 {fid[:8]} → APK {len(apks)} / TXT {len(txts)}")
    return apks, txts

def download_file(fid, fid_token, name):
    """下载文件"""
    download_url = f"https://pan.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=h5&fid={fid}&fid_token={fid_token}"
    final_name = rename_file(name)
    try:
        r = requests.get(download_url, headers=HEADERS, stream=True, timeout=300)
        r.raise_for_status()
        total_size = int(r.headers.get('content-length', 0))
        with open(final_name, 'wb') as f, tqdm(
            desc=final_name,
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
        ) as pbar:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        print(f"✅ 下载完成 {final_name}")
        return final_name
    except Exception as e:
        print(f"❌ 下载失败 {final_name}: {e}")
        return None

# ===== 主流程 =====
def main():
    print("清理旧文件...")
    for f in os.listdir():
        if f.endswith((".apk", ".txt")):
            try: os.remove(f)
            except: pass

    downloaded_files = []

    for idx, fid in enumerate(TARGET_DIRS):
        print(f"\n=== {'OK Pro版' if idx==0 else 'OK 标准版'} ===")
        apks, txts = get_all_files(fid)
        for f in txts + apks:
            fid_ = f["fid"]
            fid_token = f.get("share_fid_token")
            if not fid_token:
                print(f"❌ 没有下载链接 {f['file_name']}")
                continue
            result = download_file(fid_, fid_token, f["file_name"])
            if result:
                downloaded_files.append(result)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(downloaded_files, f, ensure_ascii=False, indent=2)
    print(f"\n已下载文件: {downloaded_files}")

if __name__ == "__main__":
    main()
