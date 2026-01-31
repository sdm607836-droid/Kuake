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
PWD_ID = "cb0ee2b9ac64"
PAGE_SIZE = 50
TARGET_DIRS = [
    "8d6dce95581c49f29183380d3805e9b5",  # OK Pro版目录
    "f0c75c96e96e4310b96383b4b22040e3",  # OK 标准版目录
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
    r"海信专版-OK影视-.*\.apk": "hisense-tv-customized.apk",
    r"mobile-armeabi_v7a-.*\.apk": "mobile-arm64_v7a-ok.apk",
    r"mobile-arm64_v8a-.*\.apk": "mobile-arm64_v8a-ok.apk",
    r"leanback-armeabi_v7a-.*\.apk": "leanback-arm64_v7a-ok.apk",
    r"leanback-arm64_v8a-.*\.apk": "leanback-arm64_v8a-ok.apk",
}

# 调试信息
print("=== 调试信息 ===")
STOKEN = os.getenv("QUARK_STOKEN")
COOKIE = os.getenv("QUARK_COOKIE")
print(f"QUARK_STOKEN 是否存在: {'是' if STOKEN else '否'}")
if STOKEN:
    print(f"QUARK_STOKEN 长度: {len(STOKEN)}")
    print(f"QUARK_STOKEN 前10字符: {STOKEN[:10]}...")
print(f"QUARK_COOKIE 是否存在: {'是' if COOKIE else '否'}")
if COOKIE:
    print(f"QUARK_COOKIE 长度: {len(COOKIE)}")
    print(f"QUARK_COOKIE 前20字符: {COOKIE[:20]}...")
print("=== 调试结束 ===\n")

if not STOKEN:
    print("❌ 缺少 QUARK_STOKEN，无法继续")
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
        r = requests.post(WORKER_URL, json={
            "pwd_id": PWD_ID,
            "stoken": STOKEN,
            "pdir_fid": pdir_fid,
            "_page": page,
            "_size": PAGE_SIZE,
            "ver": 2,
            "pr": "ucpro",
            "fr": "h5",
        }, timeout=60)
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
    apks = [f for f in files if not f.get("dir") and f.get("file_type") == 1 and f.get("file_name", "").endswith(".apk") and not f["file_name"].startswith(("OK影视-电视版", "OK影视-手机版"))]
    txts = [f for f in files if not f.get("dir") and f.get("file_name", "").endswith(".txt")]
    print(f" 目录 {fid[:8]} 找到 {len(apks)} 个符合条件的 APK, {len(txts)} 个 TXT")
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
    # ... 原转存函数保持不变
    # （省略原代码，保持你的版本）

def get_original_download(fid, share_fid_token="", name="", size=0, is_txt=False):
    # ... 原函数保持不变
    # （省略原代码，保持你的版本，只需确保下载部分有 tqdm 进度条）

    # 示例下载部分（已包含进度条）
    # ...
    try:
        dl_r = requests.get(file_url, headers=dl_headers, stream=True, timeout=600)
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
    # ...

def cleanup_transferred_files():
    # ... 原函数保持不变

def main():
    test_personal_drive()

    all_apks = []
    download_results = []
    downloaded_files = []  # 用于上传的文件列表

    # 清空旧文件（避免重复上传旧版）
    print("\n清空旧 APK 和 TXT 文件...")
    for file in os.listdir():
        if file.endswith((".apk", ".txt")):
            try:
                os.remove(file)
                print(f" 已删除旧文件: {file}")
            except:
                pass

    # 目录1: OK Pro版 - 完整循环
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
            with open(filename, 'w', encoding="utf-8") as tf:
                tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
            print(f" 已保存 Pro TXT: {filename}")
            downloaded_files.append(filename)

    for f in apks1:  # 恢复完整循环
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
            # 下载的文件已保存到本地

    # 目录2: OK 标准版 - 完整循环
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
                with open(filename, 'w', encoding="utf-8") as tf:
                    tf.write("从 " + name + " 提取的版本信息\n\n" + "（内容已下载）")
                print(f" 已保存 OK TXT: {filename}")
                downloaded_files.append(filename)

        for f in apks2:  # 完整循环
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
