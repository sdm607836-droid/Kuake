import os
import json
import requests
import time
from datetime import datetime
import threading
import re
from tqdm import tqdm

# ===== GitHub 配置（用于检查重复文件） =====
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # workflow 自动注入
REPO_OWNER = "你的用户名"  # ← 替换成你的 GitHub 用户名
REPO_NAME = "你的仓库名"   # ← 替换成你的仓库名
TAG_NAME = "latest"         # 如果用 tag，改成对应 tag 名

# ===== 获取当前 Release 已存在的文件 =====
def get_existing_release_files():
    if not GITHUB_TOKEN:
        print("⚠️ 缺少 GITHUB_TOKEN，无法检查重复文件，将全部下载")
        return set()
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{TAG_NAME}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            assets = data.get("assets", [])
            existing = {asset["name"].lower() for asset in assets}
            print(f"当前 Release 已存在 {len(existing)} 个文件")
            return existing
        print(f"获取 Release Assets 失败: {r.status_code} - {r.text[:200]}")
    except Exception as e:
        print(f"获取 Release Assets 异常: {str(e)}")
    return set()

EXISTING_FILES = get_existing_release_files()

# ===== 配置区 =====
WORKER_URL = "https://broad-mode-cbfa.sdm607836.workers.dev"
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版
]

PRO_RENAME_MAP = {
    r"OK影视Pro-电视版-32位.*\.apk": "leanback-arm64_v7a-pro.apk",
    r"OK影视Pro-电视版-64位.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版.* - 模拟器\.apk": "mobile-arm64_v7a-pro.apk",
}

OK_RENAME_MAP = {
    r"海信专版-OK影视.*\.apk": "hisense-tv-customized.apk",  # 放宽匹配
    r"mobile-armeabi_v7a.*\.apk": "mobile-arm64_v7a-ok.apk",  # 放宽匹配
    r"mobile-arm64_v8a.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# ===== 自动获取/刷新 stoken =====
def get_share_token(pwd_id=None, passcode=""):
    if pwd_id is None:
        pwd_id = PWD_ID
    print("正在通过官方接口获取/刷新 stoken...")
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Content-Type": "application/json",
        "Cookie": COOKIE,
    }
    payload = {
        "pwd_id": pwd_id,
        "passcode": passcode,
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"官方 token 接口状态码: {r.status_code}")
        print(f"官方 token 接口响应: {r.text[:500]}")
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                stoken = data.get("data", {}).get("stoken")
                name = data.get("data", {}).get("title")
                if stoken:
                    print(f"获取 stoken 成功: {stoken[:10]}...")
                    print(f"分享标题: {name}")
                    return stoken
            print("官方 token 接口返回错误:", data.get("msg", "未知"))
        else:
            print("官方 token 接口请求失败:", r.status_code)
    except Exception as e:
        print("官方 token 接口异常:", str(e))
    return None

def get_latest_stoken():
    print("强制尝试刷新 stoken...")
    stoken = get_share_token()
    if stoken:
        return stoken
    stoken = os.getenv("QUARK_STOKEN")
    if stoken:
        print("使用 Secrets 中的 stoken (可能已过期):", stoken[:10] + "...")
        return stoken
    print("❌ 无法获取 stoken")
    return None

# 调试信息
print("=== 调试信息 ===")
COOKIE = os.getenv("QUARK_COOKIE")
STOKEN = get_latest_stoken()
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
if COOKIE:
    print(f"QUARK_COOKIE 长度: {len(COOKIE)}")
    print(f"QUARK_COOKIE 前20字符: {COOKIE[:20]}...")
print(f"最终 stoken: {STOKEN[:10] + '...' if STOKEN else '无'}")
print("=== 调试结束 ===\n")

if not STOKEN:
    print("❌ 缺少有效 stoken，无法继续")
    exit(1)

if not COOKIE:
    print("⚠️ 缺少 QUARK_COOKIE → 只能扫描列表，无法转存和获取下载链接")

FILES_CACHE = {}
FILES_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

