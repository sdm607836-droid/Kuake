import os
import requests
import sys

# ====== 配置区 ======
PWD_ID = "cb0ee2b9ac64"
BASE_URL = "https://pan.quark.cn"

COOKIE = os.getenv("QUARK_COOKIE")
if not COOKIE:
    print("❌ 未检测到 QUARK_COOKIE 环境变量")
    sys.exit(1)

HEADERS = {
    "user-agent": "Mozilla/5.0",
    "accept": "application/json, text/plain, */*",
    "referer": f"https://pan.quark.cn/s/{PWD_ID}",
    "cookie": COOKIE,
}

# ====== Step 1：获取 stoken + 根目录 fid ======
def get_share_info():
    url = f"{BASE_URL}/1/clouddrive/share/sharepage/detail"
    params = {
        "pwd_id": PWD_ID,
        "pr": "ucpro",
        "fr": "h5",
    }

    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    if r.status_code != 200:
        print("❌ 获取分享信息失败")
        print(r.text)
        sys.exit(1)

    data = r.json().get("data")
    if not data:
        print("❌ 返回数据异常")
        print(r.text)
        sys.exit(1)

    return data["stoken"], data["pdir_fid"]

# ====== Step 2：列出文件 ======
def list_files(stoken, pdir_fid):
    url = f"{BASE_URL}/1/clouddrive/share/sharepage/v2/detail"
    params = {
        "pwd_id": PWD_ID,
        "stoken": stoken,
        "pdir_fid": pdir_fid,
        "_page": 1,
        "_size": 100,
        "_fetch_total": 1,
        "ver": 2,
        "pr": "ucpro",
        "fr": "h5",
    }

    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    if r.status_code != 200:
        print("❌ 获取文件列表失败")
        print(r.text)
        sys.exit(1)

    return r.json()["data"]["list"]

# ====== 主逻辑 ======
def main():
    print("🔍 获取分享信息...")
    stoken, root_fid = get_share_info()
    print("✅ stoken OK")
    print(f"📁 root_fid = {root_fid}")

    print("📦 获取文件列表...")
    files = list_files(stoken, root_fid)

    print(f"\n✅ 共 {len(files)} 个文件：\n")
    for f in files:
        print(f"- {f['file_name']} | {f['size']} bytes")

if __name__ == "__main__":
    main()
