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
PWD_ID = "cb0ee2b9ac64"  # 分享 pwd_id
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版
]

PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.* - 模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

FILES_CACHE = {}
FILES_LOCK = threading.Lock()
COOKIE = os.getenv("QUARK_COOKIE")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE if COOKIE else "",
}

# ===== 获取最新 stoken =====
def get_share_token(pwd_id=PWD_ID, passcode=""):
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
    payload = {"pwd_id": pwd_id, "passcode": passcode}
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            stoken = data.get("data", {}).get("stoken")
            return stoken
    except:
        pass
    return os.getenv("QUARK_STOKEN")

STOKEN = get_share_token()
if not STOKEN:
    print("❌ 获取 stoken 失败，退出")
    exit(1)

# ===== Worker 代理请求 =====
def fetch_page_via_worker(pdir_fid, page=1, size=PAGE_SIZE):
    payload = {
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
        "pdir_fid": pdir_fid,
        "page": page,
        "size": size
    }
    try:
        r = requests.post(WORKER_URL, json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("data", {}).get("list", [])
    except Exception as e:
        print(f"Worker 请求异常: {str(e)}")
    return []

def get_apks_in_dir(fid):
    files = []
    page = 1
    while True:
        page_data = fetch_page_via_worker(fid, page)
        if not page_data:
            break
        files.extend(page_data)
        if len(page_data) < PAGE_SIZE:
            break
        page += 1
    apks = [f for f in files if not f.get("dir") and f.get("file_type")==1 and f.get("file_name","").endswith(".apk")]
    txts = [f for f in files if not f.get("dir") and f.get("file_name","").endswith(".txt")]
    return apks, txts

def get_latest_subfolder(fid):
    files = fetch_page_via_worker(fid)
    folders = [f for f in files if f.get("dir")]
    if not folders:
        return None
    latest = max(folders, key=lambda f: int("".join(filter(str.isdigit, f.get("file_name",""))) or 0))
    return latest

# ===== 下载 + 重命名 =====
def get_original_download(fid, name="", size=0, is_txt=False):
    """通过 Worker 获取下载 URL，然后下载文件"""
    try:
        url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
        payload = {"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN}
        r = requests.post(WORKER_URL, json={"pwd_id": PWD_ID,"stoken":STOKEN,"pdir_fid":fid,"page":1,"size":1}, timeout=30)
        urls = []
        if r.status_code==200:
            data = r.json()
            for item in data.get("data", []):
                if "download_url" in item:
                    urls.append(item["download_url"])
        if not urls:
            print(f" 无下载链接 {name}")
            return [], ""
        cookies_str = "; ".join([f"{k}={v}" for k,v in r.cookies.items()])
        filename = name
        for pattern, new_name in PRO_RENAME_MAP.items():
            if re.search(pattern, name):
                filename = new_name
                break
        for pattern, new_name in OK_RENAME_MAP.items():
            if re.search(pattern, name):
                filename = new_name
                break
        if filename == name:
            filename = name.replace(".apk","").replace(" ","_").replace("/","_") + ".apk"
        if is_txt:
            filename = f"Version-{'Pro' if 'Pro版' in name else 'OK'}.txt"
        print(f"开始下载: {filename} ({size:,} bytes)")
        dl_headers = HEADERS.copy()
        dl_headers["Cookie"] = cookies_str
        dl_headers["Referer"] = "https://drive-pc.quark.cn/"
        dl_headers["Accept"] = "*/*"
        dl_headers["Accept-Encoding"] = "identity"
        dl_headers["Range"] = "bytes=0-"
        dl_r = requests.get(urls[0], headers=dl_headers, stream=True, timeout=600)
        dl_r.raise_for_status()
        with open(filename,'wb') as f, tqdm(desc=filename,total=int(dl_r.headers.get('content-length',0)),unit='B',unit_scale=True,unit_divisor=1024) as pbar:
            for chunk in dl_r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        print(f"下载完成: {filename}")
        return urls, cookies_str
    except Exception as e:
        print(f"下载失败 {name}: {str(e)}")
        return [], ""

# ===== 清理旧文件 =====
def cleanup_old_files():
    for file in os.listdir():
        if file.endswith((".apk",".txt")):
            try: os.remove(file)
            except: pass

# ===== 主逻辑 =====
def main():
    print("=== 扫描目录 ===")
    cleanup_old_files()
    all_apks=[]
    download_results=[]
    downloaded_files=[]

    # Pro 版
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])
    for f in txts1:
        urls, _ = get_original_download(f.get("fid"), f.get("file_name",""), f.get("size",0), is_txt=True)
        if urls: downloaded_files.append(f"Version-Pro.txt")
    for f in apks1:
        urls, ck = get_original_download(f.get("fid"), f.get("file_name",""), f.get("size",0))
        if urls:
            download_results.append({"name":f.get("file_name"),"size":f.get("size"),"fid":f.get("fid"),"urls":urls,"cookies":ck})
            all_apks.append(f)

    # 标准版
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        apks2, txts2 = get_apks_in_dir(latest.get("fid"))
        for f in txts2:
            urls, _ = get_original_download(f.get("fid"), f.get("file_name",""), f.get("size",0), is_txt=True)
            if urls: downloaded_files.append(f"Version-OK.txt")
        for f in apks2:
            urls, ck = get_original_download(f.get("fid"), f.get("file_name",""), f.get("size",0))
            if urls:
                download_results.append({"name":f.get("file_name"),"size":f.get("size"),"fid":f.get("fid"),"urls":urls,"cookies":ck})
                all_apks.append(f)

    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json","w",encoding="utf-8") as f: json.dump(all_apks,f,ensure_ascii=False,indent=2)
    with open(f"downloads_{ts}.json","w",encoding="utf-8") as f: json.dump(download_results,f,ensure_ascii=False,indent=2)
    print(f"\n已保存 {len(download_results)} 条下载信息，已下载文件: {downloaded_files}")

if __name__=="__main__":
    main()
