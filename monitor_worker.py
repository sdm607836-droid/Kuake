import os
import json
import requests
from github import Github

# ===== 配置 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

# ===== Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")  # 格式：owner/repo

if not all([STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY]):
    raise Exception("❌ 请确保 Secrets 已设置完整: QUARK_STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY")

# ===== Worker 请求函数 =====
def fetch_page(stoken, pdir_fid, page=1):
    try:
        resp = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": stoken,
                "pdir_fid": pdir_fid,
                "page": page,
                "size": PAGE_SIZE,
            },
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"❌ 请求目录 {pdir_fid[:8]} 失败: {e}")
        return []

def get_apks_in_dir(stoken, fid):
    files = fetch_page(stoken, fid)
    return [f for f in files if not f.get("dir") and f.get("file_type") == 1]

def get_latest_subfolder(stoken, fid):
    files = fetch_page(stoken, fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    def folder_key(f):
        digits = "".join(c for c in f.get("file_name", "") if c.isdigit())
        return int(digits) if digits else 0
    return max(folders, key=folder_key)

# ===== 下载 APK 文件 =====
def download_apks(apk_list):
    os.makedirs("apk", exist_ok=True)
    downloaded = []
    for f in apk_list:
        url = f.get("download_url")  # Worker 返回的 JSON 里必须包含 download_url
        if not url:
            print(f"⚠ 无法获取 {f.get('file_name')} 下载 URL，跳过")
            continue
        local_path = os.path.join("apk", f["file_name"])
        try:
            r = requests.get(url, stream=True, timeout=120)
            r.raise_for_status()
            with open(local_path, "wb") as fp:
                for chunk in r.iter_content(1024*1024):
                    fp.write(chunk)
            downloaded.append(local_path)
            print(f"✅ 下载完成 {f['file_name']}")
        except Exception as e:
            print(f"⚠ 下载失败 {f['file_name']}: {e}")
    return downloaded

# ===== 上传 GitHub Release =====
def upload_to_github_release(files):
    if not files:
        print("⚠ 没有可上传的 APK 文件")
        return

    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(GITHUB_REPOSITORY)

    tag_name = f"auto-{os.environ.get('GITHUB_RUN_NUMBER', '0')}"
    try:
        release = repo.create_git_release(
            tag=tag_name,
            name=f"FongMi APK {tag_name}",
            message="自动同步 Quark APK",
            draft=False,
            prerelease=False,
        )
        print(f"✅ 创建 Release {tag_name}")
    except Exception as e:
        print(f"⚠ Release 可能已存在: {e}")
        release = repo.get_release(tag_name)

    # 上传文件
    for path in files:
        fname = os.path.basename(path)
        try:
            release.upload_asset(path, label=fname)
            print(f"✅ 上传 {fname} 成功")
        except Exception as e:
            print(f"⚠ 上传 {fname} 失败: {e}")

# ===== 主逻辑 =====
def main():
    all_apks = []

    # 处理第一个目录
    apks1 = get_apks_in_dir(STOKEN, TARGET_DIRS[0])
    print(f"📦 目录 {TARGET_DIRS[0][:8]} APK 数: {len(apks1)}")
    all_apks.extend(apks1)

    # 处理第二个目录最新子文件夹
    latest_folder = get_latest_subfolder(STOKEN, TARGET_DIRS[1])
    if latest_folder:
        fid_latest = latest_folder["fid"]
        apks2 = get_apks_in_dir(STOKEN, fid_latest)
        print(f"📦 最新文件夹 {latest_folder['file_name']} APK 数: {len(apks2)}")
        all_apks.extend(apks2)

    # 保存 JSON
    with open("latest_apks.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存最新 APK 文件列表到 latest_apks.json")

    # 下载 APK
    downloaded_files = download_apks(all_apks)

    # 上传到 GitHub Release
    upload_to_github_release(downloaded_files)

if __name__ == "__main__":
    main()
