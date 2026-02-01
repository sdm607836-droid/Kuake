import os
import json
import requests
import time
from datetime import datetime
import threading
import re
from tqdm import tqdm

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"  # 你的分享 pwd_id
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版
]

# 重命名映射（Pro版）
PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.* - 模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

# 重命名映射（标准版）
OK_RENAME_MAP = {
    r"海信专版-OK影视.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a.*\.apk": "leanback-arm64_v8a-ok.apk",
}

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

# ===== 获取环境变量 =====
COOKIE = os.getenv("QUARK_COOKIE")
QUARK_STOKEN = os.getenv("QUARK_STOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

# ===== 自动获取/刷新 stoken =====
def get_share_token(pwd_id=PWD_ID, passcode=""):
    """官方接口获取 stoken"""
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
    headers = HEADERS.copy()
    payload = {"pwd_id": pwd_id, "passcode": passcode}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code == 200 and r.json().get("code") == 0:
            stoken = r.json()["data"].get("stoken")
            return stoken
    except:
        pass
    return None

def get_latest_stoken():
    stoken = get_share_token()
    if stoken:
        return stoken
    if QUARK_STOKEN:
        return QUARK_STOKEN
    return None

STOKEN = get_latest_stoken()
if not STOKEN:
    print("❌ 无有效 stoken，退出")
    exit(1)

# ===== 测试 cookie 有效性 =====
def test_personal_drive():
    url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_fetch_total=1&_size=10"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            print("✅ Cookie 有效，能访问个人网盘")
        else:
            print("⚠️ Cookie 无效或风控:", r.status_code)
    except Exception as e:
        print("测试失败:", str(e))

# ===== 获取目录列表 =====
def fetch_page(pdir_fid, page=1):
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
    params = {
        "pr": "ucpro",
        "fr": "pc",
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "pdir_fid": pdir_fid,
        "_page": page,
        "_size": PAGE_SIZE,
        "_fetch_total": "1",
        "ver": 2,
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("data", {}).get("list", [])
    except:
        pass
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
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("file_name", "").endswith(".apk")]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt")]
    return apks, txts

def get_latest_subfolder(fid):
    files = fetch_page(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    latest = max(folders, key=lambda f: int("".join(filter(str.isdigit, f.get("file_name",""))) or 0))
    return latest

# ===== 转存文件 =====
def copy_file(fid, share_fid_token=""):
    if not COOKIE:
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
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        task_id = r.json().get("data", {}).get("task_id")
        if not task_id:
            return None
        for i in range(60):
            time.sleep(1.2)
            status_url = f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&retry_index={i}&task_id={task_id}"
            rs = requests.get(status_url, headers=HEADERS, timeout=15)
            js = rs.json()
            fids = js.get("data", {}).get("save_as", {}).get("save_as_top_fids", [])
            for lf in fids:
                if lf:
                    return lf
    except:
        return None
    return None

# ===== 获取下载链接 + 下载 =====
def get_original_download(fid, share_fid_token="", name="", size=0, is_txt=False):
    if not COOKIE:
        return [], ""
    with FILES_LOCK:
        if fid in FILES_CACHE and FILES_CACHE[fid].get("ori_urls") and FILES_CACHE[fid].get("expires",0) > time.time():
            return FILES_CACHE[fid]["ori_urls"], FILES_CACHE[fid].get("cookies","")

    direct_url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    payload = {"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN}

    # 自动重试 3 次
    for attempt in range(3):
        try:
            r = requests.post(direct_url, json=payload, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                data = r.json()
                urls = [item["download_url"] for item in data.get("data",[]) if item.get("download_url")]
                if urls:
                    cookies_str = "; ".join([f"{k}={v}" for k,v in r.cookies.items()])
                    with FILES_LOCK:
                        FILES_CACHE[fid] = {"ori_urls": urls, "cookies": cookies_str, "expires": time.time()+86400, "done": False}
                    # 下载文件
                    filename = name
                    if not is_txt:
                        for pattern, new_name in PRO_RENAME_MAP.items():
                            if re.search(pattern, name):
                                filename = new_name
                                break
                        for pattern, new_name in OK_RENAME_MAP.items():
                            if re.search(pattern, name):
                                filename = new_name
                                break
                        if filename == name:
                            filename = name.replace(".apk","").replace(" ","_").replace("/","_")+".apk"

                    dl_headers = HEADERS.copy()
                    dl_headers["Cookie"] = cookies_str
                    dl_headers["Referer"] = "https://drive-pc.quark.cn/"
                    dl_headers["Accept"] = "*/*"
                    dl_headers["Accept-Encoding"] = "identity"
                    dl_headers["Range"] = "bytes=0-"

                    with requests.get(urls[0], headers=dl_headers, stream=True, timeout=600) as dl_r:
                        dl_r.raise_for_status()
                        total_size = int(dl_r.headers.get("content-length",0))
                        with open(filename,"wb") as f, tqdm(total=total_size, desc=filename, unit="B", unit_scale=True, unit_divisor=1024) as pbar:
                            for chunk in dl_r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                    return urls, cookies_str
        except Exception as e:
            print(f"下载尝试 {attempt+1} 失败 {fid[:8]}: {str(e)}")
            time.sleep(2)
    # 转存再尝试
    local_fid = copy_file(fid, share_fid_token)
    if local_fid:
        payload["fids"] = [local_fid]
        try:
            r = requests.post(direct_url, json=payload, headers=HEADERS, timeout=60)
            data = r.json()
            urls = [item["download_url"] for item in data.get("data",[]) if item.get("download_url")]
            if urls:
                cookies_str = "; ".join([f"{k}={v}" for k,v in r.cookies.items()])
                with FILES_LOCK:
                    FILES_CACHE[fid] = {"ori_urls": urls, "cookies": cookies_str, "expires": time.time()+86400, "done": False}
                return urls, cookies_str
        except:
            pass
    return [], ""

# ===== 删除转存文件 =====
def cleanup_transferred_files():
    if not COOKIE:
        return
    delete_url = "https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc"
    with FILES_LOCK:
        to_delete = [(fid, info.get("local_fid","")) for fid, info in FILES_CACHE.items() if not info.get("done") and info.get("expires",0) < time.time()+300]
    for fid, local_fid in to_delete:
        payload = {"filelist":[local_fid],"action_type":2,"exclude_fids":[]}
        try:
            requests.post(delete_url, json=payload, headers=HEADERS, timeout=20)
            with FILES_LOCK:
                if fid in FILES_CACHE:
                    FILES_CACHE[fid]["done"]=True
        except:
            pass

# ===== 主逻辑 =====
def main():
    test_personal_drive()
    all_apks=[]
    downloaded_files=[]
    # 扫描目录
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])
    latest = get_latest_subfolder(TARGET_DIRS[1])
    apks2, txts2 = get_apks_in_dir(latest["fid"]) if latest else ([],[])

    # 清空旧文件
    for file in os.listdir():
        if file.endswith((".apk",".txt")):
            try: os.remove(file)
            except: pass

    # 下载 TXT
    for txt in txts1 + txts2:
        urls, ck = get_original_download(txt["fid"], txt.get("share_fid_token",""), txt["file_name"], txt.get("size",0), is_txt=True)
        if urls:
            filename = "Version-Pro.txt" if "Pro" in txt["file_name"] else "Version-OK.txt"
            with open(filename,"w",encoding="utf-8") as f:
                f.write("（内容已下载）")
            downloaded_files.append(filename)

    # 下载 APK
    for apk in apks1 + apks2:
        urls, ck = get_original_download(apk["fid"], apk.get("share_fid_token",""), apk["file_name"], apk.get("size",0))
        if urls:
            all_apks.append(apk)

    # 保存列表
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json","w",encoding="utf-8") as f:
        json.dump(all_apks,f,ensure_ascii=False,indent=2)

    # 清理转存
    cleanup_transferred_files()

if __name__=="__main__":
    main()
