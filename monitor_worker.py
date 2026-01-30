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

# ===== Worker 请求函数 =====
def fetch_page_from_worker(stoken, pdir_fid, page):
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
        data = resp.json()
        files = data.get("data", {}).get("detail_info", {}).get("list", [])
        print(f"📡 请求目录 {pdir_fid[:8]} 第 {page} 页成功，条目数: {len(files)}")
        return data
    except Exception as e:
        print(f"❌ Worker 请求失败: {e}")
        return None

# ===== 递归获取所有 APK 文件 =====
def get_files_recursively(stoken, pdir_fid):
    all_files = []
    page = 1
    while True:
        data = fetch_page_from_worker(stoken, pdir_fid, page)
        if not data:
            break
        files = data.get("data", {}).get("detail_info", {}).get("list", [])
        for f in files:
            if f.get("dir", False):
                # 递归进入子目录
                all_files.extend(get_files_recursively(stoken, f["fid"]))
            elif f.get("file_type") == 1 or f.get("format_type") == "application/vnd.android.package-archive":
                all_files.append(f)
        # 判断是否还有下一页
        meta = data.get("metadata", {}).get("detail_meta", {})
        if page * PAGE_SIZE >= meta.get("_total", len(files)):
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
    print("\n🔍 开始获取所有 APK 文件...")
    files = get_files_recursively(STOKEN, ROOT_FID)
    if not files:
        print("❌ 没有获取到 APK 文件")
        exit(1)

    print(f"\n📦 获取到总 APK 文件数: {len(files)}\n")
    for f in files:
        print(f"- {f.get('file_name')} | {f.get('size',0)} bytes")

    # 保存 JSON
    with open("apk_files.json", "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
    print("\n💾 APK 文件列表已保存到 apk_files.json")

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
