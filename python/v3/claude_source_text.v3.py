#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_source_text.v3.py —— 独立于原解析器，从原始简历文件抽取全文（用于回源核对）。

运行环境：云端 Linux（LibreOffice + pdftotext + python-docx/openpyxl/bs4）。
输入：claude_pack 解压目录（originals/<key><后缀>）
输出：<out>/texts/<key>.txt 和 <out>/extract_ledger.csv

抽取方法：
  .doc .docm .dotx .dot .wps .rtf  → LibreOffice 转 .docx → 直接读 OOXML（含文本框、页眉页脚、表格，跳过 mc:Fallback 重复）
  .docx                            → 直接读 OOXML
  .xls .xlsx .xlsm .et             → LibreOffice 转 .xlsx → openpyxl 读全部工作表
  .pdf                             → pdftotext
  .htm .html                       → 按 meta/BOM 判定编码 → BeautifulSoup 文本
  .mht .mhtml .eml                 → email 解析 HTML/文本部分
  .ppt .pptx                       → LibreOffice 转 PDF → pdftotext
  .txt                             → 编码探测
  .jpg .png 等图片                 → 无法抽取（记为 image_no_text）

EN: claude_source_text.v3.py -- extracts the full text from the original résumé files independently of the original parsers (for checking against the source).

Runtime: cloud Linux (LibreOffice + pdftotext + python-docx/openpyxl/bs4).
Input: the extracted claude_pack directory (originals/<key><suffix>)
Output: <out>/texts/<key>.txt and <out>/extract_ledger.csv

Extraction methods:
  .doc .docm .dotx .dot .wps .rtf  → LibreOffice to .docx → read the OOXML directly (including text boxes, headers/footers, tables; skipping mc:Fallback duplicates)
  .docx                            → read the OOXML directly
  .xls .xlsx .xlsm .et             → LibreOffice to .xlsx → openpyxl reads all worksheets
  .pdf                             → pdftotext
  .htm .html                       → determine the encoding by meta/BOM → BeautifulSoup text
  .mht .mhtml .eml                 → email parses the HTML/text parts
  .ppt .pptx                       → LibreOffice to PDF → pdftotext
  .txt                             → encoding detection
  .jpg .png and other images       → cannot be extracted (recorded as image_no_text)

JA: claude_source_text.v3.py —— 元のパーサーとは独立に、元の履歴書ファイルから全文を抽出する（原文との照合用）。

実行環境：クラウドの Linux（LibreOffice + pdftotext + python-docx/openpyxl/bs4）。
入力：claude_pack を展開したディレクトリ（originals/<key><拡張子>）
出力：<out>/texts/<key>.txt と <out>/extract_ledger.csv

抽出方法：
  .doc .docm .dotx .dot .wps .rtf  → LibreOffice で .docx に変換 → OOXML を直接読む（テキストボックス・ヘッダー・フッター・表を含み、mc:Fallback の重複はスキップ）
  .docx                            → OOXML を直接読む
  .xls .xlsx .xlsm .et             → LibreOffice で .xlsx に変換 → openpyxl ですべてのワークシートを読む
  .pdf                             → pdftotext
  .htm .html                       → meta/BOM でエンコーディングを判定 → BeautifulSoup のテキスト
  .mht .mhtml .eml                 → email で HTML・テキストの部分を解析
  .ppt .pptx                       → LibreOffice で PDF に変換 → pdftotext
  .txt                             → エンコーディングを検出
  .jpg .png などの画像             → 抽出できない（image_no_text として記録）
