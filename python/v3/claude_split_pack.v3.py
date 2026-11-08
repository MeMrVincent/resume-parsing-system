#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude_split_pack.v3.py —— 把 claude_pack 的大分卷切成 30MB 小块，便于传输（只新增 .partNNN 文件，不改原分卷）。

EN: claude_split_pack.v3.py -- splits the large claude_pack volumes into 30MB chunks for easier transfer (only adds .partNNN files; the original volumes are not changed).

JA: claude_split_pack.v3.py —— 転送しやすいよう claude_pack の大きな分割ファイルを 30MB の小さな塊に分ける（.partNNN ファイルを追加するだけで、元の分割ファイルは変更しない）。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）
import sys
from pathlib import Path

ROOT = _rc.path("output_dir") / "claude_pack"
CHUNK = 30 * 1024 * 1024
latest = sorted(p for p in ROOT.iterdir() if p.is_dir())[-1]
out = latest / "chunks"
out.mkdir(exist_ok=True)
names = sys.argv[1:] or ["pack_part01.zip", "pack_part02.zip", "pack_part05.zip", "pack_part07.zip", "pack_part08.zip"]
for n in names:
    src = latest / n
    with open(src, "rb") as fh:
        i = 0
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            i += 1
            (out / f"{n}.{i:03d}").write_bytes(b)
    print(f"{n}: {i} 块" f" / {n}: {i} blocks / {n}：{i} ブロック", flush=True)
print(f"完成：{out}" f" / Done: {out} / 完了：{out}")
