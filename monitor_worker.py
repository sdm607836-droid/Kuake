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
    r"OK影视Pro-电视版-32位-.*\.apk": "leanback-armeabi_v7a-pro.apk",
    r"OK影视Pro-电视版-64位-.*\.apk": "leanback-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.*(?<!模拟器)\.apk": "mobile-arm64_v8a-pro.apk",
    r"OK影视Pro-手机版-.* - 模拟器\.apk": "mobile-armeabi_v7a-pro.apk",
}

# 重命名映射（标准版）
OK_RENAME_MAP = {
    r"海信专版-OK影视-.*\.apk": "hisense-tv-universal-ok.apk",
    r"OK影视-电视版-.*\.apk": "leanback-armeabi_v7a-ok.apk",
    r"OK影视-手机版-.*\.apk": "mobile-arm64_v8a-ok.apk",
}

# ===== stoken 获取 =====
def get_share_token(pwd_id=PWD_ID, passcode=""):
    print("正在通过官方接口获取/刷新 stoken...")
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Content-Type": "application/json",
        "Cookie": COOKIE,
    }
    payload = {"pwd_id": pwd_id, "passcode": passcode}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"官方 token 接口状态码: {r.status_code}")
        print(f"响应: {r.text[:300]}...")  # 调试用
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
    except Exception as e:
        print("官方 token 接口异常:", str(e))
    return None

def get_latest_stoken():
    stoken = get_share_token()
    if stoken:
        return stoken
    stoken = os.getenv("QUARK_STOKEN")
    if stoken:
        print("使用 GitHub Secrets 的 stoken:", stoken[:10] + "...")
        return stoken
    print("❌ 所有方式都无法获取有效 stoken")
    return None

# 调试信息
print("=== 调试信息 ===")
COOKIE = os.getenv("QUARK_COOKIE")
STOKEN = get_latest_stoken()
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
if COOKIE:
    print(f"QUARK_COOKIE 长度: {len(COOKIE)}")
    print(f"QUARK_COOKIE 前20字符: {COOKIE[:20]}...")
print(f"最终使用的 stoken: {STOKEN[:10] + '...' if STOKEN else '无'}")
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

# ===== 打印当前目录（排查用） =====
print("\n当前工作目录:", os.getcwd())
print("当前目录初始文件列表:", os.listdir('.'))

# ===== 测试个人网盘访问 =====
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

def get_apks_in_dir(fid, is_pro=False):
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
    if is_pro:
        apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("file_name", "").endswith(".apk")]
    else:
        target_keywords = ["OK影视-电视版", "OK影视-手机版", "海信专版-OK影视"]
        apks = [
            f for f in files
            if not f.get("dir")
            and f.get("file_type") == 1
            and f.get("file_name", "").endswith(".apk")
            and any(kw in f.get("file_name", "") for kw in target_keywords)
        ]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").lower().endswith(".txt")]
    print(f" 目录 {fid[:8]} 找到 {len(apks)} 个目标 APK, {len(txts)} 个 TXT")
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

# ===== 判断是否需要下载 =====
def should_download(filename):
    if os.path.exists(filename):
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"文件已存在，跳过下载: {filename} ({size_mb:.2f} MB)")
        return False
    return True

# ===== 从 TXT 提取版本号和更新日志（更鲁棒版） =====
def extract_version_and_changelog(txt_path, edition="OK"):
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        print(f"\n=== TXT 文件内容预览 ({os.path.basename(txt_path)}) 前800字符 ===")
        print(content[:800] + ("..." if len(content) > 800 else ""))
        print("=== TXT 内容预览结束 ===\n")

        # 提取版本号
        version_patterns = [
            r'(?:版本|v|Ver|Version|build)\s*[:]?[\s]*([vV]?\d+\.\d+\.\d+(?:[-_][a-zA-Z0-9]+)?)',
            r'(\d+\.\d+\.\d+(?:[-_][a-zA-Z0-9]+)?)',
            r'v?(\d+\.\d+\.\d+)',
        ]
        version = "未知版本"
        for pat in version_patterns:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                version = m.group(1).strip()
                break

        # 提取更新日志 - 更宽松：找不到关键词就取全部
        changelog_keywords = [
            r'更新日志[:]?',
            r'更新内容[:]?',
            r'变更日志[:]?',
            r'更新说明[:]?',
            r"What's new[:]?",
            r'新版本特性[:]?',
            r'本次更新[:]?',
            r'更新记录[:]?',
        ]
        changelog_start = 0  # 默认从头取
        for kw in changelog_keywords:
            m = re.search(kw, content, re.IGNORECASE)
            if m:
                changelog_start = m.end()  # 从关键词后开始取
                break

        changelog = content[changelog_start:].strip()
        if not changelog or len(changelog) < 20:
            changelog = content.strip()  # 如果太短，直接取全部

        changelog = re.sub(r'\n{3,}', '\n\n', changelog).strip()

        return version, changelog, os.path.basename(txt_path)

    except FileNotFoundError:
        print(f"TXT 文件不存在: {txt_path}")
        return "无 TXT 下载", "没有下载到更新日志文件", "无"
    except Exception as e:
        print(f"读取或解析 {txt_path} 失败: {str(e)}")
        return "提取失败", "无法读取 TXT 文件内容", os.path.basename(txt_path)