"""

import argparse
import csv
import email
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from email import policy
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
WORDISH = {".doc", ".docm", ".dotx", ".dot", ".wps", ".rtf", ".odt"}
SHEETISH = {".xls", ".xlsx", ".xlsm", ".et", ".ods"}
SLIDEISH = {".ppt", ".pptx", ".pps", ".ppsx"}
IMAGES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}


# ------------------------------------------------------------------ 解码
# EN: ------------------------------------------------------------------ Decoding
# JA: ------------------------------------------------------------------ デコード
def decode_bytes(b: bytes, hint: str = "") -> str:
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")
    if b.startswith((b"\xff\xfe", b"\xfe\xff")):
        return b.decode("utf-16", "replace")
    cands = []
    if hint:
        cands.append(hint)
    m = re.search(rb"charset\s*=\s*[\"']?([A-Za-z0-9_\-]+)", b[:4000])
    if m:
        cands.append(m.group(1).decode("ascii", "ignore"))
    cands += ["utf-8", "gb18030", "shift_jis", "euc-jp", "big5"]
    for c in cands:
        c = {"gb2312": "gb18030", "gbk": "gb18030", "x-sjis": "shift_jis", "unicode": "utf-16"}.get(c.lower(), c)
        try:
            return b.decode(c)
        except (LookupError, UnicodeDecodeError):
            continue
    return b.decode("gb18030", "replace")


def html_text(s: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(s, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    txt = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n", txt)


# ------------------------------------------------------------------ OOXML
def docx_text(path: Path) -> str:
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = ["word/document.xml"] + sorted(n for n in names if re.match(r"word/(header|footer)\d*\.xml$", n)) \
            + [n for n in ("word/footnotes.xml", "word/endnotes.xml") if n in names]
        for part in parts:
            if part not in names:
                continue
            root = ET.fromstring(z.read(part))
            _walk_docx(root, out)
    return "\n".join(x for x in out if x.strip())


def _walk_docx(node, out):
    for ch in list(node):
        tag = ch.tag
        if tag == MC + "Fallback":
            continue  # 与 mc:Choice 重复
            # EN: Duplicated with mc:Choice
            # JA: mc:Choice と重複
        if tag == W + "p":
            buf = []
            _collect_p(ch, buf, out)
            out.append("".join(buf))
        elif tag == W + "tr":
            cells = []
            for tc in ch.findall(W + "tc"):
                sub = []
                _walk_docx(tc, sub)
                cells.append(" ".join(x for x in sub if x.strip()))
            out.append("\t".join(cells))
        else:
            _walk_docx(ch, out)


def _collect_p(p, buf, out):
    for ch in list(p):
        tag = ch.tag
        if tag == MC + "Fallback":
            continue
        if tag == W + "t":
            buf.append(ch.text or "")
        elif tag == W + "tab":
            buf.append("\t")
        elif tag in (W + "br", W + "cr"):
            buf.append("\n")
        elif tag == W + "txbxContent":
            sub = []
            _walk_docx(ch, sub)
            out.extend(sub)
        else:
            _collect_p(ch, buf, out)


def xlsx_text(path: Path) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"### sheet {ws.title}")
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v).strip() for v in row]
            while vals and not vals[-1]:
                vals.pop()
            if any(vals):
                out.append("\t".join(vals))
    wb.close()
    return "\n".join(out)


# ------------------------------------------------------------------ LibreOffice
def soffice_convert(src: Path, fmt: str, workdir: Path, timeout=120) -> Path:
    prof = workdir.parent / f"lo_profile_{os.getpid()}"  # 每个进程复用一个 LibreOffice 配置，避免每个文件重建
    # EN: Each process reuses one LibreOffice profile, to avoid rebuilding it for every file
    # JA: 各プロセスで 1 つの LibreOffice の設定を再利用し、ファイルごとに作り直さないようにする
    outdir = workdir / "lo_out"
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = ["soffice", f"-env:UserInstallation=file://{prof}", "--headless", "--norestore", "--convert-to", fmt,
           "--outdir", str(outdir), str(src)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    ext = "." + fmt.split(":")[0]
    res = outdir / (src.stem + ext)
    if not res.exists():
        raise RuntimeError(f"soffice 未生成 {ext}")
    return res


def pdf_text(path: Path) -> str:
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", "replace")


def mht_text(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    htmls, plains = [], []
    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/html", "text/plain"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:  # noqa: BLE001
            continue
        s = decode_bytes(payload, part.get_content_charset() or "")
        (htmls if ct == "text/html" else plains).append(s)
    if htmls:
        return "\n".join(html_text(h) for h in htmls)
    if plains:
        return "\n".join(plains)
    return html_text(decode_bytes(path.read_bytes()))


def sniff(head: bytes) -> str:
    """按内容判断真实格式（很多 .doc/.xls 其实是 HTML 或 MIME 邮件）。

    EN: Determine the real format by content (many .doc/.xls are actually HTML or MIME e-mails).

    JA: 内容から実際の形式を判定する（多くの .doc/.xls は実際には HTML か MIME のメール）。
    """
    h = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip_docx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"
    if h.startswith(b"{\\rtf"):
        return "rtf"
    if b"mime-version" in h[:2000] or h.startswith(b"from:") or h.startswith(b"content-type"):
        return "mime"
    if h.startswith((b"<html", b"<!doctype html", b"<meta", b"<head", b"<table")) or (b"<html" in h[:1500]):
        return "html"
    return ""


# ------------------------------------------------------------------ 单文件
# EN: ------------------------------------------------------------------ Single file
# JA: ------------------------------------------------------------------ 単一ファイル
def _extract_primary(src: str, dst: str, tmp_root: str):
    src, dst = Path(src), Path(dst)
    ext = src.suffix.lower()
    work = Path(tempfile.mkdtemp(dir=tmp_root))
    method = ""
    try:
        head = src.read_bytes()[:4096]
        hl = head.lower().lstrip()
        kind = sniff(head)
        if kind == "mime" and ext not in IMAGES:
            method = f"sniff_mime({ext})"
            txt = mht_text(src)
        elif kind == "html" and ext not in IMAGES:
            method = f"sniff_html({ext})"
            txt = html_text(decode_bytes(src.read_bytes()))
        elif kind == "zip_docx" and (ext in WORDISH or ext == ".docx"):
            method = "ooxml"
            txt = docx_text(src)
        elif kind == "pdf":
            method = f"pdftotext({ext})"
            txt = pdf_text(src)
        elif ext == ".docx" or ext in WORDISH:
            try:
                if ext == ".docx":
                    method = "ooxml"
                    txt = docx_text(src)
                else:
                    raise zipfile.BadZipFile
            except (zipfile.BadZipFile, KeyError, ET.ParseError):
                # 扩展名与实际格式不符（如 .doc 实为 RTF/HTML/docx）也交给 LibreOffice
                # EN: When the extension does not match the actual format (e.g. a .doc that is really RTF/HTML/docx), also hand it to LibreOffice
                # JA: 拡張子と実際の形式が一致しない場合（例：実態は RTF/HTML/docx の .doc）も LibreOffice に任せる
                method = "soffice_docx+ooxml"
                conv = soffice_convert(src, "docx", work)
                txt = docx_text(conv)
            if not txt.strip():
                head = src.read_bytes()[:2000].lower()
                if b"<html" in head or b"mime-version" in head:
                    method += "|html_fallback"
                    txt = mht_text(src) if b"mime-version" in head else html_text(decode_bytes(src.read_bytes()))
        elif ext in SHEETISH:
            if ext == ".xlsx":
                method = "openpyxl"
                try:
                    txt = xlsx_text(src)
                except Exception:  # noqa: BLE001
                    method = "soffice_xlsx+openpyxl"
                    txt = xlsx_text(soffice_convert(src, "xlsx", work))
            else:
                head = src.read_bytes()[:2000].lower()
                if b"<html" in head or b"<table" in head:
                    method = "html_in_xls"
                    txt = html_text(decode_bytes(src.read_bytes()))
                else:
                    method = "soffice_xlsx+openpyxl"
                    txt = xlsx_text(soffice_convert(src, "xlsx", work))
        elif ext == ".pdf":
            method = "pdftotext"
            txt = pdf_text(src)
        elif ext in (".htm", ".html", ".xhtml"):
            method = "html"
            b = src.read_bytes()
            txt = mht_text(src) if b[:2000].lower().find(b"mime-version") >= 0 else html_text(decode_bytes(b))
        elif ext in (".mht", ".mhtml", ".eml"):
            method = "mime"
            txt = mht_text(src)
        elif ext in SLIDEISH:
            method = "soffice_pdf+pdftotext"
            txt = pdf_text(soffice_convert(src, "pdf", work))
        elif ext == ".txt":
            method = "text"
            txt = decode_bytes(src.read_bytes())
        elif ext in IMAGES:
            return {"method": "image_no_text", "ok": False, "chars": 0, "error": "图片文件，需要 OCR"}
        else:
            method = "soffice_txt"
            txt = soffice_convert(src, "txt:Text (encoded):UTF8", work).read_text(encoding="utf-8", errors="replace")
        txt = txt.replace("\r\n", "\n").replace("\r", "\n")
        dst.write_text(txt, encoding="utf-8")
        return {"method": method, "ok": bool(txt.strip()), "chars": len(txt), "error": "" if txt.strip() else "抽取结果为空"}
    except subprocess.TimeoutExpired:
        return {"method": method, "ok": False, "chars": 0, "error": "timeout"}
    except Exception as ex:  # noqa: BLE001
        return {"method": method, "ok": False, "chars": 0, "error": f"{type(ex).__name__}: {str(ex)[:200]}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def extract_one(src: str, dst: str, tmp_root: str):
    r = _extract_primary(src, dst, tmp_root)
    if r["ok"] or r["method"] == "image_no_text":
        return r
    # 兜底：LibreOffice 直接转纯文本，超时放宽到 300 秒
    # EN: Fallback: LibreOffice converts directly to plain text, with the timeout relaxed to 300 seconds
    # JA: 最終手段：LibreOffice で直接プレーンテキストに変換し、タイムアウトを 300 秒に緩める
    work = Path(tempfile.mkdtemp(dir=tmp_root))
    try:
        conv = soffice_convert(Path(src), "txt:Text (encoded):UTF8", work, timeout=300)
        txt = conv.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        if txt.strip():
            Path(dst).write_text(txt, encoding="utf-8")
            return {"method": (r["method"] or "") + "|fallback_soffice_txt", "ok": True, "chars": len(txt),
                    "error": f"首选方法失败：{r['error']}"}
        return {**r, "error": r["error"] + "; fallback 为空"}
    except Exception as ex:  # noqa: BLE001
        return {**r, "error": f"{r['error']}; fallback: {type(ex).__name__}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-dir", type=Path, required=True, help="解压后的目录，含 originals/" " / Extracted directory, containing originals/ / 展開後のディレクトリ（originals/ を含む）")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retry-failed", action="store_true", help="重试台账中失败的文件（图片除外），结果追加到台账，以最后一行为准" " / Retry the files that failed in the ledger (except images); results are appended to the ledger and the last line prevails / 台帳で失敗したファイル（画像を除く）をやり直し、結果を台帳に追記する（最後の行を有効とする）")
    a = ap.parse_args()
    texts = a.out / "texts"
    texts.mkdir(parents=True, exist_ok=True)
    tmp_root = a.out / "_tmp"
    tmp_root.mkdir(exist_ok=True)
    ledger = a.out / "extract_ledger.csv"
    done = {}
    if ledger.exists():
        for r in csv.DictReader(open(ledger, encoding="utf-8-sig")):
            done[r["pack_key"]] = r
    files = sorted((a.pack_dir / "originals").iterdir())
    if a.limit:
        files = files[: a.limit]
    if a.retry_failed:
        todo = [f for f in files if f"originals/{f.name}" in done and done[f"originals/{f.name}"]["ok"] != "True"
                and done[f"originals/{f.name}"]["method"] != "image_no_text"]
    else:
        todo = [f for f in files if f"originals/{f.name}" not in done]
    print(f"原始文件 {len(files)}，已完成 {len(files) - len(todo)}，待抽取 {len(todo)}" f" / Original files {len(files)}, done {len(files) - len(todo)}, to extract {len(todo)} / 元ファイル {len(files)}、完了 {len(files) - len(todo)}、抽出待ち {len(todo)}", flush=True)
    new_file = not ledger.exists()
    fh = open(ledger, "a", encoding="utf-8-sig" if new_file else "utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=["pack_key", "ext", "method", "ok", "chars", "error"])
    if new_file:
        w.writeheader()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(extract_one, str(f), str(texts / (f.stem + ".txt")), str(tmp_root)): f for f in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            f = futs[fu]
            try:
                r = fu.result()
            except Exception as e:  # noqa: BLE001
                r = {"method": "", "ok": False, "chars": 0, "error": f"worker: {e}"}
            w.writerow({"pack_key": f"originals/{f.name}", "ext": f.suffix.lower(), **r})
            if i % 200 == 0:
                fh.flush()
                print(f"  {i}/{len(todo)}", flush=True)
    fh.close()
    shutil.rmtree(tmp_root, ignore_errors=True)
    print("完成" " / Done / 完了", flush=True)


if __name__ == "__main__":
    sys.exit(main())
