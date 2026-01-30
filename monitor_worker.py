import os
import json
import requests

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 修改为你的 Worker URL
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

# ===== 需要监控的目录 =====
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # 直接获取里面的4个APK
    "f0c75c96e96e4310b96383b4b22040e3",  # 获取最新文件夹
]

# ===== Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")  # 可选，主要用于Worker验证

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

# ===== 主逻辑 =====
def main():
    result_files = []

    # 处理 8d6dce95581c49f29183380d3805e9b5 下的 APK
    dir1 = TARGET_DIRS[0]
    apks_dir1 = get_apks_in_dir(STOKEN, dir1)
    print(f"\n📦 目录 {dir1[:8]} APK 文件 {len(apks_dir1)} 个")
    for f in apks_dir1:
        print(f"- {f['file_name']} | {f['size']} bytes")
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
            print(f"- {f['file_name']} | {f['size']} bytes")
            result_files.append(f)
    else:
        print(f"⚠ 目录 {dir2[:8]} 没有子文件夹")

    # 保存 JSON
    with open("latest_apks.json", "w", encoding="utf-8") as f:
        json.dump(result_files, f, ensure_ascii=False, indent=2)
    print("\n💾 已保存最新 APK 文件列表到 latest_apks.json")

if __name__ == "__main__":
    main()