# ===== 获取下载链接 + 下载 + 强制生成 Version 文件 =====
def get_original_download(fid, share_fid_token="", name="", size=0, is_txt=False):
    if not COOKIE:
        print(f" 无 COOKIE，跳过 {fid[:8]}")
        return [], ""

    with FILES_LOCK:
        if fid in FILES_CACHE:
            c = FILES_CACHE[fid]
            if c.get("ori_urls") and c.get("expires", 0) > time.time():
                print(f" 缓存命中 {fid[:8]}")
                return c["ori_urls"], c.get("cookies", "")

    print(f" 开始获取链接 {fid[:8]}...")
    direct_url = "https://drive-pc.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc"
    direct_payload = {"fids": [fid], "pwd_id": PWD_ID, "stoken": STOKEN}
    print(f" 尝试直接下载 {fid[:8]}...")

    urls = []
    cookies_str = ""
    try:
        r = requests.post(direct_url, json=direct_payload, headers=HEADERS, timeout=30)
        print(f" 直接下载状态码: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if "download_url" in item and item["download_url"]:
                        urls.append(item["download_url"])
            if urls:
                cookies_str = "; ".join([f"{k}={v}" for k, v in r.cookies.items()])
                expires = time.time() + 86400
                with FILES_LOCK:
                    FILES_CACHE[fid] = {"ori_urls": urls, "cookies": cookies_str, "expires": expires, "done": False}
                print(f" 直接下载成功 ({len(urls)} 条链接)")
            else:
                print(" 直接下载无有效 url")
        else:
            print(f" 直接下载失败: {r.text[:200]}...")
    except Exception as e:
        print(f" 直接下载异常: {str(e)}")

    if is_txt:
        edition = 'Pro' if 'Pro版' in name or 'Pro' in name else 'OK'
        final_file = f"Version-{edition}.txt"
        abs_path = os.path.abspath(final_file)
        print(f"准备处理 TXT 版本文件: {abs_path}")

        if urls:
            temp_filename = f"temp_txt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            print(f" 开始下载 TXT: {temp_filename}")
            try:
                dl_headers = HEADERS.copy()
                dl_headers["Cookie"] = cookies_str
                dl_r = requests.get(urls[0], headers=dl_headers, stream=True, timeout=300)
                dl_r.raise_for_status()
                with open(temp_filename, 'wb') as f:
                    for chunk in dl_r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f" TXT 下载完成: {temp_filename}")

                version, changelog, source_name = extract_version_and_changelog(temp_filename, edition)

                with open(final_file, 'a', encoding='utf-8') as vf:
                    vf.write(f"\n{'='*70}\n")
                    vf.write(f"版本: {version}\n")
                    vf.write(f"来源文件名: {source_name}\n")
                    vf.write(f"提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    vf.write("-" * 70 + "\n\n")
                    vf.write("更新日志:\n\n")
                    vf.write(changelog if changelog else "未提取到更新日志内容（TXT 可能为空或格式异常）\n")
                    vf.write("\n\n")

                print(f"版本信息已追加到: {abs_path}")
                print(f"最新日志预览: {changelog[:200]}...")

                try:
                    os.remove(temp_filename)
                except:
                    pass

            except Exception as e:
                print(f" TXT 下载/处理失败 {name}: {str(e)}")

        # 无论下载成功与否，都确保文件存在
        if not os.path.exists(final_file):
            print(f"警告: 未下载到 TXT，强制生成空日志文件 {final_file}")
            with open(final_file, 'a', encoding='utf-8') as vf:
                vf.write(f"\n{'='*70}\n")
                vf.write(f"版本: 无 TXT 下载\n")
                vf.write(f"来源文件名: {name}\n")
                vf.write(f"提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                vf.write("-" * 70 + "\n\n")
                vf.write("更新日志:\n")
                vf.write("没有下载到更新日志 TXT 文件，请检查分享目录\n\n")

        return urls, cookies_str

    else:
        # APK 下载部分（保持不变）
        filename = name
        for pattern, new_name in PRO_RENAME_MAP.items():
            if re.search(pattern, name):
                filename = new_name
                break
        else:
            for pattern, new_name in OK_RENAME_MAP.items():
                if re.search(pattern, name):
                    filename = new_name
                    break
        if filename == name:
            filename = name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"
        else:
            print(f" 重命名: {name} → {filename}")

        if not should_download(filename):
            return urls, cookies_str

        print(f" 开始下载: {filename} ({size:,} bytes)")
        try:
            print("等待 4 秒，避免触发下载限速...")
            time.sleep(4)
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

        return urls, cookies_str

    # 转存备用（如果直接下载失败）
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
            FILES_CACHE[fid] = {"local_fid": local_fid, "ori_urls": urls, "cookies": cookies_str, "expires": expires, "done": False}
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
        payload = {"filelist": [local_fid], "action_type": 2, "exclude_fids": []}
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
    test_personal_drive()
    all_apks = []
    download_results = []
    downloaded_files = []

    # 第一阶段：OK 标准版 - 只处理指定 3 类
    print("\n" + "="*70)
    print("=== 第一阶段：处理 OK 标准版（仅 OK影视-电视版 / OK影视-手机版 / 海信专版） ===")
    print("="*70 + "\n")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        print(f"最新子文件夹：{latest.get('file_name', '?')}")
        apks_std, txts_std = get_apks_in_dir(latest["fid"], is_pro=False)
        for f in txts_std:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            print(f" • TXT: {name:<50} {size:>12,} B")
            urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
            if urls:
                downloaded_files.append(f"Version-OK.txt (from {name})")
        for f in apks_std:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            filename = name
            for pattern, new_name in OK_RENAME_MAP.items():
                if re.search(pattern, name):
                    filename = new_name
                    break
            if filename == name:
                filename = name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"
            print(f" • {name:<50} {size:>12,} B → 将保存为: {filename}")
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
                print(f" → 处理完成 ({len(urls)} 条链接)")

    # 第二阶段：OK Pro 版 - 全部处理
    print("\n" + "="*70)
    print("=== 第二阶段：处理 OK Pro 版（全部文件） ===")
    print("="*70 + "\n")
    apks_pro, txts_pro = get_apks_in_dir(TARGET_DIRS[0], is_pro=True)
    for f in txts_pro:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        print(f" • TXT: {name:<50} {size:>12,} B")
        urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
        if urls:
            downloaded_files.append(f"Version-Pro.txt (from {name})")
    for f in apks_pro:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        filename = name
        for pattern, new_name in PRO_RENAME_MAP.items():
            if re.search(pattern, name):
                filename = new_name
                break
        if filename == name:
            filename = name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"
        print(f" • {name:<50} {size:>12,} B → 将保存为: {filename}")
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
            print(f" → 处理完成 ({len(urls)} 条链接)")

    # 保存结果
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"apks_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(all_apks, f, ensure_ascii=False, indent=2)
    print(f"\n已保存 APK 列表到 apks_{ts}.json")

    if download_results:
        with open(f"downloads_{ts}.json", "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
        print(f"已保存 {len(download_results)} 条下载信息到 downloads_{ts}.json")

    print("\n已生成版本信息文件：")
    for df in set(downloaded_files):
        print(f"  - {df}")

    # 打印最终文件列表
    print("\n=== 最终生成的文件列表 ===")
    print(os.listdir('.'))
    print("\n如果看到 Version-OK.txt / Version-Pro.txt，则已成功生成，可用于 Release")

    print("\n开始清理转存文件...")
    cleanup_transferred_files()

if __name__ == "__main__":
    main()
