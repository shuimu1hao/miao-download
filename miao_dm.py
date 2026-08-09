#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
喵下载 (≧▽≦)
IDM 风格的 aria2 网页控制台 —— 多线程 + 断点续传 + 队列管理 + 限速 + 完成通知
用法: python3 miao_dm.py [端口]
浏览器打开 http://localhost:8383 使用
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.path.expanduser("~")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOWNLOAD_DIR = os.path.join(HOME, "storage", "shared", "zoombase", "downloads")
ARIA2_RPC = "http://127.0.0.1:6800/jsonrpc"
RPC_PORT = 6800
WEB_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8383
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
NOTIFY = os.path.join(PREFIX, "bin", "termux-notification")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# 已发过完成通知的 gid（只在运行期间有效，重启后不再重复补发）
_notified = set()


# ---------- aria2 JSON-RPC ----------
def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "id": "miao", "method": method, "params": params or []}
    req = urllib.request.Request(
        ARIA2_RPC,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError("aria2 RPC 不可用: %s" % e)
    if "error" in data:
        raise RuntimeError(data["error"]["message"])
    return data.get("result")


# rpc_alive: 探测 aria2 JSON-RPC 是否存活。
def rpc_alive():
    try:
        rpc("aria2.getVersion")
        return True
    except Exception:
        return False


# ensure_aria2: 确保 aria2 已以后台 RPC 模式启动（无则拉起）。
def ensure_aria2():
    """aria2 RPC 没活着就拉起一个后台实例"""
    if rpc_alive():
        return
    cmd = [
        "aria2c",
        "--enable-rpc",
        "--rpc-listen-port=%d" % RPC_PORT,
        "--rpc-listen-all=false",
        "--dir=" + DOWNLOAD_DIR,
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--continue=true",
        "--file-allocation=none",
        "--daemon=true",
        "--quiet=true",
        "--console-log-level=error",
    ]
    try:
        subprocess.run(cmd, timeout=15)
    except Exception:
        pass
    # 等待 RPC 就绪
    for _ in range(20):
        if rpc_alive():
            return
        time.sleep(0.5)
    raise RuntimeError("aria2 RPC 启动失败")


# safe_filename: 文件名安全化（去掉非法字符）。
def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name or None


# notify_done: 下载完成时发系统通知。
def notify_done(filename):
    """下载完成弹通知（termux-api 可用时）"""
    if not os.path.exists(NOTIFY) or not filename:
        return
    try:
        subprocess.Popen(
            [NOTIFY, "-t", "喵下载 完成喵", "-c", "主人！%s 下载好了 (≧▽≦)" % filename],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------- 任务模型 ----------
_KEYS = [
    "gid", "status", "totalLength", "completedLength",
    "downloadSpeed", "uploadSpeed", "files", "errorMessage", "errorCode",
]


# _clean: 内部工具：清理/规范化文本。
def _clean(t):
    try:
        total = int(t.get("totalLength") or 0)
        done = int(t.get("completedLength") or 0)
        speed = int(t.get("downloadSpeed") or 0)
    except (TypeError, ValueError):
        total = done = speed = 0
    f = (t.get("files") or [{}])[0]
    path = f.get("path") or ""
    name = os.path.basename(path) or "未知文件"
    return {
        "gid": t.get("gid", ""),
        "status": t.get("status", "unknown"),
        "name": name,
        "total": total,
        "done": done,
        "speed": speed,
        "progress": (done / total * 100) if total else 0,
        "error": t.get("errorMessage", "") or "",
    }


# get_tasks: 获取当前任务列表（状态/进度/速度）。
def get_tasks():
    """合并 active / waiting / stopped 三区任务"""
    tasks = []
    tasks += [_clean(t) for t in (rpc("aria2.tellActive", [_KEYS]) or [])]
    tasks += [_clean(t) for t in (rpc("aria2.tellWaiting", [0, 1000, _KEYS]) or [])]
    tasks += [_clean(t) for t in (rpc("aria2.tellStopped", [0, 1000, _KEYS]) or [])]
    # 去重（按 gid），保持 active 优先
    seen = set()
    uniq = []
    for t in tasks:
        if t["gid"] and t["gid"] not in seen:
            seen.add(t["gid"])
            uniq.append(t)
    # 完成通知：检查 complete 且未通知过的
    for t in uniq:
        if t["status"] == "complete" and t["gid"] not in _notified:
            _notified.add(t["gid"])
            notify_done(t["name"])
    try:
        stat = rpc("aria2.getGlobalStat") or {}
        gspeed = int(stat.get("downloadSpeed") or 0)
    except Exception:
        gspeed = 0
    return {"tasks": uniq, "global_speed": gspeed}


# add_task: 添加下载任务（URL + 可选保存目录）。
def add_task(url, out=None):
    # 每个任务显式指定下载目录，避免 aria2 常驻进程仍用旧 --dir
    opts = {"dir": DOWNLOAD_DIR}
    if out and safe_filename(out):
        opts["out"] = safe_filename(out)
    gid = rpc("aria2.addUri", [[url], opts])
    return gid


# action: 任务操作（暂停/继续/删除）。
def action(gid, act):
    if act == "pause":
        rpc("aria2.pause", [gid])
    elif act == "resume":
        rpc("aria2.unpause", [gid])
    elif act == "remove":
        # 进行中/等待中的任务：先 remove，失败就 forceRemove
        try:
            rpc("aria2.remove", [gid])
        except Exception:
            pass
        try:
            rpc("aria2.forceRemove", [gid])
        except Exception:
            pass
        # 已停止（完成/出错）的任务：用 removeDownloadResult 清记录
        try:
            rpc("aria2.removeDownloadResult", [gid])
        except Exception:
            pass
    else:
        raise RuntimeError("未知操作: %s" % act)


# set_limit: 设置下载速度上限（KB/s）。
def set_limit(kbs):
    """kbs <= 0 表示不限速"""
    val = "0" if kbs <= 0 else "%dK" % kbs
    rpc("aria2.changeGlobalOption", [{"max-overall-download-limit": val}])


# get_limit: 查询当前速度上限。
def get_limit():
    try:
        opts = rpc("aria2.getGlobalOption") or {}
        v = opts.get("max-overall-download-limit", "0")
        if v in ("0", "off", ""):
            return 0
        if v.endswith("K"):
            return int(v[:-1])
        # aria2 部分版本返回字节数
        return int(v) // 1024
    except Exception:
        return 0


# ---------- HTTP 服务 ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默访问日志
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/index.html":
            try:
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, "static/index.html 不存在喵", "text/plain; charset=utf-8")
        elif path == "/api/tasks":
            try:
                self._json(get_tasks())
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif path == "/api/limit":
            self._json({"limit_kbs": get_limit()})
        else:
            self._send(404, "喵？没这个页面", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()
        try:
            if path == "/api/add":
                url = (body.get("url") or "").strip()
                if not url:
                    return self._json({"error": "URL 不能为空喵"}, 400)
                gid = add_task(url, body.get("out"))
                self._json({"gid": gid})
            elif path == "/api/action":
                gid = body.get("gid") or ""
                act = body.get("action") or ""
                if not gid or not act:
                    return self._json({"error": "参数不全喵"}, 400)
                action(gid, act)
                self._json({"ok": True})
            elif path == "/api/limit":
                try:
                    kbs = int(body.get("limit_kbs") or 0)
                except (TypeError, ValueError):
                    return self._json({"error": "限速格式不对喵"}, 400)
                set_limit(kbs)
                self._json({"ok": True, "limit_kbs": get_limit()})
            else:
                self._json({"error": "喵？没这个接口"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


# main: 程序入口（启动 HTTP 服务，提供网页 GUI + API）。
def main():
    try:
        ensure_aria2()
    except Exception as e:
        print("!! %s" % e)
        sys.exit(1)
    server = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)
    print("喵下载 上线喵 (≧▽≦)")
    print("  下载目录: %s" % DOWNLOAD_DIR)
    print("  网页控制台: http://localhost:%d" % WEB_PORT)
    print("  按 Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n喵~ 下班啦！")


if __name__ == "__main__":
    main()
