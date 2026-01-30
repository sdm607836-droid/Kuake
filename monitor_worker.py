import os
import json
import time
import requests
from github import Github

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 你的 Worker URL
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # 获取里面的 4 个 APK
    "f0c75c96e96e4310b96383b4b22040e3",  # 获取最新文件夹
]

# ===== Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")  # 可选
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BOT_API_BASE = os.getenv("BOT_API_BASE", "https://api.telegram.org")

if not all([STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY, BOT_TOKEN, CHAT_ID]):
    raise Exception("❌ 请检查 Secrets 是否设置完整：QUARK_STOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY, BOT_TOKEN, CHAT_ID")

# ===== Worker 请求函数，支持重试 =====
def fetch_page(stoken, pdir_fid, page=1, retries=3):
    for i in range(retries):
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
            data_list = resp.json().get("data", {}).get("detail_info", {}).get("list", [])
            return data_list
        except Exception as e:
            print(f"❌ 请求目录 {pdir_fid[:8]} 第 {i+1} 次失败: {e}")
            if i < retries - 1:
                print("⏳ 等待 5 秒重试...")
                time.sleep(5)
    return []

# ===== 获取目录下 APK =====
def get_apks_in_dir(stoken, fid):
    files = fetch_page(stoken, fid)
    apks = []
    for f in files:
        if not f.get("dir") and f.get("file_type") == 1:
            # Worker 返回的文件可能没有直接 download_url，需要自己构造
            download_url = f.get("download_url")
            if download_url:
                apks.append({
                    "file_name": f["file_name"],
                    "size": f["size"],
                    "download_url": download_url
                })
            else:
                print(f"⚠ 无法获取 {f['file_name']} 下载 URL，跳过")
    return apks

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
    latest = max(folders, key=folder_key)
    return latest

# ===== 下载 APK 到本地 =====
def download_apks(apks, folder="apk"):
    os.makedirs(folder, exist_ok=True)
    downloaded = []
    for f in apks:
        local_path = os.path.join(folder, f["file_name"])
        try:
            r = requests.get(f["download_url"], stream=True, timeout=120)
            r.raise_for_status()
            with open(local_path, "wb") as fp:
                for chunk in r.iter_content(8192):
                    fp.write(chunk)
            downloaded.append(local_path)
            print(f"✅ 下载完成: {f['file_name']}")
        except Exception as e:
            print(f"❌ 下载失败: {f['file_name']} → {e}")
    return downloaded

# ===== 上传 GitHub Release =====
def upload_release(apk_files):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPOSITORY)
    tag_name = f"auto-{time.strftime('%Y%m%d-%H%M')}"
    release_name = f"Auto Release {tag_name}"
    notes = "自动同步 Quark APK，只包含最新文件"
    try:
        release = repo.create_git_release(tag=tag_name, name=release_name, message=notes)
    except:
        release = repo.get_release(tag_name)
    for f in apk_files:
        release.upload_asset(f)
    return tag_name

# ===== 推送 Telegram =====
def push_telegram(apk_files):
    if not apk_files:
        print("⚠ 没有 APK 文件可推送")
        return
    media = []
    for i, f in enumerate(apk_files):
        item = {"type": "document", "media": f"attach://{os.path.basename(f)}"}
        if i == len(apk_files) - 1:
            item["caption"] = f"📦 最新 APK 上传成功，共 {len(apk_files)} 个文件"
        media.append(item)
    # 构造 multipart/form-data
    from requests_toolbelt.multipart.encoder import MultipartEncoder
    fields = {"chat_id": CHAT_ID, "media": json.dumps(media)}
    for f in apk_files:
        fields[os.path.basename(f)] = (os.path.basename(f), open(f, "rb"))
    m = MultipartEncoder(fields=fields)
    resp = requests.post(f"{BOT_API_BASE}/bot{BOT_TOKEN}/sendMediaGroup",
                         data=m,
                         headers={"Content-Type": m.content_type})
    print("Telegram 响应:", resp.text)

# ===== 主逻辑 =====
def main():
    all_apks = []

    # 目录 8d6dce95
    dir1_apks = get_apks_in_dir(STOKEN, TARGET_DIRS[0])
    all_apks.extend(dir1_apks)

    # 目录 f0c75c96 最新文件夹
    latest_folder = get_latest_subfolder(STOKEN, TARGET_DIRS[1])
    if latest_folder:
        apks_latest = get_apks_in_dir(STOKEN, latest_folder["fid"])
        all_apks.extend(apks_latest)

    if not all_apks:
        print("⚠ 没有可上传的 APK 文件")
        return

    # 下载 APK
    apk_files = download_apks(all_apks)

    if not apk_files:
        print("⚠ 没有成功下载的 APK")
        return

    # 上传 GitHub Release
    tag_name = upload_release(apk_files)
    print(f"✅ 已上传到 GitHub Release: {tag_name}")

    # 推送 Telegram
    push_telegram(apk_files)
    print("✅ Telegram 推送完成")

if __name__ == "__main__":
    main()
