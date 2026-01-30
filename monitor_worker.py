import os
import json
import requests
import hashlib
from datetime import datetime
from github import Github

# ====== 配置 ======
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"

STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BOT_API_BASE = os.getenv("BOT_API_BASE", "https://api.telegram.org")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")  # "username/repo"

APK_DIR = "apk"
HASH_FILE = ".last_apk_hash"

if not all([STOKEN, ROOT_FID, GITHUB_TOKEN, BOT_TOKEN, CHAT_ID, REPO_NAME]):
    raise Exception("❌ 请检查所有 Secrets 是否已设置: QUARK_STOKEN, QUARK_ROOT_FID, GITHUB_TOKEN, BOT_TOKEN, CHAT_ID, GITHUB_REPOSITORY")

# ====== SHA256 hash 计算 ======
def compute_hash(file_paths):
    sha = hashlib.sha256()
    for path in sorted(file_paths):
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
    return sha.hexdigest()

def load_last_hash():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            return f.read().strip()
    return None

def save_last_hash(hash_str):
    with open(HASH_FILE, "w") as f:
        f.write(hash_str)

# ====== 获取指定文件夹内容 ======
def get_files(pdir_fid):
    files = []
    page = 1
    while True:
        resp = requests.get(
            WORKER_URL,
            params={
                "pwd_id": PWD_ID,
                "stoken": STOKEN,
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": 50
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("list", [])
        if not data:
            break
        files.extend(data)
        if len(data) < 50:
            break
        page += 1
    return files

# ====== 获取最新文件夹 ======
def get_latest_folder(folders):
    numeric_folders = [f for f in folders if f.get("dir", False)]
    if not numeric_folders:
        return None
    latest = max(numeric_folders, key=lambda x: x.get("file_name", "0"))
    return latest

# ====== 下载文件到本地 ======
def download_file(file_info, target_dir=APK_DIR):
    os.makedirs(target_dir, exist_ok=True)
    download_url = f"{WORKER_URL}?pwd_id={PWD_ID}&stoken={STOKEN}&pdir_fid={file_info['fid']}"
    file_path = os.path.join(target_dir, file_info["file_name"])
    resp = requests.get(download_url, timeout=30)
    resp.raise_for_status()
    with open(file_path, "wb") as f:
        f.write(resp.content)
    print(f"✅ 下载完成: {file_info['file_name']}")
    return file_path

# ====== 上传 GitHub Release ======
def upload_release(apk_files):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    tag_name = f"auto-{datetime.now().strftime('%Y%m%d-%H%M')}"

    release = repo.create_git_release(
        tag=tag_name,
        name=f"FongMi APK {tag_name}",
        message=f"自动同步自：https://github.com/FongMi/Release/tree/fongmi/apk\n仅当 APK 内容变化时发布。",
        draft=False,
        prerelease=False
    )

    for apk in apk_files:
        release.upload_asset(apk)
        print(f"⚡ 上传到 Release: {apk}")

# ====== 推送 Telegram ======
def push_telegram(apk_files, caption):
    media = []
    for i, apk in enumerate(apk_files):
        m = {"type": "document", "media": f"attach://{os.path.basename(apk)}"}
        if i == len(apk_files) - 1:
            m["caption"] = caption
        media.append(m)
    media_json = json.dumps(media)

    files = {os.path.basename(apk): open(apk, "rb") for apk in apk_files}
    resp = requests.post(
        f"{BOT_API_BASE}/bot{BOT_TOKEN}/sendMediaGroup",
        data={"chat_id": CHAT_ID, "media": media_json},
        files=files
    )
    for f in files.values():
        f.close()

    resp_json = resp.json()
    if resp_json.get("ok"):
        print("✅ Telegram 推送成功")
    else:
        print("❌ Telegram 推送失败:", resp.text)

# ====== 主逻辑 ======
def main():
    print("🔍 获取根目录文件夹列表...")
    all_files = get_files(ROOT_FID)

    # 最新文件夹
    f0_folder = next((f for f in all_files if f["fid"]=="f0c75c96e96e4310b96383b4b22040e3"), None)
    f0_files = get_files(f0_folder["fid"]) if f0_folder else []
    latest_f0_file = get_latest_folder(f0_files)

    # 四个 APK
    f8_folder = next((f for f in all_files if f["fid"]=="8d6dce95581c49f29183380d3805e9b5"), None)
    f8_files = get_files(f8_folder["fid"]) if f8_folder else []

    print(f"📦 最新文件夹数量: {1 if latest_f0_file else 0}")
    print(f"📦 四个 APK 数量: {len(f8_files)}")

    # 下载到本地
    apk_files = []
    if latest_f0_file:
        apk_files.append(download_file(latest_f0_file))
    for apk in f8_files:
        apk_files.append(download_file(apk))

    # ====== 检测变更 ======
    new_hash = compute_hash(apk_files)
    last_hash = load_last_hash()
    if new_hash == last_hash:
        print("ℹ️ APK 内容未变化 → 跳过 Release 和 Telegram 推送")
        return
    save_last_hash(new_hash)
    print("🔔 APK 内容有变化 → 执行 Release 和 Telegram 推送")

    # 创建 GitHub Release 并上传
    upload_release(apk_files)

    # 构造 Telegram caption
    update_time = datetime.now().strftime('%Y/%m/%d %H:%M')
    caption = f"FongMi APK 更新 - 时间: {update_time}\n共 {len(apk_files)} 个文件"

    # 推送到 Telegram
    push_telegram(apk_files, caption)

if __name__ == "__main__":
    main()
