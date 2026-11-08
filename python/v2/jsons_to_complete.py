"""
jsons_to_complete.py
====================
流水线第二步（单线程）：jsons/ → complete-jsons/

逐文件处理：
  1. 读取 jsons/ 里的 JSON（含 raw_text）
  2. 用 UniversalSchemaParser 提取结构化字段
  3. 按 demo.(贺俊新)__b44afaf3c40a.json 的格式写入 complete-jsons/

文件命名：(候选人姓名)__[record_id前12位].json

EN: jsons_to_complete.py
====================
Pipeline step 2 (single-threaded): jsons/ → complete-jsons/

Per-file processing:
  1. Read the JSON in jsons/ (including raw_text)
  2. Extract structured fields with UniversalSchemaParser
  3. Write to complete-jsons/ in the format of demo.(贺俊新)__b44afaf3c40a.json

File naming: (candidate name)__[first 12 chars of record_id].json

JA: jsons_to_complete.py
====================
パイプラインの第 2 段階（シングルスレッド）：jsons/ → complete-jsons/

ファイルごとの処理：
  1. jsons/ 内の JSON（raw_text を含む）を読む
  2. UniversalSchemaParser で構造化フィールドを抽出する
  3. demo.(贺俊新)__b44afaf3c40a.json の形式で complete-jsons/ に書き込む

ファイル名：(候補者名)__[record_id の先頭 12 文字].json
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = _rc.project_root()
sys.path.insert(0, str(_rc.PYTHON_DIR / "v2"))

from resume_importer.universal_schema_parser import UniversalSchemaParser

# 东京时区
# EN: Tokyo time zone
# JA: 東京のタイムゾーン
TZ_JST = timezone(timedelta(hours=9))


# ─── 空对象模板 ────────────────────────────────────────────────────────────────
# EN: ─── Empty object templates ───
# JA: ─── 空オブジェクトのテンプレート ───

def _empty_base_info() -> dict:
    return {
        "full_name": "", "gender": "", "age": "", "birth_date": "",
        "birth_year": "", "marital_status": "", "children_status": "",
        "political_status": "", "height_cm": "", "weight_kg": "",
        "household_registration": "", "address": "", "postal_code": "",
        "platform_from": "", "platform_resume_id": "",
        "phone": "", "email": "", "city": "", "nationality": "", "pr": ""
    }

def _empty_expected_info() -> list:
    return [{
        "expected_city": "", "expected_position": "", "expected_salary": "",
        "expected_annual_salary_min": "", "expected_annual_salary_max": "",
        "expected_industry": "", "expected_employment_type": "",
        "expected_start_date": ""
    }]

def _empty_current_info() -> dict:
    return {
        "company_name": "", "company_employees": "", "company_industry": "",
        "position": "", "position_type": "", "position_salary": "",
        "position_dept": "", "position_report_to": "", "position_subordinate": "",
        "employment_type": "", "annual_salary_min": "", "annual_salary_max": "",
        "status": "", "position_start": "", "position_resigned": ""
    }

def _empty_education_info() -> dict:
    return {
        "school_name": "", "school_major_name": "", "school_degree_type": "",
        "school_degree_rank": "", "school_education_type": "",
        "school_start_ym": "", "school_end_ym": ""
    }

def _empty_work_experience() -> dict:
    return {
        "company_name": "", "company_employees": "", "company_industry": "",
        "position": "", "position_type": "", "position_salary": "",
        "position_dept": "", "position_report_to": "", "position_subordinate": "",
        "employment_type": "", "annual_salary_min": "", "annual_salary_max": "",
        "status": "", "position_start": "", "position_resigned": "",
        "resigned_reason": "", "position_responsibilities": ""
    }

def _empty_education_item() -> dict:
    return {
        "school_name": "", "school_major_name": "", "school_degree_type": "",
        "school_degree_rank": "", "school_education_type": "",
        "school_start_ym": "", "school_end_ym": ""
    }


# ─── 日期处理 ──────────────────────────────────────────────────────────────────
# EN: ─── Date handling ───
# JA: ─── 日付処理 ───

def _resolve_dates(dates_raw: dict) -> dict:
    """
    统一日期字段，兼容新旧字段名。
    规则：resume_download_date 为空 → 用 resume_updated_date 兜底

    EN: Unify the date fields, compatible with old and new field names.
    Rule: if resume_download_date is empty → fall back to resume_updated_date

    JA: 日付フィールドを統一し、新旧のフィールド名の両方に対応する。
    ルール：resume_download_date が空 → resume_updated_date で補う
    """
    updated = (
        dates_raw.get("resume_updated_date")
        or dates_raw.get("candidate_created_date")
        or ""
    )
    download = (
        dates_raw.get("resume_download_date")
        or dates_raw.get("download_date")
        or ""
    )
    if not download:
        download = updated  # 兜底规则
        # EN: Fallback rule
        # JA: 最後の手段のルール

    sys_created = (
        dates_raw.get("sys_created_date")
        or dates_raw.get("system_collected_at")
        or datetime.now(TZ_JST).isoformat(timespec="seconds")
    )
    sys_updated = datetime.now(TZ_JST).isoformat(timespec="seconds")

    return {
        "resume_updated_date": updated,
        "resume_download_date": download,
        "sys_created_date": sys_created,
        "sys_updated_date": sys_updated,
    }


# ─── 清洗 parser 输出 ─────────────────────────────────────────────────────────
# EN: ─── Clean parser output ───
# JA: ─── パーサー出力のクレンジング ───

def _clean_value(v: Any) -> Any:
    """移除说明注释字段（demo中的中文说明），只保留真实数据字段。

    EN: Remove explanatory comment fields (the Chinese notes in the demo) and keep only real data fields.

    JA: 説明用のコメントフィールド（demo 内の中国語の説明）を削除し、実データのフィールドだけを残す。
    """
    if isinstance(v, dict):
        return {k: _clean_value(val) for k, val in v.items() if k != "说明"}
    if isinstance(v, list):
        return [_clean_value(item) for item in v]
    return v


def _ensure_resume_fields(resume: dict) -> dict:
    """确保 resumes[] 每个对象包含所有必要字段，缺失的补空。

    EN: Make sure every object in resumes[] has all required fields, filling missing ones with empty values.

    JA: resumes[] の各オブジェクトが必要なフィールドをすべて持つようにし、欠けているものは空で補う。
    """
    lang = resume.get("resume_languge", "zh")
    # 只保留合法语言代码
    # EN: Keep only valid language codes
    # JA: 有効な言語コードだけを残す
    if lang not in ("zh", "jp", "en", "de", "fr", "es", "pt"):
        lang = "zh"

    works = resume.get("work_experiences", [])
    if not works:
        works = [_empty_work_experience()]
    else:
        cleaned = []
        for w in works:
            entry = _empty_work_experience()
            entry.update({k: v for k, v in w.items() if k in entry})
            cleaned.append(entry)
        works = cleaned

    edus = resume.get("education_list", [])
    if not edus:
        edus = [_empty_education_item()]
    else:
        cleaned = []
        for e in edus:
            entry = _empty_education_item()
            entry.update({k: v for k, v in e.items() if k in entry})
            cleaned.append(entry)
        edus = cleaned

    bi = dict(_empty_base_info())
    bi.update({k: v for k, v in (resume.get("base_info") or {}).items() if k in bi})

    ei = resume.get("expected_info") or _empty_expected_info()
    ci = resume.get("certificate_list") or resume.get("certificate_info") or []
    li = resume.get("language_list") or resume.get("language_info") or []
    si = resume.get("skills_list") or resume.get("skills_info") or []
    ti = resume.get("training_list") or resume.get("training_experiences") or []
    pi = resume.get("project_list") or []
    coi = resume.get("communication_list") or []

    return {
        "resume_languge": lang,
        "base_info": bi,
        "expected_info": ei,
        "work_experiences": works,
        "education_list": edus,
        "certificate_list": ci,
        "language_list": li,
        "skills_list": si,
        "training_list": ti,
        "project_list": pi,
        "communication_list": coi,
    }


def _build_structured_data(parsed: dict) -> dict:
    if not parsed:
        return {
            "base_info": _empty_base_info(),
            "expected_info": _empty_expected_info(),
            "current_info": _empty_current_info(),
            "education_info": _empty_education_info(),
            "certificate_list": [],
            "language_list": [],
            "skills_list": [],
            "training_list": [],
            "project_list": [],
            "communication_list": [],
            "resumes": []
        }
    return parsed


# ─── 文件名生成 ────────────────────────────────────────────────────────────────
# EN: ─── File name generation ───
# JA: ─── ファイル名の生成 ───

def _make_filename(full_name: str, record_id: str, source_filename: str, source_path: str = "") -> str:
    """(候选人姓名)__[12位哈希].json

    EN: (candidate name)__[12-char hash].json

    JA: (候補者名)__[12 文字のハッシュ].json
    """
    import hashlib, re
    hash12 = (record_id or "")[:12]
    if not hash12:
        hash12 = hashlib.md5(source_filename.encode()).hexdigest()[:12]

    exclude = {"简历", "推荐报告", "履書", "履歴書", "職務経歴書", "中文", "日文", "英文", "面试登记表", "看图王", "副本"}

    # 1. 优先使用已解析出的合法 full_name（无数字）
    # EN: 1. Prefer an already-parsed valid full_name (no digits)
    # JA: 1. 解析済みの有効な full_name（数字なし）を優先する
    if full_name and full_name.strip() and not any(char.isdigit() for char in full_name):
        name = full_name.strip()
    else:
        name = ""
        # 2. 尝试从源文件物理路径向上溯源找中文人名
        # EN: 2. Try tracing up the source file's physical path to find a Chinese personal name
        # JA: 2. ソースファイルの物理パスをさかのぼって中国語の人名を探す
        if source_path:
            p = Path(source_path)
            for parent in list(p.parents)[:3]:
                fn = parent.name.strip()
                clean_f = re.sub(r"^\d+[-_\s]*", "", fn).strip()
                if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", clean_f) and clean_f not in exclude:
                    name = clean_f
                    break

        # 3. 尝试从源文件名清洗提取
        # EN: 3. Try extracting it by cleaning the source file name
        # JA: 3. ソースファイル名をクレンジングして抽出を試みる
        if not name:
            stem = Path(source_filename).stem
            # 剥离开头的数字前缀
            # EN: Strip leading numeric prefixes
            # JA: 先頭の数字の接頭辞を除去する
            clean_s = re.sub(r"^\d+[-_\.\s]*", "", stem)
            clean_s = re.sub(r"\(.*?\)|（.*?）|简历|推荐报告|履書|履歴書|職務経歴書|中文|日文|英文|\d{4}\.\d{1,2}\.\d{1,2}|面试登记表|看图王|副本|_|-|CH\d+|JP\d+", "", clean_s, flags=re.IGNORECASE).strip("._-－—– ")
            m_cn = re.search(r"[\u4e00-\u9fff]{2,4}", clean_s)
            if m_cn and m_cn.group(0) not in exclude:
                name = m_cn.group(0)
            elif clean_s and clean_s not in exclude and len(clean_s) <= 10:
                name = clean_s

    # 剔除 Windows 非法文件名字符 \ / : * ? " < > |
    # EN: Remove characters illegal in Windows file names \ / : * ? " < > |
    # JA: Windows のファイル名に使えない文字 \ / : * ? " < > | を除去する
    name = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    name = name or "未知"
    return f"({name})__{hash12}.json"


# ─── 单文件处理 ───────────────────────────────────────────────────────────────
# EN: ─── Single-file processing ───
# JA: ─── 単一ファイルの処理 ───

def process_file(
    json_path: Path,
    output_dir: Path,
    parser: UniversalSchemaParser,
    extractor: ResumeTextExtractor,
    force: bool,
    verbose: bool,
) -> str:
    """
    处理单个 jsons/ 文件。
    返回: "ok" | "skipped" | "failed" | "not_resume"

    EN: Process a single jsons/ file.
    Returns: "ok" | "skipped" | "failed" | "not_resume"

    JA: jsons/ のファイルを 1 件処理する。
    戻り値："ok" | "skipped" | "failed" | "not_resume"
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except Exception as e:
        print(f"  [读取JSON失败] {e}" f" / [failed to read JSON] {e} / [JSON の読み込みに失敗] {e}")
        return "failed"

    raw_text = ""
    source = record.get("source") or {}
    source_path = source.get("path", "")
    source_filename = source.get("filename", json_path.name)
    record_id = record.get("record_id", "")

    # 优先强力直接从物理源文件重新提取无损文本
    # EN: Prefer re-extracting lossless text directly from the physical source file
    # JA: 物理的なソースファイルからロスのないテキストを直接再抽出することを優先する
    if source_path:
        p_src = Path(source_path)
        if p_src.exists():
            try:
                raw_text = extractor.extract(p_src)
            except Exception as e:
                if verbose:
                    print(f"  [物理源文件读取提示] {p_src}: {e}" f" / [physical source file read notice] {p_src}: {e} / [物理的な元ファイルの読み込みに関する注意] {p_src}：{e}")

    # 回退：如果物理源文件不可读，降级尝试 json_path 原有的 raw_text
    # EN: Fallback: if the physical source file is unreadable, fall back to the existing raw_text from json_path
    # JA: 代替：物理的なソースファイルが読めない場合は、json_path にある既存の raw_text に切り替える
    if not raw_text:
        raw_text = record.get("raw_text") or ""

    if not raw_text or not raw_text.strip():
        if verbose:
            print(f"  [跳过] 文本内容为空，源文件不可读" f" / [skipped] text content is empty, source file unreadable / [スキップ] テキストの内容が空で、元ファイルを読み取れません")
        return "not_resume"

    # 日期字段
    # EN: Date fields
    # JA: 日付フィールド
    dates = _resolve_dates(record.get("dates") or {})

    # 解析结构化字段
    # EN: Parse structured fields
    # JA: 構造化フィールドを解析する
    try:
        parsed = parser.parse(raw_text, source_filename, source_path)
    except Exception as e:
        print(f"  [解析失败] {e}" f" / [parse failed] {e} / [解析失敗] {e}")
        return "failed"

    structured = _build_structured_data(parsed)
    full_name = (structured.get("base_info") or {}).get("full_name", "")

    # 生成输出文件名
    # EN: Generate the output file name
    # JA: 出力ファイル名を生成する
    out_filename = _make_filename(full_name, record_id, source_filename, source_path)
    out_path = output_dir / out_filename

    if out_path.exists() and not force:
        if verbose:
            print(f"  [跳过] 已存在 → {out_filename}" f" / [skipped] already exists → {out_filename} / [スキップ] 既に存在します → {out_filename}")
        return "skipped"

    # 组装最终 JSON（严格对齐 demo 格式）
    # EN: Assemble the final JSON (strictly matching the demo format)
    # JA: 最終 JSON を組み立てる（demo の形式に厳密に合わせる）
    complete = {
        "source": {
            "path": source_path,
            "filename": source_filename,
            "extension": source.get("extension", Path(source_filename).suffix.lower()),
            "size": source.get("size", 0),
        },
        "dates": dates,
        "structured_data": structured,
    }

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(complete, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"  [写入] {out_filename}  姓名:{full_name}" f" / [written] {out_filename}  name:{full_name} / [書き込み] {out_filename}  氏名：{full_name}")
        return "ok"
    except Exception as e:
        print(f"  [写入失败] {e}" f" / [write failed] {e} / [書き込み失敗] {e}")
        return "failed"