def test_personal_drive():
    test_url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_fetch_total=1&_size=10"
    print("\n=== 测试个人网盘访问 ===")
    try:
        r = requests.get(test_url, headers=HEADERS, timeout=20)
        print(f"状态码: {r.status_code}")
        if r.status_code == 200:
            print("Cookie 有效，能访问个人网盘")
        else:
            print(f"Cookie 无效或风控: {r.text[:200]}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    print("=== 测试结束 ===\n")

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
        for item in list_data:
            print(f"  - 文件名: {item.get('file_name', '未知')}")
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
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("file_name", "").endswith(".apk") and not f["file_name"].startswith(("OK影视-电视版", "OK影视-手机版"))]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt")]
    print(f" 目录 {fid[:8]} 找到 {len(apks)} 个符合条件的 APK, {len(txts)} 个 TXT")
    for apk in apks:
        print(f"  APK: {apk.get('file_name')}")
    for txt in txts:
        print(f"  TXT: {txt.get('file_name')}")
    return apks, txts

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

def get_original_download(fid, share_fid_token="", name="", size=0, is_txt=False):
    if not COOKIE:
        print(f" 无 COOKIE，跳过 {fid[:8]}")
        return [], ""

    # 确定最终文件名
    if is_txt:
        filename = f"Version-{'Pro' if 'Pro版' in name else 'OK'}.txt"
    else:
        filename = name
        matched = False
        for pattern, new_name in PRO_RENAME_MAP.items():
            if re.search(pattern, name):
                filename = new_name
                matched = True
                print(f" Pro版匹配: {name} → {filename}")
                break
        if not matched:
            for pattern, new_name in OK_RENAME_MAP.items():
                if re.search(pattern, name):
                    filename = new_name
                    matched = True
                    print(f" OK版匹配: {name} → {filename}")
                    break
        if not matched:
            filename = name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"
            print(f" 无匹配，使用默认重命名: {filename}")

    # 检查是否已存在于 Release
    if filename.lower() in [f.lower() for f in EXISTING_FILES]:
        print(f" 文件已存在于 Release，跳过下载/上传: {filename}")
        return [], ""

    with FILES_LOCK:
        if fid in FILES_CACHE:
            c = FILES_CACHE[fid]
            if c.get("ori_urls") and c.get("expires", 0) > time.time():
                print(f" 缓存命中 {fid[:8]}")
                return c["ori_urls"], c.get("cookies", "")

    print(f" 开始获取链接 {fid[:8]} ({'TXT' if is_txt else 'APK'})...")

    direct_url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    direct_payload = {
        "fids": [fid],
        "pwd_id": PWD_ID,
        "stoken": STOKEN,
    }
    try:
        r = requests.post(direct_url, json=direct_payload, headers=HEADERS, timeout=30)
        print(f" 直接下载状态码: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            urls = []
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if "download_url" in item and item["download_url"]:
                        urls.append(item["download_url"])
            if urls:
                cookies_str = "; ".join([f"{k}={v}" for k, v in r.cookies.items()])
                expires = time.time() + 86400
                with FILES_LOCK:
                    FILES_CACHE[fid] = {
                        "ori_urls": urls,
                        "cookies": cookies_str,
                        "expires": expires,
                        "done": False
                    }
                print(f" 直接下载成功 ({len(urls)} 条链接)")

                # TXT 处理
                if is_txt:
                    version = "未知版本"
                    version_match = re.search(r'(\d+\.\d+\.\d+)', name)
                    if version_match:
                        version = version_match.group(1)
                    print(f" 开始下载 TXT: {filename} (版本: {version})")
                    try:
                        dl_headers = HEADERS.copy()
                        dl_headers["Cookie"] = cookies_str
                        dl_r = requests.get(urls[0], headers=dl_headers, stream=True, timeout=300)
                        dl_r.raise_for_status()
                        content = dl_r.content.decode('utf-8', errors='ignore')
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(f"版本: {version}\n\n")
                            f.write(content)
                        print(f" TXT 下载并保存完成: {filename}")
                    except Exception as e:
                        print(f" TXT 下载失败 {filename}: {str(e)}")
                        # 记录到 JSON
                        return [], f"TXT 下载失败: {str(e)}"
                else:
                    print(f" 开始下载: {filename} ({size:,} bytes)")
                    try:
                        dl_headers = HEADERS.copy()
                        dl_headers["Cookie"] = cookies_str
                        dl_r = requests.get(urls[0], headers=dl_headers, stream=True, timeout=600)
                        dl_r.raise_for_status()
                        total_size = int(dl_r.headers.get('content-length', 0))
                        with open(filename, 'wb') as f, tqdm(
                            desc=filename,
                            total=total_size,
                            unit='B',
                            unit_scale=True,
                            unit_divisor=1024,
                        ) as pbar:
                            for chunk in dl_r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
                        print(f" 下载完成: {filename} ({file_size_mb:.2f} MB)")
                    except Exception as e:
                        print(f" 下载失败 {filename}: {str(e)}")
                        return [], f"下载失败: {str(e)}"

                return urls, cookies_str
            else:
                print(" 直接下载无有效 url")
        else:
            print(f" 直接下载失败: {r.text[:200]}...")
    except Exception as e:
        print(f" 直接下载异常: {str(e)}")

    if is_txt:
        print(" TXT 文件不需要转存，直接失败处理")
        return [], "TXT 不需要转存"

    print(f" 直接下载失败，尝试转存 {fid[:8]}...")
    local_fid = copy_file(fid, share_fid_token)
    if not local_fid:
        print(f" 转存失败，无法继续 {fid[:8]}")
        return [], ""

    url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    payload = {"fids": [local_fid]}
    print(f" 请求转码下载链接 {fid[:8]} (local_fid={local_fid[:8]})...")
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

def main():
    test_personal_drive()

    all_apks = []
    download_results = []
    downloaded_files = []

    print("\n清空旧 APK 和 TXT 文件...")
    for file in os.listdir():
        if file.endswith((".apk", ".txt")):
            try:
                os.remove(file)
                print(f" 已删除旧文件: {file}")
            except:
                pass

    print("\n=== 扫描目录1 (OK Pro版) ===")
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])
    for f in txts1:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        print(f" • TXT: {name:<50} {size:>12,} B")
        urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
        if urls:
            filename = "Version-Pro.txt"
            if filename.lower() not in [f.lower() for f in EXISTING_FILES]:
                with open(filename, 'w', encoding="utf-8") as tf:
                    tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
                print(f" 已保存 Pro TXT: {filename}")
                downloaded_files.append(filename)
            else:
                print(f" Version-Pro.txt 已存在于 Release，跳过")

    for f in apks1:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        print(f" • {name:<50} {size:>12,} B")
        all_apks.append(f)
        urls, ck = get_original_download(fid, sft, name, size)
        if urls:
            download_results.append({
                "name": name,
                "size": size,
                "fid": fid,
                "urls": urls,
                "cookies": ck
            })
            print(f" → 下载链接已获取 ({len(urls)} 条)")

    print("\n=== 扫描目录2 (OK 标准版) - 最新子文件夹 ===")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        print(f"最新文件夹：{latest.get('file_name', '?')}")
        apks2, txts2 = get_apks_in_dir(latest["fid"])
        for f in txts2:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            print(f" • TXT: {name:<50} {size:>12,} B")
            urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
            if urls:
                filename = "Version-OK.txt"
                if filename.lower() not in [f.lower() for f in EXISTING_FILES]:
                    with open(filename, 'w', encoding="utf-8") as tf:
                        tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
                    print(f" 已保存 OK TXT: {filename}")
                    downloaded_files.append(filename)
                else:
                    print(f" Version-OK.txt 已存在于 Release，跳过")

        for f in apks2:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            print(f" • {name:<50} {size:>12,} B")
            all_apks.append(f)
            urls, ck = get_original_download(fid, sft, name, size)
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

    print("\n已下载的文件（用于上传）:", downloaded_files)

    print("\n开始清理转存文件...")
    cleanup_transferred_files()

if __name__ == "__main__":
    main()
