#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用喵下载批量下载今天翻唱过的歌的完整版 (≧▽≦)"""
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/hermes11/喵下载"))
import miao_dm

SONGS = [
    ("https://music.163.com/song/media/outer/url?id=2722510685.mp3", "耀斑-HOYO-MiX.mp3"),
    ("https://music.163.com/song/media/outer/url?id=2709812973.mp3", "拂晓-ProiProi-HOYO-MiX.mp3"),
    ("https://music.163.com/song/media/outer/url?id=22677558.mp3", "甩葱歌-初音未来.mp3"),
    ("https://music.163.com/song/media/outer/url?id=1815684465.mp3", "Rubia-周深.mp3"),
    ("https://music.163.com/song/media/outer/url?id=1417892367.mp3", "两只老虎-贝乐虎儿歌.mp3"),
]

def main():
    miao_dm.ensure_aria2()
    print("aria2 RPC 就绪，添加任务喵...")
    gids = {}
    for url, out in SONGS:
        try:
            gid = miao_dm.add_task(url, out)
            gids[gid] = out
            print("已添加: %s (gid=%s)" % (out, gid))
        except Exception as e:
            print("添加失败: %s -> %s" % (out, e))

    # 轮询直到全部结束（最多 120s）
    deadline = time.time() + 120
    while time.time() < deadline and gids:
        time.sleep(2)
        try:
            tasks = miao_dm.get_tasks()["tasks"]
        except Exception:
            continue
        done = set()
        for t in tasks:
            if t["gid"] in gids:
                if t["status"] in ("complete", "error"):
                    done.add(t["gid"])
                    mark = "完成 ✔" if t["status"] == "complete" else "失败 ✘ " + t["error"]
                    print("[%s] %s" % (mark, gids[t["gid"]]))
        for g in done:
            gids.pop(g)

    if gids:
        print("还有 %d 个任务未结束（可能较慢），稍后可看 /api/tasks 或手动检查" % len(gids))

    print("\n=== 下载目录文件 ===")
    for f in sorted(os.listdir(miao_dm.DOWNLOAD_DIR)):
        p = os.path.join(miao_dm.DOWNLOAD_DIR, f)
        if os.path.isfile(p):
            print("  %s  (%d KB)" % (f, os.path.getsize(p) // 1024))

if __name__ == "__main__":
    main()
