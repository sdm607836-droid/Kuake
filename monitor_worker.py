import os
import json
import requests

# ===== 配置 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # 直接取里面的 APK
    "f0c75c96e96e4310b96383b4b22040e3",  # 获取最新文件夹
]

# ===== Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")  # 可选，Worker 验证

if not STOKEN:
    raise Exception("❌ 请在 GitHub Secrets 设置 QUARK_STOKEN")

# ===== Worker 请求函数 =====
def fetch_page(stoken, pdir_fid, page=1):
    try:
        resp = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": stoken,
                "pdir_fid": pdir_fid,
                "page": page,   # ⚠ 注意这里
                "size": PAGE_SIZE
            },
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"❌ 请求目录 {pdir_fid[:8]} 失败: {e}")
        return []

# ===== 获取目录 APK =====
def get_apks_in_dir(stoken, fid):
    files = fetch_page(stoken, fid)
    return [f for f in files if not f.get("dir") and f.get("file_type") == 1]

# ===== 获取最新子文件夹 =====
def get_latest_subfolder(stoken, fid):
    files = fetch_page(stoken, fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    def folder_key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 0
    return max(folders, key=folder_key)

# ===== 主逻辑 =====
def main():
    result_files = []

    # 处理第一个目录
    apks1 = get_apks_in_dir(STOKEN, TARGET_DIRS[0])
    print(f"📦 目录 {TARGET_DIRS[0][:8]} APK 数: {len(apks1)}")
    result_files.extend(apks1)

    # 处理第二个目录最新子文件夹
    latest_folder = get_latest_subfolder(STOKEN, TARGET_DIRS[1])
    if latest_folder:
        fid_latest = latest_folder["fid"]
        apks2 = get_apks_in_dir(STOKEN, fid_latest)
        print(f"📦 最新文件夹 {latest_folder['file_name']} APK 数: {len(apks2)}")
        result_files.extend(apks2)

    # 保存 JSON
    with open("latest_apks.json", "w", encoding="utf-8") as f:
        json.dump(result_files, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存最新 APK 文件列表到 latest_apks.json")

if __name__ == "__main__":
    main()
