from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import io
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_JST = timezone(timedelta(hours=9))

PROJECT_ROOT = _rc.project_root()
sys.path.insert(0, str(_rc.PYTHON_DIR / "v2"))

from resume_importer.gemini_html_schema_parser import GeminiHtmlSchemaParser
from jsons_to_complete import _build_structured_data, _make_filename, _resolve_dates

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def build_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Word/Doc -> HTML (transfered-htmls) -> complete-jsons 终极流水线" " / Ultimate pipeline Word/Doc -> HTML (transfered-htmls) -> complete-jsons / 究極のパイプライン：Word/Doc -> HTML (transfered-htmls) -> complete-jsons")
    p.add_argument("--src-dir", type=Path, default=PROJECT_ROOT / _rc.dirname("需要采集的简历文件夹"), help="源简历 Word 文件夹" " / Folder of source résumé Word files / 元の履歴書 Word ファイルのフォルダ")
    p.add_argument("--html-dir", type=Path, default=PROJECT_ROOT / "transfered-htmls", help="HTML 转出保存目录" " / Directory to save the converted HTML / HTML 変換結果の保存先ディレクトリ")
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "complete-jsons", help="complete-jsons 输出目录" " / Output directory for complete-jsons / complete-jsons の出力ディレクトリ")
    p.add_argument("--limit", type=int, default=100, help="处理文件数量限制（默认 100 条）" " / Limit on the number of files to process (default 100) / 処理するファイル数の上限（既定 100 件）")
    p.add_argument("--force", action="store_true", help="强制重新转换与写入" " / Force re-conversion and re-writing / 強制的に再変換して書き込み直す")
    p.add_argument("--convert-single", nargs=2, metavar=('SRC', 'DST'), help="内部单文件隔离转换接口" " / Internal single-file isolated conversion interface / 内部用：単一ファイルの分離変換インターフェース")
    return p


