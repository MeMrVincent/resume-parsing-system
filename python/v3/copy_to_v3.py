#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
copy_to_v3.py —— 把某次合并运行中的 formal/*.json 复制到 v3_dir（默认 complete-v3），并逐份核对 sha256。

用法：
  python python/v3/copy_to_v3.py                 # 取 merge_out_dir 下名字最新、且不是 -witness 的运行目录
  python python/v3/copy_to_v3.py --run-dir <运行目录> [--dest <目标目录>]
只复制、不删除、不改动源文件。

EN: copy_to_v3.py -- copies formal/*.json from a merge run into v3_dir (default complete-v3) and verifies the sha256 of each file.

Usage:
  python python/v3/copy_to_v3.py                 # take the run directory under merge_out_dir with the latest name that is not -witness
  python python/v3/copy_to_v3.py --run-dir <run directory> [--dest <destination directory>]
Only copies; never deletes or changes the source files.

JA: copy_to_v3.py —— ある統合の実行の formal/*.json を v3_dir（既定は complete-v3）にコピーし、1 件ずつ sha256 を照合する。

使い方：
  python python/v3/copy_to_v3.py                 # merge_out_dir 配下で名前が最も新しく、-witness ではない実行ディレクトリを取る
  python python/v3/copy_to_v3.py --run-dir <実行ディレクトリ> [--dest <コピー先ディレクトリ>]
コピーするだけで、元のファイルを削除・変更することはない。
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path)
    ap.add_argument("--dest", type=Path, default=_rc.path("v3_dir"))
    a = ap.parse_args()
    run = a.run_dir
    if run is None:
        root = _rc.path("merge_out_dir")
        runs = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.endswith("-witness"))
        if not runs:
            print(f"找不到合并运行目录：{root}" f" / Merge run directory not found: {root} / 統合の実行ディレクトリが見つかりません：{root}")
            return 1
        run = runs[-1]
    src = run / "formal"
    if not src.is_dir():
        print(f"找不到 {src}" f" / {src} not found / {src} が見つかりません")
        return 1
    a.dest.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*.json"))
    for f in files:
        shutil.copy2(f, a.dest / f.name)
    bad = [f.name for f in files if not (a.dest / f.name).exists() or sha(f) != sha(a.dest / f.name)]
    print(f"来源：{run}\n目标：{a.dest}\n源文件 {len(files)}，目标文件 {len(list(a.dest.glob('*.json')))}，不一致/缺失 {len(bad)}" f" / Source: {run}\nTarget: {a.dest}\nSource files {len(files)}, target files {len(list(a.dest.glob('*.json')))}, inconsistent/missing {len(bad)} / 元：{run}\n先：{a.dest}\n元ファイル {len(files)}、先ファイル {len(list(a.dest.glob('*.json')))}、不一致／欠落 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
