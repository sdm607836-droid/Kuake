import os
import json
import requests
import time
from datetime import datetime
import threading

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50

TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",
    "f0c75c96e96e4310b96383b4b22040e3",
]

STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")  # 必须设置完整的 Cookie 字符串

if not STOKEN or not COOKIE:
    print("❌ 缺少 QUARK_STOKEN 或 QUARK_COOKIE")
    exit(1)

# 全局缓存：记录转存后的 local_fid 和过期时间
FILES_CACHE = {}           # { fid: { "local_fid": "...", "expires": timestamp, "done": False } }
FILES_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

# ===== 列表相关函数 =====
def fetch_page(pdir_fid, page=1):
    try:
        r = requests.post(
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
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("detail_info", {}).get("list", [])
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {e}")
        return []

def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        page_data = fetch_page(fid, page)
        if not page_data:
            break
        files.extend(page_data)
        if len(page_data) < PAGE_SIZE:
            break
        page += 1
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

# ===== 转存文件 =====
def copy_file(fid, share_fid_token):
    url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
    payload = {
        "fid_list": [fid],
        "fid_token_list": [share_fid_token],
        "to_pdir_fid": "0",
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "pdir_fid": "0",
        "scene": "link",
    }

    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()
        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            print(f"转存 {fid[:8]} 失败：无 task_id")
            return None

        for i in range(60):
            time.sleep(1.2)
            status_url = f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&retry_index={i}&task_id={task_id}"
            rs = requests.get(status_url, headers=HEADERS, timeout=15)
            js = rs.json()
            code = js.get("code")
            if code in [31001, 32003]:
                print(f"转存失败 {fid[:8]} code={code}")
                return None
            fids = js.get("data", {}).get("save_as", {}).get("save_as_top_fids", [])
            for lf in fids:
                if lf:
                    return lf
        print(f"转存 {fid[:8]} 超时")
        return None
    except Exception as e:
        print(f"转存异常 {fid[:8]}: {e}")
        return None

# ===== 获取原画下载链接 =====
def get_original_download(fid, share_fid_token):
    with FILES_LOCK:
        if fid in FILES_CACHE:
            c = FILES_CACHE[fid]
            if c.get("ori_urls") and c.get("expires", 0) > time.time():
                return c["ori_urls"], c.get("cookies", "")

    local_fid = copy_file(fid, share_fid_token)
    if not local_fid:
        return [], ""

    url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    payload = {"fids": [local_fid]}

    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()

        urls = []
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                if "download_url" in item and item["download_url"]:
                    urls.append(item["download_url"])

        if not urls:
            print(f"无下载链接 {fid[:8]}")
            return [], ""

        cookies_str = "; ".join([f"{k}={v}" for k, v in r.cookies.items()])

        expires = time.time() + 86400  # 24小时

        with FILES_LOCK:
            FILES_CACHE[fid] = {
                "local_fid": local_fid,
                "ori_urls": urls,
                "cookies": cookies_str,
                "expires": expires,
                "done": False
            }

        return urls, cookies_str

    except Exception as e:
        print(f"获取链接失败 {fid[:8]}: {e}")
        return [], ""

# ===== 删除转存文件 =====
def cleanup_transferred_files():
    delete_url = "https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc"
    with FILES_LOCK:
        to_delete = []
        for fid, info in list(FILES_CACHE.items()):
            if not info.get("done") and info.get("expires", 0) < time.time() + 300:
                to_delete.append((fid, info["local_fid"]))

    for fid, local_fid in to_delete:
        payload = {
            "filelist": [local_fid],
            "action_type": 2,
            "exclude_fids": [],
        }
        try:
            r = requests.post(delete_url, json=payload, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                with FILES_LOCK:
                    if fid in FILES_CACHE:
                        FILES_CACHE[fid]["done"] = True
                print(f"删除成功 {local_fid[:8]}")
        except Exception as e:
            print(f"删除失败 {local_fid[:8]}: {e}")

# ===== 主逻辑 =====
def main():
    all_apks = []
    download_results = []

    print("\n=== 目录1 ===")
    apks1 = get_apks_in_dir(TARGET_DIRS[0])
    print(f"找到 {len(apks1)} 个 APK")
    for f in apks1:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid")
        sft = f.get("share_fid_token", "")
        print(f"  • {name:<50} {size:>12,} B")
        all_apks.append(f)

        urls, ck = get_original_download(fid, sft)
        if urls:
            download_results.append({
                "name": name,
                "size": size,
                "fid": fid,
                "urls": urls,
                "cookies": ck
            })
            print(f"    下载链接已获取 ({len(urls)} 条)")

    print("\n=== 目录2 最新文件夹 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        print(f"最新：{latest.get('file_name', '?')}")
        apks2 = get_apks_in_dir(latest["fid"])
        print(f"找到 {len(apks2)} 个 APK")
        for f in apks2:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid")
            sft = f.get("share_fid_token", "")
            print(f"  • {name:<50} {size:>12,} B")
            all_apks.append(f)

            urls, ck = get_original_download(fid, sft)
            if urls:
                download_results.append({
                    "name": name,
                    "size": size,
                    "fid": fid,
                    "urls": urls,
                    "cookies": ck
                })
                print(f"    下载链接已获取 ({len(urls)} 条)")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)

    if download_results:
        with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
        print(f"\n保存了 {len(download_results)} 条下载信息")

    # 延迟 3 分钟后清理（避免 Actions 超时）
    threading.Timer(180, cleanup_transferred_files).start()

if __name__ == "__main__":
    main()
