import os
import json
import requests
from packaging import version as ver_parser

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 修改为你的 Worker URL
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
LAST_VERSION_FILE = ".last_version"

# ===== 获取 Secrets =====
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")

if not STOKEN or not ROOT_FID:
    print("❌ 请在 GitHub Secrets 设置 QUARK_STOKEN 和 QUARK_ROOT_FID")
    exit(1)

# ===== 日志打印环境信息 =====
print(f"▶ Worker URL: {WORKER_URL}")
print(f"▶ PWD_ID: {PWD_ID}")
print(f"▶ STOKEN: {STOKEN[:8]}... (隐藏部分)")
print(f"▶ ROOT_FID: {ROOT_FID[:8]}... (隐藏部分)")

# ===== 分页请求 Worker 获取文件 =====
def fetch_page(page):
    print(f"📡 请求第 {page} 页文件列表...")
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
            timeout=60  # 延长超时
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("data", {}).get("detail_info", {}).get("list", [])
        print(f"✅ 第 {page} 页请求成功，文件数: {len(files)}")
        return data
    except Exception as e:
        print(f"❌ Worker 请求失败: {e}")
        return None

def get_all_files():
    all_files = []
    page = 1
    while True:
        data = fetch_page(page)
        if not data:
            print("❌ 获取文件列表失败")
            break

        files = data.get("data", {}).get("detail_info", {}).get("list", [])
        all_files.extend(files)

        # 判断是否有更多页
        meta = data.get("metadata", {}).get("detail_meta", {})
        total_count = meta.get("_total", len(files))
        if page * PAGE_SIZE >= total_count:
            break
        page += 1

    return all_files

# ===== 检测最新版本 =====
def detect_new_version(files):
    version_candidates = []
    for f in files:
        name = f.get("file_name", "")
        # x.y.z 格式
        if name.count('.') == 2 and all(p.isdigit() for p in name.split('.') if p.isdigit() or p.isalpha()):
            version_candidates.append(name)
        # 纯数字长串（日期）
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

# ===== 主逻辑 =====
def main():
    print("\n🔍 开始获取文件列表...")
    files = get_all_files()
    if not files:
        print("❌ 没有获取到文件")
        exit(1)

    print(f"\n📦 获取到总文件数: {len(files)}\n")
    for f in files:
        print(f"- {f.get('file_name')} | {f.get('size',0)} bytes")

    # 保存 JSON
    with open("files.json", "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
    print("\n💾 文件列表已保存到 files.json")

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
        print("\n✅ 当前没有新版本")

if __name__ == "__main__":
    main()
