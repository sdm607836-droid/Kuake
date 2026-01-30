import os
import json
import requests
from github import Github

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 修改为你的 Worker URL
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

# 需要监控的目录
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # 直接获取里面的4个APK
    "f0c75c96e96e4310b96383b4b22040e3",  # 获取最新文件夹
]

# Secrets
STOKEN = os.getenv("QUARK_STOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")  # 例如 username/repo
RELEASE_TAG_PREFIX = "auto"

if not STOKEN or not GITHUB_TOKEN or not GITHUB_REPOSITORY:
    raise Exception("❌ 请检查 Secrets 是否已设置: QUARK_STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY")

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
    def folder_key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 0
    latest = max(folders, key=folder_key)
    return latest

# ===== 下载 APK 文件 =====
def download_apk(apk):
    url = apk.get("download_url") or apk.get("source_url")  # Worker 需返回真实下载链接
    if not url:
        print(f"⚠ 无法获取 {apk['file_name']} 下载 URL，跳过")
        return None
    local_path = os.path.join("apk", apk["file_name"])
    os.makedirs("apk", exist_ok=True)
    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
        return local_path
    except Exception as e:
        print(f"❌ 下载 {apk['file_name']} 失败: {e}")
        return None

# ===== 上传到 GitHub Release =====
def upload_to_github_release(files):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPOSITORY)
    tag_name = f"{RELEASE_TAG_PREFIX}-{os.popen('date +%Y%m%d-%H%M').read().strip()}"

    # 尝试获取已存在 Release
    try:
        release = repo.get_release(tag_name)
    except:
        release = repo.create_git_release(
            tag=tag_name,
            name=f"FongMi APK {tag_name}",
            message="自动同步自 Quark APK",
            draft=False,
            prerelease=False
        )

    # 上传 APK
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            release.upload_asset(fpath, label=fname)
            print(f"✅ 上传 {fname} 到 Release")
        except Exception as e:
            print(f"⚠ 上传 {fname} 失败: {e}")

# ===== 主逻辑 =====
def main():
    result_files = []

    # 处理 8d6dce95581c49f29183380d3805e9b5 下的 APK
    dir1 = TARGET_DIRS[0]
    apks_dir1 = get_apks_in_dir(STOKEN, dir1)
    print(f"\n📦 目录 {dir1[:8]} APK 文件 {len(apks_dir1)} 个")
    result_files.extend(apks_dir1)

    # 处理 f0c75c96e96e4310b96383b4b22040e3 下最新文件夹
    dir2 = TARGET_DIRS[1]
    latest_folder = get_latest_subfolder(STOKEN, dir2)
    if latest_folder:
        print(f"\n📂 目录 {dir2[:8]} 最新文件夹: {latest_folder['file_name']}")
        apks_latest = get_apks_in_dir(STOKEN, latest_folder["fid"])
        print(f"📦 最新文件夹 APK 文件 {len(apks_latest)} 个")
        result_files.extend(apks_latest)
    else:
        print(f"⚠ 目录 {dir2[:8]} 没有子文件夹")

    # 保存 JSON
    os.makedirs("apk", exist_ok=True)
    with open("latest_apks.json", "w", encoding="utf-8") as f:
        json.dump(result_files, f, ensure_ascii=False, indent=2)
    print("\n💾 已保存最新 APK 文件列表到 latest_apks.json")

    # 下载 APK 文件
    local_files = []
    for apk in result_files:
        path = download_apk(apk)
        if path:
            local_files.append(path)

    # 上传到 GitHub Release
    if local_files:
        upload_to_github_release(local_files)
    else:
        print("⚠ 没有可上传的 APK 文件")

if __name__ == "__main__":
    main()
