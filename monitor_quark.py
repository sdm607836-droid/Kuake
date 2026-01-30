import os, json, requests

# Worker URL
WORKER_URL = "https://你的worker子域名.workers.dev"

# 分享页参数
PWD_ID = "cb0ee2b9ac64"
STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")

if not STOKEN or not ROOT_FID:
    print("❌ 请设置 QUARK_STOKEN 和 QUARK_ROOT_FID Secrets")
    exit(1)

# 调用 Worker 获取文件列表
resp = requests.get(
    f"{WORKER_URL}?pwd_id={PWD_ID}&stoken={STOKEN}&pdir_fid={ROOT_FID}",
    timeout=15
)
resp.raise_for_status()
data = resp.json()

if "data" not in data or "list" not in data["data"]:
    print("❌ 获取文件列表失败")
    print(data)
    exit(1)

files = data["data"]["list"]
print(f"\n📦 共 {len(files)} 个文件：\n")
for f in files:
    print(f"- {f['file_name']} | {f['size']} bytes")

# 保存 JSON（可选）
with open("files.json", "w", encoding="utf-8") as f:
    json.dump(files, f, ensure_ascii=False, indent=2)
