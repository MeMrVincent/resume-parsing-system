"""猎聘网简历 HTML -> JSON 专用转换脚本。

复用 CodexGeminiHtmlSchemaParser + DocumentClassifier，
处理猎聘网简历 DOM 特征、平台标识修正、学校专业颠倒自动纠偏及多语言 0 号位 Copy 翻译重构。

EN: Dedicated conversion script for Liepin résumé HTML -> JSON.

Reuses CodexGeminiHtmlSchemaParser + DocumentClassifier,
handling Liepin résumé DOM features, platform label correction, automatic correction of swapped school/major, and the multilingual slot-0 copy-translation rebuild.

JA: Liepin の履歴書 HTML -> JSON 専用の変換スクリプト。

CodexGeminiHtmlSchemaParser + DocumentClassifier を再利用し、
Liepin の履歴書の DOM の特徴、プラットフォーム表示の補正、学校と専攻の取り違えの自動補正、多言語の 0 番目へのコピー翻訳による再構築を処理する。
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from resume_importer.codex_gemini_html_schema_parser import CodexGeminiHtmlSchemaParser
from resume_importer.classifier import DocumentClassifier

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

TZ_JST = timezone(timedelta(hours=9))

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="猎聘网 HTML -> JSON 转换" " / Liepin HTML -> JSON conversion / 猎聘の HTML -> JSON 変換")
    p.add_argument(
        "--html-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "猎聘网简历",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "猎聘网简历",
    )
    p.add_argument("--limit", type=int, default=0, help="0=全部" " / 0 = all / 0 は全件")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=20)
    return p.parse_args()


def read_html_text(html_path: Path) -> str:
    """自动检测并用最佳编码读取 HTML 文本

    EN: Automatically detect and read HTML text with the best encoding

    JA: 最適なエンコーディングを自動検出して HTML のテキストを読む
    """
    raw_bytes = html_path.read_bytes()
    for enc in ("gb18030", "gbk", "utf-8"):
        try:
            t = raw_bytes.decode(enc)
            if "个人信息" in t or "简历编号" in t or "姓名" in t:
                return t
        except Exception:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def plain_text(html_text: str) -> str:
    """提取纯文本并清理控制字符与多余空格

    EN: Extract plain text and clean control characters and extra spaces

    JA: プレーンテキストを抽出し、制御文字と余分な空白を除く
    """
    if not html_text:
        return ""
    if BeautifulSoup is None:
        raw = re.sub(r"<[^>]+>", "\n", html_text)
    else:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "xml", "meta", "link"]):
            tag.decompose()
        for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "tr", "br"]):
            p.append("\n")
        raw = soup.get_text("\n")

    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)


def html_record_id(html_path: Path) -> str:
    stat = html_path.stat()
    value = f"{html_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def normalize_degree_rank(deg: str) -> tuple[str, str]:
    """归一化学历名称到 rank + education_type。支持中文+日文+英文学历名。

    EN: Normalise degree names to rank + education_type. Supports Chinese + Japanese + English degree names.

    JA: 学歴名を rank + education_type に正規化する。中国語・日本語・英語の学歴名に対応する。
    """
    degree_rank = {
        "博士后": "7", "博士": "6", "phd": "6", "doctor": "6",
        "硕士": "5", "修士": "5", "研究生": "5", "mba": "5", "emba": "5", "master": "5", "ma": "5", "ms": "5",
        "大学院": "5",
        "本科": "4", "学士": "4", "大卒": "4", "bachelor": "4", "bs": "4", "ba": "4",
        "大专": "3", "专科": "3", "短大": "3", "大専": "3", "associate": "3", "diploma": "3",
        "高中": "2", "中专": "2", "职高": "2", "中学": "2", "high school": "2",
        "中級専門学校": "2", "専門学校": "2",
        "初中": "1", "小学": "1",
    }
    etype_map = {
        "7": "全日制研究生", "6": "全日制研究生", "5": "全日制研究生",
        "4": "全日制大学", "3": "全日制大专", "2": "全日制高中", "1": "全日制初中及以下",
    }
    deg_clean = re.sub(r"[（(].*?[)）]", "", deg or "").strip().lower()
    rank = degree_rank.get(deg_clean, "")
    if not rank:
        for key, val in degree_rank.items():
            if key in deg_clean:
                rank = val
                break
    etype = etype_map.get(rank, "")
    return rank, etype


def standardize_datetime(raw: str) -> str:
    """将各种乱序/年月格式日期统一洗净标准化为 YYYY-MM-DD HH:MM:SS 规范格式。

    EN: Clean and normalise dates in all kinds of jumbled/year-month formats to the standard YYYY-MM-DD HH:MM:SS format.

    JA: さまざまな順序・年月形式の日付を、標準の YYYY-MM-DD HH:MM:SS 形式に統一して正規化する。
    """
    raw = raw.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = raw.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"

    d_parts = date_part.split("-")
    if len(d_parts) >= 3:
        y, m, d = d_parts[0], d_parts[1], d_parts[2]
        date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    else:
        date_str = date_part

    t_parts = time_part.split(":")
    if len(t_parts) == 2:
        time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:00"
    elif len(t_parts) == 3:
        time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:{int(t_parts[2]):02d}"
    else:
        time_str = "00:00:00"

    return f"{date_str} {time_str}"


def parse_resume_dates(text: str, fallback_date: str) -> tuple[str, str, str, str]:
    """通用精准提取 resume_updated_date 与 resume_download_date 及其权威来源说明。

    EN: General precise extraction of resume_updated_date and resume_download_date and the description of their authoritative source.

    JA: resume_updated_date と resume_download_date、およびその根拠となる取得元の説明を汎用的に正確に抽出する。
    """
    m_up = re.search(r"(?:简历)?更新[日时]?[期间]?[：\s]*((?:19|20)\d{2}[./年-]\d{1,2}[./年-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)", text, re.I)
    if not m_up:
        m_up = re.search(r"((?:19|20)\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", text[:500])

    if m_up:
        raw_up = m_up.group(1).strip()
        updated_date = standardize_datetime(raw_up)
        updated_source = "文档正文更新时间"
    else:
        updated_date = fallback_date
        updated_source = "HTML文件修改时间（历史资料替代）"

    m_dl = re.search(r"(?:简历)?(?:下载|投递)[日时]?[期间]?[：\s]*((?:19|20)\d{2}[./年-]\d{1,2}[./年-]\d{1,2}(?:\s+\d{1,2}:\d{1,2}(?::\d{1,2})?)?)", text, re.I)
    if m_dl:
        raw_dl = m_dl.group(1).strip()
        download_date = standardize_datetime(raw_dl)
        download_source = "文档正文下载/投递时间"
    else:
        download_date = fallback_date
        download_source = "HTML文件修改时间（历史资料替代）"

    return updated_date, download_date, updated_source, download_source


def normalize_education_list(edu_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对教育经历列表进行后处理：重新校准 rank + school_education_type。

    EN: Post-process the education list: recalibrate rank + school_education_type.

    JA: 学歴の一覧を後処理する：rank と school_education_type を補正し直す。
    """
    for edu in edu_list:
        deg = edu.get("school_degree_type", "")
        rank, etype = normalize_degree_rank(deg)
        if rank:
            edu["school_degree_rank"] = rank
            if not edu.get("school_education_type") or edu.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                edu["school_education_type"] = etype
    return edu_list


def _format_ym(s: str) -> str:
    m = re.search(r"((?:19|20)\d{2})[./年-]?(\d{1,2})?", s)
    if m:
        y = m.group(1)
        m_str = m.group(2) or "01"
        return f"{y}年{int(m_str):02d}月01日"
    return ""


