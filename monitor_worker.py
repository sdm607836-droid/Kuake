# -*- coding: utf-8 -*-
import os
import json
import requests
import time
from datetime import datetime

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

STOKEN = os.getenv("QUARK_STOKEN")
if not STOKEN:
    print("❌ 请设置环境变量 QUARK_STOKEN")
    exit(1)

# ===== Worker 统一请求函数 =====
def worker_post(payload, timeout=60):
    try:
        r = requests.post(WORKER_URL, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True):
            print(f"Worker 返回错误: {data.get('msg') or data.get('error')}")
            return None
        return data.get("data")
    except Exception as e:
        print(f"Worker 请求失败: {e}")
        return None


# ===== 列目录（原有） =====
def fetch_page(pdir_fid, page=1):
    payload = {
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "pdir_fid": pdir_fid,
        "_page": page,
        "_size": PAGE_SIZE,
        "ver": 2,
        "pr": "ucpro",
        "fr": "h5",
    }
    data = worker_post(payload)
    if data:
        return data.get("detail_info", {}).get("list", [])
    return []


def get_apks_in_dir(fid):
    files = fetch_page(fid)
    return [f for f in files if not f.get("dir") and f.get("file_type") == 1]


def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None

    def key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else -1

    return max(folders, key=key)


# ===== 新增：尝试直接从分享链接获取下载地址（不转存） =====
def try_get_direct_download(fid, share_fid_token=""):
    payload = {
        "action": "get_share_download",
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "fid": fid,
        "share_fid_token": share_fid_token,  # 如果有就传
    }
    data = worker_post(payload, timeout=45)
    if not data:
        return None

    urls = data.get("urls", [])
    if urls:
        return {
            "success": True,
            "urls": urls,
            "cookies": data.get("cookies", ""),
            "from": "direct_share"
        }
    return None


# ===== 主逻辑 =====
def main():
    all_apks = []
    download_infos = []

    print("\n=== 扫描目录 1 ===")
    dir1 = TARGET_DIRS[0]
    apks1 = get_apks_in_dir(dir1)
    print(f"找到 {len(apks1)} 个 APK")
    for f in apks1:
        name = f.get("file_name", "unknown")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        print(f"  • {name:<50} {size:>12,} bytes")
        all_apks.append(f)

        # 尝试直链
        dl_info = try_get_direct_download(fid, f.get("share_fid_token", ""))
        if dl_info and dl_info["urls"]:
            download_infos.append({
                "name": name,
                "size": size,
                "fid": fid,
                "urls": dl_info["urls"],
                "method": "direct"
            })
            print(f"    → 找到直链 ({len(dl_info['urls'])} 条)")

    print("\n=== 扫描目录 2 - 最新子文件夹 ===")
    dir2 = TARGET_DIRS[1]
    latest = get_latest_subfolder(dir2)
    if latest:
        folder_name = latest.get("file_name", "?")
        fid_latest = latest.get("fid")
        print(f"最新文件夹：{folder_name}")

        apks2 = get_apks_in_dir(fid_latest)
        print(f"找到 {len(apks2)} 个 APK")
        for f in apks2:
            name = f.get("file_name", "unknown")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            print(f"  • {name:<50} {size:>12,} bytes")
            all_apks.append(f)

            dl_info = try_get_direct_download(fid, f.get("share_fid_token", ""))
            if dl_info and dl_info["urls"]:
                download_infos.append({
                    "name": name,
                    "size": size,
                    "fid": fid,
                    "parent": folder_name,
                    "urls": dl_info["urls"],
                    "method": "direct"
                })
                print(f"    → 找到直链 ({len(dl_info['urls'])} 条)")
    else:
        print("  没有找到子文件夹")

    # 保存结果
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)

    if download_infos:
        with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
            json.dump(download_infos, f, ensure_ascii=False, indent=2)
        print(f"\n保存了 {len(download_infos)} 个文件的下载尝试结果")

    print("\n执行结束")


if __name__ == "__main__":
    main()