# ─── 主流程 ───────────────────────────────────────────────────────────────────
# EN: ─── Main flow ───
# JA: ─── メインフロー ───

from resume_importer.extractors import ResumeTextExtractor

def build_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="单线程 jsons/ → complete-jsons/ 格式转换" " / Single-thread jsons/ → complete-jsons/ format conversion / シングルスレッドでの jsons/ → complete-jsons/ の形式変換")
    p.add_argument("--jsons",   type=Path, default=PROJECT_ROOT / "jsons",
                   help="jsons 输入目录" " / Input directory of jsons / jsons の入力ディレクトリ")
    p.add_argument("--output",  type=Path, default=PROJECT_ROOT / "complete-jsons",
                   help="complete-jsons 输出目录" " / Output directory for complete-jsons / complete-jsons の出力ディレクトリ")
    p.add_argument("--group",   type=str,  default="",
                   help="按类型组筛选，如 word (包含 .doc,.docx,.wps), pdf, excel, web, text 等" " / Filter by type group, e.g. word (includes .doc,.docx,.wps), pdf, excel, web, text / 種類のグループで絞り込む。例：word（.doc,.docx,.wps を含む）、pdf、excel、web、text など")
    p.add_argument("--ext",     type=str,  default="",
                   help="按具体扩展名筛选，如 .doc 或 .docx" " / Filter by concrete extension, e.g. .doc or .docx / 具体的な拡張子で絞り込む。例：.doc または .docx")
    p.add_argument("--limit",   type=int,  default=0,
                   help="只处理前 N 个文件（0=全部）" " / Process only the first N files (0 = all) / 先頭の N 個のファイルだけを処理する（0 は全件）")
    p.add_argument("--start",   type=int,  default=0,
                   help="从第 N 个文件开始（断点续跑，0=从头）" " / Start from the N-th file (resume from a breakpoint, 0 = from the beginning) / N 番目のファイルから始める（途中から再開、0 は最初から）")
    p.add_argument("--force",   action="store_true",
                   help="强制重新生成（覆盖已存在）" " / Force regeneration (overwrite existing) / 強制的に再生成する（既存のものを上書き）")
    p.add_argument("--verbose", action="store_true", default=True,
                   help="打印每个文件的详细信息" " / Print detailed information for each file / 各ファイルの詳細情報を出力する")
    return p


