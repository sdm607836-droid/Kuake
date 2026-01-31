import os
import json
import time
import requests
from datetime import datetime
import threading
import re

# ================= 配置 =================
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIR_PRO = "8d6dce95581c49f29183380d3805e9b5"
TARGET_DIR_OK = "f0c75c96e96e4310b96383b4b22040e3"

REPO = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")

if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN")
    exit(1)

HEADERS = {
    "User-Agent": "quark-cloud-drive",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE or "",
}

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

# ================= 工具函数 =================
def fetch_page(pdir_fid, page=1):
    r = requests.post(
        WORKER_URL,
        json={
            "pwd_id": PWD_ID,
            "stoken": STOKEN,
            "pdir_fid": pdir_fid,
            "_page": page,
            "_size": PAGE_SIZE,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("data", {}).get("detail_info", {}).get("list", [])

def list_all(fid):
    all_files = []
    page = 1
    while True:
        data = fetch_page(fid, page)
        if not data:
            break
        all_files.extend(data)
        if len(data) < PAGE_SIZE:
            break
        page += 1
    return all_files

def latest_subfolder(fid):
    folders = [f for f in fetch_page(fid) if f.get("dir")]
    if not folders:
        return None

    def key(f):
        digits = "".join(c for c in f.get("file_name", "") if c.isdigit())
        return int(digits) if digits else 0

    return max(folders, key=key)

def extract_version(text):
    m = re.search(r"\d+(\.\d+)+", text)
    return m.group(0) if m else "unknown"

# ================= 下载 =================
def get_download_url(fid):
    url = "https://drive-pc.quark.cn/1/clouddrive/file/download"
    r = requests.post(
        url,
        json={"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN},
        headers=HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    for item in data:
        if item.get("download_url"):
            cookies = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
            return item["download_url"], cookies
    return None, None

def download_file(url, cookies, filename):
    h = HEADERS.copy()
    h["Cookie"] = cookies
    with requests.get(url, headers=h, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for c in r.iter_content(8192):
                if c:
                    f.write(c)

# ================= 重命名规则 =================
PRO_RENAME = {
    "电视版-32": "leanback-arm64_v7a-pro.apk",
    "电视版-64": "leanback-arm64_v8a-pro.apk",
    "手机版-64": "mobile-arm64_v8a-pro.apk",
    "模拟器": "mobile-arm64_v7a-pro.apk",
}

OK_RENAME = {
    "海信": "hisense-tv-customized.apk",
    "mobile-armeabi": "mobile-arm64_v7a-ok.apk",
    "mobile-arm64": "mobile-arm64_v8a-ok.apk",
    "leanback-armeabi": "leanback-arm64_v7a-ok.apk",
    "leanback-arm64": "leanback-arm64_v8a-ok.apk",
}

EXCLUDE = [
    "OK影视-电视版",
    "OK影视-手机版",
]

def rename_apk(name, is_pro):
    table = PRO_RENAME if is_pro else OK_RENAME
    for k, v in table.items():
        if k in name:
            return v
    return None

# ================= GitHub Release =================
def upload_release(file, tag):
    url = f"https://uploads.github.com/repos/{REPO}/releases/{tag}/assets?name={os.path.basename(file)}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/octet-stream",
    }
    with open(file, "rb") as f:
        r = requests.post(url, headers=headers, data=f)
    if r.status_code not in (200, 201):
        print("上传失败:", r.text)

def get_or_create_release(tag):
    api = f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
    r = requests.get(api, headers={"Authorization": f"token {GITHUB_TOKEN}"})
    if r.status_code == 200:
        return r.json()["id"]

    r = requests.post(
        f"https://api.github.com/repos/{REPO}/releases",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"tag_name": tag, "name": tag},
    )
    r.raise_for_status()
    return r.json()["id"]

# ================= 主流程 =================
def process_dir(fid, is_pro):
    files = list_all(fid)
    txt_content = ""
    version = "unknown"

    for f in files:
        name = f["file_name"]

        if f.get("file_type") == 2:
            url, ck = get_download_url(f["fid"])
            if url:
                tmp = f"tmp_{name}"
                download_file(url, ck, tmp)
                with open(tmp, "r", encoding="utf-8", errors="ignore") as tf:
                    txt_content = tf.read()
                version = extract_version(txt_content)
                os.remove(tmp)

    for f in files:
        if f.get("dir"):
            continue
        name = f["file_name"]

        if any(x in name for x in EXCLUDE):
            continue

        new_name = rename_apk(name, is_pro)
        if not new_name:
            continue

        url, ck = get_download_url(f["fid"])
        if not url:
            continue

        download_file(url, ck, new_name)
        upload_release(new_name, RELEASE_ID)
        os.remove(new_name)

    txt_name = "Version-Pro.txt" if is_pro else "Version-OK.txt"
    with open(txt_name, "w", encoding="utf-8") as f:
        f.write(txt_content)
    upload_release(txt_name, RELEASE_ID)
    os.remove(txt_name)

def main():
    global RELEASE_ID
    tag = datetime.now().strftime("auto-%Y%m%d")
    RELEASE_ID = get_or_create_release(tag)

    print("处理 OK Pro 版")
    process_dir(TARGET_DIR_PRO, True)

    print("处理 OK 标准版")
    latest = latest_subfolder(TARGET_DIR_OK)
    if latest:
        process_dir(latest["fid"], False)

if __name__ == "__main__":
    main()
