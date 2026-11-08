#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_pack_sources.v3.py —— 把“回源检查解析器”所需的全部材料打包（只读，不改动任何原文件）。

打包内容：
  inputs/v2/*.json, inputs/v1/*.json      complete-transfered-jsons、complete-v1 全部 JSON（含无联系方式）
  originals/<key><后缀>                    每个 JSON 引用的原始简历文件（需要采集的简历文件夹）
  html/<key>.html                          JSON 中登记、且仍存在的中间 HTML
  maps/...                                 complete-transfered-htmls 下的转换映射 JSON/CSV（文件名含 map/manifest）
  manifest.csv                             input_json → original_path / html_path → 包内 key 的对照

输出：<output_dir>\\claude_pack\\<时间戳>\\pack_partNN.zip（每个分卷 ≤ --part-mb）

EN: claude_pack_sources.v3.py -- packs all the materials needed for "checking parsers against the sources" (read-only; no original file is changed).

Package contents:
  inputs/v2/*.json, inputs/v1/*.json      all JSON in complete-transfered-jsons and complete-v1 (including those without contacts)
  originals/<key><suffix>                  the original résumé file referenced by each JSON (from the résumé source folder)
  html/<key>.html                          intermediate HTML registered in the JSON that still exists
  maps/...                                 conversion map JSON/CSV under complete-transfered-htmls (file names containing map/manifest)
  manifest.csv                             mapping input_json → original_path / html_path → key inside the package

Output: <output_dir>\\claude_pack\\<timestamp>\\pack_partNN.zip (each volume ≤ --part-mb)

JA: claude_pack_sources.v3.py —— 「パーサーを原文と照合する」のに必要なすべての材料をまとめる（読み取り専用。元のファイルは一切変更しない）。

まとめる内容：
  inputs/v2/*.json, inputs/v1/*.json      complete-transfered-jsons と complete-v1 のすべての JSON（連絡先のないものを含む）
  originals/<key><拡張子>                  各 JSON が参照する元の履歴書ファイル（履歴書の収集元フォルダ）
  html/<key>.html                          JSON に登録され、まだ存在する中間 HTML
  maps/...                                 complete-transfered-htmls 配下の変換マップの JSON/CSV（ファイル名に map/manifest を含むもの）
  manifest.csv                             input_json → original_path / html_path → パッケージ内の key の対応表

出力：<output_dir>\\claude_pack\\<タイムスタンプ>\\pack_partNN.zip（各分割ファイルは --part-mb 以下）
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = _rc.project_root()


def log(msg, fh):
    print(msg, flush=True)
    fh.write(msg + "\n")
    fh.flush()


def long_path(sp: str) -> Path:
    """Windows 长路径（>240 字符）加 \\?\\ 前缀。

    EN: Windows long paths (>240 characters) get the \\?\\ prefix.

    JA: Windows の長いパス（240 文字超）には \\?\\ の接頭辞を付ける。
    """
    if os.name == "nt" and len(sp) > 240 and not sp.startswith("\\\\?\\"):
        return Path("\\\\?\\" + os.path.abspath(sp))
    return Path(sp)


def safe_size(fp: Path):
    try:
        st = fp.stat()
    except OSError:
        return None
    import stat as _st
    return st.st_size if _st.S_ISREG(st.st_mode) else None


def key_of(path: str) -> str:
    return hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:20]


def collect_paths(doc: dict):
    src = doc.get("source") or {}
    origs, htmls = [], []

    def add(lst, v):
        if isinstance(v, str) and v.strip() and v not in lst:
            lst.append(v.strip())

    add(origs, src.get("original_path"))
    for x in src.get("merged_original_paths") or []:
        add(origs, x)
    for sf in src.get("source_files") or []:
        if isinstance(sf, dict):
            add(origs, sf.get("original_path"))
            add(htmls, sf.get("html_path"))
    p = src.get("path")
    if isinstance(p, str) and p.lower().endswith((".html", ".htm", ".mht")):
        add(htmls, p)
    add(htmls, (doc.get("extraction") or {}).get("html_path"))
    return origs, htmls


class PartWriter:
    def __init__(self, out_dir: Path, limit_bytes: int, fh):
        self.out_dir, self.limit, self.fh = out_dir, limit_bytes, fh
        self.idx, self.zf, self.cur = 0, None, 0
        self.written = set()
        self._open()

    def _open(self):
        if self.zf:
            self.zf.close()
            log(f"  分卷完成：pack_part{self.idx:02d}.zip", self.fh)
        self.idx += 1
        self.zf = zipfile.ZipFile(self.out_dir / f"pack_part{self.idx:02d}.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=6)
        self.cur = 0

    def add(self, src: Path, arc: str):
        if arc in self.written:
            return True
        src = Path(_rc.resolve_path(str(src)))  # 旧路径失效时按 config.json 的 path_map 换算
        # EN: When the old path is invalid, convert it via path_map in config.json
        # JA: 古いパスが無効なときは config.json の path_map で変換する
        try:
            size = src.stat().st_size
        except OSError:
            return False
        if self.cur and self.cur + size > self.limit:
            self._open()
        try:
            self.zf.write(src, arc)
        except (OSError, ValueError) as ex:
            log(f"  读取失败 {src}: {ex}", self.fh)
            return False
        self.cur += size
        self.written.add(arc)
        return True

    def add_bytes(self, data: bytes, arc: str):
        if self.cur and self.cur + len(data) > self.limit:
            self._open()
        self.zf.writestr(arc, data)
        self.cur += len(data)

    def close(self):
        if self.zf:
            self.zf.close()
            log(f"  分卷完成：pack_part{self.idx:02d}.zip", self.fh)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2-dir", type=Path, default=ROOT / "complete-transfered-jsons")
    ap.add_argument("--v1-dir", type=Path, default=ROOT / "complete-v1")
    ap.add_argument("--html-root", type=Path, default=ROOT / "complete-transfered-htmls")
    ap.add_argument("--out-root", type=Path, default=ROOT / "output" / "claude_pack")
    ap.add_argument("--part-mb", type=int, default=380)
    a = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M")
    out = a.out_root / stamp
    out.mkdir(parents=True, exist_ok=True)
    fh = open(out / "pack.log", "w", encoding="utf-8")
    log(f"输出目录：{out}", fh)
    pw = PartWriter(out, a.part_mb * 1024 * 1024, fh)

    rows = []
    stats = {"inputs": 0, "json_error": 0, "orig_refs": 0, "orig_missing": 0, "html_refs": 0, "html_missing": 0,
             "orig_bytes": 0, "maps": 0}
    ext_count = {}
    for ver, d in (("v2", a.v2_dir), ("v1", a.v1_dir)):
        with os.scandir(d) as it:
            names = sorted(e.name for e in it if e.is_file() and e.name.lower().endswith(".json") and not e.name.startswith("_"))
        log(f"[{ver}] {d}：{len(names)} 个 JSON", fh)
        for i, n in enumerate(names, 1):
            p = d / n
            stats["inputs"] += 1
            pw.add(p, f"inputs/{ver}/{n}")
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except Exception as ex:  # noqa: BLE001
                stats["json_error"] += 1
                rows.append({"input_json": str(p), "version": ver, "kind": "json_error", "path": "", "exists": "", "size": "",
                             "ext": "", "pack_key": "", "note": str(ex)[:200]})
                continue
            origs, htmls = collect_paths(doc)
            if not origs:
                rows.append({"input_json": str(p), "version": ver, "kind": "original", "path": "", "exists": "False",
                             "size": "", "ext": "", "pack_key": "", "note": "JSON 未登记原始文件"})
            for kind, lst in (("original", origs), ("html", htmls)):
                for sp in lst:
                    fp = long_path(sp)
                    ext = Path(sp).suffix.lower()
                    k = key_of(sp)
                    sz = safe_size(fp)
                    ok = sz is not None
                    size = sz if ok else ""
                    stats[("orig" if kind == "original" else "html") + "_refs"] += 1
                    if not ok:
                        stats[("orig" if kind == "original" else "html") + "_missing"] += 1
                    arc = f"{'originals' if kind == 'original' else 'html'}/{k}{ext}"
                    if ok:
                        first = arc not in pw.written
                        ok = pw.add(fp, arc)
                        if ok and first and kind == "original":
                            stats["orig_bytes"] += size
                            ext_count[ext] = ext_count.get(ext, 0) + 1
                    rows.append({"input_json": str(p), "version": ver, "kind": kind, "path": sp, "exists": str(ok),
                                 "size": size, "ext": ext, "pack_key": arc if ok else "", "note": ""})
            if i % 1000 == 0:
                log(f"  {ver} 已处理 {i}/{len(names)}，原始文件累计 {stats['orig_bytes'] / 1048576:.0f} MB", fh)

    log("[maps] 转换映射与清单", fh)
    if a.html_root.is_dir():
        for dp, _, fns in os.walk(a.html_root):
            for fn in fns:
                low = fn.lower()
                if low.endswith((".json", ".csv")) and ("map" in low or "manifest" in low or "report" in low):
                    fp = Path(dp) / fn
                    if pw.add(fp, "maps/" + str(fp.relative_to(a.html_root)).replace("\\", "/")):
                        stats["maps"] += 1

    import io
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=["input_json", "version", "kind", "path", "exists", "size", "ext", "pack_key", "note"])
    w.writeheader()
    w.writerows(rows)
    data = ("\ufeff" + sio.getvalue()).encode("utf-8")
    (out / "manifest.csv").write_bytes(data)
    pw.add_bytes(data, "manifest.csv")
    stats["ext_count"] = ext_count
    stats["parts"] = pw.idx
    pw.add_bytes(json.dumps(stats, ensure_ascii=False, indent=1).encode("utf-8"), "pack_stats.json")
    pw.close()
    (out / "pack_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    log(json.dumps(stats, ensure_ascii=False, indent=1), fh)
    log(f"完成：{out}", fh)


if __name__ == "__main__":
    main()
