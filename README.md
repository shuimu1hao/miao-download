# 喵下载 — 音乐 / 视频下载工具

Termux 上的下载工具集合。

## 功能

- `miao_dm.py` — 喵下载：通用下载（默认目录 `~/storage/shared/zoombase/downloads`）
- `dl_songs.py` — 歌曲批量下载

## 使用

```bash
python3 miao_dm.py <url> [更多url...]
python3 dl_songs.py
```

网页界面在 `static/`。

## 协议

MIT License（见 LICENSE）

## 开发环境

- 设备：小米手机（MIUI / Android 13）
- 环境：Termux（Android 终端）+ termux-x11 + XFCE 图形桌面
- 语言：Go / Python 为主，纯 CLI 开发
- 注意：本项目在 Android / Termux 上开发与测试，其他平台运行可能需要调整

## 生成声明

本项目全部代码与文档由 AI 生成（Hermes Agent + DeepSeek 模型），不含一丝人类手写代码。仅供学习交流。