def parse_education_from_raw_text(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """从纯文本 raw_text 中按通用模式精准解析教育经历列表与提纯培训经历列表。

    EN: Precisely parse the education list and refine the training list from the plain text raw_text using generic patterns.

    JA: プレーンテキストの raw_text から汎用パターンで学歴の一覧を正確に解析し、研修歴の一覧を精製する。
    """
    if not text:
        return [], []

    m_sec = re.search(
        r"(?:教育经历|教育背景|学歴|Learning\s+Experience|Education)\s*\n(.*?)(?=\n\s*(?:语言能力|语言|技能|工作经历|工作经验|项目经历|项目经验|自我评价|培训经历|证书|Qualifications|Work\s+Experience|Projects|Skills|\Z))",
        text,
        re.S | re.I,
    )
    if not m_sec:
        return [], []

    block = m_sec.group(1).strip()
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    training_keywords = ("咨询", "顾问", "认证", "培训", "企业管理", "管理咨询", "有限公司", "有限责任公司", "事务所", "机构", "中心")
    cert_keywords = ("iso", "内审员", "品管圈", "五大工具", "apqp", "ppap", "spc", "msa", "fmea", "证书", "资格", "培训", "沟通", "审员")

    edus = []
    trainings = []
    # 通用日期范围正则：支持连字符 -、EN DASH –、EM DASH —、波浪号 ~ 及 "至、到"
    # EN: Generic date-range regex: supports hyphen -, EN DASH –, EM DASH —, tilde ~ and "至、到" (to)
    # JA: 汎用的な期間の正規表現：ハイフン -、EN DASH –、EM DASH —、波線 ~、「至、到」に対応する
    DATE_RANGE_RE = r"^(?:[（(]\s*)?((?:19|20)\d{2}[./年\-]\d{1,2}\s*[\-\u2010-\u2015~～至到‒―〜]{1,4}\s*(?:(?:19|20)\d{2}[./年\-]\d{1,2}|至今|现在|Present))(?:[,\s，].*?)?(?:[）)]\s*)?$"
    DATE_START_RE = r"^(?:[（(]\s*)?(?:19|20)\d{2}[./年\-]"
    DATE_SPLIT_RE = r"[\-\u2010-\u2015~～至到‒―〜]{1,4}"
    DEGREE_VALUES = ("博士后", "博士", "硕士", "本科", "大专", "专科", "高中", "中专", "职高", "初中", "小学", "修士", "大卒", "専門", "短大")

    i = 0
    while i < len(lines):
        line = lines[i]
        date_m_current = re.search(DATE_RANGE_RE, line)
        date_m_next = None
        if i + 1 < len(lines):
            date_m_next = re.search(DATE_RANGE_RE, lines[i + 1])

        if date_m_next and not date_m_current:
            school_cand = line.strip("（）()| ")
            time_str = date_m_next.group(1).strip()
            j_start = i + 2
        elif date_m_current and i + 1 < len(lines):
            time_str = date_m_current.group(1).strip()
            school_cand = lines[i + 1].strip("（）()| ")
            j_start = i + 2
        else:
            i += 1
            continue

        school_name = re.sub(r"^[,\s，\d年月)\(（）.]+", "", school_cand)
        school_name = re.sub(r"[,\s，\d年月)\(（）.]+$", "", school_name).strip()

        t_parts = re.split(r"\s*" + DATE_SPLIT_RE + r"\s*", time_str)
        start_ym = _format_ym(t_parts[0]) if len(t_parts) > 0 else ""
        end_ym = _format_ym(t_parts[1]) if len(t_parts) > 1 and "今" not in t_parts[1] and "现" not in t_parts[1] and "Present" not in t_parts[1] else ""

        major = ""
        degree = ""
        edu_type = ""

        j = j_start
        while j < len(lines):
            cur = lines[j]
            if cur == "|":
                j += 1
                continue
            # 专业： 或 专业: 格式
            # EN: 专业： or 专业: format (major:)
            # JA: 专业： または 专业: の形式（専攻：）
            if cur.startswith("专业：") or cur.startswith("专业:"):
                major = (cur.split("：", 1)[-1] if "：" in cur else cur.split(":", 1)[-1]).strip("（）()| ")
                j += 1
                continue
            # 学历： 或 学历: 格式
            # EN: 学历： or 学历: format (degree:)
            # JA: 学历： または 学历: の形式（学歴：）
            if cur.startswith("学历：") or cur.startswith("学历:"):
                degree = (cur.split("：", 1)[-1] if "：" in cur else cur.split(":", 1)[-1]).strip("（）()| ")
                j += 1
                continue
            if cur.startswith("是否统招：") or cur.startswith("是否统招:"):
                val = (cur.split("：", 1)[-1] if "：" in cur else cur.split(":", 1)[-1]).strip()
                edu_type = "全日制大学" if "是" in val else "非全日制大学"
                j += 1
                continue

            # 猎聘特殊格式：专业（学历） 如 "市场流通（硕士）"
            # EN: Liepin special format: major (degree), e.g. "市场流通（硕士）"
            # JA: Liepin の特殊な形式：専攻（学歴）、例："市场流通（硕士）"
            m_maj_deg = re.match(r"^(.+?)[（(]\s*(博士后|博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学|修士|大卒|専門|短大)\s*[）)]\s*$", cur)
            if m_maj_deg and not major:
                major = m_maj_deg.group(1).strip("（）()| ")
                degree = m_maj_deg.group(2).strip()
                j += 1
                continue

            # 单独一行就是学历名称（猎聘格式）
            # EN: A line containing only the degree name (Liepin format)
            # JA: 学歴名だけの行（Liepin の形式）
            if cur in DEGREE_VALUES:
                degree = cur
                j += 1
                # 学历之后通常就没有更多内容了
                # EN: There is usually no more content after the degree
                # JA: 学歴の後には通常それ以上の内容はない
                if j + 1 >= len(lines) or re.search(DATE_START_RE, lines[j]) or lines[j] in ("工作经历", "项目经历", "自我评价", "语言能力"):
                    break
                continue

            if (j + 1 < len(lines) and re.search(DATE_START_RE, lines[j + 1])) or cur.startswith("|") or cur in ("工作经历", "项目经历", "自我评价", "语言能力"):
                break
            # 如果当前行还没有 major，且不像学校名开头的新条目，可能是专业名
            # EN: If the current line has no major yet and does not look like a new entry starting with a school name, it may be the major name
            # JA: 現在の行にまだ major がなく、学校名で始まる新しい項目にも見えなければ、専攻名かもしれない
            if not major and not re.search(DATE_START_RE, cur):
                major = cur.strip("（）()| ")
            j += 1

        is_training = any(k in school_name for k in training_keywords) or any(k in major.lower() for k in cert_keywords)
        if is_training and school_name:
            trainings.append({
                "sequence_no": len(trainings) + 1,
                "organization_name": school_name,
                "training_name": major or school_name,
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": major if any(k in major.lower() for k in ("证书", "资格", "内审员", "证")) else "",
                "description": major,
            })
        elif school_name:
            rank, etype = normalize_degree_rank(degree)
            edus.append({
                "school_name": school_name,
                "school_major_name": major,
                "school_degree_type": degree or "本科",
                "school_degree_rank": rank or "4",
                "school_education_type": etype or edu_type,
                "school_start_ym": start_ym,
                "school_end_ym": end_ym,
            })

        i = j
        continue
    i += 1

    return edus, trainings


def parse_work_from_raw_text(text: str) -> list[dict[str, Any]]:
    """从纯文本 raw_text 中按通用模式精准解析工作经历列表。

    EN: Precisely parse the work-history list from the plain text raw_text using generic patterns.

    JA: プレーンテキストの raw_text から汎用パターンで職歴の一覧を正確に解析する。
    """
    if not text:
        return []

    m_sec = re.search(
        r"(?:\|?\s*工作经历|Work\s+Experience)\s*\n(.*?)(?=\n\s*(?:\|?\s*教育经历|\|?\s*教育背景|\|?\s*项目经历|\|?\s*语言能力|\|?\s*自我评价|Education|\Z))",
        text,
        re.S | re.I,
    )
    if not m_sec:
        return []

    block = m_sec.group(1).strip()
    lines = [l.strip() for l in block.splitlines() if l.strip()]

    attr_keywords = (
        "公司性质", "公司规模", "公司行业", "公司描述", "所在地区", "所在部门", "汇报对象",
        "工作地点", "下属人数", "薪酬情况", "薪酬", "月薪", "所在地", "国内上市公司",
        "私营·民营企业", "中外合营", "外商独资", "民营", "外企", "500-999人", "100-499人", "1-49人", "50-99人",
        "1000-9999人", "10000人以上", "20-99人", "50-150人", "未填写"
    )

    invalid_comp_keywords = (
        "策划", "跟进", "维护", "组织", "实施", "建设", "运营", "负责", "管理", "企划", "项目",
        "预算", "设计", "制作", "发放", "招募", "大赛", "选址", "宣传", "开发", "协调", "沟通",
        "制定", "战略", "信息", "对手", "增加", "完成", "建立", "拓展", "收集", "提供", "搜集",
        "配合", "协助", "积极", "通过", "促进", "进行", "建立", "提高", "改善"
    )
    # 通用日期正则（支持 EN/EM DASH 等 Unicode 分隔符）
    # EN: Generic date regex (supports Unicode separators such as EN/EM DASH)
    # JA: 汎用的な日付の正規表現（EN/EM DASH などの Unicode の区切りに対応）
    DATE_RANGE_RE = r"^(?:[（(]\s*)?((?:19|20)\d{2}[./年\-]\d{1,2}\s*[\-\u2010-\u2015~～至到‒―〜]{1,4}\s*(?:(?:19|20)\d{2}[./年\-]\d{1,2}|至今|现在|Present))(?:[,\s，].*?)?(?:[）)]\s*)?$"
    DATE_RANGE_PREFIX_RE = r"^(?:[（(]\s*)?((?:19|20)\d{2}[./年\-]\d{1,2}\s*[\-\u2010-\u2015~～至到‒―〜]{1,4}\s*(?:(?:19|20)\d{2}[./年\-]\d{1,2}|至今|现在|Present))"
    DATE_SPLIT_RE = r"[\-\u2010-\u2015~～至到‒―〜]{1,4}"
    DATE_START_RE = r"^(?:[（(]\s*)?(?:19|20)\d{2}[./年\-]"

    works = []
    i = 0
    last_time_str = ""
    while i < len(lines):
        line = lines[i]
        date_m_current = re.search(DATE_RANGE_RE, line)
        date_m_next = None
        if i + 1 < len(lines):
            date_m_next = re.search(DATE_RANGE_RE, lines[i + 1])

        prev_cand_valid = False
        if date_m_next and not date_m_current:
            cand = line.strip("（）()| ")
            has_comp_suffix = any(k in cand for k in ("公司", "厂", "集团", "中心", "单位", "局", "院", "行", "店", "社", "所"))
            if not any(k in cand for k in invalid_comp_keywords) and not cand.startswith("工作业绩") and not cand.startswith("工作职责") and not re.search(r"^\d+[.、]", cand):
                if len(cand) <= 25 or has_comp_suffix:
                    prev_cand_valid = True

        if date_m_next and prev_cand_valid:
            comp_cand = line.strip("（）()| ")
            time_str = date_m_next.group(1).strip()
            j_start = i + 2
        elif date_m_current and i + 1 < len(lines):
            time_str = date_m_current.group(1).strip()
            comp_cand = lines[i + 1].strip("（）()| ")
            j_start = i + 2
        else:
            i += 1
            continue

        # 核心滤重：判定 time_str 是否与上一段起止时间相同
        # EN: Core dedup: decide whether time_str has the same start/end as the previous entry
        # JA: 重複排除の中核：time_str が前の項目と同じ期間かを判定する
        clean_time = re.sub(r"\s+", "", time_str)
        if clean_time == last_time_str:
            i += 1
            continue

        comp_cand = re.sub(r"^[,\s，\d年月)\(（）.]+", "", comp_cand)
        comp_cand = re.sub(r"[,\s，\d年月)\(（）.]+$", "", comp_cand).strip()

        if any(k in comp_cand for k in ("%", "率", "过程控制", "降本增效", "推进", "现场管理", "安全生产")) or len(comp_cand) > 35:
            i += 1
            continue

        if any(k in comp_cand for k in ("大学", "学院", "分校", "学园")) and not any(k in comp_cand for k in ("公司", "厂", "集团", "中心", "有限")):
            i = j_start
            continue

        t_parts = re.split(r"\s*" + DATE_SPLIT_RE + r"\s*", time_str)
        start_ym = _format_ym(t_parts[0]) if len(t_parts) > 0 else ""
        end_ym = _format_ym(t_parts[1]) if len(t_parts) > 1 and "今" not in t_parts[1] and "现" not in t_parts[1] and "Present" not in t_parts[1] else ""
        status = "在职" if ("今" in time_str or "现" in time_str or "Present" in time_str) else "离职"

        pos = ""
        subordinate = ""
        comp_employees = ""
        comp_industry = ""
        pos_dept = ""
        pos_report_to = ""
        resp_lines = []

        j = j_start
        while j < len(lines):
            cur = lines[j]
            if cur == "|":
                j += 1
                continue

            if cur.startswith("公司规模：") or cur.startswith("公司规模:"):
                val = cur.split("：", 1)[-1].strip() if "：" in cur else cur.split(":", 1)[-1].strip()
                if not val and j + 1 < len(lines) and lines[j + 1] != "|":
                    val = lines[j + 1].strip()
                    j += 1
                comp_employees = val.strip("（）()| ")
                j += 1
                continue

            if cur.startswith("公司行业：") or cur.startswith("公司行业:"):
                val = cur.split("：", 1)[-1].strip() if "：" in cur else cur.split(":", 1)[-1].strip()
                if not val and j + 1 < len(lines) and lines[j + 1] != "|":
                    val = lines[j + 1].strip()
                    j += 1
                comp_industry = val.strip("（）()| ")
                j += 1
                continue

            if cur.startswith("公司性质：") or cur.startswith("公司性质:") or cur.startswith("公司描述：") or cur.startswith("公司描述:"):
                if (cur in ("公司性质：", "公司性质:", "公司描述：", "公司描述:")) and j + 1 < len(lines) and lines[j + 1] != "|":
                    j += 1
                j += 1
                continue

            if cur.startswith("所在部门：") or cur.startswith("所在部门:"):
                val = cur.split("：", 1)[-1].strip() if "：" in cur else cur.split(":", 1)[-1].strip()
                if not val and j + 1 < len(lines) and lines[j + 1] != "|":
                    val = lines[j + 1].strip()
                    j += 1
                pos_dept = val.strip("（）()| ")
                j += 1
                continue

            if cur.startswith("汇报对象：") or cur.startswith("汇报对象:"):
                val = cur.split("：", 1)[-1].strip() if "：" in cur else cur.split(":", 1)[-1].strip()
                if not val and j + 1 < len(lines) and lines[j + 1] != "|":
                    val = lines[j + 1].strip()
                    j += 1
                pos_report_to = val.strip("（）()| ")
                j += 1
                continue

            if not pos and not any(cur.startswith(k) for k in ("所在", "汇报对象", "下属人数", "职责业绩", "薪酬", "月薪", "工作职责", "工作内容")):
                cand_pos = cur.strip("（）()| ")
                if len(cand_pos) <= 35 and not any(k in cand_pos for k in ("简介", "创立", "业务", "涵盖", "主要客户", "主营业务", "有限公司", "株式会社")):
                    pos = cand_pos
                    j += 1
                    continue

            m_sub = re.search(r"下属人数[：:]\s*(\d+人?)", cur)
            if m_sub:
                subordinate = m_sub.group(1).strip()
                j += 1
                continue

            if cur.startswith("职责业绩：") or cur.startswith("工作内容：") or cur.startswith("工作职责：") or cur.startswith("工作职责和业绩："):
                val = cur.split("：", 1)[-1].strip()
                if val:
                    resp_lines.append(val)
                j += 1
                continue

            # 下一段工作切割判定：当遇到全新时间串时 break
            # EN: Next-job split decision: break when a brand-new time string is met
            # JA: 次の職歴の区切りの判定：まったく新しい日時の文字列が現れたら break する
            m_next_date = re.search(DATE_RANGE_PREFIX_RE, cur)
            if m_next_date:
                nd_clean = re.sub(r"\s+", "", m_next_date.group(1))
                if nd_clean != clean_time:
                    break

            if cur.startswith("|") or cur in ("教育经历", "项目经历", "自我评价", "语言能力", "职业期望"):
                break

            if not any(cur.startswith(k) for k in ("所在地区", "所在部门", "汇报对象", "工作地点", "月薪", "月    薪")):
                resp_lines.append(cur)
            j += 1

        clean_resp = []
        for l_item in resp_lines:
            l_str = l_item.strip()
            if (
                any(l_str.startswith(k) or k in l_str for k in attr_keywords)
                or l_str in ("|", "0", "0人", "未填写", "上海", "北京", "广州", "深圳", "月薪", "月    薪", "月    薪：", "月薪：", "工作业绩：", "工作职责和业绩：", "工作职责：")
                or re.search(r"^\d+(?:-\d+)?人?$", l_str)
                or re.search(r"^(?:工作地点|所在地区|所在部门|汇报对象|月薪|薪酬)[：:]?", l_str)
                or re.search(DATE_RANGE_PREFIX_RE, l_str)
                or "简介：" in l_str
                or "简介:" in l_str
            ):
                continue
            clean_resp.append(l_str)

        if comp_cand in ("未填写", "未公开") or comp_cand.startswith("汇报对象") or comp_cand.startswith("下属人数"):
            if works:
                last_w = works[-1]
                if comp_employees:
                    last_w["company_employees"] = comp_employees
                if comp_industry:
                    last_w["company_industry"] = comp_industry
                if pos_dept:
                    last_w["position_dept"] = pos_dept
                if pos_report_to:
                    last_w["position_report_to"] = pos_report_to
                if subordinate:
                    last_w["position_subordinate"] = subordinate
                if clean_resp:
                    last_w["position_responsibilities"] = "\n".join(clean_resp).strip()
                i = j
                continue

        if comp_cand:
            works.append({
                "company_name": comp_cand,
                "company_employees": comp_employees,
                "company_industry": comp_industry,
                "position": pos,
                "position_type": "",
                "position_salary": "",
                "position_dept": pos_dept,
                "position_report_to": pos_report_to,
                "position_subordinate": subordinate,
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": status,
                "position_start": start_ym,
                "position_resigned": end_ym,
                "resigned_reason": "",
                "position_responsibilities": "\n".join(clean_resp).strip(),
                "position_achievements": "",
            })
            last_time_str = clean_time
        i = j
        continue
    i += 1

    return works


def parse_liepin_html_work_experiences(soup: Any) -> list[dict[str, Any]]:
    """针对猎聘网 HTML 结构的表格 DOM 精准解析工作经历，全面支持一企多岗/多工作段落嵌套

    EN: Precise table-DOM parsing of work history for Liepin's HTML structure, fully supporting one company with several posts / nested multiple work sections

    JA: Liepin の HTML 構造向けに表の DOM から職歴を正確に解析する。1 社で複数の職位・複数の職歴段落の入れ子に完全対応
    """
    if soup is None:
        return []

    work_table_header = None
    for tbl in soup.find_all("table"):
        if "工作经历" in tbl.get_text():
            work_table_header = tbl
            break

    if not work_table_header:
        return []

    works = []
    curr_tbl = work_table_header.find_next_sibling("table")
    while curr_tbl:
        txt = curr_tbl.get_text()
        if any(stop in txt for stop in ["项目经历", "教育经历", "语言能力", "自我评价", "附加信息"]):
            break

        rows = curr_tbl.find_all("tr")
        if not rows:
            curr_tbl = curr_tbl.find_next_sibling("table")
            continue

        r0 = rows[0]
        tds0 = r0.find_all("td")
        if len(tds0) >= 2:
            time_txt0 = tds0[0].get_text(strip=True)
            comp_name0 = tds0[1].get_text(strip=True)

            m_comp_time = re.search(
                r"((?:19|20)\d{2}[\.\/年-]\d{1,2})\s*[-—–~∼～\-./~〜ー]{1,5}\s*((?:19|20)\d{2}[\.\/年-]\d{1,2}|至今|现在|Present)",
                time_txt0,
            )
            if m_comp_time and comp_name0 and not any(stop in comp_name0 for stop in ["项目经历", "教育经历"]):
                comp_employees = ""
                comp_industry = ""

                if len(rows) > 1:
                    r1_txt = rows[1].get_text(strip=True)
                    m_emp = re.search(r"公司规模[：:]\s*([^|\n\r]+)", r1_txt)
                    if m_emp:
                        comp_employees = m_emp.group(1).strip()
                    m_ind = re.search(r"公司行业[：:]\s*([^|\n\r]+)", r1_txt)
                    if m_ind:
                        ind_val = m_ind.group(1).strip()
                        ind_val = re.sub(r"公司描述[：:].*", "", ind_val).strip()
                        comp_industry = ind_val

                pos_blocks = []
                curr_pos = None

                for r in rows[1:]:
                    tds = r.find_all("td")
                    r_txt = r.get_text(strip=True)

                    if len(tds) >= 2:
                        pos_cand = tds[0].get_text(strip=True)
                        date_cand = tds[1].get_text(strip=True)
                        m_pos_time = re.search(
                            r"((?:19|20)\d{2}[\.\/年-]\d{1,2})\s*[-—–~∼～\-./~〜ー]{1,5}\s*((?:19|20)\d{2}[\.\/年-]\d{1,2}|至今|现在|Present)",
                            date_cand,
                        )
                        if m_pos_time and pos_cand and not any(k in pos_cand for k in ["公司规模", "公司行业", "公司性质", "工作职责", "工作业绩"]):
                            if curr_pos:
                                pos_blocks.append(curr_pos)

                            start_p = _format_ym(m_pos_time.group(1))
                            end_raw = m_pos_time.group(2)
                            is_curr = end_raw in ("至今", "现在", "Present")
                            end_p = "" if is_curr else _format_ym(end_raw)

                            curr_pos = {
                                "company_name": comp_name0,
                                "company_employees": comp_employees,
                                "company_industry": comp_industry,
                                "position": pos_cand,
                                "position_type": "",
                                "position_salary": "",
                                "position_dept": "",
                                "position_report_to": "",
                                "position_subordinate": "",
                                "employment_type": "全职",
                                "annual_salary_min": "",
                                "annual_salary_max": "",
                                "status": "在职" if is_curr else "离职",
                                "position_start": start_p,
                                "position_resigned": end_p,
                                "resigned_reason": "",
                                "position_responsibilities": "",
                                "position_achievements": "",
                            }
                            continue

                    if curr_pos:
                        if "所在部门" in r_txt:
                            m_dept = re.search(r"所在部门[：:]\s*([^|\n\r]+)", r_txt)
                            if m_dept:
                                curr_pos["position_dept"] = m_dept.group(1).strip()
                        if "下属人数" in r_txt:
                            m_sub = re.search(r"下属人数[：:]\s*([^|\n\r]+)", r_txt)
                            if m_sub:
                                curr_pos["position_subordinate"] = m_sub.group(1).strip()
                        if "工作职责" in r_txt:
                            for td in tds:
                                t_content = td.get_text("\n").strip()
                                if "工作职责" not in t_content:
                                    resp = "\n".join([line.strip() for line in t_content.splitlines() if line.strip()])
                                    curr_pos["position_responsibilities"] = resp

                if curr_pos:
                    pos_blocks.append(curr_pos)

                if pos_blocks:
                    works.extend(pos_blocks)
                else:
                    start_p = _format_ym(m_comp_time.group(1))
                    end_raw = m_comp_time.group(2)
                    is_curr = end_raw in ("至今", "现在", "Present")
                    end_p = "" if is_curr else _format_ym(end_raw)

                    pos_single = ""
                    resp_single = ""
                    for r in rows[1:]:
                        r_txt = r.get_text(strip=True)
                        tds = r.find_all("td")
                        if len(tds) == 1 and not pos_single and not any(k in r_txt for k in ["公司规模", "公司行业", "公司性质", "工作职责", "工作业绩", "所在部门"]):
                            pos_single = r_txt
                        if "工作职责" in r_txt:
                            for td in tds:
                                t_content = td.get_text("\n").strip()
                                if "工作职责" not in t_content:
                                    resp_single = "\n".join([line.strip() for line in t_content.splitlines() if line.strip()])

                    works.append({
                        "company_name": comp_name0,
                        "company_employees": comp_employees,
                        "company_industry": comp_industry,
                        "position": pos_single,
                        "position_type": "",
                        "position_salary": "",
                        "position_dept": "",
                        "position_report_to": "",
                        "position_subordinate": "",
                        "employment_type": "全职",
                        "annual_salary_min": "",
                        "annual_salary_max": "",
                        "status": "在职" if is_curr else "离职",
                        "position_start": start_p,
                        "position_resigned": end_p,
                        "resigned_reason": "",
                        "position_responsibilities": resp_single,
                        "position_achievements": "",
                    })

        curr_tbl = curr_tbl.find_next_sibling("table")

    return works


def _fix_liepin_education_school_major(edu_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """纠正猎聘网简历中误将专业识别为学校、学校识别为专业的问题，并拆分粘连专业。

    EN: Correct the problem in Liepin résumés where the major is recognised as the school and the school as the major, and split stuck majors.

    JA: Liepin の履歴書で専攻が学校、学校が専攻と誤認される問題を補正し、くっついた専攻を分ける。
    """
    major_keywords = {"专业", "文学", "工程", "管理", "科学", "艺术", "技术", "系", "方向", "学"}
    school_keywords = {"大学", "学院", "学校", "分校", "大学院", "短大", "专科学校", "University", "College", "School", "Institute"}

    for edu in edu_list:
        sch = str(edu.get("school_name") or "").strip()
        maj = str(edu.get("school_major_name") or "").strip()

        # 清理异常收尾字符如 ")" 或 "(" 或空专业
        # EN: Clean abnormal trailing characters like ")" or "(" or an empty major
        # JA: 「)」や「(」などの異常な末尾の文字や空の専攻を除去する
        if maj in (")", "(", "）", "（", "语言能力", "专业", "未填写"):
            edu["school_major_name"] = ""
            maj = ""

        if not sch:
            continue

        # 拆分粘连在学校名后面的专业，如 "山东交通学院  计算机科学与技术·本科·统招"
        # EN: Split a major stuck after the school name, e.g. "山东交通学院  计算机科学与技术·本科·统招"
        # JA: 学校名の後にくっついた専攻を分ける。例："山东交通学院  计算机科学与技术·本科·统招"
        m_split = re.search(r"^([^\s·│]+(?:大学|学院|学校|分校))\s+([^·│\n\r]+)", sch)
        if m_split:
            sch = m_split.group(1).strip()
            maj_cand = m_split.group(2).strip()
            edu["school_name"] = sch
            if not maj or maj in (")", "(", "）", "（", "语言能力", "专业", "未填写"):
                maj = maj_cand
                edu["school_major_name"] = maj

        sch_is_major = any(k in sch for k in major_keywords) and not any(k in sch for k in school_keywords)
        maj_is_school = any(k in maj for k in school_keywords)

        if sch_is_major and maj_is_school:
            edu["school_name"] = maj
            edu["school_major_name"] = sch

    return edu_list


def _detect_resume_language(text: str) -> str:
    """检测简历文本的主要语言：zh / jp / en

    EN: Detect the main language of the résumé text: zh / jp / en

    JA: 履歴書テキストの主な言語を検出する：zh / jp / en
    """
    kana_count = len(re.findall(r"[\u3040-\u30ff]", text))
    if kana_count >= 5:
        return "jp"

    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_words = len(re.findall(r"\b[A-Za-z]{2,}\b", text))

    if en_words > 50 and zh_chars < 25:
        return "en"

    has_en_header = bool(re.search(r"\b(?:Work Experience|Education|Personal Information|Learning Experience|Project Experience)\b", text, re.I))
    if has_en_header and en_words > zh_chars:
        return "en"

    if zh_chars >= 10:
        return "zh"

    return "en" if en_words > zh_chars else "zh"


def _translate_resume_to_chinese(resume: dict[str, Any]) -> None:
    """将从外文简历深拷贝得到的 resumes[0] 对象的文本与枚举字段翻译转换归一化为中文。

    EN: Translate and normalise into Chinese the text and enum fields of the resumes[0] object deep-copied from a foreign-language résumé.

    JA: 外国語の履歴書からディープコピーした resumes[0] オブジェクトのテキストと列挙値のフィールドを、中国語に翻訳・正規化する。
    """
    base = resume.get("base_info") or {}
    if base:
        g = base.get("gender", "")
        if g.lower() in ("male", "man", "m"):
            base["gender"] = "男"
        elif g.lower() in ("female", "woman", "f"):
            base["gender"] = "女"

        m = base.get("marital_status", "")
        m_map = {"married": "已婚", "single": "未婚", "divorced": "离异"}
        if m.lower() in m_map:
            base["marital_status"] = m_map[m.lower()]

        st = base.get("employment_status", "")
        st_map = {"not": "离职", "no": "离职", "yes": "在职", "in position": "在职"}
        if st.lower() in st_map:
            base["employment_status"] = st_map[st.lower()]

    edus = resume.get("education_list") or []
    deg_trans = {
        "bachelor": "本科",
        "master": "硕士", "ma": "硕士", "ms": "硕士", "mba": "硕士",
        "phd": "博士", "doctor": "博士",
        "associate": "大专", "diploma": "大专",
        "high school": "高中",
    }
    for e in edus:
        dt = e.get("school_degree_type", "")
        if dt.lower() in deg_trans:
            e["school_degree_type"] = deg_trans[dt.lower()]

        rank = e.get("school_degree_rank", "4")
        if rank in ("5", "6", "7"):
            e["school_education_type"] = "全日制研究生"
        elif rank == "4":
            e["school_education_type"] = "全日制大学"
        elif rank == "3":
            e["school_education_type"] = "全日制大专"

    works = resume.get("work_experiences") or []
    pos_trans = [
        (r"\bTraining Manager\b", "培训经理"),
        (r"\bTraining Director\b", "培训总监"),
        (r"\bTraining Instructor\b", "培训讲师"),
        (r"\bCivil Servant\b", "公务员"),
        (r"\bEngaged in free lecturer\b", "自由讲师"),
        (r"\bfree lecturer\b", "自由讲师"),
        (r"\bBranch manager\b", "分公司经理"),
        (r"\bVP\b", "副总裁"),
        (r"\bManager\b", "经理"),
        (r"\bDirector\b", "总监"),
        (r"\bEngineer\b", "工程师"),
        (r"\bConsultant\b", "顾问"),
        (r"\bSpecialist\b", "专员"),
        (r"\bOfficer\b", "专员"),
        (r"\bSupervisor\b", "主管"),
        (r"\bAnalyst\b", "分析师"),
        (r"\bDeveloper\b", "开发工程师"),
        (r"\bDesigner\b", "设计师"),
        (r"\bSales\b", "销售"),
        (r"\bLecturer\b", "讲师"),
    ]
    for w in works:
        pos = w.get("position", "")
        for pat, replacement in pos_trans:
            if re.search(pat, pos, re.I):
                pos = re.sub(pat, replacement, pos, flags=re.I).strip()
        w["position"] = pos

        rep = w.get("position_report_to", "")
        for pat, replacement in pos_trans:
            if re.search(pat, rep, re.I):
                rep = re.sub(pat, replacement, rep, flags=re.I).strip()
        w["position_report_to"] = rep

        comp = w.get("company_name", "")
        if "the people’s government" in comp.lower():
            w["company_name"] = re.sub(r"The people’s government\s+in\s+Beijing", "北京市人民政府", comp, flags=re.I)

        emp = w.get("employment_type", "")
        if emp.lower() in ("full-time", "fulltime"):
            w["employment_type"] = "全职"
        elif emp.lower() in ("part-time", "parttime"):
            w["employment_type"] = "兼职"
        elif emp.lower() in ("intern", "internship"):
            w["employment_type"] = "实习"


def _extract_liepin_name(text: str, filename: str, parsed_name: str) -> str:
    """智能提纯猎聘网简历姓名，彻底过滤 '网简' 等假名，并结合文件名精准提取。

    EN: Smartly refine Liepin résumé names, thoroughly filtering fake names like '网简', and extract precisely in combination with the file name.

    JA: Liepin の履歴書の氏名を賢く精製し、'网简' などの偽の氏名を徹底的に除外して、ファイル名と組み合わせて正確に抽出する。
    """
    # 0. 优先判断带 姓名-XX岁 特征的文件名 (如 李梦琦-24岁)
    # EN: 0. First check file names with the "name-XX岁" (age) feature (e.g. <name>-24岁)
    # JA: 0. 「氏名-XX岁」（年齢）の特徴を持つファイル名を優先して判定する（例：<氏名>-24岁）
    m_age = re.search(r"(?:__|_|\b)([^\s\-_0-9]{2,8})-\d{1,2}岁", filename)
    if m_age:
        cand = m_age.group(1).strip()
        if cand not in ("无关联职", "无关联", "人事专员", "未公开", "简历", "未知", "网简", "IT系统实施", "运维工程师"):
            return cand

    clean_p = re.sub(r"\s+", "", parsed_name or "").strip()
    if clean_p and re.search(r"(?:网简|无关联|职位|简历|未知|未公开|猎聘|个人|推荐|系统实施|运维工程师)", clean_p):
        clean_p = ""

    if clean_p and 2 <= len(clean_p) <= 12:
        return clean_p

    base_fn = re.sub(r"__[0-9a-fA-F]+\.html$", "", filename)
    base_fn = re.sub(r"^\d+-", "", base_fn)

    # 1. 优先尝试提取 "猎聘网简历_姓名_" 或 "无关联职位简历_姓名-"
    # EN: 1. First try extracting "猎聘网简历_name_" (Liepin résumé_name_) or "无关联职位简历_name-" (résumé without linked position_name-)
    # JA: 1. まず「猎聘网简历_氏名_」（Liepin 履歴書_氏名_）または「无关联职位简历_氏名-」（職位未関連の履歴書_氏名-）の抽出を試みる
    m_prefix = re.search(r"^(?:猎聘网简历|无关联职位简历|简历)_([^\s\-_0-9]{2,8})", base_fn)
    if m_prefix:
        cand = m_prefix.group(1).strip()
        if cand not in ("无关联职", "无关联", "人事专员", "未公开", "简历", "未知", "网简"):
            return cand

    # 2. 通用文件名分割匹配
    # EN: 2. Generic file-name split matching
    # JA: 2. 汎用的なファイル名の分割によるマッチ
    sub_fn = re.sub(r"^(?:猎聘网简历|无关联职位简历|无关联职位|简历)_", "", base_fn)
    m_name = re.search(r"^([^\s\-_0-9]{2,8})(?:-\d+岁|-|_|\s|\Z)", sub_fn)
    if m_name:
        cand = m_name.group(1).strip()
        if cand not in ("无关联职", "无关联", "人事专员", "未公开", "简历", "未知", "网简"):
            return cand

    m_text = re.search(r"姓名[：:]?\s*([^\s\n\r|│<]{2,10})", text)
    if m_text:
        cand = m_text.group(1).strip()
        if not re.search(r"(?:网简|无关联|职位|简历|未知|未公开)", cand):
            return cand

    return "未知"


def _build_empty_education_info() -> dict[str, str]:
    return {
        "school_name": "",
        "school_major_name": "",
        "school_degree_type": "",
        "school_degree_rank": "",
        "school_education_type": "",
        "school_start_ym": "",
        "school_end_ym": "",
    }


def _build_empty_current_info() -> dict[str, str]:
    return {
        "company_name": "",
        "company_employees": "",
        "company_industry": "",
        "position": "",
        "position_type": "",
        "position_salary": "",
        "position_dept": "",
        "position_report_to": "",
        "position_subordinate": "",
        "employment_type": "全职",
        "annual_salary_min": "",
        "annual_salary_max": "",
        "status": "",
        "position_start": "",
        "position_resigned": "",
    }


def build_record_from_html(
    html_path: Path,
    parser: CodexGeminiHtmlSchemaParser,
    classifier: DocumentClassifier,
) -> tuple[dict[str, Any] | None, str]:
    try:
        html_text = read_html_text(html_path)
    except Exception as exc:
        return None, f"read_error:{exc}"

    text = plain_text(html_text)
    if len(text) < 10:
        return None, "empty_text"

    try:
        classification = classifier.classify(text, filename=html_path.name)
    except Exception:
        classification = type("C", (), {"document_type": "ambiguous_resume", "reason": "classifier_exception"})()

    if classification.document_type not in {"resume", "ambiguous_resume"}:
        return None, f"non_resume:{classification.document_type}"

    fake_source_path = str(html_path.resolve())
    try:
        parsed = parser.parse(html_text, filename=html_path.name, source_path=fake_source_path)
    except Exception as exc:
        return None, f"parser_error:{exc}"

    structured_data = parsed

    # 提纯与全域矫正姓名 full_name
    # EN: Refine and globally correct the name full_name
    # JA: 氏名 full_name を精製し、全体的に補正する
    parsed_fn = (structured_data.get("base_info") or {}).get("full_name", "")
    correct_fn = _extract_liepin_name(text, html_path.name, parsed_fn)
    if structured_data.get("base_info"):
        structured_data["base_info"]["full_name"] = correct_fn

    # 提取猎聘网 12 位平台 resume_id（保留在 base_info 中，不放入 source）
    # EN: Extract Liepin's 12-digit platform resume_id (kept in base_info, not in source)
    # JA: Liepin の 12 桁のプラットフォーム resume_id を抽出する（source ではなく base_info に保持）
    m_rid = re.search(r"__([0-9a-fA-F]{12})\.html$", html_path.name)
    platform_resume_id = m_rid.group(1) if m_rid else ""

    # 将平台简历ID写入 base_info.platform_resume_id
    # EN: Write the platform résumé ID into base_info.platform_resume_id
    # JA: プラットフォームの履歴書 ID を base_info.platform_resume_id に書き込む
    if structured_data.get("base_info"):
        structured_data["base_info"]["platform_resume_id"] = platform_resume_id

    # 1. 结合 raw_text 通用模式解析与 DOM 抽取，彻底消灭 DOM 节点污染 (如误抓右括号 ')')
    # EN: 1. Combine generic pattern parsing of raw_text with DOM extraction to eliminate DOM node pollution completely (e.g. mistakenly grabbing a closing bracket ')')
    # JA: 1. raw_text の汎用パターンの解析と DOM の抽出を組み合わせ、DOM ノードによる汚染（閉じ括弧 ')' の誤取得など）を完全になくす
    raw_edus, raw_trainings = parse_education_from_raw_text(text)
    edus = structured_data.get("education_list") or []

    if raw_edus:
        if not edus or len(edus) != len(raw_edus):
            edus = raw_edus
        else:
            for idx, e in enumerate(edus):
                r_e = raw_edus[idx]
                if not e.get("school_major_name") or e.get("school_major_name") in (")", "(", "）", "（", "语言能力", "未填写"):
                    e["school_major_name"] = r_e.get("school_major_name", "")
                if not e.get("school_name"):
                    e["school_name"] = r_e.get("school_name", "")

    if edus:
        edus = _fix_liepin_education_school_major(edus)
        structured_data["education_list"] = normalize_education_list(edus)
    else:
        structured_data["education_list"] = []

    # 训练经历：使用 training_list 统一命名
    # EN: Training history: use the unified name training_list
    # JA: 研修歴：統一名 training_list を使う
    training_list = raw_trainings
    # 为培训经历添加 position_achievements 不适用，但需保证字段规范
    # EN: Adding position_achievements to training history does not apply, but the fields must still follow the spec
    # JA: 研修歴に position_achievements を追加するのは当てはまらないが、フィールドは仕様に従わせる必要がある
    structured_data["training_list"] = training_list

    for r in structured_data.get("resumes") or []:
        r["education_list"] = copy.deepcopy(structured_data["education_list"])
        r["training_list"] = copy.deepcopy(training_list)

    # 1.5 结合 DOM 解析与 raw_text 提取的工作经历进行清洗与权威覆盖，彻底消灭 DOM 误把学校当公司或把时间字符串当公司名的脏数据
    # EN: 1.5 Clean and authoritatively override the work history extracted by DOM parsing and from raw_text, eliminating dirty data where the DOM took a school as the company or a time string as the company name
    # JA: 1.5 DOM の解析と raw_text から抽出した職歴をクレンジングして正として上書きし、DOM が学校を会社と誤認したり日時の文字列を会社名にしたりした汚れたデータを完全になくす
    dom_works = []
    if BeautifulSoup is not None and html_text:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            dom_works = parse_liepin_html_work_experiences(soup)
        except Exception:
            dom_works = []

    if dom_works:
        structured_data["work_experiences"] = dom_works
    else:
        raw_works = parse_work_from_raw_text(text)
        if raw_works:
            structured_data["work_experiences"] = raw_works

    for r in structured_data.get("resumes") or []:
        r["work_experiences"] = copy.deepcopy(structured_data.get("work_experiences") or [])

    # 2. 检测语言与处理多语言 resumes 对象 Copy 机制
    # EN: 2. Detect the language and handle the copy mechanism for multilingual resumes objects
    # JA: 2. 言語を検出し、多言語の resumes オブジェクトのコピー機構を処理する
    real_lang = _detect_resume_language(text)
    resumes = structured_data.get("resumes") or []

    # 查找已有 resumes 列表中是否有中文版对象
    # EN: Look for a Chinese-version object in the existing resumes list
    # JA: 既存の resumes の一覧に中国語版のオブジェクトがあるかを探す
    zh_index = -1
    for idx, r in enumerate(resumes):
        if r.get("resume_language") == "zh":
            zh_index = idx
            break

    if zh_index > 0:
        # 将现有的中文对象拉到 0 号位
        # EN: Move the existing Chinese object to slot 0
        # JA: 既存の中国語のオブジェクトを 0 番目に移す
        zh_obj = resumes.pop(zh_index)
        resumes.insert(0, zh_obj)
    elif zh_index == -1 and len(resumes) > 0:
        # 纯外文简历：在 0 号位深拷贝现有的外文简历对象 (resumes[0]) 作为中文版 (zh)
        # EN: Foreign-language-only résumé: deep-copy the existing foreign résumé object (resumes[0]) into slot 0 as the Chinese version (zh)
        # JA: 外国語のみの履歴書：既存の外国語の履歴書オブジェクト（resumes[0]）を 0 番目にディープコピーして中国語版（zh）とする
        src_resume = resumes[0]
        src_resume["resume_language"] = real_lang

        # 彻底 Deepcopy 隔离引用
        # EN: Deepcopy completely to isolate references
        # JA: deepcopy で参照を完全に分離する
        zh_resume = copy.deepcopy(src_resume)
        zh_resume["resume_language"] = "zh"

        if edus:
            zh_resume["education_list"] = copy.deepcopy(edus)

        # 对 0 号位中文版执行中文翻译转换
        # EN: Run the Chinese translation conversion on the Chinese version in slot 0
        # JA: 0 番目の中国語版に中国語への翻訳変換を実行する
        _translate_resume_to_chinese(zh_resume)

        foreign_resumes = [r for r in resumes if r.get("resume_language") != "zh"]
        resumes = [zh_resume] + foreign_resumes
    elif not resumes:
        resumes = [{
            "resume_language": "zh",
            "base_info": {},
            "expected_info": [],
            "work_experiences": [],
            "education_list": [],
            "certificate_list": [],
            "language_list": [],
            "skills_list": [],
            "training_list": [],
            "project_list": [],
            "communication_list": [],
        }]

    structured_data["resumes"] = resumes

    # 3. 内部 Schema 补齐：校准平台属性、姓名，补齐每个 resume 对象缺失的标准列表键
    # EN: 3. Internal schema completion: calibrate platform attributes and name, and fill missing standard list keys in each resume object
    # JA: 3. 内部スキーマの補完：プラットフォームの属性と氏名を補正し、各 resume オブジェクトに欠けている標準のリストのキーを補う
    lp_platform = "猎聘网"
    for r in resumes:
        r.setdefault("base_info", {})
        r.setdefault("expected_info", [])
        r.setdefault("work_experiences", [])
        r.setdefault("education_list", [])
        r.setdefault("certificate_list", [])
        r.setdefault("language_list", [])
        r.setdefault("skills_list", [])
        r.setdefault("training_list", [])
        r.setdefault("project_list", [])
        r.setdefault("communication_list", [])

        # 向后兼容：如果有旧字段名，迁移到新字段名（始终删除旧字段）
        # EN: Backward compatibility: if there are old field names, migrate them to the new ones (always deleting the old fields)
        # JA: 後方互換：旧フィールド名があれば新しい名前に移行する（旧フィールドは常に削除）
        for old, new in [("certificate_info", "certificate_list"), ("language_info", "language_list"),
                          ("skills_info", "skills_list"), ("training_experiences", "training_list"),
                          ("resume_languge", "resume_language")]:
            if old in r:
                if new not in r:
                    r[new] = r[old]
                r.pop(old)

        r["base_info"]["platform_from"] = lp_platform
        r["base_info"]["full_name"] = correct_fn

    # 4. 基于 resumes[0] (中文主版本) 补齐与重构顶层外部数据
    # EN: 4. Complete and rebuild the top-level external data based on resumes[0] (the Chinese primary version)
    # JA: 4. resumes[0]（中国語主版）に基づいてトップレベルの外部データを補完・再構築する
    r0 = resumes[0]
    r0_base = r0.get("base_info") or {}
    structured_data["base_info"] = dict(r0_base)

    # 顶层 expected_info 同步（如果有）
    # EN: Sync the top-level expected_info (if any)
    # JA: トップレベルの expected_info を同期する（あれば）
    r0_expected = r0.get("expected_info") or []
    structured_data["expected_info"] = copy.deepcopy(r0_expected) if r0_expected else []

    r0_edus = r0.get("education_list") or []
    if r0_edus:
        # 取学历等级最高的一条（rank 数字越大学历越高）
        # EN: Take the entry with the highest degree rank (a larger rank number means a higher degree)
        # JA: 学歴ランクが最も高い 1 件を取る（rank の数値が大きいほど学歴が高い）
        top_edu = max(r0_edus, key=lambda e: int(e.get("school_degree_rank", "1")))
        structured_data["education_info"] = {
            "school_name": top_edu.get("school_name", ""),
            "school_major_name": top_edu.get("school_major_name", ""),
            "school_degree_type": top_edu.get("school_degree_type", ""),
            "school_degree_rank": top_edu.get("school_degree_rank", "4"),
            "school_education_type": top_edu.get("school_education_type", "全日制大学"),
            "school_start_ym": top_edu.get("school_start_ym", ""),
            "school_end_ym": top_edu.get("school_end_ym", ""),
        }
    else:
        structured_data["education_info"] = _build_empty_education_info()

    r0_works = r0.get("work_experiences") or []
    if r0_works:
        w = r0_works[0]
        structured_data["current_info"] = {
            "company_name": w.get("company_name", ""),
            "company_employees": w.get("company_employees", ""),
            "company_industry": w.get("company_industry", ""),
            "position": w.get("position", ""),
            "position_type": w.get("position_type", ""),
            "position_salary": w.get("position_salary", ""),
            "position_dept": w.get("position_dept", ""),
            "position_report_to": w.get("position_report_to", ""),
            "position_subordinate": w.get("position_subordinate", ""),
            "employment_type": w.get("employment_type", "全职"),
            "annual_salary_min": w.get("annual_salary_min", ""),
            "annual_salary_max": w.get("annual_salary_max", ""),
            "status": w.get("status", ""),
            "position_start": w.get("position_start", ""),
            "position_resigned": w.get("position_resigned", ""),
        }
    else:
        structured_data["current_info"] = _build_empty_current_info()

    # 确保所有工作经历包含 position_achievements 字段
    # EN: Make sure every work experience includes the position_achievements field
    # JA: すべての職歴に position_achievements フィールドが含まれるようにする
    for r in structured_data.get("resumes") or []:
        for w in (r.get("work_experiences") or []):
            w.setdefault("position_achievements", "")

    # 递归删除 structured_data 内部所有 raw_text 字段（仅保留最外层 record 的 raw_text）
    # EN: Recursively delete every raw_text field inside structured_data (keep only the outermost record's raw_text)
    # JA: structured_data 内部の raw_text フィールドを再帰的にすべて削除する（最も外側のレコードの raw_text だけを残す）
    def _strip_inner_raw_text(obj):
        if isinstance(obj, dict):
            obj.pop("raw_text", None)
            for v in obj.values():
                _strip_inner_raw_text(v)
        elif isinstance(obj, list):
            for item in obj:
                _strip_inner_raw_text(item)
    _strip_inner_raw_text(structured_data)

    # 清除顶层冗余列表字段（明细保留在 resumes 内）
    # EN: Remove redundant top-level list fields (the details stay in resumes)
    # JA: 冗長なトップレベルのリストフィールドを削除する（明細は resumes 内に残す）
    _top_level_blacklist = {"work_experiences", "education_list", "project_experiences",
                            "communication_assessment", "training_experiences",
                            "certificate_list", "language_list", "skills_list",
                            "training_list", "project_list", "communication_list"}
    structured_data = {k: v for k, v in structured_data.items() if k not in _top_level_blacklist}

    fallback_date = date_from_mtime(html_path)
    now = datetime.now(TZ_JST).isoformat(timespec="seconds")
    rec_id = html_record_id(html_path)
    stat = html_path.stat()

    up_date, dl_date, up_src, dl_src = parse_resume_dates(text, fallback_date)

    w_count = len((structured_data.get("resumes") or [{}])[0].get("work_experiences") or [])
    e_count = len((structured_data.get("resumes") or [{}])[0].get("education_list") or [])

    record = {
        "schema_version": "codex-resume-json-1.0",
        "record_id": rec_id,
        "source": {
            "path": fake_source_path,
            "original_path": fake_source_path,
            "filename": html_path.name,
            "extension": ".html",
            "size": stat.st_size,
            "html_filename": html_path.name,
            "note": "由 run_liepin_html_to_json.py 从猎聘网 HTML 转换",
        },
        "dates": {
            "resume_updated_date": up_date,
            "resume_download_date": dl_date,
            "resume_updated_date_source": up_src,
            "resume_download_date_source": dl_src,
            "sys_created_date": now,
            "sys_updated_date": now,
        },
        "extraction": {
            "reader_group": "liepin_html_dom",
            "converter": "run_liepin_html_to_json.py",
            "parser": "codex_gemini_html_schema_parser",
            "status": "success",
            "html_path": str(html_path.resolve()),
        },
        "classification": {
            "document_type": classification.document_type,
            "reason": getattr(classification, "reason", ""),
        },
        "structured_data": structured_data,
        "raw_text": text,
        "quality": {
            "full_name": (structured_data.get("base_info") or {}).get("full_name", ""),
            "has_work": w_count > 0,
            "work_count": w_count,
            "has_education": e_count > 0,
            "education_count": e_count,
            "raw_text_length": len(text),
        },
    }
    return record, "success"


def main() -> int:
    args = parse_args()
    if os.name == "nt":
        os.system("title 猎聘网 HTML -> JSON")

    html_dir = args.html_dir.resolve()
    json_dir = args.json_dir.resolve()
    json_dir.mkdir(parents=True, exist_ok=True)

    print(f"源 HTML 目录: {html_dir}" f" / Source HTML directory: {html_dir} / 元の HTML ディレクトリ：{html_dir}")
    print(f"输出 JSON 目录: {json_dir}" f" / Output JSON directory: {json_dir} / 出力する JSON のディレクトリ：{json_dir}")

    if not html_dir.exists():
        print(f"错误: 目录不存在 -> {html_dir}" f" / Error: directory does not exist -> {html_dir} / エラー：ディレクトリが存在しません -> {html_dir}")
        return 1

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        print("未找到 HTML 文件。" " / No HTML files found. / HTML ファイルが見つかりません。")
        return 0

    if args.limit > 0:
        html_files = html_files[: args.limit]

    print(f"共发现 {len(html_files)} 个猎聘网 HTML 文件。" f" / Found {len(html_files)} Liepin HTML files. / 猎聘の HTML ファイルを {len(html_files)} 個検出しました。")

    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()

    success_count = 0
    failed_count = 0
    skipped_count = 0
    non_resume_count = 0
    items_report: list[dict[str, Any]] = []

    start_time = time.time()

    for idx, html_path in enumerate(html_files, 1):
        rec_id = html_record_id(html_path)
        record, status = build_record_from_html(html_path, parser, classifier)

        if not record or status.startswith("non_resume"):
            non_resume_count += 1
            print(f"[{idx:04d}/{len(html_files):04d}] SKIP(非简历) {html_path.name} -> {status}" f" / [{idx:04d}/{len(html_files):04d}] SKIP (non-résumé) {html_path.name} -> {status} / [{idx:04d}/{len(html_files):04d}] SKIP（履歴書でない） {html_path.name} -> {status}")
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": status,
            })
            continue

        full_name = record["quality"].get("full_name", "") or "未知"
        work_cnt = record["quality"].get("work_count", 0)

        json_filename = f"{full_name}_{rec_id[:8]}.json"
        json_path = json_dir / json_filename

        if json_path.exists() and not args.force:
            skipped_count += 1
            print(f"[{idx:04d}/{len(html_files):04d}] EXIST {html_path.name}")
            continue

        try:
            json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            success_count += 1
            if idx % args.progress_interval == 0 or idx == len(html_files):
                print(f"[{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name} (工作{work_cnt}段)" f" / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name} ({work_cnt} work entries) / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {full_name}（職歴 {work_cnt} 件）")
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "json": str(json_path),
                "status": "success",
                "full_name": full_name,
                "work_count": work_cnt,
            })
        except Exception as exc:
            failed_count += 1
            print(f"[{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {exc}")
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": f"write_error:{exc}",
            })

    elapsed = time.time() - start_time
    report_path = json_dir / "_liepin_batch_report.json"
    report_data = {
        "workflow": "liepin_html_to_json",
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "total": len(html_files),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "non_resume_count": non_resume_count,
        "elapsed_seconds": round(elapsed, 2),
        "items": items_report,
    }
    report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 猎聘网 HTML→JSON 批处理完成 ===" " / \n=== Liepin HTML→JSON batch finished === / \n=== 猎聘の HTML→JSON 一括処理が完了しました ===")
    print(f"总计: {len(html_files)}；成功: {success_count}；失败: {failed_count}；跳过: {skipped_count}；非简历: {non_resume_count}" f" / Total: {len(html_files)}; success: {success_count}; failed: {failed_count}; skipped: {skipped_count}; non-résumé: {non_resume_count} / 合計：{len(html_files)}、成功：{success_count}、失敗：{failed_count}、スキップ：{skipped_count}、履歴書でない：{non_resume_count}")
    print(f"耗时: {elapsed:.2f} 秒；报告: {report_path}" f" / Elapsed: {elapsed:.2f} s; report: {report_path} / 所要時間：{elapsed:.2f} 秒、レポート：{report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
