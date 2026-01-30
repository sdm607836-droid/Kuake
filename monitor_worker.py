import os
import json
import requests
from pathlib import Path

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 你的 Worker URL
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # 获取4个APK
    "f0c75c96e96e4310b96383b4b22040e3",  # 获取最新文件夹
]

# ===== Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")  # 可选，用于 Worker 验证

if not STOKEN:
    print("❌ 请在 GitHub Secrets 设置 QUARK_STOKEN")
    exit(1)

# ===== Worker 请求函数 =====
def fetch_page(stoken, pdir_fid, page=1):
    try:
        resp = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": stoken,
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
        print(f"❌ 请求目录 {pdir_fid[:8]} 失败: {e}")
        return []

# ===== 获取目录下 APK =====
def get_apks_in_dir(stoken, fid):
    files = fetch_page(stoken, fid)
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1]
    return apks

# ===== 获取目录下最新文件夹 =====
def get_latest_subfolder(stoken, fid):
    files = fetch_page(stoken, fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    # 文件夹名字里数字越大表示越新
    def folder_key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 0
    latest = max(folders, key=folder_key)
    return latest

# ===== 生成下载 URL =====
def get_download_url(fid, share_fid_token):
    url = f"https://pan.quark.cn/1/clouddrive/file/download"
    params = {
        "fid": fid,
        "share_fid_token": share_fid_token,
        "stoken": STOKEN,
        "pdir_fid": ROOT_FID,
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("code") == 0 and "data" in data:
            return data["data"].get("download_url")
        else:
            return None
    except:
        return None

# ===== 下载 APK =====
def download_apk(file_info, folder="apk"):
    url = file_info.get("download_url")
    if not url:
        print(f"⚠ 无法获取 {file_info['file_name']} 下载 URL，跳过")
        return None
    Path(folder).mkdir(exist_ok=True)
    local_path = Path(folder) / file_info["file_name"]
    try:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ 下载成功: {file_info['file_name']}")
        return str(local_path)
    except Exception as e:
        print(f"❌ 下载失败: {file_info['file_name']} -> {e}")
        return None

# ===== 主逻辑 =====
def main():
    result_files = []

    # 处理 8d6dce95581c49f29183380d3805e9b5 下的 APK
    dir1 = TARGET_DIRS[0]
    apks_dir1 = get_apks_in_dir(STOKEN, dir1)
    print(f"\n📦 目录 {dir1[:8]} APK 文件 {len(apks_dir1)} 个")
    for f in apks_dir1:
        f["download_url"] = get_download_url(f["fid"], f.get("share_fid_token"))
        local_path = download_apk(f)
        if local_path:
            result_files.append(f)

    # 处理 f0c75c96e96e4310b96383b4b22040e3 下最新文件夹
    dir2 = TARGET_DIRS[1]
    latest_folder = get_latest_subfolder(STOKEN, dir2)
    if latest_folder:
        print(f"\n📂 目录 {dir2[:8]} 最新文件夹: {latest_folder['file_name']}")
        fid_latest = latest_folder["fid"]
        apks_latest = get_apks_in_dir(STOKEN, fid_latest)
        print(f"📦 最新文件夹 APK 文件 {len(apks_latest)} 个")
        for f in apks_latest:
            f["download_url"] = get_download_url(f["fid"], f.get("share_fid_token"))
            local_path = download_apk(f)
            if local_path:
                result_files.append(f)
    else:
        print(f"⚠ 目录 {dir2[:8]} 没有子文件夹")

    # 保存 JSON
    with open("latest_apks.json", "w", encoding="utf-8") as f:
        json.dump(result_files, f, ensure_ascii=False, indent=2)
    print("\n💾 已保存最新 APK 文件列表到 latest_apks.json")

if __name__ == "__main__":
    main()
