import os
import json
import requests
from github import Github

# ===== 配置 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 你的 Worker
PWD_ID = os.getenv("QUARK_PWD_ID")  # GitHub Secret
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3"
]
STOKEN = os.getenv("QUARK_STOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")  # e.g. username/repo

if not all([STOKEN, GITHUB_TOKEN, GITHUB_REPO]):
    raise Exception("❌ 请检查 Secrets 是否完整：QUARK_STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY")

# ===== Worker 请求函数 =====
def fetch_worker(fid):
    resp = requests.post(WORKER_URL, json={
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "pdir_fid": fid,
        "_page": 1,
        "_size": 50
    }, timeout=60)
    resp.raise_for_status()
    return resp.json().get("files", [])

# ===== 获取最新文件夹 =====
def get_latest_subfolder(fid):
    files = fetch_worker(fid)
    folders = [f for f in files if f["dir"]]
    if not folders:
        return None
    def key(f):
        digits = "".join(c for c in f["file_name"] if c.isdigit())
        return int(digits) if digits else 0
    return max(folders, key=key)

# ===== 下载文件 =====
def download_file(url, save_path):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            f.write(chunk)

# ===== 上传到 GitHub Release =====
def upload_to_github(apk_files):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    tag = f"auto-{os.popen('date +%Y%m%d-%H%M').read().strip()}"
    release = repo.create_git_release(tag=tag, name=f"FongMi APK {tag}", message="自动同步 Quark APK")
    
    for apk in apk_files:
        release.upload_asset(apk)
        print(f"✅ 上传完成: {apk}")

# ===== 主逻辑 =====
def main():
    apk_files = []

    # 处理第一个目录
    files1 = fetch_worker(TARGET_DIRS[0])
    for f in files1:
        if f["file_type"] == 1:
            save_path = f"apk_{f['file_name']}"
            print(f"📥 下载 {f['file_name']}")
            try:
                download_file(f["download_url"], save_path)
                apk_files.append(save_path)
            except Exception as e:
                print(f"⚠ 下载失败 {f['file_name']}: {e}")

    # 第二个目录最新子文件夹
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        files2 = fetch_worker(latest["fid"])
        for f in files2:
            if f["file_type"] == 1:
                save_path = f"apk_{f['file_name']}"
                print(f"📥 下载 {f['file_name']}")
                try:
                    download_file(f["download_url"], save_path)
                    apk_files.append(save_path)
                except Exception as e:
                    print(f"⚠ 下载失败 {f['file_name']}: {e}")

    if apk_files:
        print(f"📦 共下载 {len(apk_files)} 个 APK，准备上传 GitHub Release")
        upload_to_github(apk_files)
    else:
        print("⚠ 没有 APK 文件可上传")

if __name__ == "__main__":
    main()