def main() -> int:
    args = build_args().parse_args()
    jsons_dir = args.jsons.resolve()
    output_dir = args.output.resolve()

    if not jsons_dir.exists():
        print(f"[错误] jsons 目录不存在：{jsons_dir}" f" / [error] jsons directory does not exist: {jsons_dir} / [エラー] jsons ディレクトリが存在しません：{jsons_dir}")
        return 1

    # 优先从 sqlite 数据库 _map.sqlite3 中的 file_map 表按顺序读取
    # EN: Prefer reading in order from the file_map table in the sqlite database _map.sqlite3
    # JA: sqlite データベース _map.sqlite3 の file_map テーブルから順に読むことを優先する
    db_path = jsons_dir / "_map.sqlite3"
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            query = "SELECT json_path FROM file_map WHERE 1=1"
            params = []
            if args.group:
                query += " AND reader_group = ?"
                params.append(args.group.lower().strip())
            query += " ORDER BY rowid ASC"
            
            c.execute(query, params)
            rows = c.fetchall()
            db_files = []
            for r in rows:
                p = Path(r[0])
                if p.exists():
                    db_files.append(p)
            if db_files:
                all_files = db_files
                print(f"[数据库表读取] 成功从 _map.sqlite3 的 file_map 数据表中按 '{args.group or '全量'}' 匹配到 {len(all_files)} 个记录。" f" / [database table read] matched {len(all_files)} records by '{args.group or '全量'}' in the file_map table of _map.sqlite3. / [データベース表の読み込み] _map.sqlite3 の file_map テーブルから、'{args.group or '全量'}' に一致するレコード {len(all_files)} 件を取得しました。")
        except Exception as e:
            print(f"[数据库提示] 读取 sqlite file_map 表失败，回退到磁盘扫描: {e}" f" / [database notice] failed to read the sqlite file_map table, falling back to disk scan: {e} / [データベースの注意] sqlite の file_map テーブルの読み込みに失敗したため、ディスク走査に切り替えます：{e}")

    # 兜底：如果未读数据库，按 --ext 参数过滤类型
    # EN: Fallback: if the database was not read, filter types by the --ext argument
    # JA: 代替：データベースを読まなかった場合は --ext 引数で種類を絞り込む
    if not db_path.exists() and target_exts:
        filtered = []
        for p in all_files:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                ext = (rec.get("source") or {}).get("extension", "").lower()
                if not ext.startswith("."):
                    ext = "." + ext
                if ext in target_exts:
                    filtered.append(p)
            except Exception:
                pass
        all_files = filtered
        print(f"[类型筛选] 组/扩展名筛选: {target_exts}，共匹配到 {len(all_files)} 个 JSON 记录。" f" / [type filter] group/extension filter: {target_exts}, {len(all_files)} JSON records matched. / [種類の絞り込み] グループ／拡張子の絞り込み：{target_exts}、JSON レコード {len(all_files)} 件に一致しました。")

    # 断点续跑与数量限制
    # EN: Resume from checkpoint and limit the count
    # JA: 中断箇所からの再開と件数の制限
    if args.start:
        all_files = all_files[args.start:]
    if args.limit:
        all_files = all_files[: args.limit]

    total = len(all_files)
    counters = {"ok": 0, "skipped": 0, "failed": 0, "not_resume": 0}

    print(f"[开始] 共 {total} 个文件  输出目录: {output_dir}" f" / [start] {total} files  output directory: {output_dir} / [開始] 全 {total} ファイル  出力ディレクトリ：{output_dir}")
    print(f"       force={args.force}  verbose={args.verbose}")
    print()

    parser = UniversalSchemaParser()
    extractor = ResumeTextExtractor()

    for i, json_path in enumerate(all_files, 1):
        print(f"[{i:>6}/{total}] {json_path.name}")
        status = process_file(json_path, output_dir, parser, extractor, args.force, args.verbose)
        counters[status] = counters.get(status, 0) + 1

    print()
    print("─" * 60)
    print(f"[完成]  总计:{total}" f" / [done]  total:{total} / [完了]  合計：{total}")
    print(f"  成功写入:   {counters['ok']}" f" / written successfully:   {counters['ok']} / 書き込み成功：   {counters['ok']}")
    print(f"  跳过已存在: {counters['skipped']}" f" / skipped, already exist: {counters['skipped']} / 既存のためスキップ：{counters['skipped']}")
    print(f"  非简历跳过: {counters['not_resume']}" f" / skipped, non-résumé:    {counters['not_resume']} / 履歴書でないためスキップ：{counters['not_resume']}")
    print(f"  失败:       {counters['failed']}" f" / failed:                 {counters['failed']} / 失敗：           {counters['failed']}")
    print(f"  输出目录:   {output_dir}" f" / output directory:       {output_dir} / 出力ディレクトリ：{output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