def clean_html_styles(html_text: str) -> str:
    """彻底剥离 Word HTML 导出中冗余的内联样式、class、style、xml、style 块与 span 包装

    EN: Completely strip redundant inline styles, class, style, xml, style blocks and span wrappers from Word HTML exports

    JA: Word の HTML エクスポートから冗長なインラインスタイル・class・style・xml・style ブロック・span ラッパーを完全に除去する
    """
    if not html_text:
        return ""
    text = html_text
    # 1. 剔除 <style>...</style>, <script>...</script>, <xml>...</xml> 和注释
    # EN: 1. Remove <style>...</style>, <script>...</script>, <xml>...</xml> and comments
    # JA: 1. <style>...</style>、<script>...</script>、<xml>...</xml> とコメントを除去する
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<xml[\s\S]*?</xml>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    
    # 2. 移除所有的内联属性：style, class, lang, align, valign, width, height, color, bgcolor 等
    # EN: 2. Remove all inline attributes: style, class, lang, align, valign, width, height, color, bgcolor, etc.
    # JA: 2. すべてのインライン属性を除去する：style、class、lang、align、valign、width、height、color、bgcolor など
    text = re.sub(r'\s+(?:style|class|lang|align|valign|width|height|color|bgcolor|border|cellspacing|cellpadding|vspace|hspace|marginheight|marginwidth)="[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:style|class|lang|align|valign|width|height|color|bgcolor|border|cellspacing|cellpadding|vspace|hspace|marginheight|marginwidth)='[^']*'", '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+mso-[a-z\-]+="[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s+mso-[a-z\-]+='[^']*'", '', text, flags=re.IGNORECASE)
    
    # 3. 剥离无意义的 <span> 与 <font> 包装（保留其内部标签文本）
    # EN: 3. Strip meaningless <span> and <font> wrappers (keeping the text of their inner tags)
    # JA: 3. 意味のない <span> と <font> のラッパーを除去する（内側のタグのテキストは残す）
    text = re.sub(r'</?span[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?font[^>]*>', '', text, flags=re.IGNORECASE)
    
    # 4. 压缩空行与缩进
    # EN: 4. Compress blank lines and indentation
    # JA: 4. 空行とインデントを詰める
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def convert_single_word_file(src_path_str: str, dst_path_str: str) -> bool:
    """单文件独立子进程全静默自动修复转换引擎，自动在 HTML 头部写入源文件绝对路径与本地修改下载时间(st_mtime)

    EN: Fully silent auto-repair conversion engine running each file in its own subprocess; writes the source file's absolute path and local modification/download time (st_mtime) into the HTML header

    JA: 1 ファイルごとに独立したサブプロセスで動く完全サイレントの自動修復変換エンジン。HTML ヘッダーにソースファイルの絶対パスとローカルの更新・ダウンロード日時（st_mtime）を書き込む
    """
    src_p = Path(src_path_str).resolve()
    dst_p = Path(dst_path_str).resolve()

    # 获取本地文件上一次修改时间 (st_mtime) 作为真正的简历下载时间
    # EN: Use the local file's last modification time (st_mtime) as the real résumé download time
    # JA: ローカルファイルの最終更新日時（st_mtime）を実際の履歴書ダウンロード日時として使う
    file_stat = src_p.stat()
    mtime_dt = datetime.fromtimestamp(file_stat.st_mtime)
    mtime_str = mtime_dt.strftime("%Y年%m月%d日 %H:%M:%S")

    # 构建 HTML 头部元数据行
    # EN: Build the HTML header metadata lines
    # JA: HTML ヘッダーのメタデータ行を作る
    meta_header_html = f"""<div class="resume-source-header" style="border-bottom:1px dashed #ccc; padding-bottom:8px; margin-bottom:12px; font-family:sans-serif; color:#333;">
  <p><b>源文件路径：</b>{src_p}</p>
  <p><b>简历下载时间：</b>{mtime_str}</p>
</div>
"""

    full_html_body = ""

    # 0. 强力侦测：针对智联招聘/51job重命名伪装成 .doc 的原生 HTML / MHT 文件（0 毫秒闪电秒解！）
    # EN: 0. Aggressive detection: native HTML / MHT files from Zhaopin/51job renamed to look like .doc (parsed instantly!)
    # JA: 0. 強力な検出：Zhaopin／51job で .doc に偽装されたネイティブの HTML / MHT ファイル（瞬時に解析！）
    try:
        raw_head = ""
        for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
            try:
                raw_head = src_p.read_text(encoding=enc, errors="ignore")[:400]
                if raw_head: break
            except Exception:
                pass
        if "<html" in raw_head.lower() or "<table" in raw_head.lower() or "<body" in raw_head.lower() or "<div" in raw_head.lower() or "mime-version:" in raw_head.lower():
            for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
                try:
                    full_html_body = src_p.read_text(encoding=enc, errors="ignore")
                    if full_html_body: break
                except Exception:
                    pass
    except Exception:
        pass

    # 1. 优先方案：对于真正的 .docx 文件，使用 mammoth 神器解析为高精纯净 HTML DOM（解决嵌套表格 5 列平铺重复的 Bug！）
    # EN: 1. Preferred: for real .docx files, use mammoth to parse into a clean, accurate HTML DOM (fixes the bug where nested tables were flattened into 5 duplicated columns!)
    # JA: 1. 第一案：本物の .docx ファイルは mammoth で精度の高いクリーンな HTML DOM に解析する（入れ子の表が 5 列に平坦化されて重複するバグを解消！）
    if not full_html_body and src_p.suffix.lower() == ".docx":
        try:
            import mammoth
            with open(src_p, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                full_html_body = f"<html><body>{result.value}</body></html>"
        except Exception:
            pass

    # 2. 备选方案：对于旧版 .doc / .rtf 文件，使用 MS Word COM 接口 OpenAndRepair=True 静默修复转换
    # EN: 2. Fallback: for old .doc / .rtf files, use the MS Word COM interface with OpenAndRepair=True to repair and convert silently
    # JA: 2. 代替案：旧 .doc / .rtf ファイルは MS Word COM インターフェースの OpenAndRepair=True で静かに修復・変換する
    if not full_html_body:
        try:
            import win32com.client
            word_app = win32com.client.DispatchEx("Word.Application")
            word_app.Visible = False
            word_app.DisplayAlerts = 0  # wdAlertsNone 强行屏蔽一切警报弹窗
            # EN: wdAlertsNone forcibly suppresses every alert dialog
            # JA: wdAlertsNone ですべての警告ダイアログを強制的に抑止する
            try:
                word_app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
                word_app.Options.ConfirmConversions = False
                word_app.Options.SaveNormalPrompt = False
            except Exception:
                pass

            doc = word_app.Documents.Open(
                FileName=str(src_p),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                PasswordDocument="",
                WritePasswordDocument="",
                OpenAndRepair=True
            )
            doc.SaveAs2(str(dst_p), FileFormat=10) # 10 = wdFormatFilteredHTML
            doc.Close(False)
            word_app.Quit()

            if dst_p.exists() and dst_p.stat().st_size > 100:
                for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
                    try:
                        full_html_body = dst_p.read_text(encoding=enc)
                        if full_html_body: break
                    except Exception:
                        pass
        except Exception:
            try:
                word_app.Quit()
            except Exception:
                pass

    if full_html_body:
        cleaned_h = clean_html_styles(full_html_body)
        # 将源文件路径与简历下载时间安全注入 HTML 头部（避免 Windows 路径反斜杠转义报错）
        # EN: Safely inject the source file path and résumé download time into the HTML header (avoiding escape errors from Windows path backslashes)
        # JA: ソースファイルのパスと履歴書のダウンロード日時を HTML ヘッダーに安全に埋め込む（Windows パスのバックスラッシュによるエスケープエラーを避ける）
        lower_h = cleaned_h.lower()
        if "<body" in lower_h:
            body_idx = lower_h.find("<body")
            gt_idx = cleaned_h.find(">", body_idx)
            if gt_idx != -1:
                final_h = cleaned_h[:gt_idx+1] + "\n" + meta_header_html + cleaned_h[gt_idx+1:]
            else:
                final_h = meta_header_html + "\n" + cleaned_h
        else:
            final_h = meta_header_html + "\n" + cleaned_h
        dst_p.write_text(final_h, encoding="utf-8")
        return True

    return False


def get_candidate_files(src_dir: Path, limit: int = 100) -> list[Path]:
    """精选 100 个有效的简历 Word/Doc/.docx 文件

    EN: Pick 100 valid résumé Word/Doc/.docx files

    JA: 有効な履歴書の Word/Doc/.docx ファイルを 100 件選ぶ
    """
    valid_exts = {".doc", ".docx", ".mht", ".mhtml", ".html"}
    skip_keywords = ["合同", "公司简介", "推荐报告", "喜虫", "太阳诱电", "模板", "登记表", "契約書"]
    
    candidates = []
    for p in src_dir.rglob("*"):
        if not p.is_file() or p.name.startswith("~$") or p.suffix.lower() not in valid_exts:
            continue
        if any(kw in p.name for kw in skip_keywords):
            continue
        candidates.append(p)

    priority_files = []
    normal_files = []
    for p in candidates:
        if any(kw in p.name for kw in ["51job", "智联", "猎聘", "简历", "履历", "基本信息", "个人"]):
            priority_files.append(p)
        else:
            normal_files.append(p)

    result = (priority_files + normal_files)[:limit]
    return result


def main():
    args = build_args().parse_args()

    # 单文件转换模式
    # EN: Single-file conversion mode
    # JA: 単一ファイル変換モード
    if args.convert_single:
        src_f, dst_f = args.convert_single
        ok = convert_single_word_file(src_f, dst_f)
        sys.exit(0 if ok else 1)

    src_dir = args.src_dir.resolve()
    html_dir = args.html_dir.resolve()
    output_dir = args.output_dir.resolve()

    html_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 严格清理 complete-jsons 目录，保留 3 个 demo. 文件
    # EN: 1. Strictly clean the complete-jsons directory, keeping the 3 demo. files
    # JA: 1. complete-jsons ディレクトリを厳密に整理し、demo. ファイル 3 件は残す
    deleted = 0
    retained = 0
    for p in output_dir.glob("*.json"):
        if p.name.startswith("demo."):
            retained += 1
        else:
            p.unlink()
            deleted += 1
    print(f"=== 已清理 complete-jsons/ (删除旧文件: {deleted} 个, 保留 demo 文件: {retained} 个) ===" f" / === Cleaned complete-jsons/ (old files deleted: {deleted}, demo files kept: {retained}) === / === complete-jsons/ を整理しました（削除した古いファイル：{deleted} 個、残したデモファイル：{retained} 個） ===")

    # 2. 选取 100 个有效源 Word 简历
    # EN: 2. Select 100 valid source Word résumés
    # JA: 2. 有効な Word 履歴書を 100 件選ぶ
    files = get_candidate_files(src_dir, args.limit)
    print(f"=== 精选 {len(files)} 条 Word/Doc 源简历文件准备转换与解析 ===" f" / === {len(files)} Word/Doc source résumé files selected for conversion and parsing === / === Word/Doc の元履歴書ファイル {len(files)} 件を選び、変換・解析の準備をします ===")

    import subprocess
    converted_htmls = []
    print(f"--- 阶段 1: 单文件超时隔离转码 HTML 到 {html_dir.name}/ ---" f" / --- Stage 1: isolated per-file conversion to HTML with timeout, into {html_dir.name}/ --- / --- 段階 1：1 ファイルずつタイムアウト付きで分離して HTML に変換、保存先 {html_dir.name}/ ---")

    for i, p_src in enumerate(files, 1):
        rel_name = p_src.stem
        hash_suffix = hashlib.md5(str(p_src).encode('utf-8')).hexdigest()[:8]
        clean_stem = re.sub(r"[^\w\u4e00-\u9fff\(\)-]", "_", rel_name)
        out_html_name = f"{clean_stem}_{hash_suffix}.html"
        out_html_path = html_dir / out_html_name

        if p_src.suffix.lower() in [".htm", ".html", ".mht", ".mhtml"]:
            out_html_path = p_src
            converted_htmls.append((p_src, out_html_path))
            print(f"[{i:3d}/{len(files)}] [纯HTML就绪] {out_html_path.name}" f" / [{i:3d}/{len(files)}] [pure HTML ready] {out_html_path.name} / [{i:3d}/{len(files)}] [HTML のみ準備完了] {out_html_path.name}")
        else:
            if out_html_path.exists() and out_html_path.stat().st_size > 100 and not args.force:
                converted_htmls.append((p_src, out_html_path))
                print(f"[{i:3d}/{len(files)}] [HTML已存在] {out_html_path.name}" f" / [{i:3d}/{len(files)}] [HTML already exists] {out_html_path.name} / [{i:3d}/{len(files)}] [HTML は既に存在] {out_html_path.name}")
            else:
                # 触发单文件独立子进程防悬挂转换，5秒强超时
                # EN: Run each file in its own subprocess to prevent hangs, with a hard 5-second timeout
                # JA: ハングを防ぐため 1 ファイルごとに独立したサブプロセスで変換し、5 秒の強制タイムアウトを設ける
                try:
                    res = subprocess.run(
                        [sys.executable, __file__, "--convert-single", str(p_src), str(out_html_path)],
                        timeout=6,
                        capture_output=True
                    )
                    if out_html_path.exists() and out_html_path.stat().st_size > 100:
                        converted_htmls.append((p_src, out_html_path))
                        print(f"[{i:3d}/{len(files)}] [HTML转换成功] {out_html_path.name}" f" / [{i:3d}/{len(files)}] [HTML converted] {out_html_path.name} / [{i:3d}/{len(files)}] [HTML 変換成功] {out_html_path.name}")
                    else:
                        print(f"[{i:3d}/{len(files)}] [HTML转换跳过] {p_src.name}" f" / [{i:3d}/{len(files)}] [HTML conversion skipped] {p_src.name} / [{i:3d}/{len(files)}] [HTML 変換をスキップ] {p_src.name}")
                except subprocess.TimeoutExpired:
                    print(f"[{i:3d}/{len(files)}] [超时杀进程跳过] {p_src.name}" f" / [{i:3d}/{len(files)}] [timed out, process killed, skipped] {p_src.name} / [タイムアウトでプロセスを終了しスキップ] [{i:3d}/{len(files)}] {p_src.name}")
                    # 杀掉残留的 WINWORD 进程
                    # EN: Kill leftover WINWORD processes
                    # JA: 残っている WINWORD プロセスを終了させる
                    try:
                        subprocess.run(["powershell", "-Command", "Stop-Process -Name WINWORD -Force -ErrorAction SilentlyContinue"], capture_output=True)
                    except Exception:
                        pass


    print(f"\n--- 阶段 2: 使用 GeminiHtmlSchemaParser 解析 HTML 并落盘 complete-jsons ---" f" / \n--- Stage 2: parse the HTML with GeminiHtmlSchemaParser and write to complete-jsons --- / \n--- 段階 2：GeminiHtmlSchemaParser で HTML を解析し complete-jsons に書き出し ---")
    parser = GeminiHtmlSchemaParser()

    success_cnt = 0
    fail_cnt = 0

    for i, (p_src, p_html) in enumerate(converted_htmls, 1):
        try:
            raw_html = ""
            for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
                try:
                    raw_html = p_html.read_text(encoding=enc)
                    if raw_html: break
                except Exception:
                    pass

            if not raw_html:
                print(f"[{i:3d}/{len(converted_htmls)}] [读取失败] {p_html.name}" f" / [{i:3d}/{len(converted_htmls)}] [read failed] {p_html.name} / [{i:3d}/{len(converted_htmls)}] [読み込み失敗] {p_html.name}")
                fail_cnt += 1
                continue

            parsed_dict = parser.parse(raw_html, filename=p_src.name, source_path=str(p_src))
            resumes = parsed_dict.get("resumes", [])
            name = ""
            if resumes:
                name = resumes[0].get("base_info", {}).get("full_name", "")

            file_stat = p_src.stat()
            # 1. source 节点
            # EN: 1. source node
            # JA: 1. source ノード
            source_info = {
                "path": str(p_src.resolve()),
                "filename": p_src.name,
                "extension": p_src.suffix.lower(),
                "size": file_stat.st_size if file_stat else 0
            }

            # 2. resume_download_date 精确到时分秒: YYYY-MM-DD HH:MM:SS
            # EN: 2. resume_download_date to the second: YYYY-MM-DD HH:MM:SS
            # JA: 2. resume_download_date は秒まで：YYYY-MM-DD HH:MM:SS
            mtime_dt = datetime.fromtimestamp(file_stat.st_mtime)
            download_date_str = mtime_dt.strftime("%Y-%m-%d %H:%M:%S")

            # 3. resume_updated_date 优先正文/底部 操作时间：2022.03.11 13:30:52
            # EN: 3. resume_updated_date prefers the operation time in the body/footer: 操作时间：2022.03.11 13:30:52
            # JA: 3. resume_updated_date は本文・フッターの操作日時を優先：操作时间：2022.03.11 13:30:52
            m_upd = re.search(r"(?:操作时间|操作日期|更新时间|更新日期|简历更新时间|履历更新)\s*[:：\t\s]*((?:19|20)\d{2}[-./年]\d{1,2}[-./月]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)", raw_html)
            updated_date_str = ""
            if m_upd:
                raw_d = m_upd.group(1).strip()
                m_parts = re.search(r"((?:19|20)\d{2})[-./年]\s*(\d{1,2})[-./月]\s*(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?", raw_d)
                if m_parts:
                    y, m, d = m_parts.group(1), f"{int(m_parts.group(2)):02d}", f"{int(m_parts.group(3)):02d}"
                    hh = f"{int(m_parts.group(4)):02d}" if m_parts.group(4) else "00"
                    mm = f"{int(m_parts.group(5)):02d}" if m_parts.group(5) else "00"
                    ss = f"{int(m_parts.group(6)):02d}" if m_parts.group(6) else "00"
                    updated_date_str = f"{y}-{m}-{d} {hh}:{mm}:{ss}"

            if not updated_date_str:
                updated_date_str = download_date_str

            dates_info = {
                "resume_updated_date": updated_date_str,
                "resume_download_date": download_date_str,
                "sys_created_date": datetime.now(TZ_JST).isoformat(timespec="seconds"),
                "sys_updated_date": datetime.now(TZ_JST).isoformat(timespec="seconds")
            }

            structured_data = _build_structured_data(parsed_dict)

            final_json = {
                "source": source_info,
                "dates": dates_info,
                "structured_data": structured_data
            }

            out_json_name = _make_filename(name or "未知候选人", p_src.name, p_src.name, str(p_src))
            out_json_path = output_dir / out_json_name

            out_json_path.write_text(json.dumps(final_json, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{i:3d}/{len(converted_htmls)}] [JSON写入成功] {out_json_path.name} (姓名: {name or '未知'})" f" / [{i:3d}/{len(converted_htmls)}] [JSON written] {out_json_path.name} (name: {name or '未知'}) / [{i:3d}/{len(converted_htmls)}] [JSON 書き込み成功] {out_json_path.name}（氏名：{name or '未知'}）")
            success_cnt += 1

        except Exception as e:
            print(f"[{i:3d}/{len(converted_htmls)}] [解析异常] {p_html.name}: {e}" f" / [{i:3d}/{len(converted_htmls)}] [parse error] {p_html.name}: {e} / [{i:3d}/{len(converted_htmls)}] [解析エラー] {p_html.name}：{e}")
            fail_cnt += 1

    print(f"\n=== Word -> HTML -> complete-jsons 跑批完成 ===" f" / \n=== Word -> HTML -> complete-jsons batch finished === / \n=== Word -> HTML -> complete-jsons の一括処理が完了しました ===")
    print(f"  总计转换 HTML: {len(converted_htmls)}" f" / Total HTML converted: {len(converted_htmls)} / 変換した HTML の合計：{len(converted_htmls)}")
    print(f"  成功写入 JSON: {success_cnt}" f" / JSON written successfully: {success_cnt} / JSON の書き込み成功：{success_cnt}")
    print(f"  失败数: {fail_cnt}" f" / Failures: {fail_cnt} / 失敗数：{fail_cnt}")


if __name__ == "__main__":
    main()
