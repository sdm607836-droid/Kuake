import os
import json
import requests

# ========== 配置 ==========
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"  # 改成你部署的 Worker URL
PWD_ID = "cb0ee2b9ac64"

STOKEN = os.getenv("QUARK_STOKEN")
ROOT_FID = os.getenv("QUARK_ROOT_FID")

if not STOKEN or not ROOT_FID:
    print("❌ 请在 GitHub Secrets 设置 QUARK_STOKEN 和 QUARK_ROOT_FID")
    exit(1)

# ========== 调用 Worker ==========
try:
    resp = requests.post(
        WORKER_URL,
        json={
            "pwd_id": PWD_ID,
            "stoken": STOKEN,
            "pdir_fid": ROOT_FID,
            "_page": 1,
            "_size": 100,
            "_fetch_total": 1,
            "ver": 2,
            "pr": "ucpro",
            "fr": "h5",
        },
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
except Exception as e:
    print(f"❌ 调用 Worker 失败: {e}")
    exit(1)

# ========== 检查返回数据 ==========
if "data" not in data or "detail_info" not in data["data"] or "list" not in data["data"]["detail_info"]:
    print("❌ 获取文件列表失败")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    exit(1)

files = data["data"]["detail_info"]["list"]

# ========== 输出文件列表 ==========
print(f"\n📦 共 {len(files)} 个文件：\n")
for f in files:
    print(f"- {f['file_name']} | {f['size']} bytes")

# ========== 可选：保存 JSON ==========
with open("files.json", "w", encoding="utf-8") as f:
    json.dump(files, f, ensure_ascii=False, indent=2)
