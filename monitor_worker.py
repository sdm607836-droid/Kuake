import os
import json
import requests
import time
from datetime import datetime
import threading

# ===== 配置区 =====
# 注意: 请在 GitHub Secrets 中设置 QUARK_COOKIE 为完整的 Quark Cookie 字符串，例如 "puid=xxx; _token=yyy; ..."
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")

if not STOKEN or not COOKIE:
    print("❌ 请在 Secrets 设置 QUARK_STOKEN 和 QUARK_COOKIE")
    exit(1)

# 全局缓存
FILES_CACHE = {}
FILES_LOCK = threading.Lock()

# ===== 列目录函数（原有） =====
def fetch_page(pdir_fid, page=1):
    try:
        resp = requests.post(
            WORKER_URL,
            json={
                "pwd_id": PWD_ID,
                "stoken": STOKEN,
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
        return resp.json().get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"❌ 请求目录 {pdir_fid[:8]} 失败: {e}")
        return []

def get_apks_in_dir(fid):
    files = fetch_page(fid)
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1]
    return apks

def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    def folder_key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 0
    latest = max(folders, key=folder_key)
    return latest

# ===== 转存文件 (copyFile) =====
def copy_file(auth_id, fid, share_id, share_token, share_fid_token):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Cookie": COOKIE,
    }

    session = requests.Session()
    session.headers.update(headers)

    post_json = {
        "fid_list": [fid],
        "fid_token_list": [share_fid_token],
        "to_pdir_fid": "0",
        "pwd_id": share_id,
        "stoken": share_token,
        "pdir_fid": "0",
        "scene": "link",
    }
    url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"

    try:
        resp = session.post(url, json=post_json, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            print("转存失败: 未获取 task_id")
            return None

        for retry in range(50):
            status_url = f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&retry_index={retry}&task_id={task_id}"
            r = session.get(status_url, timeout=10)
            r.raise_for_status()
            j = r.json()
            code = j.get("code")
            if code == 31001:
                print("转存失败: Cookies 已失效")
                return None
            if code == 32003:
                print("转存失败: 云盘空间已满")
                return None

            fids = j.get("data", {}).get("save_as", {}).get("save_as_top_fids", [])
            for local_fid in fids:
                if local_fid:
                    timestamp = time.time() + 180
                    with FILES_LOCK:
                        if auth_id not in FILES_CACHE:
                            FILES_CACHE[auth_id] = {}
                        FILES_CACHE[auth_id][fid] = {
                            "local_fid": local_fid,
                            "time": timestamp,
                            "done": False,
                        }
                    return local_fid
            time.sleep(1)

        print("转存超时")
        return None
    except Exception as e:
        print(f"转存失败: {e}")
        return None

# ===== 获取下载链接 (oriUrl) =====
def ori_url(auth_id, fid, share_id, share_token, share_fid_token):
    with FILES_LOCK:
        if auth_id in FILES_CACHE and fid in FILES_CACHE[auth_id]:
            info = FILES_CACHE[auth_id][fid]
            if "ori_urls" in info and info.get("ori_expires", 0) > time.time():
                return info["ori_urls"], info.get("cookies", "")

    local_id = copy_file(auth_id, fid, share_id, share_token, share_fid_token)
    if not local_id:
        return [], ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Cookie": COOKIE,
    }

    session = requests.Session()
    session.headers.update(headers)

    post_json = {
        "fids": [local_id],
    }
    url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"

    try:
        resp = session.post(url, json=post_json, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        urls = []
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                if "download_url" in item:
                    urls.append(item["download_url"])

        if not urls:
            print("未找到下载链接")
            return [], ""

        cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])

        expires = time.time() + 24 * 3600

        with FILES_LOCK:
            if fid not in FILES_CACHE[auth_id]:
                FILES_CACHE[auth_id][fid] = {}
            FILES_CACHE[auth_id][fid]["ori_urls"] = urls
            FILES_CACHE[auth_id][fid]["cookies"] = cookie_str
            FILES_CACHE[auth_id][fid]["ori_expires"] = expires

        return urls, cookie_str
    except Exception as e:
        print(f"获取链接失败: {e}")
        return [], ""

# ===== 删除文件 (DeleteFiles) =====
def delete_files(auth_id, fid=None, share_id=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Cookie": COOKIE,
    }

    session = requests.Session()
    session.headers.update(headers)

    delete_url = "https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc"

    with FILES_LOCK:
        if auth_id not in FILES_CACHE:
            return
        items = FILES_CACHE[auth_id].copy()

    for key, value in items.items():
        if value["done"]:
            continue
        remaining = value["time"] - time.time()
        if remaining > 0:
            time.sleep(remaining)

        post_json = {
            "filelist": [value["local_fid"]],
            "action_type": 2,
            "exclude_fids": [],
        }
        try:
            resp = session.post(delete_url, json=post_json, timeout=15)
            resp.raise_for_status()
            if resp.status_code == 200 or "文件已经删除" in resp.text:
                with FILES_LOCK:
                    FILES_CACHE[auth_id][key]["done"] = True
                print(f"已删除文件 {value['local_fid']}")
        except Exception as e:
            print(f"删除失败: {e}")

# ===== 主逻辑 =====
def main():
    all_apks = []
    download_infos = []
    auth_id = "default_user"  # 可以替换为动态用户 ID

    print("\n=== 扫描目录 1 ===")
    dir1 = TARGET_DIRS[0]
    apks1 = get_apks_in_dir(dir1)
    print(f"找到 {len(apks1)} 个 APK 文件")
    for f in apks1:
        name = f.get("file_name", "unknown.apk")
        size = f.get("size", 0)
        fid = f.get("fid")
        share_fid_token = f.get("share_fid_token", "")  # 假设列表返回此字段，如果没有需调试
        print(f"  • {name:<50} {size:>12,} bytes")
        all_apks.append(f)

        urls, cookies = ori_url(auth_id, fid, PWD_ID, STOKEN, share_fid_token)
        if urls:
            download_infos.append({
                "name": name,
                "size": size,
                "fid": fid,
                "urls": urls,
                "cookies": cookies
            })
            print(f"    → 找到下载链接 ({len(urls)} 条)")

    print("\n=== 扫描目录 2 - 最新子文件夹 ===")
    dir2 = TARGET_DIRS[1]
    latest = get_latest_subfolder(dir2)
    if latest:
        folder_name = latest.get("file_name", "??")
        fid_latest = latest["fid"]
        print(f"最新文件夹：{folder_name}")

        apks2 = get_apks_in_dir(fid_latest)
        print(f"找到 {len(apks2)} 个 APK 文件")
        for f in apks2:
            name = f.get("file_name", "unknown.apk")
            size = f.get("size", 0)
            fid = f.get("fid")
            share_fid_token = f.get("share_fid_token", "")  # 同上
            print(f"  • {name:<50} {size:>12,} bytes")
            all_apks.append(f)

            urls, cookies = ori_url(auth_id, fid, PWD_ID, STOKEN, share_fid_token)
            if urls:
                download_infos.append({
                    "name": name,
                    "size": size,
                    "fid": fid,
                    "urls": urls,
                    "cookies": cookies
                })
                print(f"    → 找到下载链接 ({len(urls)} 条)")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"quark_apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)
    print(f"\n已保存 APK 列表到 quark_apks_{ts}.json")

    if download_infos:
        with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
            json.dump(download_infos, f, ensure_ascii=False, indent=2)
        print(f"已保存下载链接到 downloads_{ts}.json")

    # 延迟删除转存的文件
    threading.Timer(200, delete_files, args=(auth_id,)).start()

if __name__ == "__main__":
    main()
