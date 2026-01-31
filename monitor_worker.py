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

# 调试：立即打印环境变量状态
print("=== 调试信息 ===")
STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")

print(f"QUARK_STOKEN 是否存在: {'是' if STOKEN else '否'}")
if STOKEN:
    print(f"QUARK_STOKEN 长度: {len(STOKEN)}")
    print(f"QUARK_STOKEN 前10字符: {STOKEN[:10]}...")
else:
    print("QUARK_STOKEN 为空！请检查 GitHub Secrets 名称是否为 QUARK_STOKEN（全大写）")

print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
if COOKIE:
    print(f"QUARK_COOKIE 长度: {len(COOKIE)}")
    print(f"QUARK_COOKIE 前20字符: {COOKIE[:20]}...")
else:
    print("QUARK_COOKIE 为空！只能运行列表扫描，无法转存/下载")
print("=== 调试结束 ===\n")

# 如果 STOKEN 缺失，直接退出（必须有）
if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN，无法继续")
    exit(1)

# COOKIE 缺失只警告，继续列表功能
if not COOKIE:
    print("⚠️ 缺少 QUARK_COOKIE → 只能扫描列表，无法转存和获取下载链接")

# 全局缓存
FILES_CACHE = {}  # fid -> {"local_fid": "...", "expires": timestamp, "done": False, "ori_urls": [], "cookies": ""}
FILES_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

# ===== 测试个人网盘是否可访问（验证 Cookie 有效性） =====
def test_personal_drive():
    test_url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_fetch_total=1&_size=10"
    print("\n=== 测试个人网盘访问 ===")
    try:
        r = requests.get(test_url, headers=HEADERS, timeout=20)
        print(f"读个人网盘测试: 状态码 {r.status_code}")
        if r.status_code == 200:
            print("Cookie 有效，能访问个人网盘")
            # 可选：打印部分响应查看是否正常
            # print("响应示例:", r.json().get("data", {}).get("list", [])[:2])
        else:
            print(f"Cookie 无效或风控: {r.text[:200]}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    print("=== 测试结束 ===\n")

# ===== 列表相关函数 =====
def fetch_page(pdir_fid, page=1):
    print(f"请求列表: pdir_fid={pdir_fid[:8]}, page={page}")
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
        data = r.json()
        list_data = data.get("data", {}).get("detail_info", {}).get("list", [])
        print(f" 返回 {len(list_data)} 条数据")
        return list_data
    except Exception as e:
        print(f"列表请求失败 {pdir_fid[:8]}: {str(e)}")
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
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1]
    print(f" 目录 {fid[:8]} 共找到 {len(apks)} 个 APK")
    return apks

def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        print(f" 目录 {fid[:8]} 无子文件夹")
        return None
    def key(f):
        name = f.get("file_name", "")
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else -1
    latest = max(folders, key=key)
    print(f" 找到最新子文件夹: {latest.get('file_name', '?')}")
    return latest

# ===== 转存文件 =====
def copy_file(fid, share_fid_token=""):
    if not COOKIE:
        print(f" 无 COOKIE，跳过转存 {fid[:8]}")
        return None
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
    print(f"开始转存 {fid[:8]}...")
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()
        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            print(f" 转存失败 {fid[:8]}: 无 task_id")
            return None
        for i in range(60):
            time.sleep(1.2)
            status_url = f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&retry_index={i}&task_id={task_id}"
            rs = requests.get(status_url, headers=HEADERS, timeout=15)
            js = rs.json()
            code = js.get("code")
            if code in [31001, 32003]:
                print(f" 转存失败 {fid[:8]} code={code}")
                return None
            fids = js.get("data", {}).get("save_as", {}).get("save_as_top_fids", [])
            for lf in fids:
                if lf:
                    print(f" 转存成功 {fid[:8]} → local_fid={lf[:8]}")
                    return lf
        print(f" 转存超时 {fid[:8]}")
        return None
    except Exception as e:
        print(f" 转存异常 {fid[:8]}: {str(e)}")
        return None

# ===== 获取原画下载链接 =====
def get_original_download(fid, share_fid_token=""):
    if not COOKIE:
        print(f" 无 COOKIE，跳过下载链接获取 {fid[:8]}")
        return [], ""
    with FILES_LOCK:
        if fid in FILES_CACHE:
            c = FILES_CACHE[fid]
            if c.get("ori_urls") and c.get("expires", 0) > time.time():
                print(f" 缓存命中 {fid[:8]}")
                return c["ori_urls"], c.get("cookies", "")
    local_fid = copy_file(fid, share_fid_token)
    if not local_fid:
        return [], ""
    url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    payload = {"fids": [local_fid]}
    print(f" 请求下载链接 {fid[:8]}...")
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
            print(f" 无下载链接 {fid[:8]}")
            return [], ""
        cookies_str = "; ".join([f"{k}={v}" for k, v in r.cookies.items()])
        expires = time.time() + 86400
        with FILES_LOCK:
            FILES_CACHE[fid] = {
                "local_fid": local_fid,
                "ori_urls": urls,
                "cookies": cookies_str,
                "expires": expires,
                "done": False
            }
        print(f" 获取成功 {fid[:8]} ({len(urls)} 条链接)")
        return urls, cookies_str
    except Exception as e:
        print(f" 获取链接失败 {fid[:8]}: {str(e)}")
        return [], ""

# ===== 删除转存文件 =====
def cleanup_transferred_files():
    if not COOKIE:
        print("无 COOKIE，跳过清理")
        return
    delete_url = "https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc"
    with FILES_LOCK:
        to_delete = [(fid, info["local_fid"]) for fid, info in FILES_CACHE.items()
                     if not info.get("done") and info.get("expires", 0) < time.time() + 300]
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
            print(f"删除失败 {local_fid[:8]}: {str(e)}")

# ===== 主逻辑 =====
def main():
    # 先测试个人网盘访问（验证 Cookie 是否有效）
    test_personal_drive()

    all_apks = []
    download_results = []

    print("\n=== 扫描目录1 ===")
    apks1 = get_apks_in_dir(TARGET_DIRS[0])
    for f in apks1:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        print(f" • {name:<50} {size:>12,} B")
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
            print(f" → 下载链接已获取 ({len(urls)} 条)")

    print("\n=== 扫描目录2 - 最新子文件夹 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        print(f"最新文件夹：{latest.get('file_name', '?')}")
        apks2 = get_apks_in_dir(latest["fid"])
        for f in apks2:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            print(f" • {name:<50} {size:>12,} B")
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
                print(f" → 下载链接已获取 ({len(urls)} 条)")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)
    print(f"\n已保存 APK 列表到 apks_{ts}.json")

    if download_results:
        with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
        print(f"已保存 {len(download_results)} 条下载信息到 downloads_{ts}.json")

    # 清理
    print("\n开始清理转存文件...")
    cleanup_transferred_files()

if __name__ == "__main__":
    main()
