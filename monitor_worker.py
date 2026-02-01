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
    r"海信专版-OK影视.*\.apk": "hisense-tv-customized.apk",  # 放宽匹配
    r"mobile-armeabi_v7a.*\.apk": "mobile-arm64_v7a-ok.apk",  # 放宽匹配
    r"mobile-arm64_v8a.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# ===== 自动获取/刷新 stoken（使用官方接口） =====
def get_share_token(pwd_id=PWD_ID, passcode=""):
    """调用夸克官方 /share/sharepage/token 接口获取最新 stoken"""
    print("正在通过官方接口获取/刷新 stoken...")
    url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
        "Referer": "https://drive.quark.cn/",
        "Content-Type": "application/json",
        "Cookie": COOKIE,  # 必须是有效的登录 cookie
    }
    payload = {
        "pwd_id": pwd_id,
        "passcode": passcode,  # 如果分享有密码，填在这里；无密码可为空
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"官方 token 接口状态码: {r.status_code}")
        print(f"官方 token 接口响应: {r.text[:500]}")  # 调试用

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

# ===== 获取最新 stoken（优先官方接口刷新） =====
def get_latest_stoken():
    # 先尝试官方接口刷新 stoken
    stoken = get_share_token()
    if stoken:
        return stoken

    # fallback 到 Secrets 中的 QUARK_STOKEN
    stoken = os.getenv("QUARK_STOKEN")
    if stoken:
        print("使用 GitHub Secrets 的 stoken:", stoken[:10] + "...")
        return stoken
    print("❌ 所有方式都无法获取有效 stoken")
    return None

# 调试信息
print("=== 调试信息 ===")
COOKIE = os.getenv("QUARK_COOKIE")
STOKEN = get_latest_stoken()  # 启动时自动刷新/获取
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

# ===== headers 模板（带 Origin 防 403） =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch",
    "Referer": "https://drive.quark.cn/",
    "Origin": "https://drive.quark.cn",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
}

# ===== requests.get 修复 403 自动重试函数 =====
def requests_get_retry(url, headers, stream=False, timeout=60, max_retry=3):
    for attempt in range(max_retry):
        try:
            r = requests.get(url, headers=headers, stream=stream, timeout=timeout)
            if r.status_code == 403:
                print(f"403 Forbidden, 尝试刷新 stoken 并重试 ({attempt+1}/{max_retry})")
                global STOKEN
                STOKEN = get_latest_stoken()
                headers["Cookie"] = COOKIE
                headers["Referer"] = "https://drive-pc.quark.cn/"
                headers["Origin"] = "https://drive.quark.cn"
                time.sleep(1.5)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"请求异常: {e}, 重试 ({attempt+1}/{max_retry})")
            time.sleep(1.5)
    raise Exception(f"请求失败，已重试 {max_retry} 次: {url}")

# ===== fetch_page, get_apks_in_dir, get_latest_subfolder, copy_file 不变 =====
# ...（保留你原来的逻辑，不动）...

# ===== get_original_download =====
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

                # 下载文件（TXT 或 APK）
                dl_headers = HEADERS.copy()
                dl_headers["Cookie"] = cookies_str
                dl_headers["Accept"] = "*/*"
                dl_headers["Accept-Encoding"] = "identity"
                dl_headers["Range"] = "bytes=0-"

                if is_txt:
                    filename = f"Version-{'Pro' if 'Pro版' in name else 'OK'}.txt"
                    print(f" 开始下载 TXT: {filename}")
                    dl_r = requests_get_retry(urls[0], dl_headers, stream=True, timeout=300)
                    with open(filename, 'wb') as f:
                        for chunk in dl_r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    print(f" TXT 下载完成: {filename}")
                else:
                    # 重命名 APK
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
                        filename = name.replace(".apk", "").replace(" ", "_").replace("/", "_") + ".apk"
                    else:
                        print(f" 重命名: {name} → {filename}")

                    print(f" 开始下载: {filename} ({size:,} bytes)")
                    dl_r = requests_get_retry(urls[0], dl_headers, stream=True, timeout=600)
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

                return urls, cookies_str
            else:
                print(" 直接下载无有效 url")
        else:
            print(f" 直接下载失败: {r.text[:200]}...")
    except Exception as e:
        print(f" 直接下载异常: {str(e)}")

    # 转存备用逻辑不变
    print(f" 直接下载失败，尝试转存 {fid[:8]}...")
    local_fid = copy_file(fid, share_fid_token)
    if not local_fid:
        print(f" 转存失败，无法继续 {fid[:8]}")
        return [], ""

    # 请求转码下载链接
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
    test_personal_drive()  # 先测试 cookie 有效性

    # 先完整扫描两个目录，打印所有文件信息
    print("\n=== 先扫描所有目录（不下载） ===")

    print("\n扫描目录1 (OK Pro版)...")
    apks1, txts1 = get_apks_in_dir(TARGET_DIRS[0])
    print(f"OK Pro版找到 {len(apks1)} 个 APK, {len(txts1)} 个 TXT")
    for f in apks1:
        print(f"  Pro APK: {f.get('file_name')} ({f.get('size', 0):,} B)")
    for f in txts1:
        print(f"  Pro TXT: {f.get('file_name')} ({f.get('size', 0):,} B)")

    print("\n扫描目录2 (OK 标准版) - 最新子文件夹...")
    latest = get_latest_subfolder(TARGET_DIRS[1])
    if latest:
        print(f"最新文件夹：{latest.get('file_name', '?')}")
        apks2, txts2 = get_apks_in_dir(latest["fid"])
        print(f"OK 标准版找到 {len(apks2)} 个 APK, {len(txts2)} 个 TXT")
        for f in apks2:
            print(f"  标准 APK: {f.get('file_name')} ({f.get('size', 0):,} B)")
        for f in txts2:
            print(f"  标准 TXT: {f.get('file_name')} ({f.get('size', 0):,} B)")
    else:
        print("标准版无最新子文件夹")

    print("\n=== 扫描完成，开始下载处理 ===\n")

    all_apks = []
    download_results = []
    downloaded_files = []

    # 清空旧文件
    print("\n清空旧 APK 和 TXT 文件...")
    for file in os.listdir():
        if file.endswith((".apk", ".txt")):
            try:
                os.remove(file)
                print(f" 已删除旧文件: {file}")
            except:
                pass

    # 现在处理 Pro 版
    print("\n=== 处理目录1 (OK Pro版) ===")
    for f in txts1:
        name = f.get("file_name", "?")
        size = f.get("size", 0)
        fid = f.get("fid", "")
        sft = f.get("share_fid_token", "")
        print(f" • TXT: {name:<50} {size:>12,} B")
        urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
        if urls:
            filename = "Version-Pro.txt"
            with open(filename, 'w', encoding="utf-8") as tf:
                tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
            print(f" 已保存 Pro TXT: {filename}")
            downloaded_files.append(filename)

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

    # 处理标准版
    if latest:
        print("\n=== 处理目录2 (OK 标准版) ===")
        for f in txts2:
            name = f.get("file_name", "?")
            size = f.get("size", 0)
            fid = f.get("fid", "")
            sft = f.get("share_fid_token", "")
            print(f" • TXT: {name:<50} {size:>12,} B")
            urls, ck = get_original_download(fid, sft, name, size, is_txt=True)
            if urls:
                filename = "Version-OK.txt"
                with open(filename, 'w', encoding="utf-8") as tf:
                    tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
                print(f" 已保存 OK TXT: {filename}")
                downloaded_files.append(filename)

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
