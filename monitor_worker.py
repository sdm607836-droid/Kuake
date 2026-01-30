import os
import json
import requests
from packaging import version as ver_parser

WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")
LAST_VERSION_FILE = ".last_version"

if not STOKEN or not ROOT_FID:
    print("❌ 请在 GitHub Secrets 设置 QUARK_STOKEN 和 QUARK_ROOT_FID")
    exit(1)

def fetch_page(page):
    try:
        resp = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": STOKEN,
                "pdir_fid": ROOT_FID,
                "_page": page,
                "_size": PAGE_SIZE,
                "ver": 2,
                "pr": "ucpro",
                "fr": "h5",
            },
            timeout=60
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ Worker 请求失败: {e}")
        return None

def get_all_files():
    all_files = []
    page = 1
    while True:
        data = fetch_page(page)
        if not data or "data" not in data or "detail_info" not in data["data"] or "list" not in data["data"]["detail_info"]:
            print("❌ 获取文件列表失败")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            break

        files = data["data"]["detail_info"]["list"]
        all_files.extend(files)

        # 判断是否有更多页
        meta = data.get("metadata", {}).get("detail_meta", {})
        total_count = meta.get("_total", len(files))
        if page * PAGE_SIZE >= total_count:
            break
        page += 1

    return all_files

def detect_new_version(files):
    # 提取可能版本号
    version_candidates = []
    for f in files:
        name = f.get("file_name", "")
        # x.y.z 格式
        if name.count('.') == 2 and all(p.isdigit() for p in name.split('.') if p.isdigit() or p.isalpha()):
            version_candidates.append(name)
        # 纯数字日期
        elif name.isdigit() and len(name) >= 6:
            version_candidates.append(name)

    if not version_candidates:
        return None

    def safe_parse(v):
        try:
            return ver_parser.parse(v)
        except:
            return ver_parser.parse("0.0.0")

    latest_version = max(version_candidates, key=safe_parse)
    return latest_version

def main():
    files = get_all_files()
    if not files:
        print("❌ 没有获取到文件")
        exit(1)

    print(f"\n📦 共 {len(files)} 个文件：\n")
    for f in files:
        print(f"- {f['file_name']} | {f.get('size',0)} bytes")

    # 保存 JSON
    with open("files.json", "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)

    # 检查版本变化
    latest_version = detect_new_version(files)
    last_version = None
    if os.path.exists(LAST_VERSION_FILE):
        with open(LAST_VERSION_FILE, "r", encoding="utf-8") as f:
            last_version = f.read().strip()

    if latest_version and latest_version != last_version:
        print(f"\n🚀 检测到新版本: {latest_version}")
        with open(LAST_VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(latest_version)
    else:
        print("\n✅ 没有新版本")

if __name__ == "__main__":
    main()
