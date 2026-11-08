"""complete-transfered-htmls\\docs\\中文 目录专属 HTML -> JSON 转换解析器。

整合吸收来自 51job / 智联招聘 / 猎聘网 / Newpage 四大平台解析脚本的后处理工具函数
（减少重复劳动），对 docs\\中文 目录下所有 HTML 简历做统一解析：

1. 统一 DOM→纯文本 + _preprocess_glued_text() 拆分多字段粘连 <p> + 日期被换行切断的拼接；
2. 姓名/联系方式深度识别（mailto: 优先提取邮箱，洗净 HYPERLINK 宏残留，防伪假名）；
3. _clean_company_name 统一清理公司名中的时长括号/不间断空格/字段分隔符；
4. expected_info 补齐 CONTEXT.md 7.2 要求的 8 字段（含到岗时间从「目前状况」提取）；
5. 教育经历多段切割、学校专业颠倒纠偏、school_degree_rank 1~7级归一化；
6. 工作经历多段切割、公司名清洗、position_achievements 占位；
7. 证书列表使用 _parse_zhilian_certificates_simple + _clean_certificate_list 统一去杂质；
   在校实践经历通过 _parse_zhilian_practice_simple 合并到 training_list；
8. skills_list 应用个人素质关键词（沟通能力/团队精神/责任心…）过滤，软素质移到 base_info.pr；
   并排除动作短语（负责…/每天…/上交给…）与长句子；
9. project_list 描述/职责按关键词分离（责任描述→responsibilities，项目描述→description）；
   training_name 非空但 project_name 空时做兜底映射；
10. 语言名/级别通过 LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP 统一翻译；
11. 输出文件名“姓名_手机号.json”（无手机号则邮箱；同名同联系方式追加 _2），并输出批处理报告。

EN: HTML -> JSON conversion parser dedicated to the complete-transfered-htmls\\docs\\中文 (Chinese) directory.

Integrates the post-processing helpers from the parsing scripts of the four major platforms 51job / Zhaopin / Liepin / Newpage
(to reduce duplicated work), and parses all HTML résumés under docs\\中文 uniformly:

1. Unified DOM → plain text + _preprocess_glued_text() to split multiple fields stuck in one <p> and join dates broken by line breaks;
2. Deep recognition of name/contact (mailto: e-mails extracted first, HYPERLINK macro leftovers cleaned, fake names guarded against);
3. _clean_company_name uniformly removes tenure brackets / non-breaking spaces / field separators from company names;
4. expected_info completes the 8 fields required by CONTEXT.md 7.2 (including the start date extracted from "目前状况" (current status));
5. Multi-entry splitting of education history, correction of swapped school/major, normalisation of school_degree_rank to levels 1-7;
6. Multi-entry splitting of work history, company name cleaning, position_achievements placeholder;
7. The certificate list uses _parse_zhilian_certificates_simple + _clean_certificate_list to remove noise uniformly;
   campus practice experience is merged into training_list via _parse_zhilian_practice_simple;
8. skills_list applies personal-quality keyword filtering (communication skills / team spirit / sense of responsibility …), moving soft qualities to base_info.pr;
   and excludes action phrases (负责… / 每天… / 上交给…) and long sentences;
9. project_list separates description/duties by keyword (责任描述 → responsibilities, 项目描述 → description);
   a fallback mapping applies when training_name is non-empty but project_name is empty;
10. Language names/levels are translated uniformly via LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP;
11. Output file name "name_mobile.json" (e-mail if there is no mobile; _2 appended for the same name and contact), and a batch report is produced.

JA: complete-transfered-htmls\\docs\\中文（中国語）ディレクトリ専用の HTML -> JSON 変換パーサー。

51job / Zhaopin / Liepin / Newpage の 4 大プラットフォームの解析スクリプトにある後処理ツール関数を統合して取り込み
（重複作業を減らし）、docs\\中文 配下のすべての HTML 履歴書を一律に解析する：

1. DOM → プレーンテキストの統一 + _preprocess_glued_text() で 1 つの <p> にくっついた複数フィールドを分割し、改行で分断された日付を結合する。
2. 氏名・連絡先の高度な識別（mailto: からのメール抽出を優先、HYPERLINK マクロの残骸を除去、偽名を防止）。
3. _clean_company_name で会社名の在職期間の括弧・ノーブレークスペース・フィールドの区切りを一律に除去する。
4. expected_info で CONTEXT.md 7.2 が求める 8 フィールドを補完する（「目前状况」（現在の状況）から入社可能時期を抽出することを含む）。
5. 学歴を複数件に分割し、学校と専攻の取り違えを補正し、school_degree_rank を 1〜7 段階に正規化する。
6. 職歴を複数件に分割し、会社名をクレンジングし、position_achievements のプレースホルダーを置く。
7. 資格の一覧は _parse_zhilian_certificates_simple + _clean_certificate_list で一律に不要部分を除く。
   在学中の実践経験は _parse_zhilian_practice_simple で training_list に統合する。
8. skills_list には個人の資質のキーワード（コミュニケーション能力・チームワーク・責任感…）のフィルターを適用し、ソフトスキルは base_info.pr に移す。
   さらに動作の語句（负责…／每天…／上交给…）と長い文を除く。
9. project_list は説明と担当業務をキーワードで分ける（责任描述 → responsibilities、项目描述 → description）。
   training_name が空でなく project_name が空の場合は最終手段として対応付ける。
10. 言語名・レベルは LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP で一律に変換する。
11. 出力ファイル名は「氏名_携帯番号.json」（携帯番号がなければメール。同じ氏名・連絡先には _2 を付ける）とし、バッチ処理のレポートを出力する。
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
import multiprocessing as mp
import os
import queue
import re
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from resume_importer.codex_gemini_html_schema_parser import CodexGeminiHtmlSchemaParser
from resume_importer.classifier import DocumentClassifier
from reuse_complete_v1_jsons import validate_json as validate_complete_json

TZ_JST = timezone(timedelta(hours=9))

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# =============================================================================
# （平台名仅用于 base_info.platform_from 标识，已不再做路由选择）
# =============================================================================
# EN: =============================================================================
#     (The platform name is only used as the base_info.platform_from label; it is no longer used for routing)
#     =============================================================================
# JA: =============================================================================
#     （プラットフォーム名は base_info.platform_from の識別にだけ使い、振り分けにはもう使わない）
#     =============================================================================

PLAT_DEFAULT = "中文"

# =============================================================================
# 基础 I/O：参数 / 编码读取 / record_id / mtime date
# =============================================================================
# EN: =============================================================================
#     Basic I/O: arguments / encoding-aware reading / record_id / mtime date
#     =============================================================================
# JA: =============================================================================
#     基本 I/O：引数 / エンコーディングを考慮した読み込み / record_id / mtime の日付
#     =============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="docs\\中文 目录专属 HTML -> JSON 转换（整合四大平台工具后处理）" " / HTML -> JSON conversion dedicated to the docs\\中文 directory (post-processing that integrates the four platform tools) / docs\\中文 ディレクトリ専用の HTML -> JSON 変換（4 つのプラットフォーム用ツールを統合した後処理）")
    p.add_argument(
        "--html-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "passed" / "中文",
        help="HTML 目录（默认 complete-transfered-htmls/docs/passed/中文）" " / HTML directory (default complete-transfered-htmls/docs/passed/中文) / HTML ディレクトリ（既定は complete-transfered-htmls/docs/passed/中文）",
    )
    p.add_argument(
        "--json-dir",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-jsons") / "docs" / "中文",
        help="JSON 输出目录（默认 complete-transfered-jsons/docs/中文）" " / JSON output directory (default complete-transfered-jsons/docs/中文) / JSON の出力ディレクトリ（既定は complete-transfered-jsons/docs/中文）",
    )
    p.add_argument("--limit", type=int, default=0, help="处理数量上限（0=全部）" " / Upper limit on the number processed (0 = all) / 処理する件数の上限（0 は全件）")
    p.add_argument("--offset", type=int, default=0, help="跳过排序后的前 N 个 HTML（用于分段抽样）" " / Skip the first N sorted HTML files (for segmented sampling) / 並べ替え後の先頭 N 個の HTML をスキップする（分割サンプリング用）")
    p.add_argument("--force", action="store_true", help="覆盖已存在 JSON" " / Overwrite existing JSON / 既存の JSON を上書きする")
    p.add_argument("--progress-interval", type=int, default=50)
    p.add_argument("--file-timeout", type=int, default=90, help="单文件解析超时秒数；超时会重启隔离工作进程" " / Per-file parse timeout in seconds; on timeout the isolated worker process is restarted / 1 ファイルあたりの解析タイムアウト秒数（超過すると分離したワーカープロセスを再起動する）")
    p.add_argument(
        "--map",
        type=Path,
        default=PROJECT_ROOT / _rc.dirname("complete-transfered-htmls") / "docs" / "word_conversion_map.json",
        help="用于核对原路径和联系方式的 Word 映射" " / Word map used to check original paths and contact details / 元のパスと連絡先を照合するための Word のマップ",
    )
    p.add_argument(
        "--incremental-manifest",
        type=Path,
        help="只处理增量清单中 conversion_status=passed 且尚无 staging_json 的 HTML" " / Process only HTML with conversion_status=passed and no staging_json yet in the incremental list / 増分一覧で conversion_status=passed かつ staging_json がまだない HTML だけを処理する",
    )
    p.add_argument("--rerun-staged", action="store_true", help="与增量清单配合：重跑清单中的暂存 JSON，并覆盖暂存结果" " / Used with the incremental list: re-run the staging JSON in the list and overwrite the staging results / 増分一覧と併用：一覧内のステージング JSON を再実行し、ステージングの結果を上書きする")
    p.add_argument(
        "--report",
        type=Path,
        help="批处理报告输出路径；默认写入 json_dir/_chinese_batch_report.json" " / Output path of the batch report; by default json_dir/_chinese_batch_report.json / バッチレポートの出力パス（既定は json_dir/_chinese_batch_report.json）",
    )
    p.add_argument(
        "--identity-json-dir",
        type=Path,
        help="仅在姓名解析失败时，用唯一手机号/邮箱匹配的历史 JSON 补姓名" " / Only when name parsing fails, fill in the name from historical JSON matched by a unique mobile/e-mail / 氏名の解析に失敗したときに限り、唯一の携帯番号／メールで一致した過去の JSON から氏名を補う",
    )
    # —— ★增量模式★：只处理 JSON_ROOT（--json-dir）下现存的 JSON（也就是上次校验不合格留在根目录的）
    #    逻辑：
    #    1) 扫描 json_dir 下的 *.json（排除_开头报告/complete目录）
    #    2) 从 JSON.source.path / JSON.source.original_path / JSON.extraction.html_path / record_id 4 种路径反查对应 HTML
    #    3) 只重新生成这些 HTML → 覆盖 json_dir 里的对应 JSON（相当于默认 --force）
    #    4) json_dir/complete/ 下已经合格的 JSON 完全不动（不动代码、不动文件、不重跑、不覆盖）
    # EN: —— ★Incremental mode★: process only the JSON currently present under JSON_ROOT (--json-dir) (i.e. those that failed validation last time and were left in the root)
    #        Logic:
    #        1) Scan *.json under json_dir (excluding reports starting with _ and the complete directory)
    #        2) Look up the corresponding HTML via four paths: JSON.source.path / JSON.source.original_path / JSON.extraction.html_path / record_id
    #        3) Regenerate only these HTML → overwrite the corresponding JSON in json_dir (equivalent to --force by default)
    #        4) JSON already passed under json_dir/complete/ are left completely untouched (no code change, no file change, no re-run, no overwrite)
    # JA: —— ★増分モード★：JSON_ROOT（--json-dir）配下に現存する JSON だけを処理する（前回の検証で不合格となりルートに残ったもの）
    #        ロジック：
    #        1) json_dir 配下の *.json をスキャンする（_ で始まるレポートと complete ディレクトリは除く）
    #        2) JSON.source.path / JSON.source.original_path / JSON.extraction.html_path / record_id の 4 つの経路から対応する HTML を逆引きする
    #        3) これらの HTML だけを再生成 → json_dir 内の対応する JSON を上書きする（既定で --force 相当）
    #        4) json_dir/complete/ 配下の合格済み JSON には一切手を触れない（コードもファイルも変えず、再実行も上書きもしない）
    p.add_argument(
        "--only-failed-root",
        action="store_true",
        help="【增量模式】只处理 json_dir 根目录下现存的不合格JSON（complete/ 下合格的完全不碰；默认自动 --force）" " / [Incremental mode] Process only the unqualified JSON currently in the root of json_dir (qualified ones under complete/ are not touched; --force is on automatically by default) / 【増分モード】json_dir 直下に現存する不合格の JSON だけを処理する（complete/ 配下の合格分には触れない。既定で自動的に --force）",
    )
    return p.parse_args()


def read_html_text(html_path: Path) -> str:
    """统一 HTML 解码：优先探测 meta charset，UTF-8 优先，避开 GB18030 霸道误解。

    EN: Unified HTML decoding: detect meta charset first, prefer UTF-8, and avoid GB18030's overbearing misinterpretation.

    JA: HTML のデコードの統一：まず meta charset を検出し、UTF-8 を優先して、GB18030 による強引な誤解釈を避ける。
    """
    raw_bytes = html_path.read_bytes()

    # 1. 优先尝试从 HTML <meta charset="..."> 提取
    # EN: 1. First try extracting from HTML <meta charset="...">
    # JA: 1. まず HTML の <meta charset="..."> からの抽出を試みる
    meta_m = re.search(rb"""<meta[^>]+charset=['"]?\s*([a-zA-Z0-9\-]+)""", raw_bytes, re.I)
    if meta_m:
        meta_enc = meta_m.group(1).decode("ascii", errors="ignore").lower()
        if meta_enc in ("utf-8", "utf8", "utf8-sig"):
            meta_enc = "utf-8"
        elif meta_enc in ("gbk", "gb2312", "gb18030"):
            meta_enc = "gb18030"
        try:
            t = raw_bytes.decode(meta_enc)
            if "\ufffd" not in t[:500]:
                return t
        except Exception:
            pass

    # 2. utf-8 优先，绝不能把 gb18030 放在 utf-8 前面！
    # EN: 2. utf-8 first; gb18030 must never be placed before utf-8!
    # JA: 2. utf-8 を優先。gb18030 を utf-8 より前に置いてはならない！
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16"):
        try:
            t = raw_bytes.decode(enc)
            if "\ufffd" in t[:200]:
                continue
            if "个人信息" in t or "简历" in t or "姓名" in t or "求职意向" in t or "工作经历" in t:
                return t
        except Exception:
            continue

    return raw_bytes.decode("utf-8", errors="replace")


def html_record_id(html_path: Path) -> str:
    stat = html_path.stat()
    value = f"{html_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def date_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=TZ_JST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


BASE_INFO_FIELDS = (
    "full_name", "gender", "age", "birth_date", "birth_year", "marital_status",
    "children_status", "political_status", "height_cm", "weight_kg",
    "household_registration", "address", "postal_code", "platform_from",
    "platform_resume_id", "phone", "email", "city", "nationality", "pr",
)
EXPECTED_INFO_FIELDS = (
    "expected_city", "expected_position", "expected_salary",
    "expected_annual_salary_min", "expected_annual_salary_max",
    "expected_industry", "expected_employment_type", "expected_start_date",
)
WORK_FIELDS = (
    "company_name", "company_employees", "company_industry", "position",
    "position_type", "position_salary", "position_dept", "position_report_to",
    "position_subordinate", "employment_type", "annual_salary_min",
    "annual_salary_max", "status", "position_start", "position_resigned",
    "resigned_reason", "position_responsibilities", "position_achievements",
)
EDUCATION_FIELDS = (
    "school_name", "school_major_name", "school_degree_type", "school_degree_rank",
    "school_education_type", "school_start_ym", "school_end_ym",
)


def extract_original_source_path(html_text: str, fallback: str) -> str:
    # source-path 只需普通 DOM 查询；使用内置解析器，避免整个批次被可选 lxml 依赖阻断。
    # EN: source-path only needs ordinary DOM queries; use the built-in parser so the whole batch is not blocked by the optional lxml dependency.
    # JA: source-path には通常の DOM 検索しか要らない。組み込みのパーサーを使い、任意依存の lxml でバッチ全体が止まらないようにする。
    soup = BeautifulSoup(html_text, "html.parser")
    node = soup.find(attrs={"data-field": "source-path"})
    if node:
        value = node.get_text(" ", strip=True)
        value = re.sub(r"^\s*(?:源文件路径|原始文件路径|source\s*path)\s*[:：]\s*", "", value, flags=re.I)
        if value:
            return value.strip()
    return fallback


COMMON_CHINESE_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌"
    "霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉"
    "龚程邢裴陆荣翁荀羊甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷"
    "车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司哈忻"
    "韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈"
    "燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨"
    "居衡步都耿满弘匡国文寇广禄阙东欧利蔚越夔隆师巩厍聂晁勾敖融冷訾"
    "辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)


def source_context_name(source_path: str) -> str:
    """从源文件名及最近父目录提取明确姓名；仅作为失败后的兜底。

    EN: Extract an explicit name from the source file name and the nearest parent directory; only as a fallback after failure.

    JA: ソースのファイル名と最も近い親ディレクトリから明確な氏名を抽出する。失敗した後の最終手段としてだけ使う。
    """
    path = Path(source_path)
    components = [path.stem, *[parent.name for parent in path.parents[:3]]]
    generic = {
        "简历", "中文简历", "个人简历", "人才", "智联", "猎聘", "日文", "中文",
        "老婆资料", "老婆电脑资料", "胖子", "孙晓丹", "职位介绍", "附件",
        "企划", "审计", "营业", "销售", "生产", "财务", "qc", "id",
        "夏普", "大金", "旭化成", "汽车", "事务", "品质", "市场", "采购",
    }
    for raw in components:
        value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", raw.strip())
        value = re.sub(r"(?:个人)?简历.*$", "", value).strip(" _-（）()")
        if not value:
            continue
        if value in generic:
            continue
        exact = re.fullmatch(r"([\u4e00-\u9fff]{2,3})", value)
        if exact and exact.group(1)[0] in COMMON_CHINESE_SURNAMES:
            return exact.group(1)
        prefixed = re.match(r"([\u4e00-\u9fff]{2,3})(?=[\s,，_\-（(])", raw.strip())
        if prefixed and prefixed.group(1)[0] in COMMON_CHINESE_SURNAMES:
            return prefixed.group(1)
        single_surname = re.match(r"([\u4e00-\u9fff])(?=[\s（(])", raw.strip())
        if single_surname and single_surname.group(1) in COMMON_CHINESE_SURNAMES:
            return single_surname.group(1)
        latin = re.fullmatch(r"[A-Za-z][A-Za-z.'-]{1,20}(?:\s+[A-Za-z][A-Za-z.'-]{1,20})?", value)
        if latin and value.casefold() not in {"latest", "resume", "desktop", "qc", "id", "se"}:
            return value
    return ""


def normalize_schema_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or re.search(r"至今|现在|目前|current|present", raw, re.I):
        return ""
    match = re.search(r"(?<!\d)((?:19|20)\d{2})\s*(?:年|[./-])\s*(\d{1,2})(?:\s*(?:月|[./-])\s*(\d{1,2}))?", raw)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        day = int(match.group(3) or 1)
        if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}年{month:02d}月{day:02d}日"
        return ""
    match = re.fullmatch(r"((?:19|20)\d{2})\s*年?", raw)
    if match:
        return f"{int(match.group(1)):04d}年01月01日"
    return ""


def string_record(source: Any, fields: tuple[str, ...], aliases: dict[str, tuple[str, ...]] | None = None) -> dict[str, str]:
    item = source if isinstance(source, dict) else {}
    aliases = aliases or {}
    result: dict[str, str] = {}
    for field in fields:
        value: Any = item.get(field, "")
        if value in (None, ""):
            for alias in aliases.get(field, ()):
                if item.get(alias) not in (None, ""):
                    value = item.get(alias)
                    break
        result[field] = str(value or "").strip()
    return result


def canonicalize_complete_schema(structured_data: dict[str, Any]) -> dict[str, Any]:
    resumes = structured_data.get("resumes") if isinstance(structured_data.get("resumes"), list) else []
    if not resumes:
        resumes = [{}]
    canonical_resumes: list[dict[str, Any]] = []
    for index, original in enumerate(resumes):
        resume = original if isinstance(original, dict) else {}
        base = string_record(resume.get("base_info") or structured_data.get("base_info"), BASE_INFO_FIELDS)
        base["birth_date"] = normalize_schema_date(base["birth_date"])
        language = str(resume.get("resume_language") or resume.get("resume_languge") or ("zh" if index == 0 else "")).strip().casefold()
        if index == 0:
            language = "zh"

        expected_source = resume.get("expected_list")
        if isinstance(expected_source, list):
            expected_rows = expected_source
        else:
            expected_object = resume.get("expected_info") or (structured_data.get("expected_info") if index == 0 else {})
            expected_rows = [expected_object] if isinstance(expected_object, dict) else []
        expected_list: list[dict[str, str]] = []
        for row in expected_rows:
            item = string_record(row, EXPECTED_INFO_FIELDS)
            meaningful = any(item[field] for field in EXPECTED_INFO_FIELDS if field != "expected_employment_type")
            if meaningful:
                expected_list.append(item)

        works: list[dict[str, str]] = []
        seen_works: set[tuple[str, ...]] = set()
        for row in resume.get("work_experiences") or []:
            item = string_record(row, WORK_FIELDS, {"position_dept": ("department",)})
            item["position_start"] = normalize_schema_date(item["position_start"] or (row.get("start_date") if isinstance(row, dict) else ""))
            item["position_resigned"] = normalize_schema_date(item["position_resigned"] or (row.get("end_date") if isinstance(row, dict) else ""))
            # 网页/简历更新时间（11:53:34、2018-03-20 11:53）绝不是公司名。
            # EN: Web page / résumé update times (11:53:34, 2018-03-20 11:53) are never company names.
            # JA: Web ページや履歴書の更新日時（11:53:34、2018-03-20 11:53）は決して会社名ではない。
            company_compact = re.sub(r"\s+", "", item["company_name"])
            if re.fullmatch(r"(?:\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)?[T ]?\d{1,2}:\d{2}(?::\d{2})?", company_compact):
                continue
            if company_compact in {"联系电话", "联系手机", "手机号码", "电话号码", "电话", "邮箱", "电子邮箱", "更新时间", "简历更新时间"}:
                continue

            # 公司与职位被“|”粘在一起：左侧是单位，右侧是职位。
            # EN: Company and position glued together with "|": the left side is the employer, the right side the position.
            # JA: 会社と職位が「|」でくっついている場合、左側が勤務先、右側が職位。
            if re.search(r"[|｜]", item["company_name"]):
                parts = [part.strip() for part in re.split(r"[|｜]", item["company_name"]) if part.strip()]
                if len(parts) >= 2:
                    item["company_name"] = parts[0]
                    if not item["position"] or len(item["position"]) > 24:
                        item["position"] = parts[-1]

            # 清除公司名末尾员工规模、任职时长及未闭合的时长碎片。
            # EN: Remove employee-size, tenure and unclosed tenure fragments from the end of the company name.
            # JA: 会社名の末尾にある従業員規模・在職期間・閉じていない期間の断片を除去する。
            item["company_name"] = re.sub(r"\s*[（(]\s*\d+\s*[-–~～至到]?\s*\d*\s*人(?:以上|以下|以内)?\s*[）)]?", "", item["company_name"]).strip()
            item["company_name"] = re.sub(r"\s*[\[【(（]\s*\d+\s*(?:年|个?月)[^\]】)）]*$", "", item["company_name"]).strip(" :：|｜")

            position = item["position"].strip()
            department = item["position_dept"].strip()
            # position 重复公司名并附带“(7个月)”时，真正职位通常在部门列。
            # EN: When position repeats the company name with "(7个月)" (7 months) attached, the real position is usually in the department column.
            # JA: position が会社名を繰り返し「(7个月)」（7 か月）が付いている場合、本当の職位は通常部署の列にある。
            company_core = re.sub(r"\s+", "", item["company_name"])
            position_core = re.sub(r"\s+", "", position)
            if company_core and company_core in position_core and (position_core == company_core or re.search(r"\d+个?月|\d+年", position_core)):
                position = ""
            # 长叙述式职位优先从句尾抽取明确职称，其余正文移入职责，宁空勿错。
            # EN: For long narrative positions, prefer extracting an explicit job title from the end of the sentence and move the rest into duties — better empty than wrong.
            # JA: 長い叙述式の職位は文末から明確な職名を優先して抽出し、残りの本文は職務に移す。誤るくらいなら空のほうがよい。
            if len(position) > 24 or re.match(r"^(?:19|20)\d{2}年", position):
                title_matches = re.findall(
                    r"([\u4e00-\u9fffA-Za-z/]{2,24}?(?:总经理|副总经理|培训师|工程师|设计师|分析师|经理|主管|主任|总监|专员|助理|顾问|担当|科员|翻译|会计|出纳|文员|秘书|销售|采购|客服|教师|老师|研究员|收银员))",
                    position,
                )
                extracted_title = title_matches[-1].strip() if title_matches else ""
                if not item["position_responsibilities"]:
                    item["position_responsibilities"] = position
                position = extracted_title
            if not position and department and len(department) <= 24 and any(
                token in department for token in ("经理", "主管", "主任", "总监", "专员", "助理", "担当", "工程师", "设计师", "培训师", "翻译", "会计", "出纳", "文员", "销售", "采购", "客服", "教师", "老师", "研究员", "收银员")
            ):
                position, department = department, ""
            if re.fullmatch(r"(?:所属行业|所属部门|年?\d+个?月|\d+年\d*个?月)[：:]?", department.replace(" ", "")):
                department = ""
            item["position"] = position.strip(" :：|｜")
            item["position_dept"] = department.strip(" :：|｜")
            if "兼职" in (item["position"] + item["position_responsibilities"]):
                item["employment_type"] = "兼职"

            # 薪资/公司性质不能占用行业或职位字段。
            # EN: Salary/company type must not occupy the industry or position fields.
            # JA: 給与や会社の性質が業界や職位のフィールドを占めてはならない。
            if re.search(r"\d+\s*[-–~～]\s*\d+\s*(?:元|千|万)\s*/\s*(?:月|年)", item["company_industry"]):
                item["position_salary"] = item["position_salary"] or item["company_industry"]
                item["company_industry"] = ""
            if item["position"] in {"民营", "民营公司", "外资", "外商独资", "合资", "国企", "事业单位", "上市公司"}:
                item["position"] = ""
            work_identity = "|".join(item.get(k, "") for k in ("company_name", "position", "position_dept"))
            strong_company = any(tok in item["company_name"] for tok in ("公司", "集团", "股份", "有限", "工厂", "医院", "事务所", "银行", "株式会社"))
            if not strong_company and any(tok in work_identity for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
                continue
            if item["company_name"] or item["position"]:
                work_key = tuple(item.get(field, "").casefold() for field in WORK_FIELDS)
                if work_key not in seen_works:
                    seen_works.add(work_key)
                    works.append(item)

        educations: list[dict[str, str]] = []
        seen_educations: set[tuple[str, ...]] = set()
        for row in resume.get("education_list") or []:
            item = string_record(row, EDUCATION_FIELDS)
            item["school_start_ym"] = normalize_schema_date(item["school_start_ym"])
            item["school_end_ym"] = normalize_schema_date(item["school_end_ym"])
            education_key = tuple(item[field].casefold() for field in EDUCATION_FIELDS)
            if item["school_name"] and education_key not in seen_educations:
                seen_educations.add(education_key)
                educations.append(item)

        # 同一学校、同一学历被表格重复拆成多行时合并，优先保留有专业和完整日期的那条。
        # EN: When a table splits the same school and degree into several rows, merge them, preferring the one with a major and complete dates.
        # JA: 表によって同じ学校・同じ学歴が複数行に分かれた場合は統合し、専攻と完全な日付のあるものを優先して残す。
        merged_educations: list[dict[str, str]] = []
        for item in educations:
            duplicate_index = next((i for i, old in enumerate(merged_educations)
                if old["school_name"].casefold() == item["school_name"].casefold()
                and old["school_degree_type"] == item["school_degree_type"]
                and (not old["school_major_name"] or not item["school_major_name"]
                     or old["school_major_name"].casefold() == item["school_major_name"].casefold())), None)
            if duplicate_index is None:
                merged_educations.append(item)
                continue
            old = merged_educations[duplicate_index]
            old_score = sum(bool(old.get(k)) for k in EDUCATION_FIELDS)
            new_score = sum(bool(item.get(k)) for k in EDUCATION_FIELDS)
            primary, secondary = (item, old) if new_score > old_score else (old, item)
            for field in EDUCATION_FIELDS:
                if not primary.get(field) and secondary.get(field):
                    primary[field] = secondary[field]
            merged_educations[duplicate_index] = primary
        educations = merged_educations

        certificates: list[dict[str, str]] = []
        seen_certificates: set[tuple[str, str, str]] = set()
        for row in resume.get("certificate_list") or []:
            item = string_record(row, ("certificate_name", "certificate_type", "certificate_time"))
            item["certificate_time"] = normalize_schema_date(item["certificate_time"])
            certificate_key = (item["certificate_name"].casefold(), item["certificate_type"].casefold(), item["certificate_time"])
            if item["certificate_name"] and certificate_key not in seen_certificates:
                seen_certificates.add(certificate_key)
                certificates.append(item)

        languages: list[dict[str, str]] = []
        for row in resume.get("language_list") or []:
            item = string_record(row, ("language_name", "language_level", "language_certificate", "language_certificate_time"))
            item["language_certificate_time"] = normalize_schema_date(item["language_certificate_time"])
            if item["language_name"]:
                languages.append(item)

        # 语言考试/等级只能进入 language_list；驾驶证、职业资格等仍留在 certificate_list。
        # EN: Language exams/levels may go only into language_list; driving licences, professional qualifications etc. stay in certificate_list.
        # JA: 語学試験・レベルは language_list にだけ入れる。運転免許や職業資格などは certificate_list に残す。
        retained_certificates: list[dict[str, str]] = []
        language_cert_patterns = (
            ("日语", re.compile(r"日语|日本語|JLPT|J[.-]?TEST|N[1-5]\b", re.I)),
            ("英语", re.compile(r"英语|英文|CET[- ]?[46]|TEM[- ]?[48]|TOEIC|TOEFL|IELTS|BEC|托业|托福|雅思", re.I)),
            ("韩语", re.compile(r"韩语|韩国语|TOPIK", re.I)),
            ("德语", re.compile(r"德语|TestDaF|Goethe", re.I)),
            ("法语", re.compile(r"法语|DELF|DALF", re.I)),
        )
        for certificate in certificates:
            certificate_name = certificate["certificate_name"]
            language_name = next((name for name, pattern in language_cert_patterns if pattern.search(certificate_name)), "")
            if not language_name:
                retained_certificates.append(certificate)
                continue
            language_row = next((row for row in languages if row["language_name"] == language_name), None)
            if language_row is None:
                language_row = {"language_name": language_name, "language_level": "", "language_certificate": "", "language_certificate_time": ""}
                languages.append(language_row)
            if certificate_name not in language_row["language_level"]:
                language_row["language_level"] = "；".join(filter(None, (language_row["language_level"], certificate_name)))
            language_row["language_certificate"] = "有"
            if not language_row["language_certificate_time"]:
                language_row["language_certificate_time"] = certificate["certificate_time"]
        certificates = retained_certificates

        skills: list[dict[str, str]] = []
        for row in resume.get("skills_list") or []:
            item = string_record(row, ("skill_name", "skill_level"), {"skill_name": ("skills_name",)})
            if item["skill_name"]:
                skills.append(item)

        trainings: list[dict[str, Any]] = []
        for sequence, row in enumerate(resume.get("training_list") or [], 1):
            item = string_record(row, ("organization_name", "training_name", "start_ym", "end_ym", "certificate_name", "description"), {
                "organization_name": ("training_institution", "institution_name"),
                "start_ym": ("training_start", "start_date"), "end_ym": ("training_end", "end_date"),
            })
            item["start_ym"] = normalize_schema_date(item["start_ym"])
            item["end_ym"] = normalize_schema_date(item["end_ym"])
            identity = item["organization_name"] + "|" + item["training_name"]
            if any(token in identity for token in ("技能特长", "IT技能", "语言能力", "工作经历", "教育经历", "项目经历", "自我评价", "基本信息", "个人信息")):
                continue
            if any(tok in identity for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
                continue
            item["description"] = _strip_non_business_resume_details(item["description"])
            if item["organization_name"] or item["training_name"] or item["description"]:
                trainings.append({"sequence_no": sequence, **item})

        projects: list[dict[str, Any]] = []
        for sequence, row in enumerate(resume.get("project_list") or [], 1):
            item = string_record(row, ("fingerprint", "project_name", "company_or_client", "role_name", "start_ym", "end_ym", "description", "responsibilities", "achievements", "keywords"), {
                "company_or_client": ("company_name", "client_name"), "role_name": ("project_role",),
                "start_ym": ("project_start", "start_date"), "end_ym": ("project_end", "end_date"),
                "description": ("project_description",), "responsibilities": ("project_responsibilities",),
            })
            item["start_ym"] = normalize_schema_date(item["start_ym"])
            item["end_ym"] = normalize_schema_date(item["end_ym"])
            identity = "|".join(item[k] for k in ("project_name", "company_or_client", "role_name"))
            if any(tok in identity for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
                continue
            item["description"] = _strip_non_business_resume_details(item["description"])
            item["responsibilities"] = _strip_non_business_resume_details(item["responsibilities"])
            if item["project_name"] or item["description"]:
                projects.append({"sequence_no": sequence, **item})

        communications: list[dict[str, str]] = []
        for row in resume.get("communication_list") or []:
            item = string_record(row, ("communicate_time", "communicate_content"))
            if item["communicate_content"]:
                communications.append(item)

        canonical_resumes.append({
            "resume_language": language,
            "base_info": base,
            "expected_list": expected_list,
            "work_experiences": works,
            "education_list": educations,
            "certificate_list": certificates,
            "language_list": languages,
            "skills_list": skills,
            "training_list": trainings,
            "project_list": projects,
            "communication_list": communications,
        })

    # 某些“中日文”模板只有一套中文/中日混排正文，旧解析器会把同一份内容
    # 复制成 zh、jp 两个 resume。完全相同的语言副本不是独立履历版本，应折叠。
    # EN: Some "Chinese-Japanese" templates have only one set of Chinese / mixed Chinese-Japanese body text, and the old parser copied the same content
    #     into two resumes, zh and jp. Identical language copies are not independent résumé versions and should be folded.
    # JA: 一部の「中日」テンプレートには中国語または中日混在の本文が 1 組しかないが、旧パーサーは同じ内容を
    #     zh と jp の 2 つの resume に複製していた。完全に同一の言語のコピーは独立した履歴書の版ではないため畳み込む。
    distinct_resumes: list[dict[str, Any]] = []
    seen_resume_payloads: set[str] = set()
    for resume in canonical_resumes:
        comparable = copy.deepcopy(resume)
        comparable.pop("resume_language", None)
        marker = json.dumps(comparable, ensure_ascii=False, sort_keys=True)
        if marker in seen_resume_payloads:
            continue
        seen_resume_payloads.add(marker)
        distinct_resumes.append(resume)
    canonical_resumes = distinct_resumes or canonical_resumes[:1]

    first = canonical_resumes[0]
    empty_expected = {field: "" for field in EXPECTED_INFO_FIELDS}
    empty_current = {field: ("全职" if field == "employment_type" else "") for field in WORK_FIELDS[:15]}
    empty_education = {field: "" for field in EDUCATION_FIELDS}
    current = {field: first["work_experiences"][0].get(field, "") for field in WORK_FIELDS[:15]} if first["work_experiences"] else empty_current
    education = {field: first["education_list"][0].get(field, "") for field in EDUCATION_FIELDS} if first["education_list"] else empty_education
    return {
        "base_info": copy.deepcopy(first["base_info"]),
        "expected_info": copy.deepcopy(first["expected_list"][0] if first["expected_list"] else empty_expected),
        "current_info": current,
        "education_info": education,
        "resumes": canonical_resumes,
    }


def rebuild_raw_text(resumes: list[dict[str, Any]]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    def collect(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key not in {"sequence_no", "fingerprint", "resume_language", "keywords"}:
                    collect(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, str):
            text = value.strip()
            marker = re.sub(r"\s+", "", text).casefold()
            if text and marker not in seen:
                seen.add(marker)
                values.append(text)
    collect(resumes)
    return "\n".join(values)


def validate_semantic_quality(record: dict[str, Any]) -> list[str]:
    """补充 complete-v1 结构校验覆盖不到的中文字段语义污染检查。

    EN: Additional check for semantic pollution in Chinese fields that the complete-v1 structural validation does not cover.

    JA: complete-v1 の構造検証ではカバーできない中国語フィールドの意味的な汚染を追加でチェックする。
    """
    issues: list[str] = []
    structured = record.get("structured_data") or {}
    action_heads = (
        "负责", "协助", "参与", "安排", "管理", "制定", "完成", "处理", "维护",
        "组织", "跟进", "提供", "开发", "设计", "执行", "支持", "就职于", "任职于",
    )
    organization_marks = (
        "公司", "集团", "银行", "证券", "保险", "基金", "工厂", "厂", "店", "馆",
        "医院", "学校", "大学", "学院", "研究院", "研究所", "事务所", "中心", "机构",
    )
    industry_only = (
        "原材料和加工", "石油/化工/矿产/地质", "合资", "外资", "民营", "国企",
        "互联网", "贸易", "制造业", "服务业",
    )
    for resume_index, resume in enumerate(structured.get("resumes") or []):
        for work_index, work in enumerate(resume.get("work_experiences") or []):
            company = str(work.get("company_name") or "").strip()
            position = str(work.get("position") or "").strip()
            prefix = f"resume_{resume_index}_work_{work_index}"
            if company.startswith(action_heads):
                issues.append(f"{prefix}_company_action_phrase")
            if any(token in company for token in ("是否有", "写出姓名", "工作描述", "工作内容", "岗位职责", "求职意向", "培训内容", "培训课程", "课程内容")):
                issues.append(f"{prefix}_company_form_or_section_text")
            if company in industry_only or (not any(mark in company for mark in organization_marks) and len(company) > 24):
                issues.append(f"{prefix}_company_not_organization")
            if re.match(r"^\d+", company) and ("、" in company or "，" in company or len(company) > 15):
                issues.append(f"{prefix}_company_numbered_description")
            if len(position) > 24 or (re.match(r"^\d+", position) and len(position) > 8):
                issues.append(f"{prefix}_position_description")
            start = str(work.get("position_start") or "")
            end = str(work.get("position_resigned") or "")
            if start and end and start > end:
                issues.append(f"{prefix}_date_order")

        for education_index, education in enumerate(resume.get("education_list") or []):
            school = str(education.get("school_name") or "").strip()
            prefix = f"resume_{resume_index}_education_{education_index}"
            if school.startswith(("请从", "（请", "(请", "月 ", "月　")):
                issues.append(f"{prefix}_school_instruction_or_date_fragment")
            if any(token in school for token in ("工作描述", "工作经历", "有限公司", "是否有亲戚")):
                issues.append(f"{prefix}_school_section_pollution")
            start = str(education.get("school_start_ym") or "")
            end = str(education.get("school_end_ym") or "")
            if start and end and start > end:
                issues.append(f"{prefix}_date_order")
    return list(dict.fromkeys(issues))


def discard_semantically_invalid_rows(structured: dict[str, Any]) -> None:
    """只丢弃明显不是目标字段的数据；不猜测、不改写真实经历。

    EN: Only discard data that is obviously not the target field; do not guess and do not rewrite real experiences.

    JA: 明らかに対象フィールドではないデータだけを捨てる。推測はせず、実際の経歴を書き換えない。
    """
    action_heads = (
        "负责", "协助", "参与", "安排", "管理", "制定", "完成", "处理", "维护",
        "组织", "跟进", "提供", "开发", "设计", "执行", "支持", "就职于", "任职于",
    )
    organization_marks = (
        "公司", "集团", "银行", "证券", "保险", "基金", "工厂", "厂", "店", "馆",
        "医院", "学校", "大学", "学院", "研究院", "研究所", "事务所", "中心", "机构",
    )
    industry_only = {
        "原材料和加工", "石油/化工/矿产/地质", "合资", "外资", "民营", "国企",
        "互联网", "贸易", "制造业", "服务业",
    }
    for resume in structured.get("resumes") or []:
        clean_work: list[dict[str, Any]] = []
        for work in resume.get("work_experiences") or []:
            if not isinstance(work, dict):
                continue
            company = str(work.get("company_name") or "").strip()
            if len(company) > 40:
                trailing_org = re.search(
                    r"([\u4e00-\u9fffA-Za-z0-9（）()·]{2,30}(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院))$",
                    company,
                )
                if trailing_org:
                    company = trailing_org.group(1)
                    work["company_name"] = company
                else:
                    continue
            if company.startswith(action_heads):
                continue
            if any(token in company for token in ("是否有", "写出姓名", "工作描述", "工作内容", "岗位职责", "求职意向", "培训内容", "培训课程", "课程内容")):
                continue
            if re.match(r"^\d+", company) and ("、" in company or "，" in company or len(company) > 15):
                continue
            if company in industry_only or (not any(mark in company for mark in organization_marks) and len(company) > 24):
                continue
            position = str(work.get("position") or "").strip()
            if len(position) > 24 or (re.match(r"^\d+", position) and len(position) > 8):
                work["position"] = ""
            start = str(work.get("position_start") or "")
            end = str(work.get("position_resigned") or "")
            if start and end and start > end:
                work["position_start"], work["position_resigned"] = end, start
            clean_work.append(work)
        resume["work_experiences"] = clean_work

        clean_education: list[dict[str, Any]] = []
        for education in resume.get("education_list") or []:
            if not isinstance(education, dict):
                continue
            school = str(education.get("school_name") or "").strip()
            if school.startswith(("请从", "（请", "(请", "月 ", "月　")):
                continue
            if any(token in school for token in ("工作描述", "工作经历", "有限公司", "是否有亲戚")):
                continue
            start = str(education.get("school_start_ym") or "")
            end = str(education.get("school_end_ym") or "")
            if start and end and start > end:
                education["school_start_ym"], education["school_end_ym"] = end, start
            clean_education.append(education)
        resume["education_list"] = clean_education


# =============================================================================
# Section 化核心分块引擎 (Sectionization Engine)
# 先将简历切割拆分为 10 大标准 Section 块，再按 Block 独立做字段充填，切断越界污染
# =============================================================================
# EN: =============================================================================
#     Core sectionization engine
#     First split the résumé into the 10 standard section blocks, then fill fields independently per block, cutting off out-of-bounds pollution
#     =============================================================================
# JA: =============================================================================
#     セクション化の中核エンジン（Sectionization Engine）
#     まず履歴書を 10 の標準セクションブロックに分割し、ブロックごとに独立してフィールドを埋めて、範囲外からの汚染を断つ
#     =============================================================================

from dataclasses import dataclass

@dataclass
class RawBlock:
    title: str
    lines: list[str]
    content: str

def split_into_generic_blocks(text: str) -> list[RawBlock]:
    """100% 零偏见通用结构拆分器：零预设类别，纯物理结构拆分。

    EN: 100% bias-free generic structural splitter: no preset categories, purely physical structural splitting.

    JA: 100% 先入観のない汎用の構造分割器：カテゴリを前提とせず、純粋に物理的な構造で分割する。
    """
    blocks: list[RawBlock] = []
    current_title = "HEADER"
    current_lines: list[str] = []

    lines = (text or "").splitlines()
    for line in lines:
        ln = line.strip()
        if not ln:
            continue

        clean_ln = re.sub(r"^[\s#*=\-【\[（(]+", "", ln)
        clean_ln = re.sub(r"[\s#*=\-】\]）):：]+$", "", clean_ln).strip()
        
        is_title = False
        TOP_SECTION_TITLES = ("基本信息", "个人信息", "个人资料", "联系方式", "求职意向", "职业目标", "期望工作", "自我评价", "个人总结", "个人优势",
                              "工作经历", "工作经验", "工作背景", "工作履历", "职业经历", "最近工作",
                              "教育背景", "教育经历", "学历背景", "最高学历", "项目经历", "项目经验", "项目背景", "项目列表",
                              "专业技能", "IT技能", "技能特长", "语言能力", "外语水平", "外语能力", "所获证书", "证书说明", "培训经历", "在校实践", "校内职务")
        if len(clean_ln) <= 20 and not any(c in clean_ln for c in "，,。.；;！!？?"):
            if any(clean_ln == kw or clean_ln.startswith(kw) for kw in TOP_SECTION_TITLES):
                is_title = True

        if is_title:
            if current_lines:
                blocks.append(RawBlock(title=current_title, lines=list(current_lines), content="\n".join(current_lines).strip()))
            current_title = clean_ln
            current_lines = []
            if "：" in ln or ":" in ln:
                after_colon = re.sub(r"^.*?[：:]\s*", "", ln).strip()
                if after_colon:
                    current_lines.append(after_colon)
        else:
            current_lines.append(ln)

    if current_lines:
        blocks.append(RawBlock(title=current_title, lines=list(current_lines), content="\n".join(current_lines).strip()))

    return blocks

def parse_resume_sections(text: str) -> dict[str, str]:
    """通过 review 字符串内容本身做通用语义匹配路由归类。

    EN: Generic semantic matching that routes and classifies by the content of the review string itself.

    JA: review の文字列の内容そのものに基づく汎用的な意味マッチングで振り分け・分類する。
    """
    # 核心策略：优先使用 split_resume_sections（基于 SECTION_PATTERNS 正则的精准板块切割，已修复
    # 教育状况 / 社会实践 / 教育背景粘连日期 等问题）；仅对它没切出来的空板块，再 fallback 到
    # 旧逻辑 split_into_generic_blocks + 关键词标题匹配。
    # EN: Core strategy: prefer split_resume_sections (precise section splitting based on the SECTION_PATTERNS regexes, which has fixed
    #     issues such as dates stuck to 教育状况 / 社会实践 / 教育背景); only for empty sections it did not split out do we fall back to
    #     the old logic split_into_generic_blocks + keyword heading matching.
    # JA: 中核の方針：split_resume_sections（SECTION_PATTERNS の正規表現による精密なセクション分割で、
    #     教育状况 / 社会实践 / 教育背景 に日付がくっつく問題などは修正済み）を優先する。それで切り出せなかった空のセクションだけ、
    #     旧来の split_into_generic_blocks + キーワードによる見出しマッチングにフォールバックする。
    res_map = {
        "header": "",
        "job_intention": "",
        "self_evaluation": "",
        "work_experience": "",
        "education": "",
        "project_experience": "",
        "skills": "",
        "languages": "",
        "certificates": "",
        "trainings": "",
    }

    # —— Step 1: 先跑新版 SECTION_PATTERNS 切割（split_resume_sections）
    # EN: —— Step 1: first run the new SECTION_PATTERNS split (split_resume_sections)
    # JA: —— ステップ 1：まず新しい SECTION_PATTERNS による分割（split_resume_sections）を実行する
    try:
        split_res = split_resume_sections(text)
        _KEY_MAP = {
            "header": "header",
            "job_intention": "job_intention",
            "self_evaluation": "self_evaluation",
            "work": "work_experience",
            "education": "education",
            "project": "project_experience",
            "skills": "skills",
            "language": "languages",
            "certificates": "certificates",
            "training": "trainings",
        }
        for old_k, new_k in _KEY_MAP.items():
            v = (split_res.get(old_k) or "").strip()
            if v:
                res_map[new_k] = v
    except Exception:
        split_res = {}

    # —— Step 2: 对 Step 1 中仍然为空的板块，使用旧版 split_into_generic_blocks 作为兜底
    # EN: —— Step 2: for sections still empty after step 1, use the old split_into_generic_blocks as a fallback
    # JA: —— ステップ 2：ステップ 1 の後も空のセクションには、旧来の split_into_generic_blocks を最終手段として使う
    _need_fallback = any(not v for v in res_map.values())
    if _need_fallback:
        blocks = split_into_generic_blocks(text)
        work_lines, edu_lines, proj_lines, train_lines, skill_lines, lang_lines, cert_lines = [], [], [], [], [], [], []
        header_extra, job_extra, summ_extra = "", "", ""

        for b in blocks:
            t = b.title
            cnt = b.content

            # 核心：即使标题叫「个人信息」或「HEADER」，只要内容包含真实公司与日期，也属于工作经历
            # EN: Key point: even if the heading is "个人信息" (personal info) or "HEADER", as long as the content contains a real company and dates it belongs to work history
            # JA: 要点：見出しが「个人信息」（個人情報）や「HEADER」であっても、内容に実在の会社と日付があれば職歴に属する
            is_work_content = any(k in cnt for k in ("有限公司", "股份有限公司", "集团", "办事处", "有限责任公司", "公司")) and bool(re.search(r"(?:19|20)\d{2}[./年\-]\d{1,2}", cnt))

            if any(k in t for k in ("求职意向", "职业目标", "意向", "期望")):
                job_extra += "\n" + cnt
            elif any(k in t for k in ("自我评价", "自我鉴定", "个人总结", "个人优势")):
                summ_extra += "\n" + cnt
            elif any(k in t for k in ("教育", "学历", "学位")):
                edu_lines.append(cnt)
            elif any(k in t for k in ("项目", "工程", "系统")):
                proj_lines.append(cnt)
            elif any(k in t for k in ("培训", "在校实践", "社会实践", "社会活动", "在校学习", "校内职务")):
                train_lines.append(cnt)
            elif any(k in t for k in ("工作经历", "工作经验", "工作背景", "工作履历", "职业经历", "最近工作", "当前状况")) or is_work_content:
                work_lines.append(cnt)
            elif any(k in t for k in ("技能", "IT", "专长")):
                skill_lines.append(cnt)
            elif any(k in t for k in ("语言", "外语", "英语", "日语")):
                lang_lines.append(cnt)
            elif any(k in t for k in ("证书", "认证", "资格")):
                cert_lines.append(cnt)
            elif t == "HEADER" or any(k in t for k in ("信息", "资料", "概况", "联系方式")):
                header_extra += "\n" + cnt
                if is_work_content:
                    work_lines.append(cnt)
            else:
                if is_work_content or (any(k in cnt for k in ("有限公司", "股份有限公司", "集团", "办事处", "有限责任公司", "公司")) and ("工作" in cnt or "职责" in cnt or "描述" in cnt or "部门" in cnt or "专员" in cnt or "经理" in cnt)):
                    work_lines.append(cnt)
                elif any(k in cnt for k in ("大学", "学院", "学校")) and any(k in cnt for k in ("本科", "大专", "硕士", "毕业", "专业")):
                    edu_lines.append(cnt)
                elif any(k in cnt for k in ("项目描述", "项目职责", "项目名称", "研发项目")):
                    proj_lines.append(cnt)

        # 仅在 Step 1 没拿到内容时，用旧结果补齐
        # EN: Fill in from the old result only when step 1 got no content
        # JA: ステップ 1 で内容が取れなかった場合だけ、旧来の結果で補う
        if not res_map["header"]:
            res_map["header"] = header_extra.strip()
        if not res_map["job_intention"]:
            res_map["job_intention"] = job_extra.strip()
        if not res_map["self_evaluation"]:
            res_map["self_evaluation"] = summ_extra.strip()
        if not res_map["work_experience"]:
            res_map["work_experience"] = "\n".join(work_lines).strip()
        if not res_map["education"]:
            res_map["education"] = "\n".join(edu_lines).strip()
        if not res_map["project_experience"]:
            res_map["project_experience"] = "\n".join(proj_lines).strip()
        if not res_map["trainings"]:
            res_map["trainings"] = "\n".join(train_lines).strip()
        if not res_map["skills"]:
            res_map["skills"] = "\n".join(skill_lines).strip()
        if not res_map["languages"]:
            res_map["languages"] = "\n".join(lang_lines).strip()
        if not res_map["certificates"]:
            res_map["certificates"] = "\n".join(cert_lines).strip()
    return res_map


# =============================================================================
# 统一 DOM→纯文本 + 合并来自四大平台的文本预处理/粘连拆分/日期拼接
# =============================================================================
# EN: =============================================================================
#     Unified DOM → plain text + merged text pre-processing / unsticking / date joining from the four major platforms
#     =============================================================================
# JA: =============================================================================
#     DOM → プレーンテキストの統一 + 4 大プラットフォーム由来のテキスト前処理・くっついた文字の分離・日付の結合を統合
#     =============================================================================

def _base_plain_extract(html_text: str) -> str:
    """BeautifulSoup 基本 DOM→文本，附加必要换行。

    EN: Basic BeautifulSoup DOM → text, adding the necessary line breaks.

    JA: BeautifulSoup による基本的な DOM → テキスト変換。必要な改行を付け加える。
    """
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "xml", "meta", "link", "head"]):
            tag.decompose()
        for td in soup.find_all(["td", "th"]):
            td.append("  ")
        for tr in soup.find_all("tr"):
            tr.append("\n")
        for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "br"]):
            p.append("\n")
        raw = soup.get_text("\n")
    except Exception:
        raw = re.sub(r"<[^>]+>", "\n", html_text)

    # Newpage: 清理 Word 宏残留（INCLUDEPICTURE / HYPERLINK / PAGE）
    # EN: Newpage: clean up leftover Word macros (INCLUDEPICTURE / HYPERLINK / PAGE)
    # JA: Newpage：Word のマクロの残骸（INCLUDEPICTURE / HYPERLINK / PAGE）を除去する
    raw = re.sub(r'INCLUDEPICTURE\s+"cid:[^"]*"\s+\\\*\s*MERGEFORMAT\s*', "", raw)
    raw = re.sub(r'PAGE\s+\\\*\s*MERGEFORMAT\s*\d*', "", raw)
    raw = re.sub(r'HYPERLINK\s+"[^"]*"\s+\\o\s+"[^"]*"\s*', "", raw)
    raw = re.sub(r'HYPERLINK\s+"[^"]*"\s+\\l\s+"[^"]*"\s+\\t\s+"[^"]*"\s*', "", raw)
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)


def _merge_51job_date_breaks(text: str) -> str:
    """（来自 51job）修复日期被换行切断的问题：2013\n/3--至今 / 2013/3--2018\n/5。

    EN: (From 51job) Fix dates broken by a line break, such as "2013" + newline + "/3--至今" and "2013/3--2018" + newline + "/5".

    JA: （51job 由来）改行で分断された日付を修復する。例：「2013」+ 改行 +「/3--至今」、「2013/3--2018」+ 改行 +「/5」。
    """
    lines = text.split("\n")
    merged: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines) and re.fullmatch(r"(?:19|20)\d{2}", cur):
            nxt = lines[i + 1]
            if re.match(r"/\d", nxt):
                cur = cur + nxt
                i += 1
        m = re.search(r"(?:--|[-—–~～至到一])(?:19|20)\d{2}$", cur)
        if m and i + 1 < len(lines) and re.match(r"/\d", lines[i + 1]):
            cur = cur + lines[i + 1]
            i += 1
        if re.fullmatch(r"(?:19|20)\d{2}", cur) and i + 2 < len(lines):
            mid = lines[i + 1]
            tail = lines[i + 2]
            if re.match(r"/\d.+(?:19|20)\d{2}$", mid) and re.match(r"/\d", tail):
                cur = cur + mid + tail
                i += 2
        merged.append(cur)
        i += 1
    return "\n".join(merged)


def _preprocess_glued_text(text: str) -> str:
    """（来自智联招聘）粘连文本预处理：在板块标题和字段标签前插入换行，拆分多字段挤在一个 <p> 的问题。

    EN: (From Zhaopin) Pre-processing of stuck-together text: insert line breaks before section headings and field labels, splitting multiple fields squeezed into one <p>.

    JA: （Zhaopin 由来）くっついたテキストの前処理：セクション見出しとフィールドのラベルの前に改行を入れ、1 つの <p> に詰め込まれた複数のフィールドを分ける。
    """
    if not text:
        return text

    section_headers = [
        "在校学习情况", "在校实践经历", "特长职业目标", "所获证书",
        "工作经历", "教育经历", "项目经历", "语言能力", "专业技能",
        "自我评价", "求职意向", "培训经历", "活动描述", "兴趣爱好",
        "特长",
    ]
    field_labels = [
        "期望工作地区", "期望工作性质", "期望从事职业", "期望从事行业",
        "期望月薪", "目前状况",
        "简历更新时间", "简历下载时间", "简历名称",
        "工作描述", "证书说明", "企业性质", "规模", "分数",
        "培训机构", "培训地点", "所获证书", "培训描述",
    ]
    lang_names = ["西班牙语", "意大利语", "葡萄牙语", "阿拉伯语",
                  "英语", "日语", "德语", "法语", "韩语", "俄语", "普通话", "粤语"]

    result = text

    headers_sorted = sorted(section_headers, key=len, reverse=True)
    header_pattern = "|".join(re.escape(h) for h in headers_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({header_pattern})(?=\s|$)",
        r"\n\1",
        result,
    )

    labels_sorted = sorted(field_labels, key=len, reverse=True)
    label_pattern = "|".join(re.escape(l) for l in labels_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({label_pattern})([：:])",
        r"\n\1\2",
        result,
    )

    langs_sorted = sorted(lang_names, key=len, reverse=True)
    lang_pattern = "|".join(re.escape(l) for l in langs_sorted)
    result = re.sub(
        rf"(?<=[^\n])[ \t]*({lang_pattern})([：:])",
        r"\n\1\2",
        result,
    )

    result = re.sub(r"([。．\.]\s*)证书(?=\n|$)", r"\1\n证书", result)
    return result


def normalize_dates_text(text: str) -> str:
    """（来自 Newpage + 通用）日期与英文单词粘连拆分 + 基本日期规范化。

    EN: (From Newpage + generic) Split dates stuck to English words + basic date normalisation.

    JA: （Newpage + 汎用）英単語にくっついた日付を分離 + 基本的な日付の正規化。
    """
    text = re.sub(r"(\d{4}[./．]\d{1,2})([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"(\d{4}\.\d{2})\s*[-—–~～至到]+\s*(\d{4}\.\d{2})", r"\1 - \2", text)
    text = re.sub(
        r"(\d{4}\.\d{2})\s*[-—–~～至到]+\s*(至今|现在|目前|Present|Current)",
        r"\1 - 至今",
        text,
        flags=re.I,
    )
    return text


def html_to_plain_text(html_text: str) -> str:
    """统一入口：DOM 提取 → 宏清理 → 51job 日期断行合并 → 智联粘连拆分 → 通用日期规范化。

    EN: Unified entry: DOM extraction → macro cleanup → 51job date line-break joining → Zhaopin unsticking → generic date normalisation.

    JA: 統一エントリ：DOM 抽出 → マクロの除去 → 51job の日付の改行の結合 → Zhaopin のくっつきの分離 → 汎用的な日付の正規化。
    """
    base = _base_plain_extract(html_text)
    step1 = _merge_51job_date_breaks(base)
    step2 = _preprocess_glued_text(step1)
    return normalize_dates_text(step2)


def semantic_dom_section_text(html_text: str, section_types: tuple[str, ...]) -> str:
    """直接读取生成 HTML 的语义 section；DOM 缺失时由调用方回退纯文本。

    EN: Read the semantic sections of the generated HTML directly; when the DOM is missing, the caller falls back to plain text.

    JA: 生成された HTML のセマンティックな section を直接読む。DOM がない場合は呼び出し元がプレーンテキストに戻す。
    """
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
    except Exception:
        return ""
    chunks: list[str] = []
    seen: set[str] = set()
    for section_type in section_types:
        for node in soup.select(f'section[data-section-type="{section_type}"]'):
            value = node.get_text("\n", strip=True)
            marker = re.sub(r"\s+", "", value).casefold()
            if value and marker not in seen:
                seen.add(marker)
                chunks.append(value)
        # 旧版/复杂表格简历常把章节类型标在 h2 上，而不是另包一层 section。
        # 此时读取标题及其同级内容，直到下一个带章节类型的 h2；不能退回整页正则，
        # 否则教育描述里的“专业技能”等普通短语会把真正的后续学历截断。
        # EN: Old/complex table résumés often mark the section type on the h2 rather than wrapping it in a section.
        #     In that case read the heading and its sibling content up to the next h2 with a section type; do not fall back to whole-page regexes,
        #     otherwise ordinary phrases like "专业技能" (professional skills) in an education description would cut off the real subsequent degrees.
        # JA: 旧来の・複雑な表形式の履歴書では、セクションの種類を section で包まずに h2 に付けていることが多い。
        #     その場合は見出しとその兄弟要素の内容を、セクション種類付きの次の h2 まで読む。ページ全体の正規表現に戻ってはならない。
        #     さもないと学歴の説明にある「专业技能」（専門スキル）などの普通の語句が、後続の本当の学歴を切り落としてしまう。
        for heading in soup.select(f'h2[data-section-type="{section_type}"]'):
            parts = [heading.get_text("\n", strip=True)]
            for sibling in heading.next_siblings:
                if getattr(sibling, "name", None) == "h2" and sibling.get("data-section-type"):
                    break
                if hasattr(sibling, "get_text"):
                    part = sibling.get_text("\n", strip=True)
                    if part:
                        parts.append(part)
            value = "\n".join(part for part in parts if part).strip()
            marker = re.sub(r"\s+", "", value).casefold()
            if value and marker not in seen:
                seen.add(marker)
                chunks.append(value)
    return "\n".join(chunks).strip()


# =============================================================================
# 语言映射表 + 个人素质关键词（skills_list → base_info.pr）
# =============================================================================
# EN: =============================================================================
#     Language mapping table + personal quality keywords (skills_list → base_info.pr)
#     =============================================================================
# JA: =============================================================================
#     言語の対応表 + 個人の資質を表すキーワード（skills_list → base_info.pr）
#     =============================================================================

LANGUAGE_NAME_MAP: dict[str, str] = {
    # 英文名 -> 中文名
    # EN: English name -> Chinese name
    # JA: 英語名 -> 中国語名
    "English": "英语", "Mandarin": "普通话", "Cantonese": "粤语",
    "Japanese": "日语", "Korean": "韩语", "German": "德语", "French": "法语",
    "Spanish": "西班牙语", "Italian": "意大利语", "Portuguese": "葡萄牙语",
    "Russian": "俄语", "Arabic": "阿拉伯语", "Thai": "泰语",
    "Chinese": "中文",
}

LANGUAGE_LEVEL_MAP: dict[str, str] = {
    # 英语级别
    # EN: English levels
    # JA: 英語のレベル
    "CET-4": "大学英语四级", "CET4": "大学英语四级", "CET-6": "大学英语六级", "CET6": "大学英语六级",
    "TEM-4": "专业英语四级", "TEM4": "专业英语四级", "TEM-8": "专业英语八级", "TEM8": "专业英语八级",
    "TOEFL": "托福", "IELTS": "雅思", "GRE": "GRE", "GMAT": "GMAT",
    "BEC": "剑桥商务英语",
    # 日语
    # EN: Japanese
    # JA: 日本語
    "JLPT N1": "日语能力一级", "JLPT N2": "日语能力二级", "JLPT N3": "日语能力三级",
    "N1": "日语能力一级", "N2": "日语能力二级", "N3": "日语能力三级",
    "日语一级": "日语能力一级", "日语二级": "日语能力二级",
    # 通用描述
    # EN: Generic descriptions
    # JA: 汎用的な説明
    "Native": "母语", "Mother Tongue": "母语", "Fluent": "流利", "Proficiency": "熟练",
    "Intermediate": "中级", "Basic": "基础", "Conversational": "会话",
}

PERSONAL_QUALITY_KEYWORDS_ZH = (
    "沟通能力", "团队精神", "团队协作", "责任心", "责任感", "抗压能力", "学习能力",
    "适应能力", "执行力", "创新能力", "逻辑思维", "分析能力", "解决问题",
    "人际沟通", "表达能力", "组织协调", "时间管理", "自我驱动", "积极主动",
    "认真负责", "细心严谨", "诚实守信", "吃苦耐劳", "踏实肯干", "敬业精神",
    "服务意识", "客户导向", "结果导向", "成本意识", "质量意识", "安全意识",
    "沟通", "协作", "负责", "细心", "耐心", "主动", "热情", "乐观", "开朗",
)

PERSONAL_QUALITY_KEYWORDS_EN = (
    "Communication", "Teamwork", "Team player", "Team work", "Responsibility",
    "Responsible", "Pressure resistance", "Under pressure", "Learning agility",
    "Adaptability", "Execution", "Executive ability", "Innovation", "Creative",
    "Logical thinking", "Analytical", "Problem solving", "Interpersonal",
    "Organized", "Time management", "Self-motivated", "Self driven", "Proactive",
    "Detail-oriented", "Meticulous", "Honest", "Integrity", "Hard working",
    "Diligent", "Dedicated", "Customer oriented", "Result oriented",
    "Communication skills", "Organizational skills",
)

_TRAILING_SECTION_RE = re.compile(
    r"(?:\n\s*|\A)\s*(?:语言能力|专业技能|自我评价|培训经历|项目经历|教育经历|工作经历|在校学习情况|在校实践经历|活动描述|兴趣爱好|特长|职业目标|所获证书|证书|Language|Skills|Self[- ]Assessment|Training|Project|Education|Work Experience|Certificates?|Awards)\s*(?=\n|$)",
    re.I | re.M,
)


# =============================================================================
# 板块截取 + 公司名/邮箱/杂质 通用清理
# =============================================================================
# EN: =============================================================================
#     Section extraction + general clean-up of company names / e-mails / noise
#     =============================================================================
# JA: =============================================================================
#     セクションの切り出し + 会社名・メール・不要文字の汎用的なクレンジング
#     =============================================================================

def _section_block(text: str, start_headers: list[str], stop_headers: list[str]) -> str:
    """从 text 中截取某个板块（开始标题到下一个停止标题之间）。

    EN: Cut a section out of text (from its start heading to the next stop heading).

    JA: text からあるセクション（開始見出しから次の停止見出しまで）を切り出す。
    """
    if not text:
        return ""
    start_pat = "|".join(re.escape(h) for h in start_headers)
    stop_pat = "|".join(re.escape(h) for h in stop_headers)
    m_start = re.search(rf"^\s*(?:{start_pat})(?=\s|$)", text, re.M)
    if not m_start:
        return ""
    rest = text[m_start.end():]
    m_stop = re.search(rf"^\s*(?:{stop_pat})(?=\s|$)", rest, re.M)
    if m_stop:
        return rest[: m_stop.start()].strip()
    return rest.strip()


def _clean_company_name_legacy(name: str) -> str:
    """清理公司名称：去除时长括号、控制字符、字段分隔符、尾部教育信息。

    EN: Clean company names: remove tenure brackets, control characters, field separators and trailing education information.

    JA: 会社名のクレンジング：在職期間の括弧・制御文字・フィールドの区切り・末尾の学歴情報を除く。
    """
    if not name:
        return ""
    name = re.sub(r"^(?:公司名称|公司名|单位名称|单位名|公司|名)\s*[:：]?\s*", "", name)
    name = name.replace("\xa0", " ")
    if "\x07" in name:
        name = name.split("\x07")[0]
    name = name.replace("\r", " ").replace("\n", " ")
    name = re.sub(r"[（(]\s*\d+年\s*\d+个月\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*\d+年\s*[）)]", "", name)
    name = re.sub(r"[（(]\s*[）)]", "", name)
    name = re.sub(
        r"\s+[\u4e00-\u9fffA-Za-z]{1,10}\s+(本科|大专|硕士|博士|专科|中专|高中|学士)$",
        "", name,
    )
    return name.strip(" 　\t\n\r\xa0-—–*·")


def _clean_company_name(comp: str) -> str:
    comp = (comp or "").strip()
    if not comp:
        return ""
    if comp in ("未工作", "待业", "休假", "无", "暂无", "个人兼职", "企划专员", "软件工程师", "体育老师", "网球教练"):
        return ""
    if re.match(r"^\d+\s*个?月?$", comp) or re.match(r"^\d+\s*年$", comp):
        return ""
    if "|" in comp or "｜" in comp or "500-1000" in comp or "民营公司" in comp or "外商独资" in comp or "民营企业" in comp:
        return ""
    if re.search(r"^\s*职\s*位", comp) or re.search(r"^\s*岗\s*位", comp) or re.search(r"^\s*职\s*务", comp):
        return ""
    if comp in ("团队管理", "客户维护", "业务拓展", "日常管理", "人员管理", "技术研发", "项目管理"):
        return ""
    if any(k in comp for k in ("项目职务", "项目职责", "职务：", "职位：", "职  位", "职 位的", "工作内容", "在校实践", "在校学习", "社会活动", "社会实践", "获奖情况", "比赛", "兼职充电", "充电调整", "状态调整")):
        return ""

    comp = re.sub(r"\d+(?:\s*[-–~～至到]\s*\d+)?\s*人$", "", comp).strip()
    comp = re.sub(r"^(?:公司简介|公司描述|公司介绍|公司名称|工作单位名称|公司|名)\s*[:：]?\s*", "", comp)
    comp = re.sub(r"^(?:曾经?\s*)?(?:就职于|任职于|供职于|服务于)\s*", "", comp)
    comp = re.sub(r"[\(（]\s*\d+\s*年?\s*\d*\s*个?月?\s*[\)）]?$", "", comp)
    comp = re.sub(r"\(?\s*\d+\s*年\s*\d*\s*个?月?\s*\)?$", "", comp)
    comp = re.sub(r"^\d+\s*年\s*\d*\s*个?月?$", "", comp)
    comp = re.sub(r"[\s\xa0]+\d+\s*年?\s*\d*\s*个?月?$", "", comp)

    if any(k in comp for k in ("调入", "做起", "现任", "担任", "负责", "主要", "业绩", "描述", "岗位", "职责")) or sum(comp.count(c) for c in "，,。.；;！!？?") >= 1:
        m_comp = re.search(r"([\u4e00-\u9fffA-Za-z0-9()（）]{2,20}(?:有限责任公司|股份有限公司|有限公司|股份|集团|办事处|分公司|事业部|工厂|制造厂|工作室|店|行))", comp)
        if m_comp:
            comp = m_comp.group(1).strip()
        else:
            return ""

    comp = re.sub(r"^(?:(?:19|20)\d{2}[./年\-]?\d{1,2}月?)?\s*(?:调入|调至|来到|加入|入|到)?\s*", "", comp)
    if comp.count("(") > comp.count(")"):
        comp = comp.replace("(", "")
    if comp.count("（") > comp.count("）"):
        comp = comp.replace("（", "")
    # 不能用 str.strip("()（）")：它会把“东陶（上海）有限公司”之外的合法地域括号、
    # 尤其“银行（中国）”的末尾右括号单独削掉。仅去除字段分隔符；整串外包括号才成对去除。
    # EN: str.strip("()（）") must not be used: it would chop legitimate regional brackets, such as in "东陶（上海）有限公司",
    #     and especially the trailing closing bracket of "银行（中国）". Only remove field separators; outer wrapping brackets are removed only as a pair.
    # JA: str.strip("()（）") を使ってはならない。「东陶（上海）有限公司」のような正当な地域名の括弧、
    #     特に「银行（中国）」の末尾の閉じ括弧だけを削ってしまう。フィールドの区切りだけを除去し、文字列全体を包む括弧だけを対で除去する。
    comp = comp.strip(" :：|｜-，,。.；;")
    if (comp.startswith("(") and comp.endswith(")")) or (comp.startswith("（") and comp.endswith("）")):
        comp = comp[1:-1].strip()
    return comp


# 统一的 员工规模 正则 全局 版本（和 parse_work_from_raw_text 内 的 EMPLOYEE_RE_STR 保持 一致）
# EN: Unified global version of the employee-size regex (kept consistent with EMPLOYEE_RE_STR inside parse_work_from_raw_text)
# JA: 従業員規模の正規表現の統一されたグローバル版（parse_work_from_raw_text 内の EMPLOYEE_RE_STR と一致させる）
_POST_EMPLOYEE_RE_STR = r"(?:(?:少于|小于|低于|不超过|不足|不到)?\s*\d+(?:\s*[-–~～至到]\s*\d+)?\s*(?:人以下|人以内|人以上|人)|(?:\d+(?:\s*[-–~～至到]\s*\d+)?\s*人))"
_POST_EMPLOYEE_RE = re.compile(_POST_EMPLOYEE_RE_STR)
_COMP_SIGNS_STRONG = ("公司", "有限公司", "股份", "集团", "工作室", "Inc", "Co", "Ltd", "LLC", "株式会社", "制造厂",
                      "工厂", "分公司", "事业部", "办事处", "银行", "基金", "证券", "保险", "大学", "学院",
                      "研究院", "科学院", "研究所", "医院", "学校", "事务所", "控股")
_COMP_SIGNS_WEAK = ("厂", "院", "局", "店", "行", "社", "所", "网", "部", "中心", "厅", "机构", "机关",
                    "单位", "广场", "大厦", "商城", "超市", "市场", "矿", "站", "队")

def _has_comp_sign_global(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if any(sign in s for sign in _COMP_SIGNS_STRONG):
        return True
    if len(s) >= 3 and any(s.endswith(suf) for suf in _COMP_SIGNS_WEAK):
        return True
    return False

def _is_duration_text_global(s: str) -> bool:
    s_clean = re.sub(r"[\s\u3000\xa0]+", "", (s or "").strip())
    if not s_clean:
        return False
    if re.fullmatch(r"^[（(]?\s*\d+\s*年?\s*\d*\s*个?月?\s*[）)]?$", s_clean):
        return True
    if re.fullmatch(r"^[（(]?\s*\d+\s*个?月\s*[）)]?$", s_clean):
        return True
_POST_IND_NAT_KW = ("外资", "民营", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "非欧美", "中外", "外商",
                    "上市公司", "民营企业", "外资企业", "合资企业", "国有企业", "集体企业", "个体经营")

def _try_extract_attrs_global(s: str) -> tuple[bool, str, str]:
    s2 = (s or "").strip()
    if not ("|" in s2 or "｜" in s2):
        return False, "", ""
    parts = [p.strip() for p in re.split(r"[|｜]", s2) if p.strip()]
    if not parts or len(parts) < 2:
        return False, "", ""
    has_emp = any(bool(_POST_EMPLOYEE_RE.search(p)) for p in parts)
    has_nat = any(any(kw in p for kw in _POST_IND_NAT_KW) for p in parts)
    if not (has_emp or has_nat):
        return False, "", ""
    emps = ""
    for p in parts:
        m = _POST_EMPLOYEE_RE.search(p)
        if m:
            emps = m.group(0); break
    ind_parts = [p for p in parts if not _POST_EMPLOYEE_RE.search(p) and not any(k in p for k in ("公司", "有限", "股份", "集团", "工程师", "技术员", "专员", "助理", "经理", "主管", "装配", "领班"))]
    ind = " | ".join(ind_parts)
    return True, ind, emps


def _normalize_ym_loose(val: str, allow_today_token: bool = False) -> str:
    """把各种日期格式归一化成 YYYY-MM；若 allow_today_token=True，则保留「至今」/「在读」等字面词。
    支持：2012.03 / 2012/03 / 2012-03 / 2012年03月 / 2012-03-01 / 03/2012 / 2012.3 / 2012年3月
    无法解析则返回原值。

    EN: Normalise various date formats into YYYY-MM; if allow_today_token=True, keep literal words like "至今" (present) / "在读" (studying).
    Supports: 2012.03 / 2012/03 / 2012-03 / 2012年03月 / 2012-03-01 / 03/2012 / 2012.3 / 2012年3月
    Returns the original value if it cannot be parsed.

    JA: さまざまな日付の形式を YYYY-MM に正規化する。allow_today_token=True なら「至今」（現在）／「在读」（在学中）などの語をそのまま残す。
    対応：2012.03 / 2012/03 / 2012-03 / 2012年03月 / 2012-03-01 / 03/2012 / 2012.3 / 2012年3月
    解析できなければ元の値を返す。
    """
    v0 = str(val or "").strip()
    if not v0: return ""
    if allow_today_token and v0 in ("至今", "现在", "目前", "在职", "在职中", "在读", "未毕业"):
        return v0
    # 今天 token 不允许保留 → 非法日期，原样返回（如果真的非法后续 valid 会拦）
    # EN: The "today" token is not allowed to be kept → invalid date, return it unchanged (if it really is invalid, valid will block it later)
    # JA: 「今日」のトークンは残せない → 不正な日付としてそのまま返す（本当に不正なら後で valid が弾く）
    if v0 in ("至今", "现在", "目前", "在职", "在职中"):
        # 工作段的「至今」要保留字面量（合法在职状态），再判断 allow_today_token 已在上面覆盖，这里就返回原值由 valid 决定
        # EN: "至今" (present) in work sections must be kept literally (a valid currently-employed state); allow_today_token is already handled above, so return the original value here and let valid decide
        # JA: 職歴の「至今」（現在）は文字どおり残す必要がある（有効な在職状態）。allow_today_token は上で処理済みなので、ここでは元の値を返して valid に判断させる
        if allow_today_token:
            return v0
        else:
            return v0  # 原样返回
            # EN: Return unchanged
            # JA: そのまま返す
    # MM/YYYY (如 03/2012)
    # EN: MM/YYYY (e.g. 03/2012)
    # JA: MM/YYYY（例：03/2012）
    m = re.fullmatch(r"\s*(\d{1,2})\s*[/\.]\s*((?:19|20)\d{2})\s*", v0)
    if m:
        y, mo = int(m.group(2)), int(m.group(1))
        if 1 <= mo <= 12: return f"{y:04d}-{mo:02d}"
    # YYYY.MM / YYYY/MM / YYYY-MM / YYYY.M / YYYY/M
    m = re.fullmatch(r"\s*((?:19|20)\d{2})\s*[\-/.年]\s*(\d{1,2})\s*(?:月)?\s*", v0)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12: return f"{y:04d}-{mo:02d}"
    # YYYY-MM-DD / YYYY/M/D / YYYY年M月D日 → 取前两段 YYYY-MM
    # EN: YYYY-MM-DD / YYYY/M/D / YYYY年M月D日 → take the first two parts, YYYY-MM
    # JA: YYYY-MM-DD / YYYY/M/D / YYYY年M月D日 → 先頭の 2 つの部分 YYYY-MM を取る
    m = re.match(r"\s*((?:19|20)\d{2})\s*[\-/.年]\s*(\d{1,2})\s*(?:月)?\s*[\-/.年月日]\s*\d{1,2}\s*日?\s*$", v0)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12: return f"{y:04d}-{mo:02d}"
    # 只有 年份 19xx 20xx → 原值
    # EN: Year only, 19xx 20xx → original value
    # JA: 年だけ（19xx 20xx）→ 元の値
    m = re.fullmatch(r"\s*(?:19|20)\d{2}\s*", v0)
    if m:
        return v0.strip()
    return v0  # 无法归一化就原样返回（valid会判定）
    # EN: If it cannot be normalised, return it unchanged (valid will decide)
    # JA: 正規化できなければそのまま返す（valid が判定する）

def _postprocess_work_attrs(works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """**最终 安全网**：对 所有 解析器 产生的 work_experiences 统一 再 扫描 一遍：
       - 若 position/position_dept 是 「行业|规模|性质」这种 属性行，拆成 company_industry + company_employees，position/dept 置空
       - 对 空 position 但是 part 里 有 部门/职位 词 的 再 简单 补 一下

    EN: **Final safety net**: scan the work_experiences produced by all parsers once more uniformly:
       - if position/position_dept is an "industry|size|type" attribute line, split it into company_industry + company_employees and clear position/dept
       - for an empty position where a part contains department/position words, do a simple fill-in

    JA: **最後の安全網**：すべてのパーサーが生成した work_experiences を一律にもう一度スキャンする：
       - position/position_dept が「業界|規模|性質」の属性の行なら company_industry + company_employees に分け、position/dept を空にする
       - position が空で part に部署・職位の語がある場合は、簡単に補う
    """
    if not works:
        return works
    # 日期块解析器已经按明确边界得到公司/属性/部门/职位；再次运行启发式
    # swap 会把“沪江网”之类短品牌误换成“民营公司”。全为高置信条目时不再改字段。
    # EN: The date-block parser has already obtained company/attributes/department/position from explicit boundaries; running the heuristic
    #     swap again would wrongly replace short brands such as "沪江网" with "民营公司" (private company). When all entries are high-confidence, fields are no longer changed.
    # JA: 日付ブロックのパーサーは明確な境界から会社・属性・部署・職位をすでに得ている。ヒューリスティックな
    #     swap を再度実行すると「沪江网」のような短いブランド名を「民营公司」（民間企業）に誤って入れ替えてしまう。すべて高信頼の項目ならフィールドを変更しない。
    if all(isinstance(row, dict) and row.get("_source_confidence") == "explicit_date_block" for row in works):
        return works
    # ===== 新增：先对每条的 几个关键字段 做「KV 标签前缀」清洗（如 position="所属行业：互联网" → 清掉标签后给 company_industry）=====
    # —— 关键修复：每个中文词的字之间 允许 1-8 个 空格（兼容 "职    位：销售助理" 这种竖排表格多空格格式）
    # EN: ===== New: first clean "KV label prefixes" from several key fields of each entry (e.g. position="所属行业：互联网" → strip the label and give it to company_industry) =====
    #     —— Key fix: allow 1-8 spaces between the characters of each Chinese word (for multi-space vertical table formats like "职    位：销售助理")
    # JA: ===== 追加：まず各項目の主要フィールドから「KV ラベルの接頭辞」を除去する（例：position="所属行业：互联网" → ラベルを除いて company_industry に回す）=====
    #     —— 重要な修正：中国語の各語の文字間に 1〜8 個の空白を許容する（「职    位：销售助理」のような縦並びの表の複数空白形式に対応）
    def _allow_space(words: tuple[str, ...]) -> str:
        return "|".join(r"\s*".join(list(w)) for w in words)
    _KW_POS_PREFIX = ("所属行业", "所在部门", "公司规模", "公司性质", "企业性质", "公司行业", "月薪",
                      "年薪", "薪资水平", "工号", "职位编号", "公司名称", "企业名称", "工作地点",
                      "工作城市", "工作岗位", "职位", "岗位", "职称", "职务")
    _KW_IND_PREFIX = ("所属行业", "行业类别", "行业", "公司行业", "所属行业类别")
    _KW_EMP_PREFIX = ("公司规模", "人员规模", "员工人数", "企业规模", "企业人数", "公司人数")
    _KW_DEPT_PREFIX = ("所在部门", "所属部门", "部门", "担任部门", "就职部门")
    _KW_SAL_PREFIX = ("月薪", "年薪", "薪资", "工资", "待遇", "薪酬", "薪水")
    _POS_LABEL_RE = re.compile(r"^(?:%s)\s*[:：]\s*" % _allow_space(_KW_POS_PREFIX))
    _IND_LABEL_RE = re.compile(r"^(?:%s)\s*[:：]\s*" % _allow_space(_KW_IND_PREFIX))
    _EMP_LABEL_RE = re.compile(r"^(?:%s)\s*[:：]\s*" % _allow_space(_KW_EMP_PREFIX))
    _DEPT_LABEL_RE = re.compile(r"^(?:%s)\s*[:：]\s*" % _allow_space(_KW_DEPT_PREFIX))
    _SAL_LABEL_RE = re.compile(r"^(?:%s)\s*[:：]\s*" % _allow_space(_KW_SAL_PREFIX))
    for w in works:
        # 1) position: 先剥标签，如果剥完是行业/部门类 → 转到对应字段再清空 position
        # EN: 1) position: strip the label first; if what remains is an industry/department → move it to the corresponding field and clear position
        # JA: 1) position：まずラベルを除き、残りが業界・部署の類なら対応するフィールドに移して position を空にする
        pos = (w.get("position") or "").strip()
        if pos:
            pos_stripped = _POS_LABEL_RE.sub("", pos, count=1).strip()
            if pos_stripped != pos:
                # 剥掉了标签 → 判断剥完的内容是什么
                # 内容含行业关键词 → 填到 company_industry
                # EN: A label was stripped → decide what the remaining content is
                #     Content contains industry keywords → fill company_industry
                # JA: ラベルを除いた → 残った内容が何かを判定する
                #     内容に業界のキーワードがある → company_industry に入れる
                if any(kw in pos_stripped for kw in ("行业", "贸易", "制造", "服务业", "互联网", "IT", "电子", "半导体", "通信", "金融", "银行", "基金", "证券", "保险",
                                                     "医药", "医疗", "能源", "房地产", "建筑", "传媒", "出版", "印刷", "影视", "咨询", "零售", "批发", "物流", "快递",
                                                     "汽车", "零配件", "消费", "快速消费品", "教育", "培训", "化工", "机械", "加工", "检测", "认证", "航天", "航空",
                                                     "新能源", "新材料", "环保", "农业", "食品", "餐饮", "酒店", "旅游", "服装", "纺织", "外资", "民营", "合资", "国企", "上市")):
                    if not w.get("company_industry"):
                        w["company_industry"] = pos_stripped
                    pos = ""
                # 内容匹配员工规模正则 → 填到 company_employees
                # EN: Content matches the employee-size regex → fill company_employees
                # JA: 内容が従業員規模の正規表現にマッチ → company_employees に入れる
                elif _POST_EMPLOYEE_RE.search(pos_stripped):
                    if not w.get("company_employees"):
                        m_e = _POST_EMPLOYEE_RE.search(pos_stripped)
                        if m_e:
                            w["company_employees"] = m_e.group(0)
                    pos = ""
                # 内容是部门后缀 → 填到 position_dept
                # EN: Content has a department suffix → fill position_dept
                # JA: 内容が部署の接尾辞を持つ → position_dept に入れる
                elif pos_stripped.endswith(("部", "室", "组", "科", "处", "课", "厅", "局", "所", "站", "院", "办", "中心")):
                    if not w.get("position_dept"):
                        w["position_dept"] = pos_stripped
                    pos = ""
                else:
                    pos = pos_stripped
            w["position"] = pos
        # 2) company_industry 剥标签
        # EN: 2) Strip the label from company_industry
        # JA: 2) company_industry のラベルを除く
        cind = (w.get("company_industry") or "").strip()
        if cind:
            w["company_industry"] = _IND_LABEL_RE.sub("", cind, count=1).strip()
        # 3) company_employees 剥标签
        # EN: 3) Strip the label from company_employees
        # JA: 3) company_employees のラベルを除く
        cemp = (w.get("company_employees") or "").strip()
        if cemp:
            w["company_employees"] = _EMP_LABEL_RE.sub("", cemp, count=1).strip()
        # 4) position_dept 剥标签
        # EN: 4) Strip the label from position_dept
        # JA: 4) position_dept のラベルを除く
        pdept = (w.get("position_dept") or w.get("department") or "").strip()
        if pdept:
            # —— 先过 _POS_LABEL_RE：有些值错粘了 "职    位：销售助理" 这种职位标签（陈丹妮case）
            #    如果剥掉标签后与原值不同 → 说明这不是部门，而是标签包装的职位/行业/规模 → 置空position_dept
            # EN: —— First pass through _POS_LABEL_RE: some values have a position label like "职    位：销售助理" stuck to them by mistake (a past case)
            #        If the value differs from the original after stripping the label → it is not a department but a labelled position/industry/size → clear position_dept
            # JA: —— まず _POS_LABEL_RE を通す：値に「职    位：销售助理」のような職位ラベルが誤ってくっついていることがある（過去の事例）
            #        ラベルを除いた結果が元の値と異なる → 部署ではなくラベルで包まれた職位・業界・規模 → position_dept を空にする
            stripped_by_pos = _POS_LABEL_RE.sub("", pdept, count=1).strip()
            if stripped_by_pos != pdept:
                # 被_POS_LABEL_RE剥掉了前缀 → 本质是标签包装的属性，不是部门名
                # EN: The prefix was stripped by _POS_LABEL_RE → it is essentially a labelled attribute, not a department name
                # JA: _POS_LABEL_RE で接頭辞が除かれた → 本質的にはラベルで包まれた属性で、部署名ではない
                cleaned_dept = stripped_by_pos
                # 如果结果是纯职位后缀结尾（经理/助理/主管/专员等）→ 完全不是部门 → 置空
                # EN: If the result ends with a pure position suffix (经理/助理/主管/专员: manager/assistant/supervisor/specialist, etc.) → not a department at all → clear it
                # JA: 結果が純粋な職位の接尾辞（经理／助理／主管／专员：マネージャー・アシスタント・主任・担当など）で終わる → 部署ではない → 空にする
                POS_SUFFIX_DETECT = ("经理", "主管", "主任", "总监", "专员", "助理", "顾问", "销售", "代表", "会计", "出纳",
                                     "文员", "秘书", "行政", "人事", "财务", "组长", "科长", "部长", "营业员", "导购",
                                     "业务员", "培训师", "讲师", "编辑", "记者", "设计师", "技术员", "分析师", "工程师",
                                     "翻译", "程序员", "测试员", "数据分析师", "产品运营", "新媒体运营", "文案策划", "市场策划")
                if any(cleaned_dept.endswith(suf) or cleaned_dept == suf for suf in POS_SUFFIX_DETECT):
                    cleaned_dept = ""
            else:
                cleaned_dept = _DEPT_LABEL_RE.sub("", pdept, count=1).strip()
            w["position_dept"] = cleaned_dept
        # 5) position_salary 剥标签 + 格式校验
        # EN: 5) Strip the label from position_salary + format check
        # JA: 5) position_salary のラベルを除く + 形式チェック
        psal = (w.get("position_salary") or "").strip()
        if psal:
            psal = _SAL_LABEL_RE.sub("", psal, count=1).strip()
            if psal and not re.search(r"(?:\d+\s*(?:元|千|万|K|k)\s*(?:[~～\-\/]\s*\d+\s*(?:元|千|万|K|k)?)?\s*(?:/\s*(?:月|年))?|面议|待面议)", psal):
                psal = ""
            w["position_salary"] = psal
        # 6) employment_type 剥标签 + 严格枚举
        # EN: 6) Strip the label from employment_type + strict enumeration
        # JA: 6) employment_type のラベルを除く + 厳格な列挙
        et = (w.get("employment_type") or "").strip()
        if et:
            et_clean = re.sub(r"^(?:工作性质|雇佣形式|用工形式|求职状态|就业类型|职位类型)[：:]\s*", "", et).strip()
            VALID_EMP_TYPES_POST = {"全职", "兼职", "实习", "临时", "钟点", "合同", "劳务派遣", "应届毕业生", "在校学生", "全职+兼职"}
            if et_clean in VALID_EMP_TYPES_POST:
                w["employment_type"] = et_clean
            elif et not in VALID_EMP_TYPES_POST:
                w["employment_type"] = "全职"
    for w in works:
        for field in ("position", "position_dept"):
            s = (w.get(field) or "").strip()
            if not ("|" in s or "｜" in s):
                continue
            parts = [p.strip() for p in re.split(r"[|｜]", s) if p.strip()]
            if len(parts) < 2:
                continue
            has_emp = any(bool(_POST_EMPLOYEE_RE.search(p)) for p in parts)
            has_nat = any(any(kw in p for kw in _POST_IND_NAT_KW) for p in parts)
            if not (has_emp or has_nat):
                continue
            # **注意**：只要 是 | 分隔 + 有 员工规模/公司性质，就 100% 是 行业|规模|性质 属性 组合行！
            # 真正 的 position 不可能 是 这种 格式！哪怕 first 以 "公司" 结尾（如「多元化业务集团公司」），那 也是 行业 描述！
            # → 直接 拆！不需要 检查 first 是不是 公司名！（因为 company_name 字段 已经 有 真正 的 公司名了）
            # EN: **Note**: whenever it is |-separated and has employee size / company type, it is 100% an industry|size|type attribute line!
            #     A real position can never have this format! Even if first ends with "公司" (company) (e.g. "多元化业务集团公司"), it is still an industry description!
            #     → Split directly! No need to check whether first is a company name! (because the company_name field already has the real company name)
            # JA: **注意**：| 区切りで従業員規模・会社の性質があれば、100% 業界|規模|性質の属性の組み合わせ行である！
            #     本当の position がこの形式になることはあり得ない！first が「公司」で終わっていても（例：「多元化业务集团公司」）、それは業界の説明である！
            #     → そのまま分割する！first が会社名かどうかの確認は不要！（company_name フィールドにはすでに本当の会社名があるため）
            emps = ""
            for p in parts:
                m = _POST_EMPLOYEE_RE.search(p)
                if m:
                    emps = m.group(0)
                    break
            inds = [p for p in parts if not _POST_EMPLOYEE_RE.search(p) and not any(k in p for k in ("公司", "有限", "股份", "集团", "工程师", "技术员", "专员", "助理", "经理", "主管", "装配", "领班"))]
            if emps and not w.get("company_employees"):
                w["company_employees"] = emps
            if inds and not w.get("company_industry"):
                cand_ind = " | ".join(inds)
                if any(mark in cand_ind for mark in ("行业", "贸易", "制造", "服务业", "IT", "互联网", "电子", "金融", "医药", "能源", "房地产", "传媒", "咨询", "零售", "物流", "消费", "汽车", "教育", "医疗", "半导体", "通信", "机械", "加工", "化工", "外资", "民营", "合资", "国企", "上市")):
                    w["company_industry"] = cand_ind
            w[field] = ""
    # —— 最终安全网：对 company_industry 再严格过滤，去掉「(兼职) | 客运部」这种垃圾
    # EN: —— Final safety net: filter company_industry strictly again, removing junk like "(兼职) | 客运部" ((part-time) | passenger department)
    # JA: —— 最後の安全網：company_industry を改めて厳格にフィルタリングし、「(兼职) | 客运部」（(パート) | 旅客部）のようなゴミを除く
    DEPT_NOISE_SUFFIXES = ("部", "室", "组", "科", "处", "课", "厅", "局", "所", "站", "院", "办", "中心")
    BAD_IND_KW = ("兼职", "全职", "实习", "临时工", "HR", "行政", "人事", "财务", "销售", "市场", "运营", "技术", "研发", "客服", "采购")
    INDUSTRY_STRONG_KW = ("行业", "贸易", "制造", "服务业", "互联网", "IT", "电子", "半导体", "通信", "金融", "银行", "基金", "证券", "保险",
                          "医药", "医疗", "能源", "房地产", "建筑", "传媒", "出版", "印刷", "影视", "咨询", "零售", "批发", "物流", "快递",
                          "汽车", "零配件", "消费", "快速消费品", "教育", "培训", "化工", "机械", "加工", "检测", "认证", "航天", "航空",
                          "新能源", "新材料", "环保", "农业", "食品", "餐饮", "酒店", "旅游", "服装", "纺织")
    for w in works:
        ind_raw = (w.get("company_industry") or "").strip()
        if not ind_raw:
            continue
        parts = [p.strip() for p in re.split(r"[|｜]", ind_raw) if p.strip()]
        valid_parts = []
        for p in parts:
            p_clean = p
            # 去掉括号包裹的工作性质（如 (兼职)）
            # EN: Remove the employment type wrapped in brackets (e.g. (兼职) part-time)
            # JA: 括弧で囲まれた雇用形態を除く（例：(兼职) パート）
            p_clean = re.sub(r"[（(](?:兼职|全职|实习|临时工|正式)[）)]\s*", "", p_clean).strip()
            if not p_clean:
                continue
            # 去掉「XX部」「XX中心」「XX办公室」等部门名
            # EN: Remove department names such as "XX部" "XX中心" "XX办公室" (department/centre/office)
            # JA: 「XX部」「XX中心」「XX办公室」（部・センター・事務所）などの部署名を除く
            if any(p_clean.endswith(suf) for suf in DEPT_NOISE_SUFFIXES) and len(p_clean) <= 15:
                continue
            # 去掉单独的性质/属性关键词
            # EN: Remove standalone type/attribute keywords
            # JA: 単独の性質・属性のキーワードを除く
            if p_clean in BAD_IND_KW:
                continue
            # 必须包含明确行业关键词（或长度<=30且不是纯部门/职位词）才能保留
            # EN: Keep only if it contains an explicit industry keyword (or length <= 30 and it is not a pure department/position word)
            # JA: 明確な業界のキーワードを含む場合（または長さ 30 以下で純粋な部署・職位の語でない場合）だけ残す
            has_industry_mark = any(kw in p_clean for kw in INDUSTRY_STRONG_KW)
            has_nature = any(nat in p_clean for nat in ("外资", "民营", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "非欧美"))
            if has_industry_mark or (has_nature and not any(p_clean.endswith(suf) for suf in DEPT_NOISE_SUFFIXES) and not any(bad in p_clean for bad in BAD_IND_KW)):
                valid_parts.append(p_clean)
        if valid_parts:
            w["company_industry"] = " | ".join(valid_parts)
        else:
            w["company_industry"] = ""
    # ==================== 追加：最终安全网（公司名/职位 swap + 垃圾尾部清洗 + 空段去重 + 多段粘连）====================
    # 常见职位后缀词（出现在 position 正常，出现在 company_name 就该 swap/清掉）
    # EN: ==================== Added: final safety net (company/position swap + trailing junk cleanup + empty-entry dedup + multi-entry sticking) ====================
    #     Common position suffix words (normal in position; if they appear in company_name they should be swapped/removed)
    # JA: ==================== 追加：最後の安全網（会社名と職位の入れ替え + 末尾のゴミ除去 + 空の項目の重複排除 + 複数項目のくっつき）====================
    #     よくある職位の接尾語（position にあれば正常、company_name にあれば入れ替えか除去が必要）
    POSITION_SUFFIXES = ("专员", "助理", "主管", "经理", "工程师", "顾问", "总监", "出纳", "会计", "财务",
                         "担当", "课长", "部长", "主任", "组长", "社长", "会长", "主席", "设计师", "分析师",
                         "教师", "老师", "教授", "研究员", "医生", "护士", "销售", "业务员", "采购员",
                         "客服", "人事", "行政", "翻译", "程序猿", "程序员", "开发", "运维", "测试",
                         "实习生", "培训生", "管培生", "应届生", "应届", "兼职", "全职", "临时工")
    # 公司名里「尾巴垃圾」词：员工规模/公司性质开头，一般放在公司名后面的描述
    # EN: "Trailing junk" words in company names: descriptions starting with employee size / company type, usually placed after the company name
    # JA: 会社名の「末尾のゴミ」となる語：従業員規模や会社の性質で始まる説明で、通常は会社名の後ろに置かれる
    TAIL_NOISE_PREFIX = ("少于", "小于", "低于", "不超过", "不足", "不到", "约", "近", "员工", "人员规模",
                         "公司性质", "公司行业", "公司规模", "企业性质", "单位性质", "单位规模",
                         "民营", "外资", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "外商")
    cleaned_works: list[dict[str, Any]] = []
    for w in works:
        if not isinstance(w, dict):
            continue
        cname = str(w.get("company_name") or "").strip()
        pos = str(w.get("position") or "").strip()
        pstart = str(w.get("position_start") or "").strip()
        # === A. 公司名尾部垃圾清洗 ===
        # 场景1：苏州格罗贝尔生物科技有限公司(少于50人) → 去掉括号及内部员工规模；「少于」后面内容全断
        # EN: === A. Clean trailing junk from the company name ===
        #     Scenario 1: 苏州格罗贝尔生物科技有限公司(少于50人) → remove the brackets and the employee size inside; cut everything after "少于" (fewer than)
        # JA: === A. 会社名の末尾のゴミを除去 ===
        #     ケース 1：苏州格罗贝尔生物科技有限公司(少于50人) → 括弧と中の従業員規模を除き、「少于」（未満）以降はすべて切る
        if cname:
            # —— 0. 先剥掉「(少于50人)」「（100-200人）」这种整段括号员工规模
            # EN: —— 0. First strip whole bracketed employee-size segments like "(少于50人)" "（100-200人）"
            # JA: —— 0. まず「(少于50人)」「（100-200人）」のような括弧付きの従業員規模の部分をまるごと除く
            cname_clean = re.sub(
                r"[\s（(]*(?:少于|小于|低于|不超过|不足|不到|约|近)?\s*\d+\s*[-–~～至到]?\s*\d*\s*(?:人以下|人以上|人以内|人)\s*[）)]*\s*$",
                "", cname)
            # 括号员工规模可能还在中段（如「科技有限公司(少于50人)其他」）→ 再去掉一次所有括号内含员工规模的段
            # EN: A bracketed employee size may still be in the middle (e.g. "科技有限公司(少于50人)其他") → remove every bracketed segment containing an employee size once more
            # JA: 括弧付きの従業員規模が途中に残っていることがある（例：「科技有限公司(少于50人)其他」）→ 従業員規模を含む括弧部分をもう一度すべて除く
            cname_clean = re.sub(r"[（(][^）)]*(?:少于|小于|低于|不超过|不足|不到|约|近)?\s*\d+\s*[-–~～至到]?\s*\d*\s*(?:人以下|人以上|人以内|人)[^）)]*[）)]", "", cname_clean)
            # 1. 再去掉尾部裸员工规模：少于XX人 / XX-XX人 / XX人以下 等
            # EN: 1. Then remove bare trailing employee sizes: 少于XX人 / XX-XX人 / XX人以下 etc.
            # JA: 1. 次に末尾の裸の従業員規模を除く：少于XX人 / XX-XX人 / XX人以下 など
            cname_clean = re.sub(r"(?:\s*(?:少于|小于|低于|不超过|不足|不到|约|近)?\s*\d+\s*[-–~～至到]?\s*\d*\s*(?:人以下|人以上|人以内|人))\s*$",
                                 "", cname_clean)
            # 2. 如果尾部出现 TAIL_NOISE_PREFIX 关键词，从那截断（必须 idx > 2，避免「外资」等开头的公司被误切）
            # EN: 2. If a TAIL_NOISE_PREFIX keyword appears at the end, truncate there (idx > 2 required, so companies starting with words like "外资" (foreign-owned) are not cut by mistake)
            # JA: 2. 末尾に TAIL_NOISE_PREFIX のキーワードが現れたらそこで切る（idx > 2 が必須。「外资」（外資）などで始まる会社を誤って切らないため）
            for pref in TAIL_NOISE_PREFIX:
                idx = cname_clean.find(pref)
                if idx > 2 and idx + len(pref) < len(cname_clean):
                    cname_clean = cname_clean[:idx]
                    break
            # 3. 去掉尾部公司性质括号残留：「（外资(欧美)）」等；去掉「股份公司性质：外资」尾巴
            # EN: 3. Remove leftover trailing company-type brackets such as "（外资(欧美)）"; remove a "股份公司性质：外资" tail
            # JA: 3. 末尾に残った会社の性質の括弧（「（外资(欧美)）」など）を除き、「股份公司性质：外资」の尾部を除く
            cname_clean = re.sub(r"[\s（(:：]+公司(?:性质|行业|规模|简介|描述)?[\s:：]*[\u4e00-\u9fa5A-Za-z0-9()（）]*$", "", cname_clean).strip()
            # 4. 去掉结尾单独的「公司」（只在「公司」是结尾且前面已经有「有限/股份/责任/分/子」才保留，否则单独「公司」是尾巴垃圾）
            # EN: 4. Remove a trailing standalone "公司" (kept only when it ends the name and is preceded by 有限/股份/责任/分/子; otherwise a lone "公司" is trailing junk)
            # JA: 4. 末尾の単独の「公司」を除く（末尾にあり、前に「有限／股份／责任／分／子」がある場合だけ残す。それ以外の単独の「公司」は末尾のゴミ）
            if cname_clean.endswith("公司") and not cname_clean.endswith(("有限公司", "股份公司", "责任公司", "分公司", "子公司")):
                cname_clean = cname_clean[:-2]
            if cname_clean and cname_clean != cname:
                cname = cname_clean.strip(" :：|｜-()（）")
                w["company_name"] = cname
        # === B. 多段公司名粘连：「上海唐锋能源科技有限公司上海交通大学燃料电池研究所」→ 截到第一个「有限公司/公司/集团/银行/...」为止 ===
        # EN: === B. Multiple company names stuck together: "上海唐锋能源科技有限公司上海交通大学燃料电池研究所" → cut at the first "有限公司/公司/集团/银行/..." ===
        # JA: === B. 複数の会社名のくっつき：「上海唐锋能源科技有限公司上海交通大学燃料电池研究所」→ 最初の「有限公司／公司／集团／银行／…」までで切る ===
        if cname:
            COMP_HARD_END = ("股份有限公司", "有限责任公司", "有限公司", "集团", "股份", "银行", "基金", "证券",
                             "保险", "株式会社", "厂", "工厂", "制造厂", "分店", "分公司", "支社", "支店",
                             "办事处", "事务所", "工作室", "公司")
            # 找到第一个「硬结束词」的结束位置
            # EN: Find the end position of the first "hard end word"
            # JA: 最初の「確定的な終端語」の終了位置を探す
            cut_pos = -1
            for end in COMP_HARD_END:
                idx = cname.find(end)
                if idx >= 0:
                    ep = idx + len(end)
                    if cut_pos < 0 or ep < cut_pos:
                        cut_pos = ep
            if cut_pos > 0 and cut_pos < len(cname):
                # 切完后前缀必须是公司名（含强标志）；否则这是研究所类单位，不要乱切
                # EN: After cutting, the prefix must be a company name (with a strong marker); otherwise it is a research-institute-type unit, do not cut arbitrarily
                # JA: 切った後の前半は会社名（強い目印付き）でなければならない。そうでなければ研究所のような組織なので、むやみに切らない
                prefix = cname[:cut_pos].strip()
                if _has_comp_sign_global(prefix):
                    cname = prefix
                    w["company_name"] = cname
        # === C. 「职位-公司」swap 修复（丁嘉颖 case：company_name="出纳" position=""）===
        # EN: === C. Fix "position-company" swaps (a past case: company_name="出纳" (cashier) position="") ===
        # JA: === C. 「職位と会社」の入れ替えを修正（過去の事例：company_name="出纳"（出納係）、position=""）===
        cname_is_pos_like = bool(cname) and any(suf in cname for suf in POSITION_SUFFIXES) and not _has_comp_sign_global(cname)
        pos_has_comp = bool(pos) and _has_comp_sign_global(pos)
        need_swap = False
        if cname_is_pos_like and (not pos or pos_has_comp):
            need_swap = True
        # 另外：position 是公司（有公司标志）且 company_name 是职位 → swap
        # EN: Also: position is a company (has a company marker) and company_name is a position → swap
        # JA: さらに：position が会社（会社の目印あり）で company_name が職位 → 入れ替える
        if pos_has_comp and not _has_comp_sign_global(cname if cname else ""):
            need_swap = True
        if need_swap:
            w["company_name"], w["position"] = pos, cname
            cname, pos = str(w.get("company_name") or "").strip(), str(w.get("position") or "").strip()
        # === D. 再兜底：如果 position 是纯职位词，公司名此时还是空，保留（说明确实找不到公司）===
        #    但如果 company_name 仍是职位词（swap 后依然），且 position 空 → 把公司名清空，position 填回职位词
        # EN: === D. Further fallback: if position is a pure position word and the company name is still empty, keep it (it means the company really cannot be found) ===
        #        But if company_name is still a position word (even after the swap) and position is empty → clear the company name and put the position word back into position
        # JA: === D. さらなる最終手段：position が純粋な職位の語で、会社名がまだ空なら残す（本当に会社が見つからないということ）===
        #        ただし company_name が（入れ替え後も）職位の語で position が空 → 会社名を空にし、職位の語を position に戻す
        cname_is_still_pos = bool(cname) and any(suf in cname for suf in POSITION_SUFFIXES) and not _has_comp_sign_global(cname)
        if cname_is_still_pos and not pos:
            w["position"] = cname
            w["company_name"] = ""
            cname, pos = "", str(w.get("position") or "").strip()
        # === D-2. 职位字段「时长括号」清理：（X年X月）/（X个月）/（X年）等纯工作时长不应是职位名
        #     案例：黄 case position="（9年11月）" → 空；然后从 position_dept / responsibilities 首行反推真实职位
        # EN: === D-2. Clean "tenure brackets" in the position field: pure tenure like (X年X月) / (X个月) / (X年) should not be a position name
        #         Example: a past case with position="（9年11月）" → empty; then infer the real position from position_dept / the first line of responsibilities
        # JA: === D-2. 職位フィールドの「在職期間の括弧」を除去：（X年X月）／（X个月）／（X年）などの純粋な在職期間は職位名ではない
        #         例：過去の事例 position="（9年11月）" → 空にし、position_dept や responsibilities の 1 行目から本当の職位を逆算する
        _pos_dur_re = re.compile(
            r"^\s*[(（]\s*(?:\d+\s*年)?\s*(?:\d+\s*个?)?\s*月\s*[）)]\s*$|"
            r"^\s*[(（]\s*\d+\s*年\s*[）)]\s*$|"
            r"^\s*\d+\s*年\s*\d+\s*个?月\s*$"
        )
        if pos and _pos_dur_re.match(pos):
            # position 纯是时长 → 清空；尝试从 position_dept 拿真实职位（若 dept 像职位）
            # EN: position is pure tenure → clear it; try taking the real position from position_dept (if dept looks like a position)
            # JA: position が在職期間だけ → 空にし、position_dept から本当の職位を取ることを試みる（dept が職位らしい場合）
            dept_for_pos = str(w.get("position_dept") or "").strip()
            _pos_from_dept_suff = ("专员", "助理", "主管", "经理", "总监", "工程师", "顾问", "担当", "课长",
                                   "部长", "主任", "组长", "设计师", "分析师", "教师", "老师", "研究员",
                                   "医生", "护士", "销售", "业务员", "采购员", "客服", "人事", "行政",
                                   "财务", "翻译", "程序员", "开发", "运维", "测试", "调达", "店长",
                                   "会计", "出纳", "总经理", "厂长", "副总经理", "副厂长")
            if dept_for_pos and any(suf in dept_for_pos for suf in _pos_from_dept_suff):
                w["position"] = dept_for_pos
                pos = dept_for_pos
            else:
                w["position"] = ""
                pos = ""
        # === D-3. company_name 纯薪资格式（如：4001-6000元/月）→ 清空公司名，
        #     尝试从 position_responsibilities 第一行/附近 反推真实公司名（贾凤兰 case）
        # EN: === D-3. company_name is a pure salary format (e.g. 4001-6000元/月) → clear the company name,
        #         and try inferring the real company name from the first/nearby lines of position_responsibilities (a past case)
        # JA: === D-3. company_name が純粋な給与の形式（例：4001-6000元/月）→ 会社名を空にし、
        #         position_responsibilities の 1 行目や付近から本当の会社名の逆算を試みる（過去の事例）
        _salary_as_cname_re = re.compile(
            r"^\s*\d+\s*[-–~～—]\s*\d+\s*(?:元|千|万|块)\s*(?:/\s*月|/\s*年|月|年|元)$|"
            r"^\s*\d+\s*(?:元|千|万)\s*/\s*(?:月|年)\s*$|"
            r"^\s*[（(]?\s*\d+\s*-\s*\d+\s*(?:元|千|万)\s*/\s*(?:月|年)\s*[）)]?\s*$"
        )
        cname_raw = str(w.get("company_name") or "").strip()
        if cname_raw and _salary_as_cname_re.match(cname_raw):
            # 塞到 position_salary（若 salary 空），再从 responsibilities 首行反推公司
            # EN: Put it into position_salary (if salary is empty), then infer the company from the first line of responsibilities
            # JA: position_salary に入れ（salary が空の場合）、その後 responsibilities の 1 行目から会社を逆算する
            if not str(w.get("position_salary") or "").strip():
                w["position_salary"] = cname_raw
            resp_for_cname = str(w.get("position_responsibilities") or "").strip()
            _new_cname = ""
            if resp_for_cname:
                first_line_resp = resp_for_cname.split("\n", 1)[0].strip()
                # 去掉列表前缀：「读研期间兼职）」「读研期间兼职」括号前缀
                # EN: Remove list prefixes: bracketed prefixes like "读研期间兼职）" / "读研期间兼职" (part-time during postgraduate study)
                # JA: リストの接頭辞を除く：「读研期间兼职）」「读研期间兼职」（大学院在学中のアルバイト）のような括弧の接頭辞
                clean_fl = re.sub(r"^[\s（(（]*[\u4e00-\u9fa5]{0,10}[）)）]*\s*", "", first_line_resp)
                # 尝试取前面的公司：格式如「公司名（X个月）」或「公司名 XX 担任」或直接前几个字含公司标志
                # EN: Try taking the preceding company: formats like "company name (X个月)" or "company name XX 担任" (served as), or the first few characters directly contain a company marker
                # JA: 前にある会社の取得を試みる：「会社名（X个月）」「会社名 XX 担任」（〜を担当）の形式、または先頭の数文字に会社の目印がある場合
                m_fl = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9（）()·・\-·]+?)\s*(?:[(（][^)）]*[)）]|[,，。.；;]|担任|负责|作为|陪同)", clean_fl)
                if m_fl:
                    cand = m_fl.group(1).strip()
                    if cand and _has_comp_sign_global(cand) and len(cand) >= 4:
                        _new_cname = cand
                if not _new_cname and _has_comp_sign_global(clean_fl):
                    # 整行本身可能含公司名（如「广西巨星科技有限公司」）
                    # EN: The whole line itself may contain the company name (e.g. "广西巨星科技有限公司")
                    # JA: 行全体が会社名を含んでいることもある（例：「广西巨星科技有限公司」）
                    for sign in _COMP_SIGNS_STRONG:
                        idx = clean_fl.find(sign)
                        if idx >= 0:
                            end_pos = idx + len(sign)
                            cand = clean_fl[:end_pos].strip()
                            if len(cand) >= 4:
                                _new_cname = cand
                                break
            w["company_name"] = _new_cname
            cname_raw = _new_cname

        # === D-3+. company_name 是日期范围（所有 work entries 都适用）→ 尝试从 position_responsibilities 反推公司名
        # EN: === D-3+. company_name is a date range (applies to all work entries) → try inferring the company name from position_responsibilities
        # JA: === D-3+. company_name が日付範囲（すべての職歴項目に適用）→ position_responsibilities から会社名の逆算を試みる
        cname_raw = str(w.get("company_name") or "").strip()
        if cname_raw and not str(w.get("position_salary") or "").strip():
            # 判定像日期/薪资：直接内嵌regex避免闭包依赖
            # EN: Decide whether it looks like a date/salary: inline the regex directly to avoid closure dependencies
            # JA: 日付・給与らしいかを判定する：クロージャへの依存を避けるため正規表現を直接埋め込む
            _DATEREP_LOCAL = re.compile(
                r"^(?:\d{4}\s*[\./年\-]\s*\d{1,2}\s*月?\s*[\-~～—–至到‒―〜\-]{1,4}\s*(?:\d{4}\s*[\./年\-]\s*\d{1,2}\s*月?|\d{2,4}|至今|在读|现在))"
                r"|^(?:\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\s*[-~～]\s*\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"
                r"|^(?:\d+\s*(?:元|千|万)\s*(?:/\s*月|/\s*年|月|年)$)"
                r"|^(?:20|19)\d{2}\s*年\s*\d{1,2}\s*月\s*$"
            )
            _looks_date_salary = bool(_DATEREP_LOCAL.match(cname_raw)) or bool(re.match(
                r"^\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{1,2}\s*月?\s*[\-~～—–至到‒―〜\-]+\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{1,2}\s*月?|至今|在读|现在)|(?:19|20)\d{2}\s*[\-~～—–至到‒―〜\-]+\s*(?:19|20)\d{2})", cname_raw))
            if _looks_date_salary:
                # 先放 salary，再从 responsibilities 首行反推
                # EN: Put it into salary first, then infer from the first line of responsibilities
                # JA: まず salary に入れ、その後 responsibilities の 1 行目から逆算する
                if not str(w.get("position_salary") or "").strip() and any(kw in cname_raw for kw in ("元", "万", "千", "薪", "资")):
                    w["position_salary"] = cname_raw
                resp_for_cname = str(w.get("position_responsibilities") or "").strip()
                _new_cname = ""
                if resp_for_cname:
                    first_line_resp = resp_for_cname.split("\n", 1)[0].strip()
                    clean_fl = re.sub(r"^[\s（(（]*[\u4e00-\u9fa5]{0,10}[）)）]*\s*", "", first_line_resp)
                    m_fl = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9（）()·・\-·]+?)\s*(?:[(（][^)）]*[)）]|[,，。.；;]|担任|负责|作为|陪同)", clean_fl)
                    if m_fl:
                        cand = m_fl.group(1).strip()
                        if cand and _has_comp_sign_global(cand) and len(cand) >= 4:
                            _new_cname = cand
                    if not _new_cname and _has_comp_sign_global(clean_fl):
                        for sign in _COMP_SIGNS_STRONG:
                            idx = clean_fl.find(sign)
                            if idx >= 0:
                                end_pos = idx + len(sign)
                                cand = clean_fl[:end_pos].strip()
                                if len(cand) >= 4:
                                    _new_cname = cand
                                    break
                    if not _new_cname:
                        # 尝试用正则在 responsbilities 里搜 XX公司/XX工厂/XX集团/XX营业部
                        # EN: Try a regex search in responsibilities for XX公司/XX工厂/XX集团/XX营业部 (company/factory/group/sales office)
                        # JA: responsibilities 内で XX公司／XX工厂／XX集团／XX营业部（会社・工場・グループ・営業所）を正規表現で探してみる
                        m_comp = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()·・\-·]{2,20}(?:有限公司|股份有限公司|集团|分公司|工厂|工场|学校|医院|银行|营业部|営業部))", resp_for_cname)
                        if m_comp:
                            _new_cname = m_comp.group(1).strip()
                w["company_name"] = _new_cname
                cname_raw = _new_cname

        # === E-1. 严格过滤：伪空段（高舰阳 case）+ 垃圾公司名段（丁嘉颖 work[2]："并会前往事务所"） ===
        # EN: === E-1. Strict filtering: pseudo-empty entries (a past case) + junk company-name entries (a past case, work[2]: "并会前往事务所" (and will go to the office)) ===
        # JA: === E-1. 厳格なフィルタリング：見かけ上空の項目（過去の事例）+ ゴミの会社名の項目（過去の事例 work[2]：「并会前往事务所」（そして事務所へ向かう））===
        _NONE_KW = {"无", "暂无", "未填写", "待补充", "N/A", "NA", "None", "none", "n/a", "未知", "/", "-", "—", "－", "－－", "——"}
        # —— 公司名开头禁词：动词/连词/副词/介词开头 → 说明这是一句话，不是公司名
        # EN: —— Forbidden starting words for company names: starting with a verb/conjunction/adverb/preposition → it is a sentence, not a company name
        # JA: —— 会社名の先頭の禁止語：動詞・接続詞・副詞・前置詞で始まる → 文であって会社名ではない
        BAD_COMP_PREFIX_VERBS = (
            "负责", "协助", "组织", "开发", "维护", "参与", "制定", "管理", "进行", "配合",
            "完成", "建立", "收集", "提供", "推广", "推进", "改善", "提高", "拓展", "沟通",
            "协调", "设计", "制作", "发放", "招募", "选址", "宣传", "策划", "跟进", "运营",
            "建设", "预算", "参加", "支持", "调研", "分析",
            "在这", "在我", "期间", "主要", "其中", "包括", "并", "并且", "而且", "然后",
            "期间", "同时", "随后", "以及", "前往", "去往", "会前往", "并会",
        )
        cname_raw = str(w.get("company_name") or "").strip()
        pos_raw = str(w.get("position") or "").strip()
        ind_raw = str(w.get("company_industry") or "").strip()
        emp_raw = str(w.get("company_employees") or "").strip()
        # —— E-1.1 全空值/全「无」过滤（高舰阳）
        # EN: —— E-1.1 Filter entries that are all empty / all "无" (none) (a past case)
        # JA: —— E-1.1 すべて空・すべて「无」（なし）の項目を除外する（過去の事例）
        _is_all_none = (
            (not cname_raw or cname_raw in _NONE_KW)
            and (not pos_raw or pos_raw in _NONE_KW)
            and (not ind_raw or ind_raw in _NONE_KW)
            and (not emp_raw or emp_raw in _NONE_KW)
        )
        if _is_all_none:
            continue
        if cname_raw in _NONE_KW and (not pos_raw or pos_raw in _NONE_KW):
            continue
        # —— E-1.2 垃圾公司名过滤：（丁嘉颖 work[2]：并会前往事务所）
        #   规则（宁严勿松）：
        #     a) 开头是动词/连词 → 一律丢弃（没有任何合法公司名会以「并会/负责/前往」开头）
        #     b) 没有强公司标志 且 含多个标点 且 长度>=10 → 丢弃
        #     c) 没有强公司标志 且 含禁词 且 长度>=6 → 丢弃
        # EN: —— E-1.2 Junk company-name filter: (a past case, work[2]: 并会前往事务所)
        #       Rules (better too strict than too loose):
        #         a) starts with a verb/conjunction → always discard (no legitimate company name starts with "并会/负责/前往" (and will / responsible for / go to))
        #         b) no strong company marker and several punctuation marks and length >= 10 → discard
        #         c) no strong company marker and contains forbidden words and length >= 6 → discard
        # JA: —— E-1.2 ゴミの会社名のフィルター：（過去の事例 work[2]：并会前往事务所）
        #       ルール（緩すぎるより厳しすぎる方がよい）：
        #         a) 動詞・接続詞で始まる → 一律に破棄（正当な会社名が「并会／负责／前往」（そして〜する／担当／向かう）で始まることはない）
        #         b) 強い会社の目印がなく、句読点を複数含み、長さ 10 以上 → 破棄
        #         c) 強い会社の目印がなく、禁止語を含み、長さ 6 以上 → 破棄
        if cname_raw:
            _has_strong_sign = any(sign in cname_raw for sign in _COMP_SIGNS_STRONG)
            _prefix_bad = any(cname_raw.startswith(v) for v in BAD_COMP_PREFIX_VERBS)
            # a) 开头禁词：无论有没有强标志，一律丢弃（宁严勿松）
            # EN: a) Forbidden starting words: discard regardless of any strong marker (better too strict than too loose)
            # JA: a) 先頭の禁止語：強い目印の有無にかかわらず一律に破棄（緩すぎるより厳しすぎる方がよい）
            if _prefix_bad:
                continue
            if not _has_strong_sign:
                n_punc_cname = sum(cname_raw.count(c) for c in "，,。.！!？?；;、/\\|｜[]【】()（）")
                if len(cname_raw) >= 10 and n_punc_cname >= 2:
                    continue
                # 弱后缀 + 含禁词 → 丢弃
                # EN: Weak suffix + contains forbidden words → discard
                # JA: 弱い接尾辞 + 禁止語を含む → 破棄
                if any(v in cname_raw for v in BAD_COMP_PREFIX_VERBS) and len(cname_raw) >= 6:
                    continue

        # === E-1.3 公司名是典型部门名 → 清空/修正，从 responsibilities 第一行反推公司（程泽 case：体育组/教研组/科室） ===
        #     典型部门：教育行业的 体育组/语文组/数学组/英语组/XX教研组/年级组/教务处/德育处/总务处/政教处/教研室
        #            医疗行业的 内科/外科/儿科/妇科/眼科/耳鼻喉科/放射科/检验科/药剂科/护理部/门诊部/住院部
        #            通用：人事部/人力资源部/财务部/销售部/市场部/研发部/技术部/生产部/采购部/客服部/行政部/运营部/企划部/IT部
        # EN: === E-1.3 Company name is a typical department name → clear/correct it, inferring the company from the first line of responsibilities (a past case: 体育组/教研组/科室) ===
        #         Typical departments: in education, 体育组/语文组/数学组/英语组/XX教研组/年级组/教务处/德育处/总务处/政教处/教研室 (PE/Chinese/maths/English groups, teaching research groups, grade groups, academic affairs, moral education, general affairs, political education offices, teaching research office)
        #                in healthcare, 内科/外科/儿科/妇科/眼科/耳鼻喉科/放射科/检验科/药剂科/护理部/门诊部/住院部 (internal medicine, surgery, paediatrics, gynaecology, ophthalmology, ENT, radiology, laboratory, pharmacy, nursing, outpatient, inpatient)
        #                general: 人事部/人力资源部/财务部/销售部/市场部/研发部/技术部/生产部/采购部/客服部/行政部/运营部/企划部/IT部 (personnel, HR, finance, sales, marketing, R&D, technology, production, purchasing, customer service, administration, operations, planning, IT)
        # JA: === E-1.3 会社名が典型的な部署名 → 空にするか補正し、responsibilities の 1 行目から会社を逆算する（過去の事例：体育组／教研组／科室）===
        #         典型的な部署：教育業界の 体育组／语文组／数学组／英语组／XX教研组／年级组／教务处／德育处／总务处／政教处／教研室
        #                医療業界の 内科／外科／儿科／妇科／眼科／耳鼻喉科／放射科／检验科／药剂科／护理部／门诊部／住院部
        #                共通：人事部／人力资源部／财务部／销售部／市场部／研发部／技术部／生产部／采购部／客服部／行政部／运营部／企划部／IT部
        cname_raw2 = str(w.get("company_name") or "").strip()
        pos_raw2 = str(w.get("position") or "").strip()
        dept_raw2 = str(w.get("position_dept") or w.get("department") or "").strip()
        resp_raw = str(w.get("position_responsibilities") or "").strip()
        # —— 部门关键词（按行业分类，命中即判定 cname 是部门）
        # EN: —— Department keywords (classified by industry; a hit means cname is a department)
        # JA: —— 部署のキーワード（業界別に分類。ヒットすれば cname は部署と判定）
        DEPT_SIGNS_EDU = ("教研组", "年级组", "备课组", "教务处", "德育处", "总务处", "政教处",
                          "教研室", "教研组", "体卫艺处", "学生处", "团委", "少先队", "工会",
                          "招生办", "就业办", "图书馆", "实验室", "实训中心")
        DEPT_SIGNS_MED = ("内科", "外科", "儿科", "妇科", "产科", "眼科", "耳鼻喉科", "口腔科",
                          "皮肤科", "放射科", "检验科", "药剂科", "护理部", "门诊部", "住院部",
                          "急诊科", "麻醉科", "病理科", "B超室", "CT室", "手术室", "供应室")
        DEPT_SIGNS_SUBJECT = ("语文组", "数学组", "英语组", "物理组", "化学组", "生物组",
                              "历史组", "地理组", "政治组", "体育组", "音乐组", "美术组",
                              "信息组", "技术组", "科学组", "品德组", "社会组", "劳技组",
                              "心理组", "书法组", "美术组")
        DEPT_SIGNS_GENERAL = ("人事部", "人力资源部", "财务部", "销售部", "市场部", "研发部",
                              "技术部", "生产部", "采购部", "客服部", "行政部", "运营部",
                              "企划部", "设计部", "产品部", "质量部", "物流部", "仓储部",
                              "IT部", "信息部", "审计部", "法务部", "公关部", "品牌部",
                              "项目部", "工程部", "安全部", "保卫部", "后勤部",
                              "资材部", "资材调达", "调达部", "品保部", "品质部", "品管部",
                              "关务部", "报关部", "业务部", "营业部", "商务部", "外贸部",
                              "总务部", "总务处", "总务", "厂务部", "管理部", "经营部",
                              "工会", "审计", "法务", "总经办", "总经理办公室", "董事会办公室")
        # 单字匹配：最后一个字是「组/处/科/室/部/系/院/中心」且长度2-6且前面没有强公司标志 → 判定部门
        # EN: Single-character match: the last character is "组/处/科/室/部/系/院/中心" (group/office/section/room/department/faculty/institute/centre), length 2-6, and no strong company marker before it → judged a department
        # JA: 1 文字のマッチ：最後の文字が「组／处／科／室／部／系／院／中心」で、長さ 2〜6、前に強い会社の目印がない → 部署と判定
        _cname_strong_sign = any(sign in cname_raw2 for sign in _COMP_SIGNS_STRONG)
        _cname_is_dept = False
        if cname_raw2 and not _cname_strong_sign:
            if (any(d in cname_raw2 for d in DEPT_SIGNS_EDU) or
                any(d in cname_raw2 for d in DEPT_SIGNS_MED) or
                any(d in cname_raw2 for d in DEPT_SIGNS_SUBJECT) or
                any(d in cname_raw2 for d in DEPT_SIGNS_GENERAL)):
                _cname_is_dept = True
            # 后缀判断：末尾是 组/处/科/室/部/系 且长度2-6
            # EN: Suffix check: ends with 组/处/科/室/部/系 and length 2-6
            # JA: 接尾辞の判定：末尾が 组／处／科／室／部／系 で長さ 2〜6
            elif 2 <= len(cname_raw2) <= 6 and cname_raw2[-1] in ("组", "处", "科", "室", "部", "系"):
                _cname_is_dept = True
        if _cname_is_dept:
            # —— 把部门名填到 position_dept（原来空或更短的才覆盖）
            # EN: —— Put the department name into position_dept (only overwrite when it was empty or shorter)
            # JA: —— 部署名を position_dept に入れる（元が空かより短い場合だけ上書き）
            if not dept_raw2 or len(dept_raw2) < len(cname_raw2):
                w["position_dept"] = cname_raw2
            # —— 从 position_responsibilities 第一行反推公司名（51job格式：公司名 (X个月 )）
            # EN: —— Infer the company name from the first line of position_responsibilities (51job format: company name (X个月 ))
            # JA: —— position_responsibilities の 1 行目から会社名を逆算する（51job の形式：会社名 (X个月 )）
            _new_company = ""
            if resp_raw:
                first_line = resp_raw.split("\n", 1)[0].strip()
                # 格式：「武汉市汉南区第一中学 (4个月 )」 或 「武汉市汉南区第一中学 （4个月）」
                # EN: Format: "武汉市汉南区第一中学 (4个月 )" or "武汉市汉南区第一中学 （4个月）"
                # JA: 形式：「武汉市汉南区第一中学 (4个月 )」または「武汉市汉南区第一中学 （4个月）」
                m_comp = re.match(r"^(.+?)\s*(?:[(（][^)）]*[)）])?\s*$", first_line)
                if m_comp:
                    cand = m_comp.group(1).strip()
                    # 去掉末尾空格/标点
                    # EN: Remove trailing spaces/punctuation
                    # JA: 末尾の空白・句読点を除く
                    cand = cand.rstrip(" -—_·").strip()
                    # 必须含强/弱公司标志 或 长度>=5 且 不是部门词
                    # EN: Must contain a strong/weak company marker, or have length >= 5 and not be a department word
                    # JA: 強い・弱い会社の目印を含むか、長さ 5 以上で部署の語でないこと
                    cand_has_sign = _has_comp_sign_global(cand)
                    cand_is_bad_dept = False
                    if not cand_has_sign:
                        if (any(d in cand for d in (*DEPT_SIGNS_EDU, *DEPT_SIGNS_MED, *DEPT_SIGNS_SUBJECT, *DEPT_SIGNS_GENERAL)) or
                            (2 <= len(cand) <= 6 and cand[-1] in ("组", "处", "科", "室", "部", "系"))):
                            cand_is_bad_dept = True
                    if cand_has_sign and not cand_is_bad_dept:
                        _new_company = cand
                    elif len(cand) >= 5 and not cand_is_bad_dept:
                        _new_company = cand
            if _new_company:
                w["company_name"] = _new_company
            else:
                # 没反推出来 → 清空公司名（宁空勿错）
                # EN: Could not infer it → clear the company name (better empty than wrong)
                # JA: 逆算できなかった → 会社名を空にする（誤るくらいなら空のほうがよい）
                w["company_name"] = ""
            cname = str(w.get("company_name") or "").strip()
            cname_raw = cname  # 同步
            # EN: Sync
            # JA: 同期する
        # === E-1.4 合法短公司名保护：「自营」「个体」「自由职业」「创业」「个人」是合法公司主体（程泽 case：2016/5-2018/11 自营 羽毛球教练）===
        # EN: === E-1.4 Protect legitimate short company names: "自营" (self-employed), "个体" (sole trader), "自由职业" (freelance), "创业" (start-up), "个人" (individual) are legitimate entities (a past case: 2016/5-2018/11 自营 羽毛球教练 (self-employed badminton coach)) ===
        # JA: === E-1.4 正当な短い会社名の保護：「自营」（自営）、「个体」（個人事業）、「自由职业」（フリーランス）、「创业」（起業）、「个人」（個人）は正当な主体（過去の事例：2016/5-2018/11 自营 羽毛球教练（自営のバドミントンコーチ））===
        VALID_SHORT_COMPANY = ("自营", "个体", "个体户", "自由职业", "创业", "个人", "个人工作室", "SOHO", "自由职业者")
        if (not cname_raw) and str(w.get("company_name") or "").strip() in VALID_SHORT_COMPANY:
            # 已经是合法值，不要在 E 空段丢弃逻辑里被干掉
            # EN: Already a legitimate value; must not be removed by the E empty-entry discard logic
            # JA: すでに正当な値なので、E の空項目の破棄ロジックで消されてはならない
            pass
        cname_raw_check = str(w.get("company_name") or "").strip()
        if cname_raw_check in VALID_SHORT_COMPANY:
            # 把合法短公司名保留（后续 E 逻辑不应因 length<=2 清空）
            # EN: Keep legitimate short company names (the later E logic must not clear them because length <= 2)
            # JA: 正当な短い会社名を残す（後続の E のロジックが長さ 2 以下を理由に空にしないこと）
            cname = cname_raw_check
            cname_raw = cname_raw_check
        # === E. 空段丢弃：没有日期（position_start）也没有公司也没有职位 → 纯垃圾段 ===
        # EN: === E. Discard empty entries: no date (position_start), no company and no position → pure junk entry ===
        # JA: === E. 空の項目の破棄：日付（position_start）も会社も職位もない → 純粋なゴミの項目 ===
        if not pstart and not str(w.get("position_resigned") or "").strip() and not cname and not pos:
            continue
        # === F. 日期/职位/公司 再最后做一次格式兜底（职位里「打印。」「证书：中级会计师职称：」等垃圾清理）===
        # EN: === F. One last format fallback for date/position/company (cleaning junk in positions such as "打印。" or "证书：中级会计师职称：") ===
        # JA: === F. 日付・職位・会社に最後の形式チェックをもう一度行う（職位内の「打印。」「证书：中级会计师职称：」などのゴミを除去）===
        if pos:
            # 职位里的 KV 前缀残留：「中级会计师职称：XXX」「打印。XXX」→ 去掉前缀第一个冒号前
            # EN: Leftover KV prefixes in positions: "中级会计师职称：XXX" "打印。XXX" → remove the part before the first colon
            # JA: 職位に残った KV の接頭辞：「中级会计师职称：XXX」「打印。XXX」→ 最初のコロンの前の部分を除く
            pos_kv_clean = re.sub(r"^[\u4e00-\u9fa5A-Za-z0-9]{1,15}\s*[：:]\s*", "", pos)
            if pos_kv_clean and pos_kv_clean != pos and len(pos_kv_clean) <= 40:
                # 只在去掉冒号前缀后更短更干净时才替换（避免「岗位：工程师」→ 丢了意思）
                # EN: Replace only when it is shorter and cleaner after removing the colon prefix (to avoid "岗位：工程师" (post: engineer) losing its meaning)
                # JA: コロンの接頭辞を除いた方が短くてきれいな場合だけ置き換える（「岗位：工程师」（ポスト：エンジニア）の意味が失われるのを防ぐ）
                _prefix = pos[:len(pos) - len(pos_kv_clean)].rstrip(" :：")
                if _prefix and any(kw in _prefix for kw in ("职称", "证书", "打印", "输出", "岗位名称", "职务名称", "职位名称")):
                    pos = pos_kv_clean
            # 职位里的尾部句末标点「。.」去掉（如：负责更新仓库水洗标、合格证打印。）
            # EN: Remove trailing sentence punctuation "。." in positions (e.g. 负责更新仓库水洗标、合格证打印。)
            # JA: 職位の末尾の句点「。.」を除く（例：负责更新仓库水洗标、合格证打印。）
            pos = pos.rstrip("。.！!？?；;，,、 　")
            # 但如果句子超长（> 40字）且含多个标点 → 是职责句子，不是职位，清空职位
            # EN: But if the sentence is very long (> 40 characters) and has several punctuation marks → it is a duty sentence, not a position; clear the position
            # JA: ただし文が非常に長く（40 文字超）句読点を複数含む場合 → 職務の文であって職位ではないので、職位を空にする
            if len(pos) > 40 and sum(pos.count(c) for c in "，,。.；;！!？?") >= 2:
                pos = ""
            w["position"] = pos
        # ============================================================================
        # ★V2严格新增：company/position 垃圾值剥离 + 挪到responsibilities（倪业平/于宙等 case）
        # ============================================================================
        # EN: ============================================================================
        #     ★New in strict V2: strip junk company/position values + move them into responsibilities (past cases)
        #     ============================================================================
        # JA: ============================================================================
        #     ★V2 厳格版の追加：company/position のゴミ値を除き responsibilities に移す（過去の事例）
        #     ============================================================================
        _cname = str(w.get("company_name") or "").strip()
        _posv = str(w.get("position") or "").strip()
        _respv = str(w.get("position_responsibilities") or "").strip()
        # —— 垃圾值定义（板块标题/离职原因/动作状语开头）——
        # EN: —— Definition of junk values (section headings / reasons for leaving / starting with action adverbials) ——
        # JA: —— ゴミ値の定義（セクション見出し・退職理由・動作の状況語で始まるもの）——
        _BLOCK_TITLE_AS_GARBAGE = ("工 作 经 验", "工作经验", "工作经历", "求职意向", "教育经历",
                                   "教育背景", "培训经历", "项目经验", "自我评价", "个人简历",
                                   "个人求职简历", "简历", "基本信息", "基本资料", "个人资料")
        _EXIT_REASON_GARBAGE = ("个人原因", "家庭原因", "身体原因", "升学", "考研", "出国",
                                 "校内实习", "校外实习", "实习结束", "合同到期", "公司搬迁",
                                 "薪资问题", "发展受限", "寻求更好发展", "职业转型", "离职原因",
                                 "个人原因（", "个人原因(")
        _COMP_ACTION_HEAD = ("每月", "每季度", "每年", "每周", "每日", "定期", "按时", "及时",
                              "编制", "记录", "登记", "核算", "结算", "对账", "开票", "发票",
                              "增值税", "税务", "报税", "记账", "凭证", "现金", "银行", "转账",
                              "支付", "付款", "收款", "报销", "费用", "开支", "办理", "退单",
                              "跟踪", "跟进", "处理", "整理", "统计", "分析", "维护", "管理",
                              "监督", "接待", "服务", "各项", "固定", "临时", "当月", "当年",
                              "当期", "期末", "月初", "月末", "年初", "年末", "汇缴", "申报",
                              "入库", "出库", "盘点", "在库", "库存", "预算", "修正", "修订",
                              # —— V2.1补：通用动作动词（倪业平「负责更新...」漏网case）
                              # EN: —— V2.1 addition: generic action verbs (a past case "负责更新..." (responsible for updating...) slipped through)
                              # JA: —— V2.1 の追加：汎用的な動作の動詞（過去の事例「负责更新...」（〜の更新を担当）が漏れていた）
                              "负责", "协助", "组织", "开发", "参与", "制定", "配合", "完成",
                              "建立", "收集", "提供", "推广", "推进", "改善", "提高", "拓展",
                              "沟通", "协调", "设计", "制作", "发放", "招募", "宣传", "策划",
                              "运营", "建设", "参加", "支持", "调研",
                              # 连词/副词开头
                              # EN: Starting with a conjunction/adverb
                              # JA: 接続詞・副詞で始まる
                              "在这", "在我", "期间", "主要", "其中", "包括", "并", "并且",
                              "而且", "然后", "同时", "随后", "以及", "前往", "去往", "会前往",
                              "并会", "负责更新", "负责客户", "负责公司", "负责每月",
                              )
        _COMP_ACTION_TAIL_RE = re.compile(r"(的|地|得)(审核|支付|处理|管理|维护|登记|统计|分析|结算|对账|编制|申报|招聘|培训|销售|采购|生产|服务|接待|跟进|跟踪|整理|录入|检查|监督|报销|付款|收款|开票|认证|工作|任务|事项|内容|职责)$")
        _POS_ACTION_HEAD = _COMP_ACTION_HEAD
        _POS_ACTION_TAIL_RE = _COMP_ACTION_TAIL_RE

        # ---------- company_name 修复 ----------
        # EN: ---------- company_name fixes ----------
        # JA: ---------- company_name の修正 ----------
        if _cname:
            # a) 纯板块标题（「工 作 经 验」等）→ 直接清空，让后续从 responsibilities 反推
            # EN: a) A pure section heading ("工 作 经 验" (work experience) etc.) → clear it directly and let later steps infer from responsibilities
            # JA: a) 純粋なセクション見出し（「工 作 经 验」（職歴）など）→ そのまま空にし、後続の処理で responsibilities から逆算させる
            if any(b in _cname for b in _BLOCK_TITLE_AS_GARBAGE) and len(_cname) <= 15:
                w["company_name"] = ""
                _cname = ""
            else:
                # b) 前缀剥离：「修正工作单位上海旦瑞投资管理有限公司」→ 剥掉「修正工作单位」
                # EN: b) Prefix stripping: "修正工作单位上海旦瑞投资管理有限公司" → strip "修正工作单位" (corrected employer)
                # JA: b) 接頭辞の除去：「修正工作单位上海旦瑞投资管理有限公司」→「修正工作单位」（勤務先の訂正）を除く
                _STRIP_PREFIXES = ("修正工作单位", "工作单位", "工作公司", "公司名称", "企业名称",
                                    "单位名称", "离职原因：", "离职原因:", "个人原因：", "个人原因:")
                for _sp in _STRIP_PREFIXES:
                    if _cname.startswith(_sp):
                        _cname = _cname[len(_sp):].strip(" :：，,。.；;")
                        break
                # c) 包含离职原因词（如「个人原因校内实习」→ 整个是离职原因，直接清空；如「XX公司个人原因」→ 剥掉后半段）
                # EN: c) Contains reason-for-leaving words (e.g. "个人原因校内实习" → the whole thing is a reason for leaving, clear it; e.g. "XX公司个人原因" → strip the second half)
                # JA: c) 退職理由の語を含む（例：「个人原因校内实习」→ 全体が退職理由なので空にする。例：「XX公司个人原因」→ 後半を除く）
                _stripped_ex = False
                for _exr in _EXIT_REASON_GARBAGE:
                    _ix = _cname.find(_exr)
                    if _ix > 0:
                        # 离职原因出现在中间/末尾 → 剥掉后半段
                        # EN: A reason for leaving appears in the middle/end → strip the second half
                        # JA: 退職理由が途中・末尾に現れる → 後半を除く
                        _front = _cname[:_ix].strip(" :：，,。.；;()（）")
                        _cname = _front if len(_front) >= 2 else ""
                        _stripped_ex = True
                        break
                    elif _ix == 0:
                        # 开头就是离职原因词（如「个人原因校内实习」）→ 整段是离职原因，直接清空
                        # EN: Starts with a reason-for-leaving word (e.g. "个人原因校内实习") → the whole thing is a reason for leaving, clear it
                        # JA: 退職理由の語で始まる（例：「个人原因校内实习」）→ 全体が退職理由なので空にする
                        _cname = ""
                        _stripped_ex = True
                        break
                if not _stripped_ex:
                    pass
                # d) 动作状语开头/结尾 → 挪到 responsibilities 前面，清空company
                # EN: d) Starts/ends with an action adverbial → move it to the front of responsibilities and clear company
                # JA: d) 動作の状況語で始まる・終わる → responsibilities の前に移し、company を空にする
                _bad_head = any(_cname.startswith(ah) for ah in _COMP_ACTION_HEAD)
                _bad_tail = bool(_COMP_ACTION_TAIL_RE.search(_cname))
                if _bad_head or _bad_tail:
                    _add_to_resp = _cname
                    if _add_to_resp:
                        w["position_responsibilities"] = (_add_to_resp + "\n" + _respv) if _respv else _add_to_resp
                    _cname = ""
                w["company_name"] = _cname

        # ---------- position 修复 ----------
        # EN: ---------- position fixes ----------
        # JA: ---------- position の修正 ----------
        if _posv:
            _bad_head_pos = any(_posv.startswith(ah) for ah in _POS_ACTION_HEAD)
            _bad_tail_pos = bool(_POS_ACTION_TAIL_RE.search(_posv))
            _too_long_pos = len(_posv) > 20  # 合法职位名一般<20
            # EN: Legitimate position names are generally < 20 characters
            # JA: 正当な職位名は通常 20 文字未満
            _too_many_punc_pos = sum(_posv.count(c) for c in "，,。.！!？?；;、") >= 2
            if _bad_head_pos or _bad_tail_pos or _too_many_punc_pos:
                # 肯定是职责短语 → 放到 responsibilities 前，position 空让后续从 dept/首行反推
                # EN: Definitely a duty phrase → put it before responsibilities, leave position empty for later inference from dept/the first line
                # JA: 明らかに職務の語句 → responsibilities の前に置き、position は空にして後で dept や 1 行目から逆算させる
                _add_to_resp = _posv
                if _add_to_resp:
                    _curr_resp = str(w.get("position_responsibilities") or "").strip()
                    w["position_responsibilities"] = (_add_to_resp + "\n" + _curr_resp) if _curr_resp else _add_to_resp
                w["position"] = ""
            elif _too_long_pos:
                # 长度>20：先剥尾部动作/描述词，剥完仍>20 → 空
                # EN: Length > 20: first strip trailing action/description words; if still > 20 → empty
                # JA: 長さが 20 超：まず末尾の動作・説明の語を除き、それでも 20 超なら空にする
                _stripped_pos = re.sub(r"(负责|从事|担任|参与|协助|主要|期间).*$", "", _posv, count=1).strip()
                if len(_stripped_pos) <= 20 and _stripped_pos:
                    w["position"] = _stripped_pos
                else:
                    _curr_resp2 = str(w.get("position_responsibilities") or "").strip()
                    w["position_responsibilities"] = (_posv + "\n" + _curr_resp2) if _curr_resp2 else _posv
                    w["position"] = ""
        # ============================================================================
        # ★姜海波case补修：①[X年Y个月]/[X个月] duration标签从position/company里剥离，移到resp前缀 或 写独立work_duration
        #                 ②(500人以上)/少于50人 等 员工规模标签 → 若company_employees空则挪入
        #                 ③结束日期空，但resp/resp首行含「至今/现在/目前」等 → 补position_resigned=至今
        # ============================================================================
        # EN: ============================================================================
        #     ★Patch for a past case: ① strip duration labels [X年Y个月]/[X个月] (X years Y months) from position/company, move them to the resp prefix or write a separate work_duration
        #                     ② employee-size labels such as (500人以上)/少于50人 → move into company_employees if it is empty
        #                     ③ end date empty but resp / the first line of resp contains "至今/现在/目前" (present/now/currently) etc. → set position_resigned=至今
        #     ============================================================================
        # JA: ============================================================================
        #     ★過去の事例への追加修正：① [X年Y个月]／[X个月]（X 年 Y か月）の期間ラベルを position/company から除き、resp の先頭に移すか独立した work_duration に書く
        #                     ② (500人以上)／少于50人 などの従業員規模のラベル → company_employees が空ならそこへ移す
        #                     ③ 終了日が空だが resp やその 1 行目に「至今／现在／目前」（現在）などがある → position_resigned=至今 を補う
        #     ============================================================================
        _DURATION_LABEL_RE = re.compile(r"[\[\(（【]\s*(?:\d+\s*年)?\s*\d+\s*个?月\s*[\]\)）】]")   # 如：[ 1 年9个月]、[4个月]、（2年8个月）
        # EN: e.g.: [ 1 年9个月], [4个月], （2年8个月）
        # JA: 例：[ 1 年9个月]、[4个月]、（2年8个月）
        _DURATION_INNER_RE = re.compile(r"^[\[\(（【]\s*(.+?)\s*[\]\)）】]$")
        _EMP_SIZE_LABEL_RE = re.compile(r"[\(\(（【]\s*[^()（）\[\]【】]{0,30}\s*\d+\s*(?:[-–~～至到]\s*\d+)?\s*(?:人以下|人以内|人以上|人)\s*[\)\)）】]")
        _EMP_SIZE_INNER_RE = re.compile(r"^[\(\(（【]\s*(.+?\s*人)\s*[\)\)）】]$")
        _END_HINT_KW = ("至今", "现在", "目前", "Present", "Current")

        _pv2 = str(w.get("position") or "").strip()
        _cv2 = str(w.get("company_name") or "").strip()
        _dv2 = str(w.get("position_dept") or "").strip()
        _rv2 = str(w.get("position_responsibilities") or "").strip()
        _ev2 = str(w.get("position_resigned") or "").strip()
        _cev2 = str(w.get("company_employees") or "").strip()

        # --- 1) 从 position / company 里剥 duration 标签 ---
        # EN: --- 1) Strip duration labels from position / company ---
        # JA: --- 1) position / company から期間ラベルを除く ---
        for _fld in ("position", "company_name", "position_dept"):
            _fv = str(w.get(_fld) or "").strip()
            if not _fv:
                continue
            _m = _DURATION_LABEL_RE.search(_fv)
            if _m:
                _lab = _m.group(0).strip()
                _inner = _DURATION_INNER_RE.match(_lab)
                _dur_txt = _inner.group(1).replace(" ", "") if _inner else _lab.strip("[]()（）【】").replace(" ", "")
                # 如果是纯duration（如 "[ 1 年9个月]" / "[4个月]" → 整个是它）→ 整个清空
                # EN: If it is a pure duration (e.g. "[ 1 年9个月]" / "[4个月]" is the whole value) → clear it entirely
                # JA: 期間だけの場合（例：値全体が「[ 1 年9个月]」／「[4个月]」）→ まるごと空にする
                if _lab == _fv:
                    w[_fld] = ""
                else:
                    w[_fld] = _fv.replace(_lab, " ").strip(" :：,，.。；;")
                # 写入 work_duration（如已存在更长的就不覆盖），并在resp前加一行【工作时长：X年Y个月】
                # EN: Write into work_duration (do not overwrite if a longer one already exists), and add a line 【工作时长：X年Y个月】 (work duration) at the front of resp
                # JA: work_duration に書き込み（より長いものがすでにあれば上書きしない）、resp の先頭に【工作时长：X年Y个月】（勤務期間）の行を追加する
                _ex_dur = str(w.get("work_duration") or "").strip()
                if not _ex_dur or len(_dur_txt) > len(_ex_dur):
                    w["work_duration"] = _dur_txt
                if _dur_txt:
                    _hdr = f"【工作时长：{_dur_txt}】"
                    _curr_resp3 = str(w.get("position_responsibilities") or "").strip()
                    if _hdr not in _curr_resp3:
                        w["position_responsibilities"] = (_hdr + "\n" + _curr_resp3) if _curr_resp3 else _hdr

        # --- 2) 员工规模标签：从company_name/position_dept/position_responsibilities里剥 → company_employees ---
        # EN: --- 2) Employee-size labels: strip from company_name/position_dept/position_responsibilities → company_employees ---
        # JA: --- 2) 従業員規模のラベル：company_name／position_dept／position_responsibilities から除き → company_employees へ ---
        if not _cev2:
            for _fld in ("company_name", "position_dept", "position", "position_responsibilities"):
                _fv = str(w.get(_fld) or "").strip()
                if not _fv:
                    continue
                _m = _EMP_SIZE_LABEL_RE.search(_fv)
                if _m:
                    _lab = _m.group(0).strip()
                    _inner = _EMP_SIZE_INNER_RE.match(_lab)
                    _sz = _inner.group(1).strip() if _inner else _lab.strip("()（）【】").strip()
                    if _sz:
                        if _lab == _fv:
                            w[_fld] = ""
                        else:
                            w[_fld] = _fv.replace(_lab, " ").strip(" :：,，.。；;")
                        w["company_employees"] = _sz
                        _cev2 = _sz
                        break

        # --- 3) 结束日期空，但 respons 或 resp 首行 / dept 里有 "至今" 等关键词 → 补 position_resigned ---
        # EN: --- 3) End date empty but responsibilities, the first line of resp, or dept contains keywords like "至今" (present) → fill position_resigned ---
        # JA: --- 3) 終了日が空だが、responsibilities や resp の 1 行目、dept に「至今」（現在）などのキーワードがある → position_resigned を補う ---
        if not _ev2:
            _scan_txt = " \n ".join([
                str(w.get("position_responsibilities") or "").strip()[:400],
                str(w.get("position_dept") or ""),
                str(w.get("position") or ""),
                str(w.get("company_name") or ""),
                str(w.get("work_duration") or ""),
                str(w.get("position_achievements") or "").strip()[:200],
            ])
            for _kw in _END_HINT_KW:
                if _kw in _scan_txt:
                    # 选最精准的中文值
                    # EN: Pick the most precise Chinese value
                    # JA: 最も正確な中国語の値を選ぶ
                    if _kw in ("Present", "Current"):
                        w["position_resigned"] = "至今"
                    else:
                        w["position_resigned"] = _kw
                    break
        # ============================================================================
        # ★兜底修复1（雷审旗PD case）：company 长度<=3 或是纯大写ASCII 2~4字母 → 99%是部门代号/缩写，从responsibilities前10行里找第一个合法的公司名候选替换
        # ★兜底修复2（姜海波position空case）：position空，从responsibilities前5行里找第一个职位词 → 补position
        # ============================================================================
        # EN: ============================================================================
        #     ★Fallback fix 1 (a past case, "PD"): company length <= 3 or pure uppercase ASCII of 2-4 letters → 99% a department code/abbreviation; replace it with the first valid company-name candidate in the first 10 lines of responsibilities
        #     ★Fallback fix 2 (a past case with empty position): position empty → find the first position word in the first 5 lines of responsibilities → fill position
        #     ============================================================================
        # JA: ============================================================================
        #     ★最終手段の修正 1（過去の事例「PD」）：company が 3 文字以下、または大文字 ASCII 2〜4 文字だけ → 99% 部署コード・略語なので、responsibilities の最初の 10 行から最初の正当な会社名候補を探して置き換える
        #     ★最終手段の修正 2（position が空だった過去の事例）：position が空 → responsibilities の最初の 5 行から最初の職位の語を探して position を補う
        #     ============================================================================
        _cv3 = str(w.get("company_name") or "").strip()
        _pv3 = str(w.get("position") or "").strip()
        _rv3 = str(w.get("position_responsibilities") or "").strip()
        # ---- 公司名兜底：cvv<=3字、或纯大写(2-4字母)、或 "PD/HR/IT/RD/QA/BD" 等典型部门缩写 → 触发替换 ----
        # EN: ---- Company-name fallback: cvv <= 3 characters, or pure uppercase (2-4 letters), or typical department abbreviations like "PD/HR/IT/RD/QA/BD" → trigger replacement ----
        # JA: ---- 会社名の最終手段：cvv が 3 文字以下、大文字のみ（2〜4 文字）、または「PD/HR/IT/RD/QA/BD」などの典型的な部署略語 → 置き換えを発動 ----
        _COMP_TRIGGER_RE = re.compile(r"^[A-Z]{1,4}$")
        _need_comp_fallback = False
        if _cv3:
            if len(_cv3) <= 3:
                _need_comp_fallback = True
            elif _COMP_TRIGGER_RE.match(_cv3):
                _need_comp_fallback = True
        if not _cv3:
            _need_comp_fallback = True  # 公司名空也尝试兜底找
            # EN: Also try the fallback search when the company name is empty
            # JA: 会社名が空の場合も最終手段の探索を試みる
        if _need_comp_fallback and _rv3:
            _COMP_STRONG_SUFF_RE = re.compile(
                r"[A-Za-z\u4e00-\u9fff（）()][A-Za-z0-9\u4e00-\u9fff &.+\-·（）()]{2,50}?"
                r"(有限责任公司|股份有限公司|有限公司|股份公司|集团公司|集团|制造厂|工厂|分公司|办事处|代表处|事业部|银行|基金|证券|保险|事务所|研究院|研究所|医院|学校|大学|学院|控股)"
            )
            _COMP_FOREIGN_CITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&.+\- ]{1,30}[ \t\xa0]+(北京|上海|广州|深圳|苏州|杭州|南京|成都|武汉|西安|天津|重庆|青岛|大连|宁波|无锡|长沙|沈阳|郑州|济南|厦门)$")
            _lines = [ln.strip() for ln in _rv3.splitlines() if ln.strip()][:10]
            _found_new_comp = ""
            for _ln in _lines:
                # 1) 强公司标志优先（有限公司等）
                # EN: 1) Strong company markers first (有限公司 etc.)
                # JA: 1) 強い会社の目印を優先（有限公司など）
                m_s = _COMP_STRONG_SUFF_RE.search(_ln)
                if m_s:
                    cand = m_s.group(0).strip()
                    if _has_comp_sign_global(cand) or (len(cand) >= 4 and len(cand) <= 50):
                        _found_new_comp = cand; break
                # 2) 外企+城市格式（Polartec 上海）
                # EN: 2) Foreign company + city format (Polartec 上海)
                # JA: 2) 外資系企業 + 都市の形式（Polartec 上海）
                for _seg in re.split(r"[|｜]\s*", _ln):
                    _seg = _seg.strip()
                    if len(_seg) <= 50 and _COMP_FOREIGN_CITY_RE.match(_seg):
                        _found_new_comp = _seg; break
                if _found_new_comp: break
                # 3) 纯整行（无标点）的含_COMP_SIGNS_STRONG 的 seg
                # EN: 3) A whole-line seg (no punctuation) containing _COMP_SIGNS_STRONG
                # JA: 3) _COMP_SIGNS_STRONG を含む、行全体（句読点なし）の seg
                for _seg in re.split(r"[|｜]\s*", _ln):
                    _seg = _seg.strip()
                    if 4 <= len(_seg) <= 50 and _has_comp_sign_global(_seg):
                        # 还要排除它是纯部门/职位词（如"人事部"、"产品开发部"）
                        # EN: Also exclude pure department/position words (e.g. "人事部" (personnel dept), "产品开发部" (product development dept))
                        # JA: さらに純粋な部署・職位の語（例：「人事部」、「产品开发部」（製品開発部））を除外する
                        if not (len(_seg) <= 6 and _seg.endswith(("部","组","科","课","室","站","所","队"))):
                            _found_new_comp = _seg; break
                if _found_new_comp: break
            if _found_new_comp and _found_new_comp != _cv3:
                # 旧company如果是纯大写的部门缩写PD → 改放position_dept（如果dept原本空）
                # EN: If the old company was a pure uppercase department abbreviation like PD → move it into position_dept (if dept was empty)
                # JA: 旧 company が PD のような大文字だけの部署略語なら → position_dept に移す（dept が空の場合）
                if _cv3 and (len(_cv3) <= 3 or _COMP_TRIGGER_RE.match(_cv3)):
                    old_dept = str(w.get("position_dept") or "").strip()
                    if not old_dept and not (len(_cv3) <= 6 and _cv3.endswith(("部","组","科","课","室","站","所","队"))):
                        # PD等 → 作为部门
                        # EN: PD etc. → treat as a department
                        # JA: PD など → 部署として扱う
                        w["position_dept"] = _cv3
                w["company_name"] = _found_new_comp
        # ---- position空：从responsibilities前5行找第一个职位词 ----
        # EN: ---- position empty: find the first position word in the first 5 lines of responsibilities ----
        # JA: ---- position が空：responsibilities の最初の 5 行から最初の職位の語を探す ----
        if not _pv3 and _rv3:
            _POS_TITLE_SUFF = ("经理", "主管", "主任", "总监", "专员", "助理", "顾问", "销售", "代表", "会计", "出纳",
                               "文员", "秘书", "行政", "人事", "财务", "组长", "科长", "部长", "工程师", "设计师",
                               "技术员", "分析师", "讲师", "培训师", "编辑", "记者", "校长", "院长", "所长",
                               "店长", "厂长", "副厂长", "副经理", "总经理", "副总经理", "程序员", "测试",
                               "开发", "运营", "策划", "设计", "分析", "担当", "调达", "业务员", "营业员", "导购")
            _first_lines_pos = [ln.strip() for ln in _rv3.splitlines() if ln.strip()][:6]
            _found_pos = ""
            # 逐行找第一个含职位后缀的子串（长度<=30，非纯描述句）
            # EN: Look line by line for the first substring with a position suffix (length <= 30, not a pure descriptive sentence)
            # JA: 行ごとに、職位の接尾辞を含む最初の部分文字列を探す（長さ 30 以下、純粋な説明文ではない）
            _POS_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9·/\-&()（）]{1,25}?(?:" + "|".join(re.escape(sf) for sf in sorted(_POS_TITLE_SUFF,key=len,reverse=True)) + r")")
            for _ln in _first_lines_pos:
                # 如果是【工作时长：X年Y个月】标签，跳过
                # EN: Skip it if it is a 【工作时长：X年Y个月】 (work duration) label
                # JA: 【工作时长：X年Y个月】（勤務期間）のラベルならスキップする
                if _ln.startswith("【工作时长"): continue
                m_p = _POS_RE.search(_ln)
                if m_p:
                    cand = m_p.group(0).strip(" ·-_/&()（）")
                    # 必须不是长句（含多个标点）→ 才是职位
                    # EN: Must not be a long sentence (with several punctuation marks) → only then is it a position
                    # JA: 長い文（句読点が複数）でない場合だけ職位とみなす
                    n_punc = sum(cand.count(c) for c in "，,。.！!？?；;、")
                    if n_punc == 0 and 2 <= len(cand) <= 30:
                        _found_pos = cand; break
                # 再 fallback：整行如果 <= 30 且 含关键词"工程师/经理..." 又不超过 3个标点 → 直接取
                # EN: Further fallback: if the whole line is <= 30, contains keywords like "工程师/经理..." (engineer/manager) and has no more than 3 punctuation marks → take it directly
                # JA: さらに最終手段：行全体が 30 文字以下で「工程师／经理...」（エンジニア／マネージャー）などのキーワードを含み、句読点が 3 個以下 → そのまま採用
                n_punc2 = sum(_ln.count(c) for c in "，,。.！!？?；;、")
                if len(_ln) <= 30 and n_punc2 == 0 and any(sf in _ln for sf in _POS_TITLE_SUFF):
                    # 还要排除"XX部"（部门名不是职位）
                    # EN: Also exclude "XX部" (department names are not positions)
                    # JA: さらに「XX部」を除外する（部署名は職位ではない）
                    if not (len(_ln) <= 8 and _ln.endswith(("部", "组", "科", "课", "室", "站", "所", "队", "中心"))):
                        _found_pos = _ln; break
            if _found_pos:
                w["position"] = _found_pos
        cleaned_works.append(w)
    # 去重：公司+职位+起始日期 完全相同的段（51job 两段式打印两次），保留一个
    # EN: Dedup: entries with identical company + position + start date (51job's two-part layout printed twice) keep one
    # JA: 重複排除：会社 + 職位 + 開始日が完全に同じ項目（51job の 2 段構成で 2 回出力されたもの）は 1 件だけ残す
    seen = set()
    dedup_works = []
    for w in cleaned_works:
        key = (str(w.get("company_name") or "").strip(),
               str(w.get("position") or "").strip(),
               str(w.get("position_start") or "").strip(),
               str(w.get("position_resigned") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        dedup_works.append(w)

    # ============================================================================
    # ★同公司紧邻段合并（雷审旗等case：嘉兴伯林顿2007/5→2007/9 + 2007/10→2011/6 是同一公司内部调岗/晋升，合并成一段）
    #    合并条件：①公司名核心（剥去尾缀"有限/股份/集团/中国/代表处/分公司/办事处"）相同；②前一段的结束日期≤后一段开始日期+90天（相邻季度内）
    #    合并策略：start取最早，end取最晚；职位/部门 用 "早期职位 → 晚期职位" 拼接；resp拼接两段的resp
    # ============================================================================
    # EN: ============================================================================
    #     ★Merge adjacent entries at the same company (past cases: 2007/5→2007/9 + 2007/10→2011/6 at the same company are an internal transfer/promotion; merge into one)
    #        Merge conditions: ① the core company name (with suffixes like "有限/股份/集团/中国/代表处/分公司/办事处" stripped) is the same; ② the earlier entry's end date ≤ the later entry's start date + 90 days (within an adjacent quarter)
    #        Merge strategy: start takes the earliest, end the latest; position/department joined as "earlier position → later position"; resp concatenates both entries' resp
    #     ============================================================================
    # JA: ============================================================================
    #     ★同じ会社で隣接する項目の統合（過去の事例：同じ会社の 2007/5→2007/9 + 2007/10→2011/6 は社内異動・昇進なので 1 件に統合）
    #        統合条件：① 会社名の中核部分（「有限／股份／集团／中国／代表处／分公司／办事处」などの接尾辞を除いたもの）が同じ、② 前の項目の終了日 ≦ 後の項目の開始日 + 90 日（隣接する四半期内）
    #        統合方針：start は最も早いもの、end は最も遅いもの。職位・部署は「前の職位 → 後の職位」と連結し、resp は両方の resp を連結する
    #     ============================================================================
    def _company_core(cn: str) -> str:
        """提取公司名核心用于比较：剥掉公司尾缀、地点、性质括号等不影响同一性的部分。

        EN: Extract the core of a company name for comparison: strip company suffixes, places, type brackets and other parts that do not affect identity.

        JA: 比較用に会社名の中核を抽出する：会社の接尾辞・地名・性質の括弧など、同一性に影響しない部分を除く。
        """
        cn2 = (cn or "").strip()
        if not cn2:
            return ""
        # 先剥尾括号(性质/规模/国别)
        # EN: First strip trailing brackets (type/size/country)
        # JA: まず末尾の括弧（性質・規模・国名）を除く
        cn2 = re.sub(r"[（(][^)）]{0,30}[)）]$", "", cn2).strip()
        # 再剥公司通用法律尾缀（从长到短，避免截断正确公司名）
        # EN: Then strip generic legal suffixes of companies (from long to short, so correct company names are not truncated)
        # JA: 次に会社の一般的な法人格の接尾辞を除く（長いものから順に。正しい会社名を切り詰めないため）
        _TAIL_SUFF = ("股份有限公司", "有限责任公司", "有限公司", "（中国）", "(中国)", "中国代表处", "代表处",
                      "分公司", "办事处", "事业部", "股份公司", "集团公司", "集团", "股份")
        for _s in sorted(_TAIL_SUFF, key=len, reverse=True):
            if cn2.endswith(_s):
                cn2 = cn2[:-len(_s)].rstrip(" ·-_/&,，.。 ")
        # 再剥地名尾缀（2~3字常见中国地级市）
        # EN: Then strip place-name suffixes (common 2-3 character Chinese prefecture-level cities)
        # JA: 次に地名の接尾辞を除く（2〜3 文字のよくある中国の地級市）
        _CITY_TAIL = ("上海", "北京", "广州", "深圳", "苏州", "杭州", "南京", "成都", "武汉", "西安",
                      "重庆", "青岛", "大连", "宁波", "无锡", "长沙", "沈阳", "郑州", "济南", "厦门")
        for _ct in _CITY_TAIL:
            if len(cn2) >= 5 and cn2.endswith(_ct):
                cn2 = cn2[:-len(_ct)].rstrip(" ·-_/&,，.。 ")
        return cn2.rstrip()
    def _ym_to_months(ym: str) -> int | None:
        """2011年06月01日 / 2011年06月 / 2011.06 → 总月数（以公元0年为基准），用于比较相邻。

        EN: 2011年06月01日 / 2011年06月 / 2011.06 → total months (counted from year 0 AD), used to compare adjacency.

        JA: 2011年06月01日 / 2011年06月 / 2011.06 → 通算の月数（西暦 0 年基準）。隣接の比較に使う。
        """
        if not ym:
            return None
        m_y = re.search(r"(19|20)\d{2}", ym)
        if not m_y:
            return None
        y = int(m_y.group(0))
        mo_match = re.search(r"年\s*(\d{1,2})|[\./\-]\s*(\d{1,2})(?!\d)", ym)
        mo = int([m for m in mo_match.groups() if m][0]) if mo_match and mo_match.groups() else 1
        try:
            return y * 12 + max(1, min(12, mo))
        except Exception:
            return None

    if len(dedup_works) >= 2:
        merged_works: list[dict[str, Any]] = []
        _buf: dict[str, Any] | None = None
        # 工作段通常按时间倒序（最新在前），遍历顺序不变，只合并相邻同公司
        # EN: Work entries are usually in reverse chronological order (newest first); keep the traversal order and merge only adjacent entries at the same company
        # JA: 職歴の項目は通常新しい順（最新が先頭）なので、走査順は変えずに隣接する同じ会社の項目だけを統合する
        for w in dedup_works:
            if _buf is None:
                _buf = dict(w)
                continue
            cur_c = (w.get("company_name") or "").strip()
            buf_c = (_buf.get("company_name") or "").strip()
            cur_core = _company_core(cur_c)
            buf_core = _company_core(buf_c)
            if cur_core and buf_core and (cur_core == buf_core):
                # 比较日期（工作段倒序：buf=新→cur=旧）
                # EN: Compare dates (work entries in reverse order: buf = newer → cur = older)
                # JA: 日付を比較する（職歴は新しい順：buf = 新しい方 → cur = 古い方）
                buf_s = _ym_to_months(str(_buf.get("position_start") or ""))
                buf_e = _ym_to_months(str(_buf.get("position_resigned") or ""))
                cur_s = _ym_to_months(str(w.get("position_start") or ""))
                cur_e = _ym_to_months(str(w.get("position_resigned") or ""))
                _adjacent = False
                # 优先：倒序间隔（前一段结束 cur_e → 后一段开始 buf_s）—— 主判定
                # EN: First: reverse-order gap (end of the earlier entry cur_e → start of the later entry buf_s) — the main criterion
                # JA: 第一：新しい順での間隔（前の項目の終了 cur_e → 後の項目の開始 buf_s）— 主な判定
                if cur_e is not None and buf_s is not None:
                    _adjacent = abs(cur_e - buf_s) <= 3
                # 次优先：顺次间隔（前一段结束 buf_e → 后一段开始 cur_s）
                # EN: Second: forward-order gap (end of the earlier entry buf_e → start of the later entry cur_s)
                # JA: 第二：古い順での間隔（前の項目の終了 buf_e → 後の項目の開始 cur_s）
                elif buf_e is not None and cur_s is not None:
                    _adjacent = abs(buf_e - cur_s) <= 3
                # 其他情况：至少一侧无日期 → 认为不是紧邻（避免乱合并）
                # EN: Other cases: at least one side has no date → not considered adjacent (to avoid arbitrary merging)
                # JA: その他：少なくとも一方に日付がない → 隣接とはみなさない（むやみな統合を避ける）
                else:
                    _adjacent = False
                # —— ★雷审旗补：紧邻同公司但【两段都有明确职位名且不同】→ 不合并（保留晋升/调岗记录：后整理主管 → 产品开发经理 是两个独立阶段）
                #     同理：两段都有明确部门名且不同 → 也不合并
                #     ★★再加严格兜底：两段中任意一段的position/dept有明确非空值（>2字）→ 除非完全相同，否则坚决不合并（宁留两段，不漏一段）
                # EN: —— ★Patch for a past case: adjacent at the same company but [both entries have explicit, different position names] → do not merge (keep promotion/transfer records: e.g. finishing supervisor → product development manager are two separate stages)
                #         Likewise: both entries have explicit, different department names → do not merge either
                #         ★★Stricter fallback: if either entry has an explicit non-empty position/dept (>2 characters) → never merge unless identical (better keep two entries than lose one)
                # JA: —— ★過去の事例への追加修正：同じ会社で隣接していても【両方に明確な職位名があり、それが異なる】→ 統合しない（昇進・異動の記録を残す：例えば仕上げ主任 → 製品開発マネージャーは独立した 2 つの段階）
                #         同様に：両方に明確な部署名があり、それが異なる → 統合しない
                #         ★★さらに厳格な最終手段：どちらかの項目の position/dept に明確な空でない値（2 文字超）がある → 完全に同じでない限り絶対に統合しない（1 件を失うより 2 件残す方がよい）
                _pos_cur = (w.get("position") or "").strip()
                _pos_buf = (_buf.get("position") or "").strip()
                _dept_cur = (w.get("position_dept") or w.get("department") or "").strip()
                _dept_buf = (_buf.get("position_dept") or "").strip()
                # 明确非空判定：长度>=2且不是纯垃圾值
                # EN: Explicit non-empty check: length >= 2 and not a pure junk value
                # JA: 明確な空でない値の判定：長さ 2 以上で純粋なゴミ値ではない
                _ok_pc = len(_pos_cur) >= 2; _ok_pb = len(_pos_buf) >= 2
                _ok_dc = len(_dept_cur) >= 2; _ok_db = len(_dept_buf) >= 2
                if (_ok_pc and _ok_pb and _pos_cur != _pos_buf):
                    _adjacent = False  # 两个都有明确职位且不同 → 不合并
                    # EN: Both have explicit, different positions → do not merge
                    # JA: 両方に明確で異なる職位がある → 統合しない
                elif (_ok_dc and _ok_db and _dept_cur != _dept_buf):
                    _adjacent = False  # 两个都有明确部门且不同 → 不合并
                    # EN: Both have explicit, different departments → do not merge
                    # JA: 両方に明確で異なる部署がある → 統合しない
                elif ((_ok_pc or _ok_dc) and (_ok_pb or _ok_db)):
                    # 两边都有（职位或部门任一明确）但不完全一样 → 不合并（保留晋升）
                    # EN: Both sides have a value (either an explicit position or department) but not exactly the same → do not merge (keep the promotion)
                    # JA: 両方に値がある（職位か部署のどちらかが明確）が完全には一致しない → 統合しない（昇進を残す）
                    if (_pos_cur + _dept_cur) != (_pos_buf + _dept_buf):
                        _adjacent = False
                # —— ★再补：两段分别有员工规模(company_employees)，且都不是下属人数（≥2人），也不合并
                # EN: —— ★Further patch: the two entries each have an employee size (company_employees), neither being a number of subordinates (≥2 people) → do not merge either
                # JA: —— ★さらなる追加：両方の項目にそれぞれ従業員規模（company_employees）があり、どちらも部下の人数（2 人以上）ではない → これも統合しない
                _emps_cur = (w.get("company_employees") or "").strip()
                _emps_buf = (_buf.get("company_employees") or "").strip()
                if _adjacent and _emps_cur and _emps_buf and "人" in _emps_cur and "人" in _emps_buf:
                    # 两个都有明确公司规模 → 不合并
                    # EN: Both have explicit company sizes → do not merge
                    # JA: 両方に明確な会社規模がある → 統合しない
                    _adjacent = False
                if _adjacent:
                    # --- 合并同公司紧邻段 ---
                    # start = 两者中较早的一个；end = 两者中较晚的一个
                    # EN: --- Merge adjacent entries at the same company ---
                    #     start = the earlier of the two; end = the later of the two
                    # JA: --- 同じ会社の隣接する項目を統合 ---
                    #     start = 2 つのうち早い方、end = 2 つのうち遅い方
                    def _earlier(a: str, b: str) -> str:
                        ma = _ym_to_months(a); mb = _ym_to_months(b)
                        if ma is None: return b
                        if mb is None: return a
                        return a if ma <= mb else b
                    def _later(a: str, b: str) -> str:
                        ma = _ym_to_months(a); mb = _ym_to_months(b)
                        if ma is None: return b
                        if mb is None: return a
                        return a if ma >= mb else b
                    _new_start = _earlier(str(_buf.get("position_start") or ""), str(w.get("position_start") or ""))
                    _new_end = _later(str(_buf.get("position_resigned") or ""), str(w.get("position_resigned") or ""))
                    if _new_start: _buf["position_start"] = _new_start
                    if _new_end: _buf["position_resigned"] = _new_end
                    # 职位：倒序遍历，先遇到的是后职位 → 格式「较早职位 → 较晚职位」
                    # EN: Position: traversal is in reverse order, so the first one seen is the later position → format "earlier position → later position"
                    # JA: 職位：新しい順に走査するため先に現れるのは後の職位 → 形式は「前の職位 → 後の職位」
                    _pos_old = (w.get("position") or "").strip()
                    _pos_new = (_buf.get("position") or "").strip()
                    if _pos_old and _pos_new and _pos_old != _pos_new:
                        _buf["position"] = f"{_pos_old} → {_pos_new}"
                    elif _pos_old and not _pos_new:
                        _buf["position"] = _pos_old
                    # 部门：同职位合并
                    # EN: Department: merged the same way as position
                    # JA: 部署：職位と同じ方法で統合する
                    _dept_old = (w.get("position_dept") or w.get("department") or "").strip()
                    _dept_new = (_buf.get("position_dept") or "").strip()
                    if _dept_old and _dept_new and _dept_old != _dept_new:
                        _buf["position_dept"] = f"{_dept_old} → {_dept_new}"
                    elif _dept_old and not _dept_new:
                        _buf["position_dept"] = _dept_old
                    # 公司名：选更长更完整的那个（含"有限/代表处"）
                    # EN: Company name: choose the longer, more complete one (containing "有限/代表处")
                    # JA: 会社名：より長く完全な方（「有限／代表处」を含む）を選ぶ
                    if len(cur_c) > len(buf_c):
                        _buf["company_name"] = cur_c
                    # resp / achievements：合并（旧段→新段）
                    # EN: resp / achievements: merge (older entry → newer entry)
                    # JA: resp / achievements：統合する（古い項目 → 新しい項目）
                    _rold = (w.get("position_responsibilities") or "").strip()
                    _rnew = (_buf.get("position_responsibilities") or "").strip()
                    if _rold and _rnew:
                        # 旧段前面加标题
                        # EN: Add a heading in front of the older entry
                        # JA: 古い項目の前に見出しを付ける
                        _label = f"【{(_pos_old or '早期职位')}（{str(w.get('position_start') or '')}~{str(w.get('position_resigned') or '')}）】"
                        _buf["position_responsibilities"] = f"{_label}\n{_rold}\n\n{_rnew}" if _rold != _rnew else _rnew
                    elif _rold and not _rnew:
                        _buf["position_responsibilities"] = _rold
                    _aold = (w.get("position_achievements") or "").strip()
                    _anew = (_buf.get("position_achievements") or "").strip()
                    if _aold and _anew and _aold != _anew:
                        _buf["position_achievements"] = f"{_aold}\n\n{_anew}"
                    elif _aold and not _anew:
                        _buf["position_achievements"] = _aold
                    # 员工规模/行业：选非空的更长那个
                    # EN: Employee size / industry: choose the longer non-empty one
                    # JA: 従業員規模・業界：空でない長い方を選ぶ
                    for _k in ("company_employees", "company_industry", "position_salary", "annual_salary_min", "annual_salary_max"):
                        _v_new = str(_buf.get(_k) or "").strip()
                        _v_old = str(w.get(_k) or "").strip()
                        if _v_old and not _v_new:
                            _buf[_k] = _v_old
                    # 继续，不追加到merged（_buf继续缓冲可能的下一段同公司紧邻）
                    # EN: Continue without appending to merged (_buf keeps buffering a possible next adjacent entry at the same company)
                    # JA: merged には追加せずに続ける（_buf は同じ会社で隣接する次の項目に備えてバッファを続ける）
                    continue
            # 非同公司 或 非紧邻 → 先把_buf入队，再把当前w设为新_buf
            # EN: Different company or not adjacent → first enqueue _buf, then set the current w as the new _buf
            # JA: 別の会社か隣接していない → まず _buf をキューに入れ、現在の w を新しい _buf にする
            merged_works.append(_buf)
            _buf = dict(w)
        if _buf is not None:
            merged_works.append(_buf)
        dedup_works = merged_works

    # ================================================================
    # ★刘飞沙/王吉庆/万展/张寰宇 修复 - postprocess最后一轮强清洗
    # ================================================================
    # 简历标准section标题词表（不可能是公司/职位名，responsibilities末尾必须切掉）
    # EN: ================================================================
    #     ★Fixes for several past cases - final round of strong cleaning in postprocess
    #     ================================================================
    #     List of standard résumé section heading words (can never be company/position names; must be cut from the end of responsibilities)
    # JA: ================================================================
    #     ★過去の複数の事例への修正 - postprocess の最後の強力なクレンジング
    #     ================================================================
    #     履歴書の標準的なセクション見出しの語の一覧（会社名・職位名にはなり得ず、responsibilities の末尾から必ず切り落とす）
    _CUT_SECTION_TITLES = (
        "实验经历", "实习经历", "培训经历", "项目经历", "教育经历", "教育背景", "自我评价", "自我鉴定", "求职意向",
        "语言能力", "专业技能", "技术技能", "兴趣爱好", "校园经历", "在校经历", "社会实践", "科研经历", "获奖经历",
        "荣誉证书", "资格证书", "家庭状况", "个人简介", "个人说明", "个人能力", "个人评价", "外语能力", "英语能力",
        "备注", "附言", "作品集", "所获证书", "相关证书", "个人信息", "基本信息", "联系信息", "期望职位", "期望薪资",
        "期望城市", "期望工作", "志愿者经历", "义工经历", "创业经历", "当兵经历", "服役经历", "专利成果", "论文发表",
        "获奖情况", "证书情况", "技能特长", "计算机水平", "IT技能", "办公技能", "驾照", "在校情况",
    )
    # section标题+冒号（王吉庆position="个人能力,性格以及爱好:"）
    # EN: Section heading + colon (a past case: position="个人能力,性格以及爱好:" (personal abilities, character and hobbies:))
    # JA: セクション見出し + コロン（過去の事例：position="个人能力,性格以及爱好:"（個人の能力、性格と趣味:））
    _CUT_ALIAS_COLON_RE = re.compile(
        r"^[\s　]*"
        r"(?:个人[\u4e00-\u9fff,，\s、]{0,12}|工作[\u4e00-\u9fff]{0,4}|项目[\u4e00-\u9fff]{0,4}|教育[\u4e00-\u9fff]{0,4}|培训[\u4e00-\u9fff]{0,4}"
        r"|实习[\u4e00-\u9fff]{0,4}|科研[\u4e00-\u9fff]{0,4}|获奖[\u4e00-\u9fff]{0,4}|专业[\u4e00-\u9fff]{0,4}|语言[\u4e00-\u9fff]{0,4}"
        r"|外语[\u4e00-\u9fff]{0,4}|英语[\u4e00-\u9fff]{0,4}|技术[\u4e00-\u9fff]{0,4}|[\u4e00-\u9fff]{1,4}内容|[\u4e00-\u9fff]{1,4}职责|[\u4e00-\u9fff]{1,4}介绍|[\u4e00-\u9fff]{1,4}概况|[\u4e00-\u9fff]{1,4}薪酬|[\u4e00-\u9fff]{1,4}福利|[\u4e00-\u9fff]{1,4}时间|[\u4e00-\u9fff]{1,4}地点|[\u4e00-\u9fff]{1,4}范围|[\u4e00-\u9fff]{1,4}流程|[\u4e00-\u9fff]{1,4}状况|[\u4e00-\u9fff]{1,4}信息|[\u4e00-\u9fff]{1,4}简介|[\u4e00-\u9fff]{1,4}能力|[\u4e00-\u9fff]{1,4}说明|[\u4e00-\u9fff]{1,4}经历|[\u4e00-\u9fff]{1,4}经验|[\u4e00-\u9fff]{1,4}背景|[\u4e00-\u9fff]{1,4}技能|[\u4e00-\u9fff]{1,4}评价|[\u4e00-\u9fff]{1,4}鉴定|[\u4e00-\u9fff]{1,4}意向|[\u4e00-\u9fff]{1,4}备注|[\u4e00-\u9fff]{1,4}附言)"
        r"\s*[:：]\s*$"
    )
    # 明确section别名词（不可能是公司/职位）
    # EN: Explicit section alias words (can never be a company/position)
    # JA: 明確なセクションの別名の語（会社・職位にはなり得ない）
    _SEC_ALIAS_SET = set("""
工作与经历 工作时间 工作范围 工作概况 工作内容 工作简介 工作说明 工作经验 教育概况 基础信息 自我介绍 其它技能 外语培训师
实践经验 实践经历 实习工作经验 实习经验 培训经验 培训简介 项目概况 项目简介 项目工作内容 ESKO ESKO工作 薪酬状况 人事工作
附言 备注 说明 简介 概况 内容 """.strip().split())
    # —— 简历section标题 regex：纯「XX经历/XX经验/XX背景/XX技能/XX信息/XX评价/XX意向」
    # EN: —— Résumé section heading regex: pure "XX经历/XX经验/XX背景/XX技能/XX信息/XX评价/XX意向" (history/experience/background/skills/info/assessment/preferences)
    # JA: —— 履歴書のセクション見出しの正規表現：純粋な「XX经历／XX经验／XX背景／XX技能／XX信息／XX评价／XX意向」（経歴・経験・背景・スキル・情報・評価・希望）
    _PURE_SECTION_NAME_RE = re.compile(
        r"^(?:个人|工作|项目|教育|培训|实习|科研|社会|校园|获奖|荣誉|专业|技术|语言|外语|英语|计算机|办公|求职|期望|自我|联系|家庭|基本|相关|所获|志愿者|义工|创业|当兵|服役|志愿者|专利|论文)"
        r"(?:经历|经验|背景|概况|技能|特长|能力|信息|评价|鉴定|意向|介绍|简介|说明|内容|地址|地点|状况|情况|备注|附言|成果|发表|证书|作品|职位|薪资|城市|工作|学业|学业|学历|婚姻|政治|身高|体重|照片|驾照)$"
    )

    def _strip_section_from_resp(resp: str) -> tuple[str, list[str]]:
        """responsibilities最后切掉下一个明确section标题，返回 (切掉后的resp, 被切掉的section列表)

        EN: Finally cut the next explicit section heading off responsibilities; returns (resp after cutting, list of cut sections)

        JA: 最後に responsibilities から次の明確なセクション見出しを切り落とす。戻り値：(切り落とした後の resp, 切り落としたセクションの一覧)
        """
        if not resp: return "", []
        lines = resp.splitlines()
        cut_lines = []
        cut_idx = len(lines)
        for li in range(len(lines)):
            s = lines[li].strip()
            if not s: continue
            if s in _CUT_SECTION_TITLES:
                cut_idx = min(cut_idx, li)
                cut_lines.append(s)
                continue
            if 2 <= len(s) <= 15 and _PURE_SECTION_NAME_RE.match(s):
                cut_idx = min(cut_idx, li)
                cut_lines.append(s)
                continue
            if 2 <= len(s) <= 25 and _CUT_ALIAS_COLON_RE.match(s + "："):  # 最后不带冒号也给一次机会
            # EN: Also give one chance to a final heading without a colon
            # JA: コロンのない末尾の見出しにも 1 回だけ機会を与える
                # 要单独成行才切（避免把responsibilities中间某个标题短语误切）
                # EN: Cut only when it is on its own line (so a heading phrase in the middle of responsibilities is not cut by mistake)
                # JA: 単独の行にある場合だけ切る（responsibilities の途中にある見出しの語句を誤って切らないため）
                if 0 < li < len(lines) - 1:  # 不在最后一行
                # EN: Not on the last line
                # JA: 最後の行ではない
                    cut_idx = min(cut_idx, li)
                    cut_lines.append(s.rstrip("：:"))
        if cut_idx < len(lines):
            return "\n".join(lines[:cut_idx]).strip(), cut_lines
        return resp, cut_lines

    cleaned: list[dict[str, Any]] = []
    for w in dedup_works:
        ww = dict(w)
        c = str(ww.get("company_name") or "").strip()
        p = str(ww.get("position") or "").strip()
        resp = str(ww.get("position_responsibilities") or ww.get("responsibilities") or "")
        # ---- A. 公司名是section标题/别名 → 置空(后面兜底修)；若是第X学历形式也是置空 ----
        # EN: ---- A. Company name is a section heading/alias → clear it (fixed later by fallback); also clear it if it has the "第X学历" (Xth degree) form ----
        # JA: ---- A. 会社名がセクション見出し・別名 → 空にする（後で最終手段で補修）。「第X学历」（第 X 学歴）の形式の場合も空にする ----
        need_comp_fallback = False
        if c in _SEC_ALIAS_SET or c in _CUT_SECTION_TITLES or c.startswith("第") and c.endswith(("学历学校","学历专业","学历学位")):
            need_comp_fallback = True
            ww["company_name"] = ""
        elif (2 <= len(c) <= 12 and _PURE_SECTION_NAME_RE.match(c)) or _CUT_ALIAS_COLON_RE.match(c):
            need_comp_fallback = True
            ww["company_name"] = ""
        # ---- B. position是section别名/带冒号标题 → 置空；responsibilities里的「XX：」短语若真职位在前则反推 ----
        # EN: ---- B. position is a section alias / heading with a colon → clear it; if the real position precedes an "XX：" phrase in responsibilities, infer it ----
        # JA: ---- B. position がセクションの別名・コロン付きの見出し → 空にする。responsibilities 内の「XX：」の語句の前に本当の職位があれば逆算する ----
        if (p in _SEC_ALIAS_SET or p in _CUT_SECTION_TITLES
                or (2 <= len(p) <= 12 and _PURE_SECTION_NAME_RE.match(p))
                or _CUT_ALIAS_COLON_RE.match(p)):
            ww["position"] = ""
            p = ""
        if not p and not need_comp_fallback:
            pass  # 维持现状
            # EN: Keep as is
            # JA: 現状を維持する
        # ---- C. responsibilities切掉末尾粘入的section头（刘飞沙/张寰宇/刘雨晨/王佳乐/楼子超/马青/武文莉/陈燕清）----
        # EN: ---- C. Cut section headers stuck onto the end of responsibilities (several past cases) ----
        # JA: ---- C. responsibilities の末尾にくっついたセクション見出しを切り落とす（過去の複数の事例）----
        new_resp, _ = _strip_section_from_resp(resp)
        if new_resp != resp:
            ww["position_responsibilities"] = new_resp
            if "responsibilities" in ww:
                ww["responsibilities"] = new_resp
        # ---- D. 公司名/职位名空 → 从responsibilities开头「XX公司 部门 XX职位」反推（刘飞沙：开头是公司名职位）----
        # EN: ---- D. Company/position name empty → infer from "XX公司 department XX position" at the start of responsibilities (a past case: it starts with company name and position) ----
        # JA: ---- D. 会社名・職位名が空 → responsibilities の冒頭の「XX公司 部署 XX職位」から逆算する（過去の事例：冒頭が会社名と職位）----
        if (not ww.get("company_name") or not ww.get("position")) and new_resp:
            # 取resp前3行，找公司+职位短语
            # EN: Take the first 3 lines of resp and look for a company + position phrase
            # JA: resp の最初の 3 行を取り、会社 + 職位の語句を探す
            head_lines = [x.strip() for x in new_resp.splitlines()[:3] if x.strip()]
            for hl in head_lines:
                if not hl: continue
                # 正则：公司(带标志) + 任意分隔 + 部门/职位
                # EN: Regex: company (with marker) + any separator + department/position
                # JA: 正規表現：会社（目印付き）+ 任意の区切り + 部署／職位
                m_pos_try = re.match(
                    r"^[\s　]*([^，,。；;\n]{3,30}?(?:公司|有限|集团|工厂|医院|银行|事务所|中心|办事处|代表处|工作室|大学|学院|学校|院|株式会社|ホワイト|ジャパン|合同会社))"
                    r"[\s　|｜,，。；;\.、·\-—]+"
                    r"([^\n，,。；;]{1,20}?)[\s　]*"
                    r"(?:[。，,；;：:]|$|[\n\r])",
                    hl,
                )
                if m_pos_try:
                    cand_c = m_pos_try.group(1).strip()
                    cand_p = m_pos_try.group(2).strip()
                    # 校验 cand_p：2-20 字，不含公司标志、不含日期、不含薪资格式
                    # EN: Validate cand_p: 2-20 characters, no company marker, no date, no salary format
                    # JA: cand_p を検証する：2〜20 文字、会社の目印なし、日付なし、給与の形式なし
                    _bad_p_kw = ("负责", "管理", "开发", "维护", "担任", "工作内容", "工作描述", "主要职责",
                                 "公司", "有限", "集团", "工厂", "银行", "学校", "学院", "大学")
                    _p_ok = (2 <= len(cand_p) <= 20
                             and not _has_comp_sign_global(cand_p)
                             and not any(k in cand_p for k in _bad_p_kw)
                             and not re.search(r"\d+\s*(?:元|千|万)\s*/\s*(?:月|年)", cand_p))
                    if (not ww.get("company_name")) and 2 <= len(cand_c) <= 30:
                        ww["company_name"] = cand_c
                    if (not ww.get("position")) and _p_ok:
                        ww["position"] = cand_p
                    if ww.get("company_name") and ww.get("position"):
                        break
        # ---- E. P2：position带尾冒号（万展："时间："）、长度异常的纯标题短语 → 置空 ----
        # EN: ---- E. P2: position with a trailing colon (a past case: "时间：" (time:)), or abnormally long pure heading phrases → clear ----
        # JA: ---- E. P2：末尾にコロンの付いた position（過去の事例：「时间：」（期間：））、長さが異常な純粋な見出しの語句 → 空にする ----
        p2 = str(ww.get("position") or "").strip()
        if p2:
            # 纯标题短语判定：末尾冒号 / 或 长度<=8 且结尾是「内容/简介/概况/时间/地点/范围/薪酬/福利/流程/状况/信息/能力/说明」
            # EN: Pure heading phrase check: trailing colon / or length <= 8 and ending in "内容/简介/概况/时间/地点/范围/薪酬/福利/流程/状况/信息/能力/说明" (content/intro/overview/time/place/scope/pay/benefits/process/status/info/ability/notes)
            # JA: 純粋な見出しの語句の判定：末尾がコロン、または長さ 8 以下で「内容／简介／概况／时间／地点／范围／薪酬／福利／流程／状况／信息／能力／说明」で終わる
            _looks_bad_p = False
            if p2.endswith((":", "：")):
                _looks_bad_p = True
            elif (len(p2) <= 10 and
                  any(p2.endswith(suf) for suf in ("内容","职责","简介","概况","介绍","时间","地点","范围","薪酬","福利","流程","状况","信息","能力","说明","备注","附言","状态"))):
                _looks_bad_p = True
            elif p2 == "时间":
                _looks_bad_p = True
            if _looks_bad_p:
                # 转移到 responsibilities 前缀（保留信息，避免把有用的section标题短语完全丢了）
                # EN: Move it to the front of responsibilities (keeping the information, so useful section heading phrases are not lost entirely)
                # JA: responsibilities の先頭に移す（情報は残し、有用なセクション見出しの語句を完全に失わないようにする）
                if new_resp and p2 not in new_resp[:20]:
                    ww["position_responsibilities"] = p2 + "\n" + new_resp
                    if "responsibilities" in ww:
                        ww["responsibilities"] = ww["position_responsibilities"]
                ww["position"] = ""
                p2 = ""
        # ---- F. P3：position是动作/职责开头的整句（维护现有.../参与新设计.../负责XXX）—— 移到responsibilities前缀，position置空 ----
        # EN: ---- F. P3: position is a whole sentence starting with an action/duty (维护现有... / 参与新设计... / 负责XXX: maintain existing... / take part in new design... / responsible for...) — move it to the front of responsibilities and clear position ----
        # JA: ---- F. P3：position が動作・職務で始まる文全体（维护现有... / 参与新设计... / 负责XXX：既存の保守… / 新設計に参加… / 〜を担当）— responsibilities の先頭に移し、position を空にする ----
        if not p2:
            p2 = str(ww.get("position") or "").strip()
        if p2 and len(p2) >= 6:
            _ACTION_HEAD_KWS = (
                "维护","参与","负责","管理","开发","担任","设计","跟进","协调","处理","组织","编制","撰写","制定","规划","推进","统筹","协助","主导","监管","监督",
                "完成","执行","搭建","测试","优化","运营","推广","销售","采购","实施","培训","招聘","面试","核算","审计","统计","分析","调研","策划","拓展","谈判","签约",
                "拜访","接待","维护","解决","排查","安装","调试","生产","加工","质检","发货","运输","配送","服务","客服","咨询","指导","教学","辅导"
            )
            _looks_action_p = False
            # 1) 开头6字以内含明确动作头
            # EN: 1) Contains an explicit action head within the first 6 characters
            # JA: 1) 先頭 6 文字以内に明確な動作の語頭がある
            for kw in _ACTION_HEAD_KWS:
                if p2.startswith(kw) or p2[:6].startswith(kw):
                    _looks_action_p = True; break
            # 2) 职位超长(>20字)且里面含标点/动词结构 → 肯定是职责不是职位
            # EN: 2) Position too long (>20 characters) and containing punctuation/verb structures → definitely duties, not a position
            # JA: 2) 職位が長すぎ（20 文字超）、句読点や動詞の構造を含む → 職位ではなく明らかに職務
            if (not _looks_action_p) and len(p2) > 16 and (re.search(r"[，,。.；;]", p2) or any(k in p2 for k in _ACTION_HEAD_KWS)):
                _looks_action_p = True
            if _looks_action_p:
                # 移到 responsibilities 前缀
                # EN: Move to the front of responsibilities
                # JA: responsibilities の先頭に移す
                old_resp = str(ww.get("position_responsibilities") or ww.get("responsibilities") or "")
                merged_resp = (p2 + "\n" + old_resp) if old_resp else p2
                ww["position_responsibilities"] = merged_resp
                if "responsibilities" in ww:
                    ww["responsibilities"] = merged_resp
                ww["position"] = ""
                p2 = ""
        # ---- G. P2日期归一：position_start / position_resigned 的口语化词归一成合法格式 ----
        # EN: ---- G. P2 date normalisation: normalise colloquial words in position_start / position_resigned into valid formats ----
        # JA: ---- G. P2 日付の正規化：position_start / position_resigned の口語的な語を正しい形式に正規化する ----
        for field in ("position_start", "position_resigned"):
            raw_v = str(ww.get(field) or "").strip()
            if not raw_v: continue
            # 结束日期口语化归一：目前 / 在职中 / 在职 / 现在 / 至今未离职 / 至今在职 → 至今
            # EN: Normalise colloquial end dates: 目前 / 在职中 / 在职 / 现在 / 至今未离职 / 至今在职 (currently / employed / now / not yet left) → 至今 (present)
            # JA: 口語的な終了日の正規化：目前／在职中／在职／现在／至今未离职／至今在职（現在・在職中など）→ 至今（現在）
            if field == "position_resigned" and raw_v in ("目前", "现在", "在职中", "在职", "至今", "至今在职", "至今未离职", "未离职", "在任"):
                ww[field] = "至今"
                continue
            # 开始日期：无（起始有「至今」是异常，也置空）
            # EN: Start date: none (a start of "至今" is abnormal, also cleared)
            # JA: 開始日：なし（開始に「至今」があるのは異常なので、これも空にする）
            if field == "position_start" and raw_v in ("目前", "现在", "至今"):
                ww[field] = ""
                continue
        cleaned.append(ww)
    dedup_works = cleaned

    # —— P6 工作段日期统一归一化（YYYY-MM 或 保留至今）——
    # EN: —— P6 unified normalisation of work-entry dates (YYYY-MM, or keep 至今) ——
    # JA: —— P6 職歴の日付の統一正規化（YYYY-MM、または 至今 を保持）——
    for w in dedup_works:
        for field in ("position_start", "position_resigned"):
            raw = str(w.get(field) or "").strip()
            if not raw: continue
            # position_resigned 保留 "至今"（allow_today_token）
            # EN: position_resigned keeps "至今" (allow_today_token)
            # JA: position_resigned は「至今」を保持する（allow_today_token）
            allow_tok = (field == "position_resigned")
            norm = _normalize_ym_loose(raw, allow_today_token=allow_tok)
            if norm != raw:
                w[field] = norm
    return dedup_works


def _extract_email_enhanced(text: str) -> str:
    """提取邮箱，优先从 mailto: 提取，排除 HYPERLINK 宏残留。

    EN: Extract e-mails, preferring mailto:, and exclude HYPERLINK macro leftovers.

    JA: メールを抽出する。mailto: からの抽出を優先し、HYPERLINK マクロの残骸は除く。
    """
    m = re.search(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if m:
        value = m.group(1)
        # 表格转文本时手机号与邮箱可能无分隔地粘连：
        # 138000000010000001@qq.com -> 10000001@qq.com。
        # EN: When converting tables to text, phone and e-mail may be stuck together without a separator:
        #     138000000010000001@qq.com -> 10000001@qq.com.
        # JA: 表をテキストに変換すると、電話番号とメールが区切りなしでくっつくことがある：
        #     138000000010000001@qq.com -> 10000001@qq.com。
        value = re.sub(r"^(?:\+?86)?1[3-9]\d{9}(?=[A-Za-z0-9._%+-]+@)", "", value)
        return value
    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if m and "HYPERLINK" not in m.group(0):
        value = m.group(0)
        value = re.sub(r"^(?:\+?86)?1[3-9]\d{9}(?=[A-Za-z0-9._%+-]+@)", "", value)
        return value
    m = re.search(r'[Ee]?-?mail[：:]\s*([^\s<]+)', text)
    if m and m.group(1).upper() not in ("HYPERLINK",):
        return m.group(1).strip()
    m = re.search(r"邮箱[：:]\s*([^\s]+)", text)
    if m:
        return m.group(1).strip()
    return ""


# =============================================================================
# 学历 rank / 日期 通用工具
# =============================================================================
# EN: =============================================================================
#     General utilities for degree rank / dates
#     =============================================================================
# JA: =============================================================================
#     学歴ランク・日付の汎用ツール
#     =============================================================================

def normalize_degree_rank(deg: str) -> tuple[str, str]:
    degree_rank = {
        "博士后": "7", "博士": "6", "phd": "6", "doctor": "6",
        "硕士": "5", "修士": "5", "研究生": "5", "在职研究生": "5", "mba": "5", "emba": "5", "mpa": "5",
        "master": "5", "ma": "5", "ms": "5", "大学院": "5",
        "本科": "4", "学士": "4", "学士学位": "4", "统招本科": "4", "自考本科": "4",
        "成人本科": "4", "函授本科": "4", "专升本": "4", "本科毕业": "4",
        "大卒": "4", "bachelor": "4", "bs": "4", "ba": "4",
        "大专": "3", "专科": "3", "短大": "3", "大専": "3", "associate": "3", "diploma": "3",
        "自考专科": "3", "函授专科": "3", "成人专科": "3",
        "高中": "2", "中专": "2", "职高": "2", "中学": "2", "普通高中": "2",
        "high school": "2", "中級専門学校": "2", "専門学校": "2",
        "初中": "1", "小学": "1",
    }
    etype_map = {
        "7": "全日制研究生", "6": "全日制研究生", "5": "全日制研究生",
        "4": "全日制大学", "3": "全日制大专", "2": "全日制高中", "1": "全日制初中及以下",
    }
    # —— 清洗：去括号/去前后缀/取词干 ——
    # EN: —— Cleaning: remove brackets / remove prefixes and suffixes / take the stem ——
    # JA: —— クレンジング：括弧の除去・前後の接辞の除去・語幹の取得 ——
    raw = (deg or "").strip()
    # 先去掉前导括号（如「（硕士」→「硕士」）
    # EN: First remove a leading bracket (e.g. "（硕士" → "硕士")
    # JA: まず先頭の括弧を除く（例：「（硕士」→「硕士」）
    raw = re.sub(r"^[\s（(【\[:：\\\t]+", "", raw)
    # 去掉尾部括号（如「行政管理专业（专科」→ 先去掉「专业」再去括号）
    # 去掉常见的前后缀干扰：专业/毕业/统招/全日制/自考/函授/成人/学历：/学位：
    # EN: Remove trailing brackets (e.g. "行政管理专业（专科" → first remove "专业" then the bracket)
    #     Remove common prefix/suffix noise: 专业/毕业/统招/全日制/自考/函授/成人/学历：/学位： (major/graduated/unified enrolment/full-time/self-study/correspondence/adult/degree:)
    # JA: 末尾の括弧を除く（例：「行政管理专业（专科」→ まず「专业」を除いてから括弧を除く）
    #     よくある前後の接辞のノイズを除く：专业／毕业／统招／全日制／自考／函授／成人／学历：／学位：
    deg_clean = raw
    deg_clean = re.sub(r"^专业[：:]?\s*", "", deg_clean)
    deg_clean = re.sub(r"^学历[：:]?\s*", "", deg_clean)
    deg_clean = re.sub(r"^学位[：:]?\s*", "", deg_clean)
    deg_clean = re.sub(r"[：:].*$", "", deg_clean)  # 「：\t法学学士」后面切
    # EN: Cut after "：\t法学学士"
    # JA: 「：\t法学学士」の後ろで切る
    deg_clean = re.sub(r"专业(?:方向)?$", "", deg_clean)  # 「行政管理专业（专科」→「行政管理（专科」
    # EN: "行政管理专业（专科" → "行政管理（专科"
    # JA: 「行政管理专业（专科」→「行政管理（专科」
    # 去括号及内部
    # EN: Remove brackets and their contents
    # JA: 括弧とその中身を除く
    deg_clean_bare = re.sub(r"[（(].*?[)）]", "", deg_clean).strip()
    # 兜底：如果bare只有1-2字且后面带「（本科/（专科」，优先取括号里的学位值
    # EN: Fallback: if bare has only 1-2 characters followed by "（本科/（专科", prefer the degree value in the bracket
    # JA: 最終手段：bare が 1〜2 文字だけで後ろに「（本科／（专科」が続く場合は、括弧内の学位の値を優先する
    m_paren_deg = re.search(r"[（(]\s*(博士|硕士|研究生|本科|学士|大专|专科|高中|中专|职高|初中|小学|MBA|EMBA|MPA)\b", deg, re.I)
    if m_paren_deg and not degree_rank.get(deg_clean_bare.lower()):
        candidate = m_paren_deg.group(1)
        # 括号里值更像学位，直接用 candidate 作为 deg_clean_bare
        # EN: The bracketed value looks more like a degree; use candidate directly as deg_clean_bare
        # JA: 括弧内の値の方が学位らしいので、candidate をそのまま deg_clean_bare として使う
        deg_clean_bare = candidate
    deg_lower = deg_clean_bare.lower()
    rank = degree_rank.get(deg_lower, "")
    if not rank:
        for key, val in degree_rank.items():
            if key in deg_lower:
                rank = val
                break
    etype = etype_map.get(rank, "")
    # —— 额外：根据原 raw 判断 education_type 是否该带「在职/自考/函授/成人」——
    # EN: —— Extra: decide from the original raw whether education_type should carry "在职/自考/函授/成人" (in-service/self-study/correspondence/adult) ——
    # JA: —— 追加：元の raw から、education_type に「在职／自考／函授／成人」（在職・独学・通信・成人）を付けるべきかを判定する ——
    if rank == "5" and "在职" in raw:
        etype = "在职研究生"
    for k in ("自考", "函授", "成人"):
        if k in raw and rank in ("4", "3"):
            etype = ("成人本科" if rank == "4" else "成人专科") if not etype else etype
            break
    return rank, etype


def normalize_education_list(edu_list: list[dict[str, Any]], edu_section_text: str = "") -> list[dict[str, Any]]:
    # 内联 SCHOOL_SIGNS（避免依赖局部函数变量，防止 NameError）
    # EN: Inline SCHOOL_SIGNS (avoid depending on local function variables, preventing NameError)
    # JA: SCHOOL_SIGNS をインラインで持つ（関数のローカル変数への依存を避け、NameError を防ぐ）
    SCHOOL_SIGNS = ("大学", "学院", "学校", "分校", "大学校", "university", "college", "institute",
                    "school", "academy", "polytechnic", "vocational", "高中", "中学", "小学", "私塾",
                    "研修生", "研究所", "研究院", "党校", "干部学院", "师范", "医科", "理工", "科技",
                    "industrial", "technical", "normal")
    # ====== 全局回填：从教育section文本中搜 学校/专业/学位/GPA KV（如沈莉君："专业（Major）：市场营销" 在section末尾）======
    # EN: ====== Global back-fill: search the education section text for school/major/degree/GPA KV pairs (e.g. a past case: "专业（Major）：市场营销" at the end of the section) ======
    # JA: ====== 全体の補完：学歴セクションのテキストから学校・専攻・学位・GPA の KV を探す（例：過去の事例で「专业（Major）：市场营销」がセクション末尾にある）======
    global_school, global_major, global_degree, global_gpa = "", "", "", ""
    if edu_section_text:
        for line in [l.strip() for l in edu_section_text.split("\n") if l.strip()]:
            # 学校名：毕业学校/学校名称/学校/院校/就读学校/毕业院校：XXX
            # EN: School name: 毕业学校/学校名称/学校/院校/就读学校/毕业院校：XXX (graduated from / school name / school / institution / attended)
            # JA: 学校名：毕业学校／学校名称／学校／院校／就读学校／毕业院校：XXX（卒業校・学校名・学校・院校・在籍校）
            if not global_school:
                m_sch = re.match(r"^(?:毕业学校|学校名称|学校|院校|就读学校|毕业院校|所在学校)\s*(?:[（(][^）)]*[）)])?\s*[:：]\s*(.+)$", line)
                if m_sch:
                    cand = m_sch.group(1).strip(" |｜，,。.；;").strip()
                    if cand and 2 <= len(cand) <= 60 and any(s in cand for s in SCHOOL_SIGNS):
                        # 截断到第一个标点/括号/空格（防止后面粘专业）
                        # EN: Truncate at the first punctuation/bracket/space (to prevent a major being stuck after it)
                        # JA: 最初の句読点・括弧・空白で切る（後ろに専攻がくっつくのを防ぐ）
                        cand = re.split(r"[\s　，,。.；;（(【\[]", cand, maxsplit=1)[0].strip()
                        if 2 <= len(cand) <= 50:
                            global_school = cand
            # 专业：XXX / 专业（Major）：XXX / 专业XXX
            # EN: Major: 专业：XXX / 专业（Major）：XXX / 专业XXX
            # JA: 専攻：专业：XXX / 专业（Major）：XXX / 专业XXX
            m_maj = re.match(r"^专业\s*(?:[（(][^）)]*[）)])?\s*[:：]\s*(.+)$", line)
            if m_maj and not global_major:
                global_major = m_maj.group(1).strip(" |｜，,。.；;").strip()
                if global_major and len(global_major) >= 30:
                    # 截断到第一个标点/括号，避免 "市场营销 学位（Degree）：本科 GPA..."
                    # EN: Truncate at the first punctuation/bracket to avoid "市场营销 学位（Degree）：本科 GPA..."
                    # JA: 最初の句読点・括弧で切り、「市场营销 学位（Degree）：本科 GPA...」のようになるのを避ける
                    global_major = re.split(r"[\s　，,。.；;（(【\[]", global_major, maxsplit=1)[0].strip()
            # 学位（Degree）：XXX / 学历：XXX
            # EN: Degree: 学位（Degree）：XXX / 学历：XXX
            # JA: 学位：学位（Degree）：XXX / 学历：XXX
            if not global_degree:
                m_deg = re.match(r"^(?:学位\s*(?:[（(][^）)]*[）)])?|学历|文化程度)\s*[:：]\s*(.+)$", line)
                if m_deg:
                    global_degree = m_deg.group(1).strip(" |｜，,。.；;").strip()
                    if global_degree and "GPA" in global_degree: global_degree = global_degree.split("GPA")[0].strip()
            # GPA 可选，暂不进字段
            # EN: GPA is optional and not stored in a field for now
            # JA: GPA は任意で、今のところフィールドには入れない
        # 兜底：如果 section 末尾某行形如「XXX   一等奖学金两次」这种，中间是空格/制表/GPA 分且前半段含学位关键字 → 取学位
        # EN: Fallback: if a line at the end of the section looks like "XXX   一等奖学金两次" (first-class scholarship twice), with spaces/tabs/GPA in the middle and the first half containing a degree keyword → take the degree
        # JA: 最終手段：セクション末尾の行が「XXX   一等奖学金两次」（一等奨学金 2 回）のような形で、間に空白・タブ・GPA があり前半に学位のキーワードがある → 学位を取る
        if not global_degree:
            for line in [l.strip() for l in edu_section_text.split("\n") if l.strip()][-10:]:
                for deg_kw in ("博士", "硕士", "本科", "大专", "专科", "高中", "中专", "职高", "初中", "MBA", "EMBA"):
                    if deg_kw in line and (not global_degree):
                        global_degree = deg_kw
                        break
        # 兜底：没搜到全局学校KV → 从整个edu_section_text正则搜第一个含学校标志词的串
        # EN: Fallback: no global school KV found → regex-search the whole edu_section_text for the first string containing a school marker word
        # JA: 最終手段：全体の学校の KV が見つからない → edu_section_text 全体から学校の目印の語を含む最初の文字列を正規表現で探す
        if not global_school and edu_section_text:
            # 典型：「上海交通大学  计算机科学与技术  本科」→ 先抓校名
            # EN: Typical: "上海交通大学  计算机科学与技术  本科" → grab the school name first
            # JA: 典型例：「上海交通大学  计算机科学与技术  本科」→ まず学校名を取る
            m_s = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·]{2,40}(?:大学|学院|学校|分校|大学校|高中|中学|小学|医科|理工|科技|师范|研修生|研究所|研究院|党校|干部学院))", edu_section_text)
            if m_s:
                cand = m_s.group(1).strip()
                # 不能包含黑名单词
                # EN: Must not contain blacklisted words
                # JA: ブラックリストの語を含んではならない
                BAD_TOK_S = ("有限公司", "集团", "营业部", "工作", "负责", "担任", "经理", "销售", "客户", "采购", "营业")
                if 2 <= len(cand) <= 50 and not any(x in cand for x in BAD_TOK_S):
                    # 去掉日期前缀（如「2015.09上海交通大学」→ 「上海交通大学」）
                    # EN: Remove a date prefix (e.g. "2015.09上海交通大学" → "上海交通大学")
                    # JA: 日付の接頭辞を除く（例：「2015.09上海交通大学」→「上海交通大学」）
                    cand = re.sub(r"^\s*(?:19|20)\d{2}\s*[\./年\-]\s*\d{0,2}\s*月?\s*[\-~～—–至到‒―〜\-]*", "", cand).strip()
                    if 2 <= len(cand) <= 50 and any(s in cand for s in SCHOOL_SIGNS):
                        global_school = cand
    normalized: list[dict[str, Any]] = []
    # —— 小工具：判定字符串是否像日期或薪资（用于清洗专业/学校）——
    # EN: —— Small utility: decide whether a string looks like a date or salary (used to clean majors/schools) ——
    # JA: —— 小さなツール：文字列が日付や給与らしいかを判定する（専攻・学校のクレンジングに使う）——
    _DATEREP = re.compile(
        r"^(\d{4}\s*[\./年\-]\s*\d{1,2}\s*月?\s*[\-~～—–至到‒―〜\-]{1,4}\s*(?:\d{4}\s*[\./年\-]\s*\d{1,2}\s*月?|\d{2,4}|至今|在读|现在))"
        r"|^(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\s*[-~～]\s*\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"
        r"|^(\d+\s*(?:元|千|万)\s*(?:/\s*月|/\s*年|月|年)$)"
        r"|^(?:20|19)\d{2}\s*年\s*\d{1,2}\s*月\s*$"
    )
    # —— ★修复：_DATE_IN_MAJOR_RE 必须在使用前定义（原定义在 L1660 导致 L1603 引用报 UnboundLocalError）——
    # EN: —— ★Fix: _DATE_IN_MAJOR_RE must be defined before use (it was originally defined at L1660, so the reference at L1603 raised UnboundLocalError) ——
    # JA: —— ★修正：_DATE_IN_MAJOR_RE は使用前に定義する必要がある（元は L1660 で定義されていたため、L1603 の参照で UnboundLocalError になった）——
    _DATE_IN_MAJOR_RE = re.compile(r"\b(?:19|20)\d{2}[\./\-]\d{1,2}(?:[\./\-]\d{1,2})?\b")
    def _looks_like_date_or_salary(s: str) -> bool:
        return bool(_DATEREP.match(str(s).strip()))
    # —— 小工具：从整句里切出「学校名 + 专业 + 学位」——
    # EN: —— Small utility: cut "school name + major + degree" out of a whole sentence ——
    # JA: —— 小さなツール：文全体から「学校名 + 専攻 + 学位」を切り出す ——
    def _smash_edu_sentence(s: str) -> tuple[str, str, str]:
        """输入类似：「就读于河南理工大学机械学院工业设计系，获得本科工科学士学位」
        返回 (school_name, major_name, degree_type)

        EN: Input like: "就读于河南理工大学机械学院工业设计系，获得本科工科学士学位" (studied in the industrial design department of ... university, obtained a bachelor's degree in engineering)
        Returns (school_name, major_name, degree_type)

        JA: 入力の例：「就读于河南理工大学机械学院工业设计系，获得本科工科学士学位」（〜大学機械学院工業デザイン学科に在籍し、工学学士を取得）
        戻り値：(school_name, major_name, degree_type)
        """
        s0 = str(s or "").strip()
        if not s0:
            return "", "", ""

        # —— 先定义内部切词 helper（必须先定义，避免 NameError）——
        # EN: —— Define the internal tokenising helper first (must be defined first to avoid NameError) ——
        # JA: —— まず内部の分割用ヘルパーを定義する（NameError を避けるため先に定義する必要がある）——
        def _smash_inner_logic(_s: str) -> tuple[str, str, str]:
            _SIGNS = ("大学", "学院", "学校", "分校", "大学校", "高中", "中学", "小学", "医科", "理工", "科技",
                     "师范", "研修生", "研究所", "研究院", "党校", "干部学院")
            sch, maj, deg = "", "", ""
            best_end = -1
            for sign in _SIGNS:
                idx = _s.find(sign)
                if idx >= 0:
                    end = idx + len(sign)
                    if end > best_end:
                        best_end = end
            if best_end > 0:
                prefix = _s[:best_end]
                m_pre = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·]+(?:大学|学院|学校|分校|大学校|高中|中学|小学|医科|理工|科技|师范|研修生|研究所|研究院|党校|干部学院))", prefix)
                if m_pre:
                    sch = m_pre.group(1).strip()
                else:
                    sch = prefix.strip()
                rest = _s[best_end:]
                rest = re.sub(r"^[\s　，,、。.；;：:（(【\[-]+\s*", "", rest)
                DEG_KW = ("博士后", "博士", "硕士", "研究生", "MBA", "EMBA", "MPA", "本科", "学士", "大专", "专科", "高中", "中专", "职高", "初中", "小学")
                deg_pos = len(rest)
                matched_deg = ""
                for dk in DEG_KW:
                    p = rest.find(dk)
                    if p >= 0 and p < deg_pos:
                        deg_pos = p
                        matched_deg = dk
                major_raw = rest[:deg_pos].strip()
                major_raw = re.sub(r"^(?:学院|系|部|学科|专业)\s*", "", major_raw)
                major_raw = re.split(r"(主修课程|核心课程|主要课程|课程|工作经历|工作时间|在职|学历|学位|外语|计算机|能力|MS|技能|证书|荣誉|获奖|社会实践|实习|培训|项目|主要)", major_raw, maxsplit=1)[0]
                major_raw = re.split(r"[，,。.；;：:（(【\[]", major_raw, maxsplit=1)[0]
                major_raw = re.sub(r"(?:主修|方向|类)\s*$", "", major_raw).strip()
                if any(x in major_raw for x in ("课程", "、", "，")) and len(major_raw) > 20:
                    major_raw = ""
                if _looks_like_date_or_salary(major_raw):
                    major_raw = ""
                maj = major_raw
                deg = matched_deg
            if not sch and 2 <= len(_s) <= 20 and any(x in _s for x in ("大学", "学院", "学校", "中学", "小学", "高中")):
                BAD_TOK = ("负责", "管理", "开发", "维护", "担当", "主管", "经理", "销售", "培训", "课程", "项目", "服务", "咨询",
                           "生产", "市场", "采购", "品质", "营业", "财务", "人事", "行政", "客服", "物流", "资材", "制造", "薪资",
                           "就读于", "毕业于", "工作经历", "工作时间", "主修课程", "新媒体", "渠道", "营销")
                if not any(x in _s for x in BAD_TOK):
                    sch = _s
            return sch, maj, deg

        # 1) 先剔除头尾明显不是教育内容的前后缀
        # EN: 1) First remove leading/trailing affixes that are obviously not education content
        # JA: 1) まず明らかに学歴の内容ではない先頭・末尾の接辞を除く
        s1 = re.sub(r"^(就读于|就读|毕业于|毕业学校|学历|教育经历|教育背景|学校(名称)?[:：]?|专业[:：])\s*", "", s0)
        s1 = re.sub(r"[\s　。.!！？?]+$", "", s1)

        # 1.5) P7：优先命中 KV 关键词（"毕业学校"/"学校名称"/"就读学校"…[:：]? 后面的值）→ 直接切，最准确
        # EN: 1.5) P7: prefer hitting KV keywords (the value after "毕业学校"/"学校名称"/"就读学校"…[:：]?) → cut directly, the most accurate
        # JA: 1.5) P7：KV のキーワード（「毕业学校」／「学校名称」／「就读学校」…[:：]? の後ろの値）へのヒットを優先 → そのまま切る。最も正確
        _KV_KEYS = (
            "毕业学校", "学校名称", "就读学校", "所在学校", "毕业院校", "院校名称",
            "学校", "院校",
        )
        for _kk in sorted(_KV_KEYS, key=lambda x: -len(x)):
            pat = re.compile(
                rf"{re.escape(_kk)}\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·\s]+?)"
                rf"(?=(?:户口|所在地|年龄|民族|婚否|性别|籍贯|工作时间|工作经历|求职意向|期望|月薪|电话|邮箱|手机|Q\s*Q|微信|住址|身高|体重|政治面貌|入党时间|所学专业|专业|学历|主修课程|技能|证书|培训|项目|社会实践|实习|公司名称|公司|职位|\d{{4}}\s*[\-/.年]|$))"
            )
            mm = pat.search(s0)
            if mm:
                _cand = mm.group(1).strip()
                _cand = re.sub(r"[\s　]+", " ", _cand).strip()
                if 2 <= len(_cand) <= 40 and any(x in _cand for x in ("大学", "学院", "学校", "中学", "小学", "高中")):
                    _sub_s, _sub_m, _sub_d = _smash_inner_logic(_cand)
                    if _sub_s:
                        return _sub_s, _sub_m, _sub_d
                    return _cand, "", ""

        # 2) 普通 smash：在句子里找 学校标志词
        # EN: 2) Ordinary smash: look for school marker words in the sentence
        # JA: 2) 通常の smash：文中から学校の目印の語を探す
        school, major, deg = _smash_inner_logic(s1)
        return school, major, deg
    # —— 小工具：清洗专业名（如果是「2002/9~2006/7 上海理工大学工商管理工作时间200」这种 → 切出真正专业）——
    # EN: —— Small utility: clean the major name (for strings like "2002/9~2006/7 上海理工大学工商管理工作时间200" → cut out the real major) ——
    # JA: —— 小さなツール：専攻名をクレンジングする（「2002/9~2006/7 上海理工大学工商管理工作时间200」のような場合 → 本当の専攻を切り出す）——
    def _extract_major_from_mess(maj: str, fallback_school: str) -> str:
        if not maj:
            return ""
        if not _looks_like_date_or_salary(maj) and len(maj) <= 30:
            return maj.strip()
        # 尝试从乱串里抽出专业：取「大学/学院」后面、再到日期/工作时间之前的词
        # EN: Try extracting the major from a jumbled string: take the words after "大学/学院" (university/college) and before the date/work time
        # JA: 乱れた文字列から専攻の抽出を試みる：「大学／学院」の後ろから、日付・勤務期間の前までの語を取る
        s = maj
        # 1) 去掉开头日期段
        # EN: 1) Remove a leading date segment
        # JA: 1) 先頭の日付部分を除く
        s = re.sub(r"^\s*\d{4}\s*[\-./年]\s*\d{1,2}\s*月?\s*[\-~～—–至到]\s*(?:\d{4}\s*[\-./年]\s*\d{1,2}\s*月?|至今|在读)\s*[，,、。.\s]*", "", s)
        # 2) 如果后面跟着「学校名 专业名」，跳过学校名
        # EN: 2) If "school name major name" follows, skip the school name
        # JA: 2) 後ろに「学校名 専攻名」が続く場合は学校名を飛ばす
        if fallback_school and fallback_school in s:
            s = s.split(fallback_school, 1)[1] if fallback_school in s else s
            s = re.sub(r"^[\s　，,、。.；;：:（(【\-]+\s*", "", s)
        # 3) 再截到工作时间/日期结束
        # EN: 3) Then cut at the work time/date
        # JA: 3) 次に勤務期間・日付のところで切る
        s = re.split(r"(工作时间|工作经历|\d{4}\s*[\-./年]\s*\d{1,2}|主修课程|主要课程|课程|学历|学位|外语|技能|证书)", s, maxsplit=1)[0]
        s = re.split(r"[，,。.；;：:（(【\[]", s, maxsplit=1)[0].strip()
        if len(s) > 30:
            s = s[:30].strip()
        if _looks_like_date_or_salary(s):
            s = ""
        return s
    # —— 王吉庆/王佳乐修复：预过滤「纯占位别名」edu（没有真实内容，就是KV的key被当成分割片段）
    # EN: —— Fix for past cases: pre-filter edu entries that are "pure placeholder aliases" (no real content; just a KV key taken as a split fragment)
    # JA: —— 過去の事例への修正：「純粋なプレースホルダーの別名」の edu を事前に除外する（実内容がなく、KV のキーが分割片として扱われただけのもの）
    _PLACEHOLDER_RE = re.compile(
        r"^(?:第?\s*\d+\s*|最\s*高\s*|第?\s*[一二三四五六七八九十]\s*)?"
        r"(?:学历|学校|专业|学位)"
        r"(?:学校|专业|学位|名称|类型)?\s*$"
    )
    _filtered_list = []
    for edu in edu_list:
        _sn = str(edu.get("school_name") or edu.get("school") or "").strip()
        _deg = str(edu.get("school_degree_type") or edu.get("degree") or "").strip()
        _s18 = str(edu.get("school_start_ym") or edu.get("school_end_ym") or "").strip()
        if (_PLACEHOLDER_RE.match(_sn) and not _s18) or (len(_sn) <= 15 and _PLACEHOLDER_RE.match(_sn)):
            # 学校名就是占位别名 → 直接跳过这条（它根本不是学历条目，只是KV的key）
            # EN: The school name is just a placeholder alias → skip this entry (it is not an education entry at all, just a KV key)
            # JA: 学校名がプレースホルダーの別名にすぎない → この項目をスキップする（そもそも学歴の項目ではなく KV のキーにすぎない）
            continue
        if _deg and _PLACEHOLDER_RE.match(_deg) and not _sn and not _s18:
            # 学位是占位别名、啥都没有 → 跳过
            # EN: The degree is a placeholder alias and there is nothing else → skip
            # JA: 学位がプレースホルダーの別名で、他に何もない → スキップ
            continue
        _filtered_list.append(edu)
    edu_list = _filtered_list

    for edu in edu_list:
        # —— 第一步：先把「旧同义词字段」的值读进「标准字段」（只做一次，避免双向同步错误
        # 学校名：school (旧) | school_name(标准)
        # EN: —— Step 1: first read the values of the "old synonym fields" into the "standard fields" (done only once, to avoid two-way sync errors
        #     School name: school (old) | school_name (standard)
        # JA: —— ステップ 1：まず「旧同義フィールド」の値を「標準フィールド」に読み込む（双方向同期の誤りを避けるため 1 回だけ行う
        #     学校名：school（旧）| school_name（標準）
        _sch_std = str(edu.get("school_name") or edu.get("school") or "").strip()
        # 专业名：major(旧) | major_name(旧) | school_major_name(标准)
        # EN: Major name: major (old) | major_name (old) | school_major_name (standard)
        # JA: 専攻名：major（旧）| major_name（旧）| school_major_name（標準）
        _maj_std = str(edu.get("school_major_name") or edu.get("major_name") or edu.get("major") or "").strip()
        # 学位：degree(旧) | degree_name(旧) | school_degree_type(标准)
        # EN: Degree: degree (old) | degree_name (old) | school_degree_type (standard)
        # JA: 学位：degree（旧）| degree_name（旧）| school_degree_type（標準）
        _deg_std = str(edu.get("school_degree_type") or edu.get("degree_name") or edu.get("degree") or "").strip()
        # 日期：school_start_date（旧）→ school_start_ym（标准）
        # EN: Dates: school_start_date (old) → school_start_ym (standard)
        # JA: 日付：school_start_date（旧）→ school_start_ym（標準）
        _s_sy = str(edu.get("school_start_ym") or edu.get("school_start_date") or edu.get("start_ym") or "").strip()
        _s_ey = str(edu.get("school_end_ym") or edu.get("school_end_date") or edu.get("end_ym") or "").strip()

        # —— ★占位别名替换（王吉庆修复：原school_name是"第X学历学校"等占位key → 直接替换成global_school）
        # EN: —— ★Placeholder alias replacement (fix for a past case: the original school_name was a placeholder key like "第X学历学校" (school of Xth degree) → replace it directly with global_school)
        # JA: —— ★プレースホルダーの別名の置き換え（過去の事例への修正：元の school_name が「第X学历学校」（第 X 学歴の学校）などのプレースホルダーのキー → global_school でそのまま置き換える）
        if _PLACEHOLDER_RE.match(_sch_std):
            _sch_std = global_school if global_school else ""
        if _deg_std and _PLACEHOLDER_RE.match(_deg_std):
            _deg_std = global_degree if global_degree else ""
        if _maj_std and _PLACEHOLDER_RE.match(_maj_std):
            _maj_std = global_major if global_major else ""

        # —— ★ 1学历学校/2学历学校 空内容兜底：如果仍没值，从edu_section_text对应行号后取
        # EN: —— ★Fallback for empty "1学历学校/2学历学校" (school of 1st/2nd degree): if there is still no value, take it from the corresponding line of edu_section_text
        # JA: —— ★「1学历学校／2学历学校」（第 1・第 2 学歴の学校）が空の場合の最終手段：まだ値がなければ edu_section_text の対応する行の後から取る
        if (not _sch_std or not _maj_std) and edu_section_text:
            # 在section中找第1个/第2个「(日期段 + 学校名 + 专业 + 学位)」行组
            # EN: In the section, find the 1st/2nd group of lines "(date range + school name + major + degree)"
            # JA: セクション内で 1 つ目・2 つ目の「（期間 + 学校名 + 専攻 + 学位）」の行グループを探す
            _lines = [l.strip() for l in edu_section_text.splitlines() if l.strip()]
            _edu_pat = re.compile(
                r"(?:19|20)\d{2}\s*[\./年\-]\s*\d{0,2}\s*月?\s*[\-~～—–至到‒―〜\-]+\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{0,2}\s*月?|至今|在读|现在)"
            )
            # 数 edu_date 行，第 i 个日期对应当前 edu（如果原edu有start/end，按顺序匹配最接近的）
            # EN: Count edu_date lines; the i-th date corresponds to the current edu (if the original edu has start/end, match the closest in order)
            # JA: edu_date の行を数え、i 番目の日付が現在の edu に対応する（元の edu に start/end があれば順に最も近いものをマッチさせる）
            _edu_entries: list[dict[str, str]] = []
            i = 0
            while i < len(_lines):
                ln = _lines[i]
                m = _edu_pat.search(ln)
                if m:
                    # 收集接下来2-3行作为学校+专业+学位
                    # EN: Collect the next 2-3 lines as school + major + degree
                    # JA: 次の 2〜3 行を学校 + 専攻 + 学位として集める
                    entry_lines = [ln]
                    for j in range(1, 4):
                        if i + j < len(_lines) and not _edu_pat.search(_lines[i+j]):
                            entry_lines.append(_lines[i+j])
                        else:
                            break
                    joined = " ".join(entry_lines)
                    s, ma, d = _smash_edu_sentence(joined)
                    # 再从joined里找学校名标志词（兜底）
                    # EN: Then look for school marker words in joined (fallback)
                    # JA: 次に joined から学校の目印の語を探す（最終手段）
                    if not s:
                        m_s = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-]{2,40}(?:大学|学院|学校|分校|高中|中学|小学|医科|理工|科技|师范|党校))", joined)
                        if m_s: s = m_s.group(1).strip()
                    # 找学位词
                    # EN: Find degree words
                    # JA: 学位の語を探す
                    if not d:
                        for dk in ("博士后","博士","硕士","研究生","MBA","EMBA","MPA","本科","学士","大专","专科","高中","中专","职高","初中","小学"):
                            if dk in joined:
                                d = dk; break
                    _edu_entries.append({"s": s, "m": ma, "d": d})
                    i += len(entry_lines) - 1
                i += 1
            # 匹配当前edu到它在edu_list中的序号
            # EN: Match the current edu to its index in edu_list
            # JA: 現在の edu を edu_list 内での番号に対応付ける
            _idx_in_list = edu_list.index(edu) if edu in edu_list else 0
            if 0 <= _idx_in_list < len(_edu_entries):
                en = _edu_entries[_idx_in_list]
                if not _sch_std and en["s"]: _sch_std = en["s"]
                if not _maj_std and en["m"]: _maj_std = en["m"]
                if not _deg_std and en["d"]: _deg_std = en["d"]

        edu["school_name"] = _sch_std
        edu["school_major_name"] = _maj_std
        edu["school_degree_type"] = _deg_std
        edu["school_start_ym"] = _s_sy
        edu["school_end_ym"] = _s_ey
        # 2) 学校名清理：去掉 '&' 连接的后缀（如「井冈山大学&同济大学」→ 只保留含学校标志的第一段或清理&）
        # EN: 2) School name cleaning: remove suffixes joined by '&' (e.g. "井冈山大学&同济大学" → keep only the first segment with a school marker, or clean up the &)
        # JA: 2) 学校名のクレンジング：「&」でつながった接尾部分を除く（例：「井冈山大学&同济大学」→ 学校の目印を含む最初の部分だけを残すか & を整理する）
        sch = edu["school_name"]
        if "&" in sch or "＆" in sch:
            sch_parts = [p.strip() for p in re.split(r"[&＆]", sch) if p.strip()]
            if len(sch_parts) >= 2:
                chosen = None
                for p in sch_parts:
                    if any(s in p.lower() for s in SCHOOL_SIGNS):
                        chosen = p
                        break
                if not chosen:
                    chosen = sch_parts[0]
                sch = chosen
                edu["school_name"] = sch
        # 3) 学校/专业/学位 去尾部标点（再增强一次：全角逗号/顿号/描述后缀 截断）
        # EN: 3) Remove trailing punctuation from school/major/degree (strengthened again: truncate at full-width commas/enumeration commas/descriptive suffixes)
        # JA: 3) 学校・専攻・学位の末尾の句読点を除く（さらに強化：全角カンマ・読点・説明の接尾辞で切る）
        for fld, src in (("school_name", sch), ("school_major_name", edu["school_major_name"]), ("school_degree_type", edu["school_degree_type"])):
            v = str(edu.get(fld) or "")
            if v:
                # 去掉尾部：, 选拔交流项目/联合培养等描述
                # EN: Remove trailing descriptions such as ", 选拔交流项目/联合培养" (selected exchange programme / joint training)
                # JA: 末尾の「, 选拔交流项目／联合培养」（選抜交流プログラム／共同育成）などの説明を除く
                m_tail = re.search(r"^(.*?)[，,、；;]\s*(?:选拔|交流|访学|交换|联合培养|项目|课程|培训|实验班|基地班|创新班|就读|入学|毕业|学历|学位|全日制|函授|自考|成人|专升本|人才培养|计划生|卓越|国际|联合|合作|公费|自费|委培|定向).*$", v)
                if m_tail and any(s in m_tail.group(1).lower() for s in SCHOOL_SIGNS):
                    v = m_tail.group(1).strip()
                v = re.sub(r"[\s　:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", v).strip()
                edu[fld] = v
        # —— 3B) 整句拆解：如果学校名很长（≥20字）或包含职责词（负责/管理等），强制切出真正的学校+专业+学位
        # EN: —— 3B) Whole-sentence decomposition: if the school name is very long (≥20 characters) or contains duty words (负责/管理 etc.), force-cut the real school + major + degree
        # JA: —— 3B) 文全体の分解：学校名が非常に長い（20 文字以上）か職務の語（负责／管理など）を含む場合は、本当の学校 + 専攻 + 学位を強制的に切り出す
        _cur_school_long = len(str(edu.get("school_name") or "")) >= 20
        _cur_school_strong_bad = any(x in str(edu.get("school_name") or "") for x in
            ("负责", "管理", "开发", "维护", "担当", "主管", "经理", "工程师", "顾问", "专员", "助理",
             "销售", "生产", "采购", "营业", "财务", "人事", "行政", "客服", "物流", "资材", "制造",
             "就读于", "毕业于", "工作经历", "工作时间", "主修课程", "课程", "学位", "学历", "全日制",
             "项目", "实习", "培训", "证书", "技能", "外语", "能力", "MS", "新媒体", "渠道", "营销"))
        if _cur_school_long or _cur_school_strong_bad:
            smashed_s, smashed_m, smashed_d = _smash_edu_sentence(str(edu.get("school_name") or ""))
            if smashed_s:
                # 整句拆解出的学校名，覆盖错误值；专业/学位仅当原来为空或像垃圾时才覆盖
                # EN: The school name from whole-sentence decomposition overwrites the wrong value; major/degree are overwritten only when originally empty or junk-like
                # JA: 文全体の分解で得た学校名で誤った値を上書きする。専攻・学位は元が空かゴミらしい場合だけ上書きする
                edu["school_name"] = smashed_s
                if smashed_m and (not edu.get("school_major_name") or _looks_like_date_or_salary(edu.get("school_major_name") or "") or len(str(edu.get("school_major_name") or "")) > 40):
                    edu["school_major_name"] = smashed_m
                if smashed_d and not edu.get("school_degree_type"):
                    edu["school_degree_type"] = smashed_d
        # —— 3C) 学校名「两段直接粘连」截断：
        #      原逻辑：同一个 sign2 出现两次才切（如两个"大学"）。丁嘉颖 case 是不同标志词（学院+中学）粘连，切不到。
        #      修复：找到所有学校标志词的位置（按出现先后排），取第2个标志词的起始位置作为截断点（第一个结束后还有另一个标志→前面是第一段学校）
        #      保护（程泽 case：武汉体育学院体育科技学院）：两个标志词之间没有任何标点/空格/大写字母分隔符，且中间连接字是纯汉字 → 判定为「独立学院全名」，不截断
        # EN: —— 3C) Truncate school names where "two segments are directly stuck together":
        #          Old logic: only cut when the same sign2 appears twice (e.g. two "大学"). In a past case different marker words (学院+中学) were stuck together, so it could not cut.
        #          Fix: find the positions of all school marker words (sorted by appearance) and use the start of the second marker as the cut point (another marker after the first one ends → the part before is the first school)
        #          Protection (a past case: 武汉体育学院体育科技学院): no punctuation/space/uppercase separator between the two markers, and the connecting characters are pure Han → judged the "full name of an independent college", not truncated
        # JA: —— 3C) 「2 つの部分が直接くっついた」学校名を切る：
        #          旧ロジック：同じ sign2 が 2 回現れたとき（例：「大学」が 2 つ）だけ切っていた。過去の事例では異なる目印の語（学院 + 中学）がくっついていたため切れなかった。
        #          修正：すべての学校の目印の語の位置を（出現順に）探し、2 つ目の目印の開始位置を切断点とする（1 つ目の終了後にさらに目印があれば → その前が 1 つ目の学校）
        #          保護（過去の事例：武汉体育学院体育科技学院）：2 つの目印の間に句読点・空白・大文字の区切りがなく、つなぐ文字が漢字だけ → 「独立学院の正式名称」と判定し、切らない
        _sch_text = str(edu.get("school_name") or "")
        if _sch_text and len(_sch_text) > 10:
            _SIGNS_ALL = ("大学", "学院", "学校", "中学", "小学", "高中", "分校", "大学校")
            sign_positions: list[tuple[int, int, str]] = []  # (start_idx, end_idx, sign)
            for sign3 in _SIGNS_ALL:
                scan = 0
                # 每轮 scan 都递增；额外设置硬上限，防止异常输入或后续改动造成死循环。
                # EN: Increment on every scan round; also set a hard upper limit to prevent infinite loops from abnormal input or later changes.
                # JA: スキャンのたびに加算する。さらに上限を設け、異常な入力や今後の変更で無限ループになるのを防ぐ。
                for _ in range(len(_sch_text) + 1):
                    f = _sch_text.find(sign3, scan)
                    if f < 0:
                        break
                    sign_positions.append((f, f + len(sign3), sign3))
                    scan = f + 1
            # 按 start 排序
            # EN: Sort by start
            # JA: start で並べ替える
            sign_positions.sort(key=lambda x: x[0])
            _cut_pos = -1
            if len(sign_positions) >= 2:
                # 取第二个标志词的起始位置之前作为截断（第一个标志词结束后，再出现标志词就是第二段了）
                # EN: Cut before the start of the second marker word (after the first marker ends, another marker means the second segment)
                # JA: 2 つ目の目印の語の開始位置の前で切る（1 つ目の目印が終わった後にまた目印があれば、それは 2 つ目の部分）
                first_end = sign_positions[0][1]
                second_start = sign_positions[1][0]
                # 必须 first_end < second_start（即两个标志词之间还有其他字符）
                # EN: Must have first_end < second_start (i.e. there are other characters between the two markers)
                # JA: first_end < second_start であること（つまり 2 つの目印の間に他の文字がある）
                if second_start > first_end:
                    between_text = _sch_text[first_end:second_start]
                    # ===== 新增：独立学院全名保护（程泽 case：武汉体育学院体育科技学院） =====
                    # 两个标志之间 没有 标点/空格/斜杠/顿号 分隔符 → 不截断
                    # EN: ===== New: protect full names of independent colleges (a past case: 武汉体育学院体育科技学院) =====
                    #     No punctuation/space/slash/enumeration-comma separator between the two markers → do not truncate
                    # JA: ===== 追加：独立学院の正式名称の保護（過去の事例：武汉体育学院体育科技学院）=====
                    #     2 つの目印の間に句読点・空白・スラッシュ・読点の区切りがない → 切らない
                    _has_separator_between = bool(re.search(r"[\s　，,。.；;、/\\|｜&＆·\-—_()（）\[\]【】<>《》a-zA-Z0-9]", between_text))
                    _middle_all_chinese = bool(re.fullmatch(r"[\u4e00-\u9fa5]+", between_text))
                    if _has_separator_between or not _middle_all_chinese:
                        # 确认 first 标志词结束后的前缀 candidate 本身含学校标志
                        # EN: Confirm that the prefix candidate after the first marker ends itself contains a school marker
                        # JA: 1 つ目の目印が終わった後の接頭部分 candidate 自体に学校の目印があることを確認する
                        candidate_before = _sch_text[:first_end].strip()
                        if any(s in candidate_before.lower() for s in SCHOOL_SIGNS):
                            _cut_pos = first_end
            if _cut_pos > 0 and _cut_pos < len(_sch_text):
                candidate = _sch_text[:_cut_pos].strip()
                if any(s in candidate.lower() for s in SCHOOL_SIGNS):
                    edu["school_name"] = candidate
                    rest = _sch_text[_cut_pos:].strip()
                    if rest:
                        _, extra_m, extra_d = _smash_edu_sentence(rest)
                        if not edu.get("school_major_name") and extra_m:
                            edu["school_major_name"] = extra_m
                        if not edu.get("school_degree_type") and extra_d:
                            edu["school_degree_type"] = extra_d
        # —— P4 教育强修复：学校名长句/垃圾/完全不符合（施畅"工作时间"/张群"日本东横INN酒店"/余冯俊"3年龄31..."）
        #  先判定是「垃圾学校名」→ 清空 → 从 edu_section_text 找第 i 条真实学校
        # EN: —— P4 strong education repair: school name is a long sentence/junk/completely invalid (past cases: "工作时间" (work time), "日本东横INN酒店" (a hotel), "3年龄31..." (age))
        #      First decide it is a "junk school name" → clear it → find the i-th real school in edu_section_text
        # JA: —— P4 学歴の強力な修復：学校名が長文・ゴミ・まったく不適切（過去の事例：「工作时间」（勤務時間）、「日本东横INN酒店」（ホテル）、「3年龄31...」（年齢））
        #      まず「ゴミの学校名」と判定 → 空にする → edu_section_text から i 番目の本当の学校を探す
        _SN = str(edu.get("school_name") or "").strip()
        _BAD_CO_SUFFIXES = ("支店","分店","营业部","办事处","事务所","酒店","客栈","旅馆","招待所","商场","超市","百货","门店","旗舰店","大厦","商场","店")
        if _SN:
            _is_garbage = False
            # 1) 完全没有学校标志(大学/学院/学校/中学/小学/高中/医科/理工/师范/党校/干部学院/研修生/研究所/研究院)
            # EN: 1) No school marker at all (大学/学院/学校/中学/小学/高中/医科/理工/师范/党校/干部学院/研修生/研究所/研究院: university/college/school/middle/primary/high school/medical/polytechnic/normal/party school/cadre college/trainee/research institute)
            # JA: 1) 学校の目印がまったくない（大学／学院／学校／中学／小学／高中／医科／理工／师范／党校／干部学院／研修生／研究所／研究院）
            if not any(s in _SN for s in SCHOOL_SIGNS):
                # 再判断：是不是公司/酒店/店铺后缀结尾？或 是不是 4 字以内纯垃圾词（如"工作时间"）
                # EN: Then decide: does it end with a company/hotel/shop suffix? Or is it a pure junk word of 4 characters or fewer (e.g. "工作时间")?
                # JA: 次に判定する：会社・ホテル・店舗の接尾辞で終わるか？ または 4 文字以内の純粋なゴミの語（例：「工作时间」）か？
                if any(_SN.endswith(suf) for suf in _BAD_CO_SUFFIXES) or len(_SN) <= 8:
                    _is_garbage = True
                # 还判断：含强黑名单关键词（工作时间/负责/公司/经理/工程师 等职业词）
                # EN: Also decide: contains strong blacklist keywords (工作时间/负责/公司/经理/工程师 etc. occupational words)
                # JA: さらに判定する：強いブラックリストのキーワード（工作时间／负责／公司／经理／工程师 などの職業の語）を含むか
                if any(x in _SN for x in ("工作经历","工作时间","有限公司","股份有限公司","集团","分公司","营业部","酒店","客栈","INN")):
                    _is_garbage = True
            # 2) 超长(≥40字)但 smash 后还没救出任何学校（_cur_school_long 上面块执行但 smashed_s 为空）
            # EN: 2) Very long (≥40 characters) but smash still rescued no school (the _cur_school_long block above ran but smashed_s is empty)
            # JA: 2) 非常に長い（40 文字以上）が smash しても学校を救出できなかった（上の _cur_school_long のブロックは実行されたが smashed_s が空）
            if len(_SN) >= 40:
                # 已经在 3B) 里 smash 过一次 → 现在再 smash 一次确保救回
                # EN: Already smashed once in 3B) → smash once more now to make sure it is rescued
                # JA: 3B) ですでに 1 回 smash 済み → 確実に救出するため今もう 1 回 smash する
                if not any(s in _SN for s in SCHOOL_SIGNS):
                    _is_garbage = True
                else:
                    # 40字+含学校标志 → 强制再smash一次
                    # EN: 40+ characters with a school marker → force another smash
                    # JA: 40 文字以上で学校の目印あり → もう 1 回 smash を強制する
                    ss, sm, sd = _smash_edu_sentence(_SN)
                    if ss and len(ss) < len(_SN):
                        edu["school_name"] = ss
                        if sm and (not edu.get("school_major_name")):
                            edu["school_major_name"] = sm
                        if sd and (not edu.get("school_degree_type")):
                            edu["school_degree_type"] = sd
                    else:
                        # 有学校标志但smash不出任何东西 → 从中间正则找第一个含「XX大学/XX学院/XX学校」
                        # EN: Has a school marker but smash yields nothing → regex-search the middle for the first "XX大学/XX学院/XX学校"
                        # JA: 学校の目印はあるが smash で何も取れない → 途中から最初の「XX大学／XX学院／XX学校」を正規表現で探す
                        m_rescue = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·]{2,30}(?:大学|学院|学校|分校|大学校|高中|中学|小学|医科|理工|科技|师范|研修生|研究所|研究院|党校|干部学院))", _SN)
                        if m_rescue:
                            edu["school_name"] = m_rescue.group(1).strip()
                        else:
                            _is_garbage = True
            # 3) 如果最终判定为垃圾 → 清空，后面从section兜底
            # EN: 3) If finally judged junk → clear it; the section fallback handles it later
            # JA: 3) 最終的にゴミと判定 → 空にし、後でセクションの最終手段で補う
            if _is_garbage:
                edu["school_name"] = ""

        # —— 如果 school_name 为空（或清空垃圾后为空），从 edu_section_text 中按顺序找第 i 个真实学校条目
        # EN: —— If school_name is empty (or empty after clearing junk), find the i-th real school entry in order in edu_section_text
        # JA: —— school_name が空（またはゴミを消して空になった）なら、edu_section_text から順に i 番目の本当の学校項目を探す
        if (not edu.get("school_name")) and edu_section_text:
            # 当前 edu 在 edu_list 中的序号（0/1/2），对应当前 section 中第几条日期段
            # EN: Index of the current edu in edu_list (0/1/2), corresponding to which date range in the current section
            # JA: edu_list における現在の edu の番号（0/1/2）。現在のセクション内の何番目の期間に対応するか
            _idx = None
            for i, e in enumerate(edu_list):
                if e is edu: _idx = i; break
            if _idx is None: _idx = 0
            # 在 section 文本中按日期抓第 idx 个条目，提取学校名
            # EN: Grab the idx-th entry in the section text by date and extract the school name
            # JA: セクションのテキストから日付で idx 番目の項目を取り、学校名を抽出する
            _lns = [l.strip() for l in edu_section_text.splitlines() if l.strip()]
            _DATE_RE = re.compile(
                r"(?:19|20)\d{2}\s*[\./年\-]\s*\d{0,2}\s*月?\s*[\-~～—–至到‒―〜\-]+\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{0,2}\s*月?|至今|在读|现在)"
            )
            _entries_found: list[str] = []
            i_s = 0
            while i_s < len(_lns):
                ln = _lns[i_s]
                if _DATE_RE.search(ln):
                    # 把当前行+后续2行合并起来找学校名
                    # EN: Combine the current line + the next 2 lines to look for the school name
                    # JA: 現在の行 + 後続の 2 行を結合して学校名を探す
                    pool = " ".join(_lns[i_s:min(i_s+3, len(_lns))])
                    s_found = ""
                    s_s, _, _ = _smash_edu_sentence(pool)
                    if s_s:
                        s_found = s_s
                    else:
                        m_s2 = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·]{2,40}(?:大学|学院|学校|分校|大学校|高中|中学|小学|医科|理工|科技|师范|研修生|研究所|研究院|党校|干部学院))", pool)
                        if m_s2:
                            s_found = m_s2.group(1).strip()
                    if s_found:
                        _entries_found.append(s_found)
                        i_s += 2  # 跳过已消费的行
                        # EN: Skip lines already consumed
                        # JA: すでに使った行はスキップする
                i_s += 1
            if _idx < len(_entries_found):
                edu["school_name"] = _entries_found[_idx]
            elif _entries_found and _idx == 0:
                edu["school_name"] = _entries_found[0]
            # 再兜底：没找到分条，就用全局第一条
            # EN: Further fallback: if no separate entries were found, use the first global one
            # JA: さらに最終手段：個別の項目が見つからなければ全体の最初のものを使う
            if (not edu.get("school_name")) and _entries_found:
                edu["school_name"] = _entries_found[0]

        # —— 3D) 专业名清洗：如果是日期薪资/太长，用 extract 工具洗一遍
        # EN: —— 3D) Major name cleaning: if it is a date/salary or too long, wash it with the extract tool
        # JA: —— 3D) 専攻名のクレンジング：日付・給与だったり長すぎたりする場合は extract ツールで洗う
        _cur_maj = str(edu.get("school_major_name") or "")
        if _cur_maj and (_looks_like_date_or_salary(_cur_maj) or len(_cur_maj) > 40):
            cleaned = _extract_major_from_mess(_cur_maj, str(edu.get("school_name") or ""))
            if cleaned:
                edu["school_major_name"] = cleaned
            elif _looks_like_date_or_salary(_cur_maj):
                # 真洗不出来就清空（等 section KV 回填）
                # EN: If nothing can be washed out, clear it (wait for the section KV back-fill)
                # JA: どうしても取れなければ空にする（セクションの KV による補完を待つ）
                edu["school_major_name"] = ""
        # 3E) 再清理一次专业名：去掉「/ 高中」尾部（如「财务管理/ 高中」→「财务管理」）
        # EN: 3E) Clean the major name once more: remove a "/ 高中" (high school) tail (e.g. "财务管理/ 高中" → "财务管理")
        # JA: 3E) 専攻名をもう一度クレンジングする：末尾の「/ 高中」（高校）を除く（例：「财务管理/ 高中」→「财务管理」）
        _maj = str(edu.get("school_major_name") or "")
        if _maj:
            # 去掉尾部的「高中/本科/大专/硕士/博士」学历词（专业里混学历）
            # EN: Remove trailing degree words "高中/本科/大专/硕士/博士" (degrees mixed into the major)
            # JA: 末尾の学歴の語「高中／本科／大专／硕士／博士」を除く（専攻に学歴が混入したもの）
            _maj2 = re.sub(r"(/|\\|\|)\s*(?:高中|中专|职高|初中|小学|本科|大专|专科|硕士|博士|研究生|MBA|EMBA)\s*$", "", _maj).strip()
            _maj2 = re.sub(r"[\s　/\\|]+\s*(?:高中|中专|职高|初中|小学|本科|大专|专科|硕士|博士|研究生)\s*$", "", _maj2).strip()
            if _maj2 and len(_maj2) <= 40:
                edu["school_major_name"] = _maj2
        # 3F) 专业名非法判定：把「自我评价/技能描述串」清空（宁严勿松）
        #     触发条件：长度 >= 20 且 命中 技能/证书/语言/评价 关键词 或 多标点整句
        # EN: 3F) Invalid major check: clear "self-assessment / skill description strings" (better too strict than too loose)
        #         Trigger: length >= 20 and hits skill/certificate/language/assessment keywords, or is a whole sentence with several punctuation marks
        # JA: 3F) 不正な専攻名の判定：「自己評価・スキル説明の文字列」を空にする（緩すぎるより厳しすぎる方がよい）
        #         発動条件：長さ 20 以上で、スキル・資格・語学・評価のキーワードにヒットするか、句読点の多い文全体
        _maj3 = str(edu.get("school_major_name") or "")
        if _maj3 and len(_maj3) >= 20:
            _SKILL_KW_IN_MAJOR = (
                # 动作/评价词
                # EN: Action/assessment words
                # JA: 動作・評価の語
                "通晓", "掌握", "熟练", "熟悉", "精通", "了解", "具备", "有", "持有", "取得", "获得", "考取",
                "擅长", "运用", "应用", "能够", "可以", "良好", "优秀", "较强", "扎实", "丰富", "出色",
                # 证书/等级
                # EN: Certificates/levels
                # JA: 資格・レベル
                "证书", "等级", "资格", "职称", "资质", "执照", "N1", "N2", "N3", "专八", "专四",
                "六级", "四级", "八级", "一级", "二级", "三级", "初级", "中级", "高级", "报关",
                "CET", "TOEFL", "IELTS", "GRE", "GMAT", "JLPT",
                # 语言名（非专业）
                # EN: Language names (not majors)
                # JA: 言語名（専攻ではない）
                "英语", "日语", "韩语", "法语", "德语", "俄语", "西班牙语", "葡萄牙语", "意大利语",
                "阿拉伯语", "中文", "汉语", "粤语", "闽南语",
                # 其他：工作/经验/能力/沟通/团队/技能/实习/项目
                # EN: Others: 工作/经验/能力/沟通/团队/技能/实习/项目 (work/experience/ability/communication/team/skills/internship/project)
                # JA: その他：工作／经验／能力／沟通／团队／技能／实习／项目（業務・経験・能力・コミュニケーション・チーム・スキル・インターン・プロジェクト）
                "经验", "能力", "沟通", "团队", "协作", "技能", "实习", "项目", "工作", "社会",
                "负责", "协助", "参与", "管理",
            )
            _has_skill_kw = any(kw in _maj3 for kw in _SKILL_KW_IN_MAJOR)
            _n_punc_maj = sum(_maj3.count(c) for c in "，,。.！!？?；;、")
            _is_sentence = _n_punc_maj >= 2 and len(_maj3) >= 25
            # 再排除真正的专业名（如「国际经济与贸易」「汉语言文学」「英语（国际商务方向）」：
            #   真正的专业即使长，也不会含「证书」「N1」「等级」这种强技能词
            # EN: Then exclude real major names (e.g. "国际经济与贸易" (international economics and trade), "汉语言文学" (Chinese language and literature), "英语（国际商务方向）" (English, international business)):
            #       real majors, even long ones, never contain strong skill words like "证书" (certificate), "N1", "等级" (level)
            # JA: 次に本当の専攻名を除外する（例：「国际经济与贸易」（国際経済・貿易）、「汉语言文学」（中国語言語文学）、「英语（国际商务方向）」（英語・国際ビジネス））：
            #       本当の専攻は長くても「证书」（資格）「N1」「等级」（レベル）のような強いスキルの語を含まない
            _STRONG_NONMAJOR_KW = ("证书", "等级", "N1", "N2", "六级", "四级", "八级", "报关", "资格证", "执业", "执照")
            _has_strong_nonmajor = any(kw in _maj3 for kw in _STRONG_NONMAJOR_KW)
            if _has_strong_nonmajor or (_has_skill_kw and _is_sentence):
                edu["school_major_name"] = ""
        # 3G) 专业名「Header字段粘连」截断（陈亮 case：地质学政治面貌预备党员身体状况健康籍）
        #     常见Header字段关键词：政治面貌/民族/出生年月/身体状况/健康/籍贯/身高/体重/婚姻状况/
        #                        通讯方式/通信地址/联系电话/计算机水平/外语水平/专业课程/兴趣爱好/求职意向/社会实践/个性评价/
        #                        户口/户籍/现居住地/住址/政治面目/健康状况
        #     规则：当专业名≥10字，且在中后段（index≥3处）出现上述关键词，在关键词前截断
        # EN: 3G) Truncate majors with "header fields stuck on" (a past case: 地质学政治面貌预备党员身体状况健康籍 (geology + political status + health status + ...))
        #         Common header field keywords: 政治面貌/民族/出生年月/身体状况/健康/籍贯/身高/体重/婚姻状况/
        #                            通讯方式/通信地址/联系电话/计算机水平/外语水平/专业课程/兴趣爱好/求职意向/社会实践/个性评价/
        #                            户口/户籍/现居住地/住址/政治面目/健康状况 (political status, ethnicity, birth date, health, native place, height, weight, marital status, contact, address, phone, computer level, foreign language level, courses, hobbies, job preferences, social practice, personality, hukou, residence)
        #         Rule: when the major is ≥10 characters and one of these keywords appears in the middle/second half (index ≥3), truncate before the keyword
        # JA: 3G) 「ヘッダーのフィールドがくっついた」専攻名を切る（過去の事例：地质学政治面貌预备党员身体状况健康籍（地質学 + 政治的身分 + 健康状態 + …））
        #         よくあるヘッダーのフィールドのキーワード：政治面貌／民族／出生年月／身体状况／健康／籍贯／身高／体重／婚姻状况／
        #                            通讯方式／通信地址／联系电话／计算机水平／外语水平／专业课程／兴趣爱好／求职意向／社会实践／个性评价／
        #                            户口／户籍／现居住地／住址／政治面目／健康状况
        #         ルール：専攻名が 10 文字以上で、上記のキーワードが中盤以降（index 3 以上）に現れたら、キーワードの前で切る
        _maj_g = str(edu.get("school_major_name") or "")
        if _maj_g and len(_maj_g) >= 10:
            HEADER_STUCK_KW = (
                "政治面貌", "政治面目", "民族", "出生年月", "身体状况", "健康状况", "健康籍", "健康",
                "籍贯", "身高", "体重", "婚姻状况", "通讯方式", "通信地址", "联系电话", "联系方式",
                "计算机水平", "外语水平", "专业课程", "兴趣爱好", "求职意向", "社会实践", "个性评价", "自我评价",
                "户口", "户籍", "现居住地", "住址", "身体", "籍 贯", "民 族",
            )
            _cut_here = -1
            for hkw in HEADER_STUCK_KW:
                fidx = _maj_g.find(hkw)
                # 关键词必须出现在 index≥3（避免关键词本身是专业前缀的极端情况）
                # EN: The keyword must appear at index ≥3 (to avoid the extreme case where the keyword itself is a major prefix)
                # JA: キーワードは index 3 以上に現れなければならない（キーワード自体が専攻の接頭辞である極端なケースを避けるため）
                if fidx >= 3 and (_cut_here < 0 or fidx < _cut_here):
                    _cut_here = fidx
            if _cut_here > 0:
                cleaned_maj = _maj_g[:_cut_here].strip(" 　，,。.；;、/\\|｜-—_()（）[]【】")
                if cleaned_maj and 1 <= len(cleaned_maj) <= 40:
                    edu["school_major_name"] = cleaned_maj
        # 4) 学位 rank 规范化 + degree_type 标准化（避免校验脚本误杀）
        # EN: 4) Normalise the degree rank + standardise degree_type (so the validation script does not reject valid entries)
        # JA: 4) 学位ランクの正規化 + degree_type の標準化（検証スクリプトが誤って弾かないようにする）
        deg = edu["school_degree_type"]
        rank, etype = normalize_degree_rank(deg)
        if rank:
            edu["school_degree_rank"] = rank
            if not edu.get("school_education_type") or edu.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                edu["school_education_type"] = etype
            # 4.5) degree_type 归范化：用 rank 反查标准枚举值（避免「（硕士」「统招本科」等不在 VALID_DEGREE_TYPES 里）
            # EN: 4.5) Normalise degree_type: look up the standard enumeration value from the rank (to avoid values like "（硕士" or "统招本科" not in VALID_DEGREE_TYPES)
            # JA: 4.5) degree_type の正規化：rank から標準の列挙値を逆引きする（「（硕士」「统招本科」など VALID_DEGREE_TYPES にない値を避ける）
            _RANK_TO_STD_DEGREE = {"7": "博士后", "6": "博士", "5": "硕士", "4": "本科", "3": "大专", "2": "高中", "1": "初中"}
            std_deg = _RANK_TO_STD_DEGREE.get(str(rank), "")
            if std_deg:
                # 仅当原值含垃圾字符（括号/前后缀/长度异常）时才覆盖原值
                # EN: Overwrite the original value only when it contains junk characters (brackets/affixes/abnormal length)
                # JA: 元の値にゴミの文字（括弧・接辞・異常な長さ）がある場合だけ上書きする
                _d_raw = str(edu.get("school_degree_type") or "").strip()
                _d_has_junk = bool(re.search(r"[（(【\[:：\\\t]|专业$|统招|自考|函授|成人|全日制|在职|毕业$|学位$", _d_raw))
                _d_len_bad = len(_d_raw) > 10 or not _d_raw
                _d_not_in_enum = _d_raw not in ("博士后", "博士", "硕士", "研究生", "本科", "学士", "大专", "专科", "高中", "中专", "职高", "初中", "小学", "MBA", "EMBA", "MPA")
                if _d_has_junk or _d_len_bad or _d_not_in_enum:
                    edu["school_degree_type"] = std_deg
        # 5) 专业/学校名的尾部左括号截断（如「计算机信息管理（中日合作」 → 「计算机信息管理」，去掉 （ 之后内容）
        # EN: 5) Truncate at a trailing opening bracket in major/school names (e.g. "计算机信息管理（中日合作" → "计算机信息管理", removing everything after （)
        # JA: 5) 専攻・学校名の末尾の開き括弧で切る（例：「计算机信息管理（中日合作」→「计算机信息管理」。（ 以降を除く）
        for fld in ("school_major_name", "school_name"):
            v2 = str(edu.get(fld) or "")
            if v2:
                left_open = max(v2.rfind("（"), v2.rfind("("))
                right_close = max(v2.rfind("）"), v2.rfind(")"))
                if left_open >= 0 and left_open > right_close:
                    v2 = v2[:left_open].strip()
                edu[fld] = v2
        # 6) 全局KV回填（section末尾扫到的专业/学位）：如果当前条目缺专业/学位则补
        # EN: 6) Global KV back-fill (majors/degrees found at the end of the section): fill in if the current entry lacks a major/degree
        # JA: 6) 全体の KV による補完（セクション末尾で見つかった専攻・学位）：現在の項目に専攻・学位がなければ補う
        if global_major and not edu["school_major_name"]:
            edu["school_major_name"] = global_major
        if global_degree and not edu["school_degree_type"]:
            edu["school_degree_type"] = global_degree
            rank2, etype2 = normalize_degree_rank(global_degree)
            if rank2 and not edu.get("school_degree_rank"):
                edu["school_degree_rank"] = rank2
                if not edu.get("school_education_type") or edu.get("school_education_type") in ("全日制", "全日制大学", "全日制研究生"):
                    edu["school_education_type"] = etype2
        # —— ★v4新增补丁2b：校名后关键词截断（司吾仇 case：校名后直接粘主修/课程/工作经历/技能/获奖）——
        #    如「上海体育学院体育教育主修课程羽毛球...工作经历...」 → 截到「主修课程」前 → 变成「上海体育学院体育教育」
        #    再切：如果前半段含「学/学院/大学」但后半段是专业内容（教育/经管/等学科单字）→ 再精切到标志词位置
        # EN: —— ★v4 patch 2b: truncate at keywords after the school name (a past case: major/courses/work history/skills/awards stuck right after the school name) ——
        #        e.g. "上海体育学院体育教育主修课程羽毛球...工作经历..." → cut before "主修课程" (main courses) → becomes "上海体育学院体育教育"
        #        Cut further: if the first half contains "学/学院/大学" but the second half is major content (single-character subjects like education/economics/management) → cut precisely at the marker position
        # JA: —— ★v4 の追加パッチ 2b：学校名の後のキーワードで切る（過去の事例：学校名の直後に専攻・課程・職歴・スキル・受賞がくっついていた）——
        #        例：「上海体育学院体育教育主修课程羽毛球...工作经历...」→「主修课程」（主要課程）の前で切る →「上海体育学院体育教育」になる
        #        さらに切る：前半に「学／学院／大学」があり、後半が専攻の内容（教育・経済管理などの分野の語）なら → 目印の位置で精密に切る
        _sch_name = str(edu.get("school_name") or "")
        if _sch_name:
            # 截断关键词（出现在校名后的非学校内容的开始）：主修、核心课程、主要课程、课程、工作经历、工作经验、工作时间、
            #                技能证书、获奖、荣誉、社会实践、培训、实习、项目经历、项目经验、自我评价、自我鉴定、求职意向、
            #                主修方向、计算机能力、外语水平、语言能力、政治面貌、民族、身高、体重、婚姻状况
            # EN: Truncation keywords (the start of non-school content after the school name): 主修、核心课程、主要课程、课程、工作经历、工作经验、工作时间、
            #                    技能证书、获奖、荣誉、社会实践、培训、实习、项目经历、项目经验、自我评价、自我鉴定、求职意向、
            #                    主修方向、计算机能力、外语水平、语言能力、政治面貌、民族、身高、体重、婚姻状况 (major, core/main courses, courses, work history/experience/time, skill certificates, awards, honours, social practice, training, internship, project history/experience, self-assessment, job preferences, major direction, computer skills, foreign language level, language ability, political status, ethnicity, height, weight, marital status)
            # JA: 切断のキーワード（学校名の後に続く学校以外の内容の始まり）：主修、核心课程、主要课程、课程、工作经历、工作经验、工作时间、
            #                    技能证书、获奖、荣誉、社会实践、培训、实习、项目经历、项目经验、自我评价、自我鉴定、求职意向、
            #                    主修方向、计算机能力、外语水平、语言能力、政治面貌、民族、身高、体重、婚姻状况
            TRUNC_KW_AFTER_SCHOOL = (
                "主修课程", "核心课程", "主要课程", "主修方向", "主修专业", "专业课程",
                "课程设置", "课程简介", "课程",
                "工作经历", "工作经验", "工作时间", "工作内容", "职业经历", "社会实践",
                "技能", "技能证书", "专业技能", "计算机能力", "外语水平", "语言能力",
                "获奖", "荣誉", "奖项", "证书", "培训", "实习", "项目经历", "项目经验",
                "自我评价", "自我鉴定", "个人评价", "求职意向", "应聘职位",
                "政治面貌", "民族", "身高", "体重", "婚姻状况", "出生日期", "出生年月",
                "现居住地", "联系电话", "邮箱", "电子邮箱", "通讯地址",
            )
            best_cut = len(_sch_name)
            for kw in TRUNC_KW_AFTER_SCHOOL:
                p = _sch_name.find(kw)
                if 0 < p < best_cut:
                    # 前面必须包含学校标志词（大学/学院/学校/分校/高中/中学/小学）
                    # EN: The front part must contain a school marker word (大学/学院/学校/分校/高中/中学/小学)
                    # JA: 前半には学校の目印の語（大学／学院／学校／分校／高中／中学／小学）が必要
                    front = _sch_name[:p]
                    if any(s in front for s in ("大学", "学院", "学校", "分校", "高中", "中学", "小学", "医科", "理工",
                                                 "科技", "师范", "干部学院", "党校", "研究所", "研究院")):
                        best_cut = p
            if best_cut < len(_sch_name):
                cand = _sch_name[:best_cut].strip(" ,，。.、/|｜-—_()（）")
                if 2 <= len(cand) <= 50:
                    # 截完再剥：如果结尾是常见专业描述（「XX教育」「XX工程」这种单字教育/经管/工程）→ 保留（体育教育其实是教育方向，没问题）
                    # EN: Strip again after cutting: if it ends with a common major description ("XX教育" "XX工程" — single-word education/management/engineering) → keep it (体育教育 is really an education direction, that is fine)
                    # JA: 切った後にさらに除く：末尾がよくある専攻の説明（「XX教育」「XX工程」など教育・経済管理・工学の語）なら → 残す（体育教育は実際に教育の分野なので問題ない）
                    edu["school_name"] = cand
                    _sch_name = cand
                    # 如果截出来的专业部分是 "体育教育/工商管理" 这种 → 如果原来major空，这里补进去
                    # EN: If the cut-off major part is like "体育教育/工商管理" (physical education / business administration) → fill it in here if major was empty
                    # JA: 切り出した専攻部分が「体育教育／工商管理」（体育教育／経営管理）のようなもの → 元の major が空ならここで補う
                    extra_major_part = _sch_name[best_cut:].strip(" ,，。.、/|｜-—_()（）") if False else ""
        # —— ★v4新增补丁2c：school_major_name含YYYY格式日期子串 → 直接清空（刘解朕 case：2005.09 - 2009.06被当major）——
        #    规则：major非空时，如果包含 4 位连续年份(19xx/20xx) + 后面跟了 . / - 年 月 分隔符 → 直接认为是日期间隔碎片，清空
        # EN: —— ★v4 patch 2c: school_major_name contains a YYYY date substring → clear it directly (a past case: 2005.09 - 2009.06 taken as the major) ——
        #        Rule: when major is non-empty and contains a 4-digit year (19xx/20xx) followed by a . / - 年 月 separator → treat it as a date-range fragment and clear it
        # JA: —— ★v4 の追加パッチ 2c：school_major_name に YYYY の日付の部分文字列がある → そのまま空にする（過去の事例：2005.09 - 2009.06 が専攻になっていた）——
        #        ルール：major が空でなく、4 桁の年（19xx／20xx）の後に . / - 年 月 の区切りが続く → 期間の断片とみなして空にする
        _cur_major = str(edu.get("school_major_name") or "")
        if _cur_major:
            if re.search(r"(?:19|20)\d{2}\s*[\.\-/年]", _cur_major) and not re.search(r"[\u4e00-\u9fff]", _cur_major):
                # 完全没有中文字的专业（纯日期/数字符号）→ 100% 是日期碎片，清空
                # EN: A major with no Chinese characters at all (pure date/digit symbols) → 100% a date fragment, clear it
                # JA: 漢字がまったくない専攻（日付・数字・記号だけ）→ 100% 日付の断片なので空にする
                edu["school_major_name"] = ""
            elif len(_cur_major) < 40 and _DATE_IN_MAJOR_RE.search(_cur_major) and not re.search(r"[\u4e00-\u9fff]{2,}", _cur_major):
                # 短（<40）且有日期但没有2个以上中文字 → 也判为日期碎片
                # EN: Short (<40), has a date but fewer than 2 Chinese characters → also judged a date fragment
                # JA: 短く（40 未満）、日付があり漢字が 2 文字未満 → これも日付の断片と判定する
                edu["school_major_name"] = ""
        # —— 最后：只保留 7 个标准字段（白名单重建 dict，删除冗余别名：school/major_name/major/degree_name/degree/school_start_date/school_end_date）
        # EN: —— Finally: keep only the 7 standard fields (rebuild the dict from a whitelist, deleting redundant aliases: school/major_name/major/degree_name/degree/school_start_date/school_end_date)
        # JA: —— 最後に：標準の 7 フィールドだけを残す（ホワイトリストで dict を作り直し、冗長な別名 school／major_name／major／degree_name／degree／school_start_date／school_end_date を削除）
        std = {
            "school_name": str(edu.get("school_name", "") or ""),
            "school_major_name": str(edu.get("school_major_name", "") or ""),
            "school_degree_type": str(edu.get("school_degree_type", "") or ""),
            "school_degree_rank": str(edu.get("school_degree_rank", "") or ""),
            "school_education_type": str(edu.get("school_education_type", "") or ""),
            "school_start_ym": str(edu.get("school_start_ym", "") or ""),
            "school_end_ym": str(edu.get("school_end_ym", "") or ""),
        }
        # —— ★V2新增：空校名/空专业兜底回填（周会方 school_name 空，但有 major="日语" + edu_section_text 里肯定有校名，之前漏填）——
        # EN: —— ★New in V2: back-fill empty school/major names (a past case: school_name empty, but major="日语" (Japanese) and edu_section_text surely has the school name, previously missed) ——
        # JA: —— ★V2 の追加：空の学校名・専攻名の補完（過去の事例：school_name は空だが major="日语"（日本語）があり、edu_section_text には必ず学校名があるのに以前は漏れていた）——
        if not std["school_name"] or not std["school_major_name"]:
            # 1. 优先用全局搜出来的 KV 回填（L1290-L1336 已经扫了 section 文本中的学校名/专业名/学位名）
            # EN: 1. Prefer back-filling from the globally found KV (L1290-L1336 already scanned the section text for school/major/degree names)
            # JA: 1. 全体で見つけた KV による補完を優先する（L1290〜L1336 ですでにセクションのテキストから学校名・専攻名・学位名をスキャン済み）
            if not std["school_name"] and global_school:
                std["school_name"] = global_school
            if not std["school_major_name"] and global_major:
                std["school_major_name"] = global_major
            # 2. 再兜底：如果 section 文本里有 XX大学/XX学院/XX学校 这种，正则抓第一个，作为学校名补进去
            # EN: 2. Further fallback: if the section text has something like XX大学/XX学院/XX学校, regex-grab the first one and fill it in as the school name
            # JA: 2. さらに最終手段：セクションのテキストに XX大学／XX学院／XX学校 のようなものがあれば、正規表現で最初のものを取り学校名として補う
            if not std["school_name"] and edu_section_text:
                _re_s = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·・（）()\-·]{2,40}(?:大学|学院|学校|分校|大学校|高中|中学|小学|医科|理工|科技|师范|研修生|研究所|研究院|党校|干部学院))", edu_section_text)
                if _re_s:
                    _cand = _re_s.group(1).strip()
                    # 不能含工作/公司类禁词
                    # EN: Must not contain work/company forbidden words
                    # JA: 業務・会社の類の禁止語を含んではならない
                    _BAD_T = ("有限公司", "集团", "营业部", "工作", "负责", "担任", "经理", "销售", "客户", "采购", "营业", "工厂", "医院", "银行")
                    if not any(x in _cand for x in _BAD_T) and 2 <= len(_cand) <= 50:
                        std["school_name"] = _cand
            # 3. 如果 dept/position/responsibilities 里面的 学校名还是取不到，且原major有中文（日语/计算机等），保留（不额外操作）
            # EN: 3. If the school name still cannot be obtained from dept/position/responsibilities and the original major has Chinese (日语/计算机 etc.), keep it (no extra action)
            # JA: 3. dept／position／responsibilities からも学校名が取れず、元の major に中国語（日语／计算机など）がある場合は、そのまま残す（追加の処理はしない）
        # 安全兜底：school_degree_rank 空串默认填 "4" 与既有逻辑一致
        # EN: Safety fallback: an empty school_degree_rank defaults to "4", consistent with the existing logic
        # JA: 安全のための最終手段：school_degree_rank が空文字なら既存のロジックと同じく既定で "4" を入れる
        if not std["school_degree_rank"]:
            std["school_degree_rank"] = "4"
        normalized.append(std)
    # ===== 新增1：垃圾校名条目 过滤删除（宁严勿松） =====
    # EN: ===== New 1: filter out and delete junk school-name entries (better too strict than too loose) =====
    # JA: ===== 追加 1：ゴミの学校名の項目を除外・削除する（緩すぎるより厳しすぎる方がよい）=====
    _BAD_SCHOOL_STRONG_KW = (
        "求职信", "保存到我的电脑", "打印", "下载", "举报", "删除",
        "有限公司", "股份有限公司", "集团", "营业部", "営業部",
        "工厂", "工场", "支店", "支社", "事务所", "事務所",
        "部门", "部門", "課",
        "负责", "担当", "主管", "经理", "专员", "助理", "顾问",
        "课程", "上线", "导入", "实施", "生产", "销售", "市场",
        "采购", "品质", "营业", "财务", "人事", "行政", "客服", "物流",
        "资材", "制造", "薪资", "月薪", "年薪", "元/月", "万/月", "参观工厂",
        "就读于", "工作时间",
        "开票", "记账", "会计报表", "申报",
        "客户维系", "现地出差", "跟踪订单", "在库管理",
        "分门别类整理",
        "个人简历",
    )
    _BAD_SCHOOL_LONG_KW = (
        "管理", "开发", "维护", "工程师",
        "培训", "项目", "服务", "业务", "工程", "技术",
        "学历", "学位", "全日制", "自学", "统招", "外语", "MS", "能力",
        "专业", "GPA", "主要", "毕业", "获得", "工科学士",
        "公司", "前台服务员", "支店",
    )
    _BAD_SCHOOL_SUFFIXES = (
        "有限公司", "股份有限公司", "有限责任公司", "集团", "股份",
        "公司", "工厂", "工场", "营业部", "営業部", "支店", "支社",
        "事务所", "事務所", "医院", "诊所", "診所", "酒店", "飯店",
        "超市", "商店", "食堂", "餐厅", "餐廳",
    )
    _UI_GARBAGE_KW = (
        "HYPERLINK", "mailto:", "http://", "https://", "www.",
        "保存到我的电脑", "打印", "下载", "举报", "删除", "求职信", "收藏简历",
    )
    _SCHOOL_SIGNS_LOCAL = ("大学", "学院", "学校", "分校", "大学校", "高中", "中学", "小学", "私塾",
                            "研究所", "研究院", "党校", "干部学院", "师范", "医科", "理工", "科技",
                            "university", "college", "institute", "school", "academy", "polytechnic", "vocational")
    # 日期/薪资 正则（用于school_major_name/school_degree_type/school_name 内容判断）
    # EN: Date/salary regex (used to judge the content of school_major_name/school_degree_type/school_name)
    # JA: 日付・給与の正規表現（school_major_name／school_degree_type／school_name の内容判定に使う）
    _DATE_SALARY_RE = re.compile(
        r"^\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{1,2}\s*月?\s*[\-~～—–至到‒―〜\-]+\s*(?:(?:19|20)\d{2}\s*[\./年\-]\s*\d{1,2}\s*月?|至今|在读|现在)|\d+\s*(?:元|千|万)\s*/\s*(?:月|年))"
    )
    _DATE_IN_MAJOR_RE = re.compile(r"\b(?:19|20)\d{2}[\./\-]\d{1,2}(?:[\./\-]\d{1,2})?\b")
    _filtered: list[dict[str, Any]] = []
    for _edu in normalized:
        _sname = str(_edu.get("school_name") or "").strip()
        _major = str(_edu.get("school_major_name") or "").strip()
        _dtype = str(_edu.get("school_degree_type") or "").strip()
        _s_ym = str(_edu.get("school_start_ym") or "").strip()
        _e_ym = str(_edu.get("school_end_ym") or "").strip()
        # ===== 先对每个字段单独做垃圾清理 =====
        # a) school_name: 剥掉标签前缀（如「所学专业：」「专业学历：」「就读日期：」）
        # EN: ===== First clean junk from each field separately =====
        #     a) school_name: strip label prefixes (e.g. "所学专业：" (major studied:), "专业学历：", "就读日期：" (dates attended:))
        # JA: ===== まず各フィールドのゴミを個別に除去する =====
        #     a) school_name：ラベルの接頭辞を除く（例：「所学专业：」（専攻：）、「专业学历：」、「就读日期：」（在学期間：））
        if _sname:
            _sname = re.sub(
                r"^[\s　]*(?:所学专业|专业学历|就读日期|称就读日期|专业学历学位|学历性质|学校专业|专业学校|称就读|称\s*就读日期|学历/学位|学历学位|专业名称)[：:\s]*",
                "", _sname).strip()
            # 剥掉尾部的\xa0+重复（如「上海交大工商管理专业\xa0工商管理」→ 去\xa0及后面重复内容）
            # EN: Strip a trailing \xa0 + repetition (e.g. "上海交大工商管理专业\xa0工商管理" → remove \xa0 and the repeated content after it)
            # JA: 末尾の \xa0 + 繰り返しを除く（例：「上海交大工商管理专业\xa0工商管理」→ \xa0 とその後の繰り返し部分を除く）
            if "\xa0" in _sname or "&nbsp;" in _sname:
                _sname = re.sub(r"(\xa0|&nbsp;).*$", "", _sname).strip()
            # 含「/全日制本科」这种（专业/学历混进校名）→ 到 / 截止取前面
            # EN: Contains something like "/全日制本科" (/full-time bachelor) (major/degree mixed into the school name) → take the part before /
            # JA: 「/全日制本科」（／全日制学士）のようなものを含む（専攻・学歴が学校名に混入）→ / の前の部分を取る
            if re.search(r"/\s*(?:全日制|统招|自考|函授|成人)", _sname):
                _sname = _sname.split("/", 1)[0].strip()
        # b) school_major_name: 清理日期薪资格式
        # EN: b) school_major_name: clean date/salary formats
        # JA: b) school_major_name：日付・給与の形式を除去する
        if _major:
            if _DATE_SALARY_RE.match(_major) or _looks_like_date_or_salary(_major):
                _major = ""
            # 日期子串粘连（如「2006 /3」）→ 清
            # EN: Stuck-on date substrings (e.g. "2006 /3") → clear
            # JA: くっついた日付の部分文字列（例：「2006 /3」）→ 除去
            if _DATE_IN_MAJOR_RE.search(_major) and not re.search(
                r"(?:985|211|一二三四五六七八九十)[级届]", _major):
                _major = ""
            # 纯 KV 标签前缀（如「所学专业：工商管理」）→ 剥标签
            # EN: Pure KV label prefix (e.g. "所学专业：工商管理") → strip the label
            # JA: 純粋な KV ラベルの接頭辞（例：「所学专业：工商管理」）→ ラベルを除く
            _major = re.sub(r"^[\s　]*(?:所学专业|专业名称|主修专业|专业)[:：]\s*", "", _major).strip()
            # 纯数字/符号 → 清
            # EN: Pure digits/symbols → clear
            # JA: 数字・記号だけ → 除去
            if re.fullmatch(r"[\d\s/\-\+\.\\，,。.；;：:（）()\[\]【】]+", _major):
                _major = ""
        # c) school_degree_type: 非合法枚举且不在规范化词典里的 → 清（稍后会从 rank 反查）
        #    先留着，让后面 normalize_degree_rank 工作
        # ===== 再对整个条目做保留/删除判定 =====
        # EN: c) school_degree_type: not a valid enum and not in the normalisation dictionary → clear (it will be looked up from rank later)
        #        Keep it for now and let normalize_degree_rank work later
        #     ===== Then decide whether to keep or delete the whole entry =====
        # JA: c) school_degree_type：有効な列挙値でも正規化辞書にもない → 除去（後で rank から逆引きする）
        #        いったん残し、後で normalize_degree_rank に処理させる
        #     ===== 次に項目全体を残すか削除するかを判定する =====
        _has_school_sign = any(s.lower() in _sname.lower() for s in _SCHOOL_SIGNS_LOCAL) if _sname else False
        # 特殊：如果前面已有 _filtered 结果 >= 1（前面有有效条目），且本条 _sname 空（或将被清空）+ 没有 日期信息 → 直接删（避免"education[1] school_name为空"不合格）
        # EN: Special: if there are already >= 1 _filtered results (valid entries before), and this entry's _sname is empty (or will be cleared) + no date information → delete directly (to avoid failing with "education[1] school_name is empty")
        # JA: 特別：すでに _filtered の結果が 1 件以上あり（前に有効な項目がある）、この項目の _sname が空（または空にされる）で日付情報もない → そのまま削除する（「education[1] の school_name が空」で不合格になるのを避ける）
        _already_has_valid = len(_filtered) >= 1
        if not _sname:
            if _already_has_valid and not (_s_ym or _e_ym or _major or _dtype):
                continue  # 已有有效条目 + 本条完全没用 → 整条删
                # EN: Valid entries already exist + this entry is completely useless → delete the whole entry
                # JA: すでに有効な項目がある + この項目はまったく役に立たない → 項目全体を削除
            if (_major or _dtype or _s_ym or _e_ym):
                # 有有用信息但无校名：如果是第1条（前面无有效），保留（后面KV回填会补校名）
                # 如果不是第1条（已有有效），还得看有没有强理由保留：有日期 → 保留（后面可能从其他地方补校名）
                # EN: Has useful information but no school name: if it is the 1st entry (no valid ones before), keep it (the later KV back-fill will add the school name)
                #     If it is not the 1st (valid ones exist), there must be a strong reason to keep it: it has dates → keep (the school name may be filled from elsewhere later)
                # JA: 有用な情報はあるが学校名がない：1 件目（前に有効な項目がない）なら残す（後の KV の補完で学校名が入る）
                #     1 件目でない（有効な項目がある）場合は、残す強い理由が必要：日付がある → 残す（後で他から学校名を補えるかもしれない）
                if _already_has_valid and not (_s_ym or _e_ym):
                    # 已有有效条目 + 本条只有专业/学位但没有日期 → 太弱，整条删（宁严勿松）
                    # EN: Valid entries already exist + this entry has only a major/degree but no dates → too weak, delete the whole entry (better too strict than too loose)
                    # JA: すでに有効な項目がある + この項目は専攻・学位だけで日付がない → 弱すぎるので項目全体を削除（緩すぎるより厳しすぎる方がよい）
                    continue
                _edu["school_name"] = _sname
                _edu["school_major_name"] = _major
                _filtered.append(_edu)
            continue
        # a) UI垃圾 → 删
        # EN: a) UI junk → delete
        # JA: a) UI のゴミ → 削除
        if any(g in _sname for g in _UI_GARBAGE_KW):
            continue
        # b) 强黑名单 → 删
        # EN: b) Strong blacklist → delete
        # JA: b) 強いブラックリスト → 削除
        if any(k in _sname for k in _BAD_SCHOOL_STRONG_KW):
            continue
        # c) 长黑名单（≥25字才触发）
        # EN: c) Long blacklist (triggered only at ≥25 characters)
        # JA: c) 長いブラックリスト（25 文字以上でのみ発動）
        if len(_sname) >= 25 and any(k in _sname for k in _BAD_SCHOOL_LONG_KW):
            continue
        # d) 坏后缀 → 删
        # EN: d) Bad suffix → delete
        # JA: d) 悪い接尾辞 → 削除
        if any(_sname.endswith(s) for s in _BAD_SCHOOL_SUFFIXES):
            continue
        # e) ★核心修复★：school_name 非空 + 无任何学校标志词 → 要么整条删，要么仅留有用信息
        # EN: e) ★Core fix★: school_name non-empty + no school marker word at all → either delete the whole entry or keep only the useful information
        # JA: e) ★中核の修正★：school_name が空でない + 学校の目印の語がまったくない → 項目全体を削除するか、有用な情報だけを残す
        if not _has_school_sign:
            # 检查是否含有用信息：专业/学位/日期
            # EN: Check whether it contains useful information: major/degree/dates
            # JA: 有用な情報（専攻・学位・日付）を含むかを確認する
            has_useful = bool(_major or _dtype or _s_ym or _e_ym
                              or re.search(r"(?:博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学|研究生|MBA|EMBA|MPA)", _sname))
            if not has_useful:
                # 纯垃圾school_name，整条删
                # EN: Pure junk school_name, delete the whole entry
                # JA: 純粋なゴミの school_name なので項目全体を削除
                continue
            # 已有有效条目 + 本条无校名但有用 → 仅当有日期时保留（太弱则删）
            # EN: Valid entries already exist + this one has no school name but is useful → keep only if it has dates (delete if too weak)
            # JA: すでに有効な項目がある + この項目は学校名がないが有用 → 日付がある場合だけ残す（弱すぎれば削除）
            if _already_has_valid and not (_s_ym or _e_ym):
                continue
            # 有有用信息：把school_name清空，其他信息保留（后续KV回填补校名）
            # EN: Has useful information: clear school_name and keep the rest (the later KV back-fill adds the school name)
            # JA: 有用な情報がある：school_name を空にして他の情報は残す（後の KV の補完で学校名を補う）
            _sname = ""
            # 仅有学位/专业，没有日期，没有校名 → 前面有有效条目就不要了
            # EN: Only a degree/major, no dates, no school name → drop it if there are valid entries before
            # JA: 学位・専攻だけで日付も学校名もない → 前に有効な項目があれば捨てる
            if _already_has_valid and not _sname and not (_s_ym or _e_ym):
                continue
        # f) 学校名全是数字/标点 → 删
        # EN: f) School name is all digits/punctuation → delete
        # JA: f) 学校名が数字・句読点だけ → 削除
        if re.fullmatch(r"[\d\-\.\/\s　，,。.！!？?；;、]+", _sname):
            continue
        # g) 日期/薪资 格式的school_name → 整条删
        # EN: g) school_name in date/salary format → delete the whole entry
        # JA: g) 日付・給与の形式の school_name → 項目全体を削除
        if _DATE_SALARY_RE.match(_sname) or _looks_like_date_or_salary(_sname):
            continue
        # 回填清理后的字段
        # EN: Write back the cleaned fields
        # JA: クレンジングしたフィールドを書き戻す
        _edu["school_name"] = _sname
        _edu["school_major_name"] = _major
        # degree_type 会在后面用rank标准化；如果_degree_type含日期/薪资也清掉
        # EN: degree_type will be standardised by rank later; if _degree_type contains a date/salary, clear it too
        # JA: degree_type は後で rank により標準化する。_degree_type に日付・給与があればこれも除去する
        if _DATE_SALARY_RE.match(_dtype) or _DATE_IN_MAJOR_RE.search(_dtype):
            _edu["school_degree_type"] = ""
        _filtered.append(_edu)
    normalized = _filtered
    # ===== 新增1.5：对 normalized 中所有条目，空字段回填全局 KV（global_school / global_major / global_degree）——重点修复 education[0] school_name 为空 =====
    # EN: ===== New 1.5: for all entries in normalized, back-fill empty fields from the global KV (global_school / global_major / global_degree) — mainly fixes education[0] with an empty school_name =====
    # JA: ===== 追加 1.5：normalized のすべての項目について、空のフィールドを全体の KV（global_school / global_major / global_degree）で補う — 主に education[0] の school_name が空の問題を修正 =====
    if normalized and (global_school or global_major or global_degree):
        _LOCAL_DEG_RANK = {
            "博士后": 7, "博士": 6, "硕士": 5, "MBA": 5, "EMBA": 5, "研究生": 5,
            "本科": 4, "专升本": 4, "大专": 3, "专科": 3, "高技": 3,
            "高中": 2, "中专": 2, "职高": 2, "中技": 2, "初中": 1, "小学": 0,
        }
        _LOCAL_VALID_DEGS = tuple(_LOCAL_DEG_RANK.keys())
        for _e in normalized:
            if not str(_e.get("school_name") or "").strip() and global_school:
                _e["school_name"] = global_school
            if not str(_e.get("school_major_name") or "").strip() and global_major:
                maj_clean = re.sub(r"[（(（].*?[）)）]$", "", global_major).strip()
                if len(maj_clean) <= 30:
                    _e["school_major_name"] = maj_clean
            # degree_type 只在空值时回填（避免覆盖已有合法值）
            # EN: Back-fill degree_type only when empty (to avoid overwriting existing valid values)
            # JA: degree_type は空のときだけ補う（既存の正当な値を上書きしないため）
            if not str(_e.get("school_degree_type") or "").strip() and global_degree:
                # degree_type 值规范化（只取合法枚举中的第一匹配）
                # EN: Normalise the degree_type value (take only the first match among valid enum values)
                # JA: degree_type の値を正規化する（有効な列挙値の中で最初にマッチしたものだけを取る）
                for deg in _LOCAL_VALID_DEGS:
                    if deg == global_degree or deg in global_degree:
                        _e["school_degree_type"] = deg
                        # 同步 rank
                        # EN: Sync the rank
                        # JA: rank を同期する
                        if not str(_e.get("school_degree_rank") or "").strip():
                            _e["school_degree_rank"] = str(_LOCAL_DEG_RANK[deg])
                        break
                # 未匹配到合法枚举：但保留原文不填（避免污染）
                # EN: No valid enum value matched: keep the original text and fill nothing (to avoid pollution)
                # JA: 有効な列挙値にマッチしない：元のテキストは残し、何も埋めない（汚染を避けるため）
    # ===== 新增2：按学历rank降序 → 再按school_start_ym降序 =====
    # EN: ===== New 2: sort by degree rank descending → then by school_start_ym descending =====
    # JA: ===== 追加 2：学歴ランクの降順 → 次に school_start_ym の降順で並べ替える =====
    def _edu_sort_key(_e: dict[str, Any]):
        _rk = int(_e.get("school_degree_rank") or "0")
        # 日期：越新越在前；空日期排在后面
        # EN: Dates: newer first; empty dates go last
        # JA: 日付：新しいものほど前、空の日付は後ろ
        _sy = str(_e.get("school_start_ym") or "")
        try:
            _y, _m = 0, 0
            if _sy:
                _parts = re.split(r"[年\-/.]", _sy)
                if len(_parts) >= 1:
                    _y = int(_parts[0]) if _parts[0].isdigit() else 0
                if len(_parts) >= 2:
                    _m = int(_parts[1]) if _parts[1].isdigit() else 0
        except Exception:
            _y, _m = 0, 0
        return (-_rk, -_y, -_m)
    if len(normalized) >= 2:
        normalized.sort(key=_edu_sort_key)

    # —— P6 教育日期统一归一化 + "至今"置空（教育的end日期不能是至今）——
    # EN: —— P6 unified normalisation of education dates + clear "至今" (an education end date cannot be "present") ——
    # JA: —— P6 学歴の日付の統一正規化 +「至今」を空にする（学歴の終了日を「現在」にはできない）——
    for _e in normalized:
        s_s = str(_e.get("school_start_ym") or "").strip()
        s_e = str(_e.get("school_end_ym") or "").strip()
        # 教育不能用"至今/现在/目前/在读"当 end 日期 → 直接置空（代表没毕业，还在读，但没有实际毕业日期）
        # EN: Education cannot use "至今/现在/目前/在读" (present/now/currently/studying) as the end date → clear it directly (meaning not yet graduated, still studying, with no actual graduation date)
        # JA: 学歴では「至今／现在／目前／在读」（現在・在学中など）を end の日付にできない → そのまま空にする（未卒業で在学中、実際の卒業日がないことを表す）
        if s_e in ("至今", "现在", "目前", "在职", "在职中", "在读", "未毕业"):
            _e["school_end_ym"] = ""
            s_e = ""
        # 归一化为 YYYY-MM
        # EN: Normalise to YYYY-MM
        # JA: YYYY-MM に正規化する
        if s_s:
            _e["school_start_ym"] = _normalize_ym_loose(s_s, allow_today_token=False)
        if s_e:
            _e["school_end_ym"] = _normalize_ym_loose(s_e, allow_today_token=False)

    # ============================================================================
    # —— P10a 最终5合1强修（对付最后68个硬骨头剩余case：强黑名单/前缀脏/日期子串/垃圾major/错枚举degree）——
    # ============================================================================
    # 预定义工具：判定一个 school_name 有没有「真实学校特征」
    # EN: ============================================================================
    #     —— P10a final 5-in-1 strong fix (for the last 68 hardest remaining cases: strong blacklist / dirty prefix / date substring / junk major / wrong degree enum) ——
    #     ============================================================================
    #     Predefined tool: decide whether a school_name has "real school features"
    # JA: ============================================================================
    #     —— P10a 最終の 5 in 1 の強力な修正（最後に残った手強い 68 件向け：強いブラックリスト・汚れた接頭辞・日付の部分文字列・ゴミの専攻・誤った学位の列挙値）——
    #     ============================================================================
    #     事前定義のツール：school_name に「本物の学校の特徴」があるかを判定する
    _SCHOOL_TRUE_SIGNS = ("大学", "学院", "学校", "分校", "大学校", "高中", "中学", "小学", "医科", "理工",
                          "科技", "师范", "研修生", "研究所", "研究院", "党校", "干部学院", "中专", "职校",
                          "技校", "职业技术", "专修", "进修", "国际学校", "实验学校", "外国语")
    # 强黑名单（只要整串等于这些词/或被这些词完全套住→100%不是学校）
    # EN: Strong blacklist (if the whole string equals one of these words / or is completely wrapped by them → 100% not a school)
    # JA: 強いブラックリスト（文字列全体がこれらの語に等しいか、完全にこれらの語で包まれている → 100% 学校ではない）
    _SCHOOL_STRONG_BLACK = {"工作时间", "工作经历", "在职", "学历", "毕业时间", "毕业院校", "公司性质", "公司规模",
                            "姓名", "年龄", "民族", "户口", "所在地", "籍贯", "婚姻", "性别", "身高", "体重",
                            "政治面貌", "求职意向", "期望薪资", "期望职位", "现所在地", "现居地", "工作地点",
                            "工作年限", "出生", "生日", "手机", "电话", "邮箱", "E-mail", "QQ", "微信",
                            "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、"}
    # 强黑名单 company/行业关键词（出现在 school 里说明是把工作经历混进来了）
    # EN: Strong blacklist of company/industry keywords (appearing in school means work history got mixed in)
    # JA: 会社・業界のキーワードの強いブラックリスト（school に現れたら職歴が混入したことを意味する）
    _COMPANY_IN_SCHOOL_KW = ("物流", "快递", "贸易", "科技有限", "实业", "股份", "集团", "分公司", "代表处",
                             "电子有限", "机械有限", "化工有限", "餐饮", "酒店", "管理咨询", "传媒", "广告")
    def _has_school_sign(s: str) -> bool:
        s = str(s or "").strip()
        if not s: return False
        # 如果包含真实学校标志 → 判定有
        # EN: If it contains a real school marker → judged yes
        # JA: 本物の学校の目印を含む → あり と判定
        if any(sg in s for sg in _SCHOOL_TRUE_SIGNS): return True
        # 特例：日文「国書日本語学校」这种也属于学校标志
        # EN: Special case: Japanese names like "国書日本語学校" also count as school markers
        # JA: 特例：日本語の「国書日本語学校」のようなものも学校の目印とみなす
        if "語学校" in s or "日本語" in s: return True
        return False
    def _school_looks_garbage(s: str) -> bool:
        """判定 school_name 值是否整体像垃圾（纯脏数据，需要清空后重切）

        EN: Decide whether a school_name value as a whole looks like junk (pure dirty data that must be cleared and re-cut)

        JA: school_name の値が全体としてゴミに見えるか（空にして切り直す必要がある純粋な汚れたデータか）を判定する
        """
        s = str(s or "").strip()
        if not s: return True
        # 命中强黑名单整串
        # EN: The whole string hits the strong blacklist
        # JA: 文字列全体が強いブラックリストにヒット
        if s in _SCHOOL_STRONG_BLACK: return True
        # 命中强黑名单开头（如"工作时间：XX"、"一、二、三、"）
        # EN: Starts with a strong blacklist word (e.g. "工作时间：XX" (work time:), "一、二、三、")
        # JA: 強いブラックリストの語で始まる（例：「工作时间：XX」（勤務時間：）、「一、二、三、」）
        _short = s[:6]
        if any(_short.startswith(bk) for bk in _SCHOOL_STRONG_BLACK): return True
        # 没有任何学校特征 + 长度>10（说明是整句混入）→ 视为垃圾
        # EN: No school features + length > 10 (meaning a whole sentence got mixed in) → treated as junk
        # JA: 学校の特徴がない + 長さ 10 超（文全体が混入したことを示す）→ ゴミとみなす
        if len(s) > 10 and not _has_school_sign(s): return True
        # 没有学校特征 + 包含公司/行业关键词（如"德邦物流"）→ 垃圾
        # EN: No school features + contains company/industry keywords (e.g. "德邦物流" (a logistics company)) → junk
        # JA: 学校の特徴がない + 会社・業界のキーワードを含む（例：「德邦物流」（物流会社））→ ゴミ
        if not _has_school_sign(s) and any(ck in s for ck in _COMPANY_IN_SCHOOL_KW): return True
        return False
    # —— step 1: 遍历每个条目，做单条内部清洗 ——
    # EN: —— step 1: iterate over each entry and do per-entry internal cleaning ——
    # JA: —— step 1：各項目を走査し、項目ごとに内部のクレンジングを行う ——
    for _e in normalized:
        _SN = str(_e.get("school_name") or "").strip()
        _SM = str(_e.get("school_major_name") or "").strip()
        _SD = str(_e.get("school_degree_type") or "").strip()
        changed = False
        # ① 剥 date 粘连前缀（入学YYYY年M月/ 起止日期YYYY..--YYYY../ 32054教育背景起止日期...毕业院校）——最外层剥除
        # EN: ① Strip stuck date prefixes (入学YYYY年M月 / 起止日期YYYY..--YYYY.. / 32054教育背景起止日期...毕业院校) — stripped at the outermost level
        # JA: ① くっついた日付の接頭辞を除く（入学YYYY年M月 / 起止日期YYYY..--YYYY.. / 32054教育背景起止日期...毕业院校）— 最も外側で除去
        if _SN:
            # ①-a 通用前缀剥离：纯数字ID(4位以上) + 教育背景/学历/个人资料 + 起止日期/日期段 全部前置内容剥掉
            # EN: ①-a Generic prefix stripping: pure numeric ID (4+ digits) + 教育背景/学历/个人资料 (education background/degree/personal data) + 起止日期/date range — strip all the leading content
            # JA: ①-a 汎用的な接頭辞の除去：数字だけの ID（4 桁以上）+ 教育背景／学历／个人资料 + 起止日期・期間 — 先頭の内容をすべて除く
            _SN2 = re.sub(
                r"^\d{2,10}(教育背景|个人信息|个人资料|简历|求职简历)\s*"
                r"(?:教育背景|求学经历|学习经历|学历背景)?\s*"
                r"(?:起止日期|日期|时间段|在校时间|学习时间)?\s*"
                r"(?:\d{4}\s*[\-/.年]\s*\d{0,2}\s*月?\s*[\-~～—–至到]{1,3}\s*(?:\d{4}\s*[\-/.年]\s*\d{0,2}\s*月?|至今|在读))?\s*"
                r"(?:毕业院校|学校名称|所在学校|院校名称|学校|院校)\s*[:：]?\s*",
                "", _SN
            )
            # ①-b 前缀「入学YYYY年M月/ 入读YYYY年M月」
            # EN: ①-b Prefixes "入学YYYY年M月/ 入读YYYY年M月" (enrolled in month M of year YYYY)
            # JA: ①-b 接頭辞「入学YYYY年M月／入读YYYY年M月」（YYYY 年 M 月入学）
            _SN2 = re.sub(r"^入(?:学|读)\s*\d{4}\s*年\s*\d{1,2}\s*月?\s*", "", _SN2)
            # ①-c 前缀「3年龄31民族汉族户口XX毕业学校」 这种长脏前缀（KV里已切过，但这里再兜底重切一次smash）→ 如果包含"毕业学校/学校名称"直接用切词法抓出后面的值
            # EN: ①-c Long dirty prefixes like "3年龄31民族汉族户口XX毕业学校" (age, ethnicity, hukou, graduated school) (already cut in the KV step, but smash once more here as a fallback) → if it contains "毕业学校/学校名称" (graduated school / school name), grab the following value directly by tokenising
            # JA: ①-c 「3年龄31民族汉族户口XX毕业学校」（年齢・民族・戸籍・卒業校）のような長い汚れた接頭辞（KV の段階で切ってあるが、ここでも最終手段としてもう一度 smash する）→「毕业学校／学校名称」（卒業校／学校名）を含めば、分割してその後ろの値を直接取る
            if any(kk in _SN2 for kk in ("毕业学校", "学校名称", "就读学校", "所在学校", "毕业院校", "院校名称")):
                _ss, _mm, _dd = _smash_edu_sentence(_SN2)
                if _ss: _SN2 = _ss
                if _mm and (not _SM or _looks_like_date_or_salary(_SM) or len(_SM) > 30):
                    _SM = _mm; changed = True
                if _dd and not _SD:
                    _SD = _dd; changed = True
            if _SN2 != _SN:
                _SN = _SN2.strip()
                changed = True
        # ② school_name 被判定为垃圾 or 没学校特征 → 清空，下面统一重切（smash + section文本兜底）
        # EN: ② school_name judged junk or has no school features → clear it; re-cut uniformly below (smash + section text fallback)
        # JA: ② school_name がゴミと判定されたか学校の特徴がない → 空にし、下でまとめて切り直す（smash + セクションのテキストによる最終手段）
        if _SN and _school_looks_garbage(_SN):
            _SN = ""
            changed = True
        # ②-b school名里有学校标志但头尾还粘了前后脏内容（"上海体育学院体育教育主修课程...工作经历"）→ 截到学校标志后第一个无关关键词
        # EN: ②-b The school name has a school marker but dirty content stuck before/after it ("上海体育学院体育教育主修课程...工作经历...") → cut at the first unrelated keyword after the school marker
        # JA: ②-b 学校名に学校の目印はあるが前後に汚れた内容がくっついている（「上海体育学院体育教育主修课程...工作经历...」）→ 学校の目印の後の最初の無関係なキーワードで切る
        if _SN and _has_school_sign(_SN):
            # 截到这些关键词之前的内容就停（主修课程/核心课程/工作经历/工作时间/实习/培训/项目/技能/证书/获奖）
            # EN: Stop at the content before these keywords (主修课程/核心课程/工作经历/工作时间/实习/培训/项目/技能/证书/获奖: main/core courses, work history, work time, internship, training, project, skills, certificates, awards)
            # JA: これらのキーワードの前の内容で止める（主修课程／核心课程／工作经历／工作时间／实习／培训／项目／技能／证书／获奖）
            _cut_after = re.split(r"(主修课程|核心课程|主要课程|课程|工作经历|工作时间|在职|实习|培训|项目|技能|证书|获奖|荣誉|社会实践|MS|计算机|外语|能力|工作描述|公司)", _SN, maxsplit=1)[0]
            # 还可能「上海体育学院体育教育」→ 多了专业名后缀；如果截完还有"专业名"在后面，用 smash 切出真学校
            # EN: It may still be "上海体育学院体育教育" → with an extra major suffix; if a "major name" remains after cutting, use smash to cut out the real school
            # JA: まだ「上海体育学院体育教育」のように専攻名の接尾辞が余分に付いていることがある。切った後にも「専攻名」が残っていれば smash で本当の学校を切り出す
            if _cut_after != _SN:
                _SN = _cut_after.rstrip("，,、。.；;：:（(【[-").strip()
                changed = True
            # 额外：smash 再收一遍（从 _SN 切真学校名），如果 smash 出的学校名更短则用 smash 版
            # EN: Extra: smash once more (cut the real school name from _SN); if the smashed school name is shorter, use the smashed version
            # JA: 追加：もう一度 smash する（_SN から本当の学校名を切り出す）。smash した学校名の方が短ければ smash 版を使う
            _ss, _mm, _dd = _smash_edu_sentence(_SN)
            if _ss and len(_ss) < len(_SN) and _has_school_sign(_ss):
                _SN = _ss
                if _mm and (not _SM or _looks_like_date_or_salary(_SM)):
                    _SM = _mm
                if _dd and not _SD:
                    _SD = _dd
                changed = True
        # ③ major 像日期/薪资/学年（"2005.09 - 2008.06"、"2015-2016学年第一学期"、"2014/1 日本语能力考试二级"、"PAGE"、"4. 出口的..."）
        # EN: ③ major looks like a date/salary/academic year ("2005.09 - 2008.06", "2015-2016学年第一学期" (first term of academic year 2015-2016), "2014/1 日本语能力考试二级" (JLPT level 2), "PAGE", "4. 出口的...")
        # JA: ③ major が日付・給与・学年のように見える（「2005.09 - 2008.06」、「2015-2016学年第一学期」（2015〜2016 年度第 1 学期）、「2014/1 日本语能力考试二级」（日本語能力試験 2 級）、「PAGE」、「4. 出口的...」）
        if _SM:
            _sm_dirty = False
            if _looks_like_date_or_salary(_SM):
                _sm_dirty = True
            elif re.search(r"学年|学期|第[一二三四五六七八九十]+学期|PAGE|^\d+\s*[.、]\s*", _SM):
                _sm_dirty = True
            elif _SM in ("月", "个", "-", "—", "·", "/") or len(_SM) == 1:
                _sm_dirty = True
            if _sm_dirty:
                # 重切：如果 _SN 还能再smash出major就填，否则空
                # EN: Re-cut: if _SN can still smash out a major, fill it; otherwise empty
                # JA: 切り直す：_SN からまだ major を smash で取り出せれば入れ、なければ空にする
                _, _mm_new, _ = _smash_edu_sentence(_SN) if _SN else ("", "", "")
                _SM = _mm_new or ""
                changed = True
        # ④ degree_type 不在标准枚举（"大学"归一"本科"；"汉语言文学（自学完成大专-本科学业）"→如果内含"本科/大专"抽真degree；空）
        # EN: ④ degree_type not in the standard enum ("大学" (university) normalised to "本科" (bachelor); "汉语言文学（自学完成大专-本科学业）" → if it contains "本科/大专" extract the real degree; otherwise empty)
        # JA: ④ degree_type が標準の列挙値にない（「大学」は「本科」（学士）に正規化。「汉语言文学（自学完成大专-本科学业）」→「本科／大专」を含めば本当の学位を抽出、なければ空）
        if _SD:
            VALID_DEG = {"博士后", "博士", "硕士", "研究生", "MBA", "EMBA", "MPA", "本科", "学士", "大专", "专科",
                         "高中", "中专", "职高", "初中", "小学", "高职", "专升本", "自考本科", "自考专科", "成人本科",
                         "成人专科", "网络教育", "开放教育", "业余", "函授"}
            if _SD not in VALID_DEG:
                # 4-a 内含关键词抽真 degree（"大专-本科"→取较高=本科；"汉语言文学（自学完成大专-本科）"→本科）
                # EN: 4-a Extract the real degree from contained keywords ("大专-本科" → take the higher = 本科 (bachelor); "汉语言文学（自学完成大专-本科）" → 本科)
                # JA: 4-a 含まれるキーワードから本当の学位を抽出する（「大专-本科」→ 高い方 = 本科（学士）、「汉语言文学（自学完成大专-本科）」→ 本科）
                _degree_order = [("博士后", "博士后"), ("博士", "博士"), ("硕士", "硕士"), ("研究生", "研究生"),
                                 ("MBA", "MBA"), ("EMBA", "EMBA"), ("MPA", "MPA"),
                                 ("本科", "本科"), ("学士", "本科"),
                                 ("专升本", "本科"), ("自考本科", "本科"), ("成人本科", "本科"),
                                 ("大专", "大专"), ("专科", "大专"), ("自考专科", "大专"), ("成人专科", "大专"),
                                 ("高职", "大专"), ("网络教育", "大专"), ("开放教育", "大专"), ("函授", "大专"), ("业余", "大专"),
                                 ("高中", "高中"), ("中专", "中专"), ("职高", "职高"),
                                 ("初中", "初中"), ("小学", "小学")]
                _new_deg = ""
                for _kw, _norm in _degree_order:
                    if _kw in _SD:
                        _new_deg = _norm
                        # 不要 break，上面已经按优先级从高到低，先匹配的=高学历，保留
                        # EN: Do not break; the list above is ordered from high to low priority, so the first match = the higher degree, keep it
                        # JA: break しない。上は優先度の高い順に並んでいるので、最初にマッチしたもの = 高い学歴を残す
                        break
                # 4-b 特例 "大学" → 归一 "本科"
                # EN: 4-b Special case "大学" (university) → normalised to "本科" (bachelor)
                # JA: 4-b 特例「大学」→「本科」（学士）に正規化
                if not _new_deg and re.fullmatch(r"\s*大\s*学\s*", _SD):
                    _new_deg = "本科"
                if _new_deg and _new_deg != _SD:
                    _SD = _new_deg
                    changed = True
                elif not _new_deg:
                    # 完全不识别 → 置空
                    # EN: Not recognised at all → empty
                    # JA: まったく認識できない → 空にする
                    _SD = ""
                    changed = True
        # 回写
        # EN: Write back
        # JA: 書き戻す
        if changed:
            if _SN is not None: _e["school_name"] = _SN
            if _SM is not None: _e["school_major_name"] = _SM
            if _SD is not None: _e["school_degree_type"] = _SD

    # —— step 2: school_name 为空时（上面被清掉了），再用 edu_section_text 第i个日期段重切 ——
    # EN: —— step 2: when school_name is empty (cleared above), re-cut using the i-th date range in edu_section_text ——
    # JA: —— step 2：school_name が空（上で消された）場合は、edu_section_text の i 番目の期間で切り直す ——
    if any(str(e.get("school_name") or "").strip() == "" for e in normalized):
        _edu_section_source = edu_section_text if edu_section_text else ""
        if _edu_section_source:
            # 按日期条目抽出每段候选（YYYY/MM 或 YYYY-MM 或 YYYY年MM月 ... 至今/YYYY）→ 共 N 条，与 normalized 的 index 对应
            # EN: Extract candidates for each date entry (YYYY/MM or YYYY-MM or YYYY年MM月 ... 至今/YYYY) → N entries in total, matching the indexes of normalized
            # JA: 日付の項目ごとに候補を抽出する（YYYY/MM、YYYY-MM、YYYY年MM月 ... 至今／YYYY）→ 合計 N 件で、normalized の index に対応
            _date_entries = []
            _DATE_RANGE_RE_MULTI = re.compile(
                r"((?:19|20)\d{2}\s*[\-/.年]\s*\d{0,2}\s*月?\s*[\-~～—–至到]{1,3}\s*(?:(?:19|20)\d{2}\s*[\-/.年]\s*\d{0,2}\s*月?|至今|在读)?)"
            )
            for _dm in _DATE_RANGE_RE_MULTI.finditer(_edu_section_source):
                _date_entries.append({
                    "range_text": _dm.group(1),
                    "text_after": _edu_section_source[_dm.end(): _dm.end()+300],  # 日期后面 300 字上下文（应该含学校+专业）
                    # EN: 300 characters of context after the date (should contain school + major)
                    # JA: 日付の後ろ 300 文字の文脈（学校 + 専攻を含むはず）
                })
            for _i, _e in enumerate(normalized):
                if str(_e.get("school_name") or "").strip(): continue  # 已经有学校名，跳过
                # EN: Already has a school name, skip
                # JA: すでに学校名があるのでスキップ
                if _i < len(_date_entries):
                    _ctx = _date_entries[_i]["text_after"]
                    _ss, _mm, _dd = _smash_edu_sentence(_ctx)
                    if _ss and _has_school_sign(_ss):
                        _e["school_name"] = _ss
                        if not _e.get("school_major_name") and _mm: _e["school_major_name"] = _mm
                        if not _e.get("school_degree_type") and _dd: _e["school_degree_type"] = _dd
    return normalized


def standardize_datetime(raw: str) -> str:
    raw = raw.replace("年", "-").replace("月", "-").replace("日", " ").replace(".", "-").replace("/", "-")
    raw = re.sub(r"\s+", " ", raw).strip()
    parts = raw.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"
    d_parts = date_part.split("-")
    if len(d_parts) >= 3:
        y, m, d = d_parts[0], d_parts[1], d_parts[2]
        try:
            date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except ValueError:
            date_str = date_part
    elif len(d_parts) == 2:
        try:
            date_str = f"{int(d_parts[0]):04d}-{int(d_parts[1]):02d}-01"
        except ValueError:
            date_str = date_part
    else:
        date_str = date_part
    t_parts = time_part.split(":")
    try:
        if len(t_parts) == 2:
            time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:00"
        elif len(t_parts) == 3:
            time_str = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}:{int(t_parts[2]):02d}"
        else:
            time_str = "00:00:00"
    except ValueError:
        time_str = "00:00:00"
    return f"{date_str} {time_str}"


def parse_resume_dates(text: str, fallback_date: str) -> tuple[str, str, str, str]:
    date_val = r"(?:19|20)\d{2}[年./\-]\d{1,2}(?:[月./\-]\d{1,2}日?)?(?:[ T]?\d{1,2}:\d{1,2}(?::\d{1,2})?)?"
    m_up = re.search(rf"(?:简历)?更新(?:于|[日时]?[期间]?)[：:\s]*({date_val})", text, re.I)
    if not m_up:
        m_up = re.search(r"((?:19|20)\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", text[:500])
    if m_up:
        raw_up = m_up.group(1).strip()
        updated_date = standardize_datetime(raw_up)
        updated_source = "文档正文更新时间"
    else:
        updated_date = fallback_date
        updated_source = "HTML文件修改时间（历史资料替代）"
    m_dl = re.search(rf"(?:简历)?(?:下载|投递)(?:于|[日时]?[期间]?)[：:\s]*({date_val})", text, re.I)
    if m_dl:
        raw_dl = m_dl.group(1).strip()
        download_date = standardize_datetime(raw_dl)
        download_source = "文档正文下载/投递时间"
    else:
        download_date = fallback_date
        download_source = "HTML文件修改时间（历史资料替代）"
    return updated_date, download_date, updated_source, download_source


def _format_ym(s: str) -> str:
    m = re.search(r"((?:19|20)\d{2})[./年\-]?(\d{1,2})?", s)
    if m:
        y = m.group(1)
        m_str = m.group(2) or "01"
        return f"{y}年{int(m_str):02d}月01日"
    return ""


# =============================================================================
# 各平台姓名提取器
# =============================================================================
# EN: =============================================================================
#     Name extractors for each platform
#     =============================================================================
# JA: =============================================================================
#     各プラットフォームの氏名抽出器
#     =============================================================================

def _extract_51job_name(text: str, filename: str, parsed_name: str) -> str:
    parsed_name = (parsed_name or "").strip()
    bad_pat = r"(?:工程师|经理|主管|专员|开发|运营|总监|销售|翻译)"
    if (parsed_name and parsed_name not in ("待确认姓名", "未知", "简历", "无关联职位简历")
            and not re.search(bad_pat, parsed_name)):
        return parsed_name
    m_raw = re.search(r"\n\s*([^\s\n:：|│]{2,8})\s*\n\s*(?:\d+[-～~]\d+年工作经验|\d+年工作经验|[男女]\s*[|│]|[\d]{1,2}岁)", text)
    if m_raw:
        cand = m_raw.group(1).strip()
        if not re.search(
            r"(?:更新时间|简历关键字|最近工作|最高学历|自我评价|工作经验|工作经历|项目经历|教育经历|语言能力)",
            cand,
        ):
            return cand
    m_file = re.match(r"^51job_([^\s\-_0-9]{2,8})_\d+", filename, re.I)
    if m_file:
        return m_file.group(1).strip()
    m_file2 = re.search(r"([^\s\-_0-9]{2,8})-\d{1,2}岁", filename)
    if m_file2:
        return m_file2.group(1).strip()
    return parsed_name or "未知"


def _extract_zhilian_name(text: str, filename: str) -> str:
    _EXCLUDE_NAMES = {"智联招聘", "前程无忧", "猎聘", "简历", "ID", "求职意向",
                      "自我评价", "工作经历", "教育经历", "项目经历", "语言能力",
                      "专业技能", "培训经历", "所获证书", "所获", "证书", "基本信息",
                      "未知", "无关联职", "职位", "扫码联系TA", "付费下载", "付费下载简历", "下载简历", "下载", "付费"}
    _ZH_NAME_RE = r"[\u4e00-\u9fff]{2,5}"
    _EN_NAME_RE = r"[A-Za-z][A-Za-z\s\.\-]{1,29}"
    _JOB_TITLE_SUFFIXES = ("工程师", "经理", "主管", "总监", "专员", "助理", "代表",
                           "老师", "教师", "医生", "护士", "设计师", "分析师",
                           "顾问", "主任", "科长", "班长", "组长", "实习生", "操作员",
                           "编辑", "翻译", "会计", "出纳", "审计", "策划", "文员",
                           "前台", "客服", "司机", "厨师", "电工", "焊工", "木工",
                           "采购", "销售", "运营", "产品", "测试", "运维")

    def _valid_name(s: str) -> bool:
        s = s.strip()
        if not s or s in _EXCLUDE_NAMES or any(s.endswith(suf) for suf in ("先生", "女士", "小姐", "同志")):
            return False
        return bool(re.fullmatch(_ZH_NAME_RE, s) or re.fullmatch(_EN_NAME_RE, s))

    lines = text.splitlines()

    m = re.search(r"查看详情\s*\n\s*([\u4e00-\u9fff]{2,5})\s*\n\s*点击此处联系候选人", text)
    if m:
        return m.group(1)

    # 新增: 支持「求职人：金婉婷」这种独立 KV 行（e.g. 新页导出）
    # EN: New: support standalone KV lines like "求职人：<name>" (job seeker: ...) (e.g. Xinye exports)
    # JA: 追加：「求职人：<氏名>」（求職者：…）のような独立した KV 行に対応する（例：新页のエクスポート）
    m_applicant = re.search(r"求职人\s*[：:]\s*([^\s，,。\n\r\t|│/]+)", text)
    if m_applicant:
        cand_app = m_applicant.group(1).strip()
        # 去掉末尾标点/括号
        # EN: Remove trailing punctuation/brackets
        # JA: 末尾の句読点・括弧を除く
        cand_app = re.sub(r"[：:，,。.！!？?；;、・·•・\-—_|│/）)〕］>》]+$", "", cand_app).strip()
        if _valid_name(cand_app):
            return cand_app

    m = re.search(r"(?:扫码联系TA|点击此处联系候选人)\n?(.+?)\n?应聘职位", text, re.S)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"位图@2x|icon@2x|点击此处联系候选人|扫码联系TA|用「智联招聘App」扫码|或点击此处登录查看详情|点击此处登录|查看详情|或", "", cand)
        cand = cand.strip()
        if cand and re.fullmatch(_ZH_NAME_RE, cand):
            return cand
        m_zh = re.search(r"([\u4e00-\u9fff]{2,5})", cand)
        if m_zh:
            return m_zh.group(1)

    m_file = re.match(r"智联(?:简历|招聘)_(.+?)_(?:\d+岁|中文|英文)", filename)
    if m_file:
        fname = re.sub(r"的简历$", "", m_file.group(1).strip()).strip()
        if fname and _valid_name(fname) and fname not in _EXCLUDE_NAMES:
            return fname

    m = re.search(r"简历名称[：:]\s*\n([^\n]+)", text)
    if m:
        cand = re.sub(r"的简历$", "", m.group(1).strip()).strip()
        if (cand and re.fullmatch(_ZH_NAME_RE, cand) and cand not in _EXCLUDE_NAMES
                and not any(cand.endswith(suf) for suf in _JOB_TITLE_SUFFIXES)):
            return cand

    for i, line in enumerate(lines):
        if re.search(r"(?:手机|Mobile|Tel)[：:]", line, re.I) and i > 0:
            prev = lines[i - 1].strip()
            if _valid_name(prev):
                return prev

    for line in lines:
        m_glued = re.search(r"^([\u4e00-\u9fff]{2,5})\s*手机[：:]", line)
        if m_glued:
            cand = m_glued.group(1)
            if cand not in _EXCLUDE_NAMES:
                return cand

    _SECTION_HEADERS = {"自我评价", "工作经历", "教育经历", "项目经历", "语言能力",
                        "专业技能", "培训经历", "所获证书", "证书", "求职意向",
                        "在校学习情况", "在校实践经历", "活动描述", "特长职业目标",
                        "特长", "Self-Assessment", "Self-Evaluation", "Work Experience",
                        "Education", "Project", "Language", "Skills", "Training",
                        "Certificates", "Awards"}
    for line in lines[:40]:
        line = line.strip()
        if line in _SECTION_HEADERS:
            break
        if _valid_name(line):
            return line

    m = re.match(r"智联(?:简历|招聘)_(.+?)_(?:\d+岁|中文|英文)", filename)
    if m:
        name = m.group(1).strip()
        if name and name not in _EXCLUDE_NAMES:
            return name

    return ""


def _extract_newpage_name(text: str, filename: str) -> str:
    m = re.search(r"(?:姓|氏)\s*名\s*[:：]\s*([^\s,，。、\n]{2,10})", text)
    if m:
        return m.group(1).strip()
    m_en = re.search(
        r"(?:Personal\s+Information\s*|^\s*)Name\s*[:：]?\s*([A-Za-z]+(?:\s+[A-Za-z]+){1,2})(?=\s+(?:Gender|Male|Female|Date|Marital|Academic|Place|Location|In\s+Position|\n|$))",
        text, re.I,
    )
    if m_en:
        cand_name = m_en.group(1).strip()
        if cand_name.lower() not in ("shool name", "majoracademic", "qualification", "time period"):
            return cand_name
    stem = re.sub(r"__[a-f0-9]+\.html$", "", filename, flags=re.I)
    last_dash = stem.rfind("-")
    if last_dash >= 0:
        raw_name = stem[last_dash + 1:].strip()
        return raw_name.replace("_", " ")
    last_underscore = stem.rfind("_")
    if last_underscore >= 0:
        return stem[last_underscore + 1:].strip()
    return stem


def _extract_liepin_name(text: str, filename: str, parsed_name: str) -> str:
    _EXCLUDE = {"智联招聘", "前程无忧", "猎聘", "简历", "ID", "求职意向", "网简", "无关联", "未知", "未公开", "个人简历", "中文简历"}
    _JOB_TITLE_SUFFIXES = ("工程师", "经理", "主管", "总监", "专员", "助理", "代表", "老师", "教师", "设计师", "分析师", "顾问", "科长", "组长", "文员", "客服", "采购", "销售", "运营")
    m_resume_no = re.search(r"简历编号\s*[:：]\s*\n\s*([^\s\n:：|│]{2,8})", text)
    if m_resume_no:
        cand = m_resume_no.group(1).strip()
        if cand not in _EXCLUDE and not any(cand.endswith(suf) for suf in _JOB_TITLE_SUFFIXES):
            return cand
    m_file = re.search(r"^(?:智联|猎聘|前程无忧)?(?:简历|招聘|网简历)?_?([^\s\-_0-9]{2,8})(?:-\d+岁|_|\s|\Z)", filename)
    if m_file:
        cand = re.sub(r"的简历$", "", m_file.group(1).strip()).strip()
        if cand and cand not in _EXCLUDE and not any(cand.endswith(suf) for suf in _JOB_TITLE_SUFFIXES):
            return cand
    clean_p = re.sub(r"\s+", "", parsed_name or "").strip()
    if clean_p and 2 <= len(clean_p) <= 8 and re.search(r"^[\u4e00-\u9fff]{2,8}$", clean_p):
        if clean_p not in _EXCLUDE:
            return clean_p
    return "未知"


_SURNAMES_SET = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘黨翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公曲涂闫兰原吾寻付佘尧宗程荆柴练匡展操咸敬尚乐储商黑苟牟尚由封买柴能过阳景连全尚权干解农阴修桂房能操肖迟邝郄锁达楼母朋南宇宛彩張衛黃崇劉陳楊趙錢孫吳鄭馮蔣韓許呂華謝鄒蘇賈羅鍾盧鄧葉顧萬龔譚蕭閻")
_SURNAMES_SET.update(set("朴佟刑栄榮魯呉關關"))

def _valid_person_name_strict(s: str) -> bool:
    s = re.sub(r"[\s\u3000\xa0]+", "", s or "").strip()
    s = re.sub(r"^(?:I|V|A)\s*", "", s)
    s = re.sub(r"(?:女士|先生|小姐|同志)$", "", s)
    s = re.sub(r"(?:性别|性別|党员|党員|原籍|汉族|满族|回族).*$", "", s)
    if not s or len(s) < 2 or len(s) > 4:
        return False
    if any(c in s for c in ("@", ".com", "com", "163", "126", "139", "qq", "（", "(", "）", ")", "。", "、", ".", ",", "；", ";", "：", ":", "/")):
        return False
    if re.search(r"\d", s):
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]{1,4}", s):
        return False
    if s[0] not in _SURNAMES_SET:
        return False
    INVALID_TOKENS = (
        "工程师", "经理", "主管", "总监", "专员", "助理", "代表", "老师", "教师", "设计师",
        "分析师", "顾问", "科长", "组长", "文员", "客服", "采购", "销售", "运营", "担当",
        "研究员", "会计", "出纳", "研发", "技术", "日语", "英语", "德语", "法语", "熟练",
        "事务所", "公司", "医院", "学校", "大学", "学院", "项目", "简历", "网简", "求职",
        "个人", "中文", "英文", "日文", "日语", "日本語", "应聘", "能力", "语言", "信息", "性",
        "上海", "北京", "广州", "深圳", "杭州", "南京", "武汉", "成都", "苏州", "海关",
        "发票", "介绍", "履历", "表格", "申请", "部门", "产品", "商", "品牌", "零食", "宠物",
        "导出", "下载", "点击", "一级", "二级", "三级", "四级", "六级", "性别", "性別", "党员", "原籍",
        "工作内容包括", "工作内容及自我鉴定", "工作内容", "自我鉴定", "公司全称", "沈阳药物代谢研讨会",
        "研讨会", "大会", "论坛", "会议", "医疗器械市场推广", "市场推广", "医疗器械", "PowerPoint",
        "本市中心医院", "中心医院", "不显示职位月薪范围", "职位月薪", "月薪范围", "部门负责人", "负责人", "包含", "全称",
        "163", "126", "139", "qq", "com", "1年", "2年", "1个月", "一个月", "至今", "2019", "统括",
        "业余", "旅游", "网球", "临床", "分组", "发票", "导出", "推荐", "标签", "介绍", "集团"
    )
    if any(k in s for k in INVALID_TOKENS):
        return False
    return True

def _clean_title_suffix(s: str) -> str:
    s = re.sub(r"[\s\u3000\xa0]+", "", s or "").strip()
    s = re.sub(r"\d+$", "", s)  # 去掉末尾版本数字如 彭成2 -> 彭成
    # EN: Remove trailing version digits, e.g. <name>2 -> <name>
    # JA: 末尾のバージョン番号を除く。例：<氏名>2 -> <氏名>
    s = re.sub(r"^(?:I|V|A)\s*", "", s)
    s = re.sub(r"(?:性别|性別|党员|党員|原籍|汉族).*$", "", s)
    return re.sub(r"(?:女士|先生|小姐|同志)$", "", s)

def _extract_name_from_filename_strict(filename: str) -> str:
    if not filename:
        return ""
    stem = re.sub(r"__[a-f0-9]{8,}\.html?$", "", filename, flags=re.I)
    stem = re.sub(r"\.html?$", "", stem, flags=re.I)
    stem = re.sub(r"(?:中文|英文|日文|日语|日本語|智联简历|前程无忧|个人简历|简历2022_中文|简历2022|中文|的简历|求职申请表|求职|简历)[_\-\s]*", "", stem)
    # 去除大学名称前缀（如 上海交通大学彭成 -> 彭成）
    # EN: Remove a university-name prefix (e.g. 上海交通大学<name> -> <name>)
    # JA: 大学名の接頭辞を除く（例：上海交通大学<氏名> -> <氏名>）
    stem = re.sub(r"^(?:[\u4e00-\u9fff]{2,10}(?:大学|学院|学校|中学))", "", stem)
    
    # 优先融合中文汉字之间的下划线/空格（如 柳_学明 -> 柳学明, 郑_晶捷 -> 郑晶捷）
    # EN: First fuse underscores/spaces between Chinese characters (e.g. <surname>_<given name> -> <surname><given name>)
    # JA: まず漢字の間のアンダースコア・空白を結合する（例：<姓>_<名> -> <姓><名>）
    stem_merged = re.sub(r"(?<=[\u4e00-\u9fff])[\s_]+(?=[\u4e00-\u9fff])", "", stem)
    clean_merged = _clean_title_suffix(stem_merged)
    if _valid_person_name_strict(clean_merged):
        return clean_merged

    if "-" in stem:
        first_part = _clean_title_suffix(stem.split("-")[0])
        if _valid_person_name_strict(first_part):
            return first_part

    parts = re.split(r"[_\-\s]+", stem)
    for p in parts:
        p_clean = _clean_title_suffix(p)
        if _valid_person_name_strict(p_clean):
            return p_clean

    clean_all = _clean_title_suffix(stem)
    if _valid_person_name_strict(clean_all):
        return clean_all

    return ""


def extract_candidate_name(text: str, filename: str, parsed_name: str, html_text: str = "") -> str:
    """姓名提取级联：HTML文件名权威提取 -> 正文表头/ID粘连 -> 正文键值对 -> 平台提取器 -> HTML元数据。

    EN: Name extraction cascade: authoritative extraction from the HTML file name -> body header / stuck-on ID -> body key-value pairs -> platform extractors -> HTML metadata.

    JA: 氏名抽出の段階的な流れ：HTML のファイル名からの確実な抽出 -> 本文の見出し・くっついた ID -> 本文のキーと値のペア -> プラットフォームの抽出器 -> HTML のメタデータ。
    """
    text = re.sub(r"INCLUDEPICTURE\s*\"[^\"]*\"\s*\\\*\s*MERGEFORMATINET", "", text or "")
    text = re.sub(r"SHAPE\s*\\\*\s*MERGEFORMAT", "", text or "")
    text = re.sub(r"[\x00-\x1f]+", " ", text)
    
    _EXCLUDE = {"智联招聘", "前程无忧", "猎聘", "简历", "ID", "求职意向", "网简", "无关联", "未知", "未公开", "个人简历", "中文简历"}
    _INVALID_WORDS = {
        "English", "Excel", "Word", "RESUME", "Resume", "SAP", "CAD", "PDF", "sheng",
        "上海", "北京", "广州", "深圳", "杭州", "南京", "武汉", "成都", "苏州",
        "目前正在找工作", "观望有好机会会考虑", "寻找工作", "一次设计工程师上海", "设计工程师",
        "软件工程师", "高级工程师", "项目经理", "技术支持", "技术总监", "销售经理", "总经理"
    }
    _JOB_TITLE_SUFFIXES = ("工程师", "经理", "主管", "总监", "专员", "助理", "代表", "老师", "教师", "设计师", "分析师", "顾问", "科长", "组长", "文员", "客服", "采购", "销售", "运营")
    _BLOCK_HEADER = {
        "自我评价", "工作经历", "教育经历", "项目经历", "语言能力", "专业技能", "培训经历",
        "所获证书", "求职意向", "在校学习情况", "在校实践经历", "活动描述", "特长职业目标",
        "特长", "个人信息", "个人简历", "下载简历", "简历名称", "最近工作", "教育背景",
        "基本资料", "基本信息", "工作职责", "工作业绩", "求职申请表",
        "目前正在找工作", "我目前不想换工作", "正在找工作", "观望有好机会会考虑",
        "找工作", "暂不换工作", "工作经验", "在职", "离职", "应届毕业生",
    }
    _MOBILE_RE = r"1[3-9]\d{9}"

    def _prep(s: str) -> str:
        s_clean = re.sub(r"[\s\u3000\xa0]+", "", (s or "").strip())
        s_clean = re.sub(r"^(?:I|V|A)\s*", "", s_clean)
        s_clean = re.sub(r"(?:性别|性別|党员|党員|原籍|汉族).*$", "", s_clean)
        s_clean = re.sub(r"^[A-Za-z]+(?=[\u4e00-\u9fff]{2,4}$)", "", s_clean)
        return s_clean

    def _valid(s: str, strict: bool = True) -> bool:
        s_raw = _prep(s)
        if not s_raw:
            return False
        s_clean = _clean_title_suffix(s_raw)
        return _valid_person_name_strict(s_clean)

    # 生成阶段已经确认并标注的语义姓名节点优先级最高。日文简历中常见的繁体、
    # 异体或少见姓氏（如 劉、呉、魯、栄、佟、朴）不应再被中文百家姓表否决，
    # 否则解析器会退化到把“修士、出身地、父目录姓名”等字段误当候选人姓名。
    # EN: Semantic name nodes already confirmed and tagged at generation time have the highest priority. Traditional, variant or
    #     rare surnames common in Japanese résumés (e.g. 劉、呉、魯、栄、佟、朴) should no longer be vetoed by the Chinese surname table,
    #     otherwise the parser degrades into taking fields like "修士、出身地、parent-directory name" as the candidate's name.
    # JA: 生成段階ですでに確定しタグ付けした意味的な氏名ノードを最優先する。日本の履歴書によくある繁体字・
    #     異体字や珍しい姓（例：劉、呉、魯、栄、佟、朴）を中国語の百家姓の表で否決してはならない。
    #     さもないとパーサーは「修士、出身地、親ディレクトリの氏名」などのフィールドを候補者名と誤認する状態に退化する。
    if html_text:
        try:
            semantic_soup = BeautifulSoup(html_text, "html.parser")
            for semantic_node in semantic_soup.select('[data-field="full_name"]'):
                semantic_value = semantic_node.get_text(" ", strip=True)
                semantic_value = re.sub(r"[（(].*?[）)]", "", semantic_value)
                semantic_value = re.sub(r"\s+専(?:門)?\s*$", "", semantic_value)
                semantic_value = re.split(
                    r"性\s*[別别]|民\s*族|年\s*[齢龄]|生年月|出身|現住所|户籍|戸籍",
                    semantic_value,
                    maxsplit=1,
                )[0]
                leading_name = re.match(
                    r"^\s*([\u3400-\u9fff](?:[\s\u3000]*[\u3400-\u9fff]){1,3})(?=\s|[\u3040-\u30ff]|$)",
                    semantic_value,
                )
                candidate = _prep(leading_name.group(1) if leading_name else semantic_value)
                if not re.fullmatch(r"[\u3400-\u9fff]{2,4}", candidate or ""):
                    continue
                if any(token in candidate for token in (
                    "姓名", "氏名", "性别", "性別", "年龄", "年齢", "修士", "博士",
                    "学士", "出身", "户籍", "住所", "時間", "履歴", "简历", "個人",
                    "情報", "関係", "关系", "会社", "公司", "全称", "全稱", "学校", "大学", "学院", "担当", "職位", "履歴",
                )):
                    continue
                return candidate
        except Exception:
            pass

    m_japanese_kanji_name = re.search(
        r"氏\s*名\s*[（(]\s*漢\s*字\s*[）)]?\s*[:：]?\s*([\u3400-\u9fff](?:[\s\u3000]*[\u3400-\u9fff]){1,3})",
        text[:1800],
    )
    if m_japanese_kanji_name:
        return re.sub(r"[\s\u3000]+", "", m_japanese_kanji_name.group(1))

    m_spaced_name = re.search(
        r"(?:姓\s*名|名\s*前)\s*[:：]?\s*([\u3400-\u9fff])\s+([\u3400-\u9fff]{1,2})(?=\s+(?:男|女|性\s*[別别]|生年月日|年齢|年龄))",
        text[:1800],
    )
    if m_spaced_name:
        return m_spaced_name.group(1) + m_spaced_name.group(2)

    m_platform_note_name = re.search(
        r"简历信息\s*(?:操作记录)?\s*([\u3400-\u9fff]{2,4})(?=\s+(?:在外面|不方便|不想去|电\s*话))",
        text[:2400],
    )
    if m_platform_note_name:
        return m_platform_note_name.group(1)

    m_kv_top = re.search(r"(?:姓\s*名|名\s*前|中\s*文\s*名|求\s*职\s*人|申\s*请\s*人|应\s*聘\s*人)\s*[:：]\s*([\u4e00-\u9fff]{2,4})", text[:1500])
    if m_kv_top:
        cand_kv = re.sub(r"[\s\u3000\xa0]+", "", m_kv_top.group(1)).strip()
        if _valid(cand_kv):
            return cand_kv

    fn_name = _extract_name_from_filename_strict(filename)
    if fn_name and len(fn_name) >= 2:
        return fn_name
    single_surname_fallback = fn_name if (fn_name and len(fn_name) == 1) else ""

    if text:
        # ====== 0.1 特殊 ID 粘连提取 (例如: ID:100000001 张 三 13800000011 或 李四ID:100000002) ======
        # EN: ====== 0.1 Extraction of special stuck-on IDs (e.g.: ID:100000001 张 三 13800000011 or 李四ID:100000002) ======
        # JA: ====== 0.1 くっついた特殊な ID の抽出（例：ID:100000001 张 三 13800000011 や 李四ID:100000002）======
        m_id1 = re.search(r"ID[:：]?\s*\d+\s*([\u4e00-\u9fff]\s*[\u4e00-\u9fff]{1,3})\s*(?:1[3-9]\d{9}|ID:|\s|下载|目前|观望|剩余|女|男)", text)
        if m_id1:
            cand = _prep(m_id1.group(1))
            if _valid(cand):
                return cand

        m_id2 = re.search(r"([\u4e00-\u9fff]\s*[\u4e00-\u9fff]{1,3})\s*ID[:：]?\s*\d+", text)
        if m_id2:
            cand = _prep(m_id2.group(1))
            if _valid(cand):
                return cand

        # ====== 0.2 表格/键值对格式（含跨空格姓名如「姓    名： 南 亮」） ======
        # EN: ====== 0.2 Table/key-value format (including names spread over spaces, like "姓    名： <surname> <given name>") ======
        # JA: ====== 0.2 表・キーと値の形式（「姓    名： <姓> <名>」のように空白をまたぐ氏名を含む）======
        tbl_pat = re.compile(
            r"姓\s*名\s*[:：]?\s*([\u4e00-\u9fffA-Za-z·]\s*[\u4e00-\u9fffA-Za-z·]{1,7})\s*(?:[☆\s◇◆★\u3000\xa0]|性\s*别|$)"
        )
        mt = tbl_pat.search(text)
        if mt:
            c_tbl = _prep(mt.group(1))
            if _valid(c_tbl):
                return c_tbl

        label_pat = re.compile(
            r"(?:^|\n)\s*(?:姓\s*名|氏\s*名|名\s*前|中\s*文\s*姓\s*名)\s*[:：]?\s*(?:\n\s*)?([^\s,，。、\n\r|│<]{2,16})\s*(?:\n|$)",
        )
        m0 = label_pat.search(text)
        if m0:
            cand0 = _prep(m0.group(1))
            if _valid(cand0):
                return cand0

        m_glue = re.search(r"姓\s*名\s*([\u4e00-\u9fffA-Za-z·]{2,8})\s*(?:性\s*别|出生|身\s*高|民\s*族|$)", text)
        if m_glue:
            cand_g = _prep(m_glue.group(1))
            if _valid(cand_g):
                return cand_g

        lines_all = [l.strip() for l in (text or "").splitlines() if l.strip()][:30]
        for i, l in enumerate(lines_all):
            stripped = re.sub(r"\s+", "", l)
            if stripped in ("姓名", "氏名", "名前", "中文姓名"):
                if i + 1 < len(lines_all):
                    nxt = _prep(lines_all[i + 1])
                    if _valid(nxt):
                        return nxt
            else:
                mm = re.match(r"^(?:姓\s*名|氏\s*名|名\s*前|中\s*文\s*姓\s*名)\s*[:：]?\s*(.+)$", l)
                if mm:
                    cand = _prep(mm.group(1))
                    if _valid(cand):
                        return cand

    # ====== 1. 从 HTML <title> / <meta name="author"> / <h1> 提取 ======
    # EN: ====== 1. Extract from HTML <title> / <meta name="author"> / <h1> ======
    # JA: ====== 1. HTML の <title> / <meta name="author"> / <h1> から抽出する ======
    html_metas: list[str] = []
    if html_text:
        try:
            soup_mini = BeautifulSoup(html_text, "html.parser")
            t = soup_mini.title
            if t and t.get_text(strip=True):
                html_metas.append(t.get_text(strip=True))
            for meta in soup_mini.find_all("meta"):
                n = (meta.get("name") or "").lower()
                c = (meta.get("content") or "").strip()
                if n in ("author", "applicant", "candidate", "owner") and c:
                    html_metas.append(c)
            prop_meta = soup_mini.find("meta", attrs={"property": "og:title"})
            if prop_meta:
                prop = prop_meta.get("content") or None
                if prop:
                    html_metas.append(prop)
            for h in soup_mini.find_all(["h1", "h2", "h3"])[:5]:
                th = h.get_text(strip=True)
                if th:
                    html_metas.append(th)
        except Exception:
            html_metas = []
    for meta in html_metas:
        cand = re.sub(r"[_\-]{2,}.*$", "", meta).strip()
        cand = re.sub(r"的简历$|个人简历$|简历$|求职申请表$", "", cand).strip()
        mm = re.match(r"^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z ]{1,8})[\s\-_]+(?:" + _MOBILE_RE + r")", cand)
        if mm:
            cand = mm.group(1)
        cand_c = _prep(cand)
        if _valid(cand_c):
            return cand_c
        zh = re.search(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z·]{1,8}", cand)
        if zh and _valid(zh.group(0)):
            return zh.group(0)

    # ====== 2. 正文顶部提取 ======
    # EN: ====== 2. Extract from the top of the body ======
    # JA: ====== 2. 本文の冒頭から抽出する ======
    top_lines = [l.strip() for l in (text or "").splitlines() if l.strip()][:15]
    for l in top_lines:
        mm = re.match(r"^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z ]{1,8})[\s\xa0]+(?:1[3-9]\d{9}|手机)", l)
        if mm:
            cand = _prep(mm.group(1))
            if _valid(cand):
                return cand
        mm = re.match(r"^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z ]{1,8})(?=男|女|[\(（]\s*\d{4}年\d{1,2}月)", l)
        if mm:
            cand_m = _clean_title_suffix(_prep(mm.group(1)))
            if _valid(cand_m):
                return cand_m

        mm2 = re.search(r"(?:ID[:：]?\d{6,}|[A-F0-9]{8,})([\u4e00-\u9fff][\u4e00-\u9fff ]{1,6}[\u4e00-\u9fff])", l)
        if mm2:
            cand = _prep(mm2.group(1))
            if _valid(cand):
                return cand

        mm3 = re.search(r"(?:ID[:：]?\d{0,10}|^\d{0,10})[\s\xa0]*([\u4e00-\u9fff]{2,6})(?=1[3-9]\d{9})", l)
        if mm3:
            cand3 = _prep(mm3.group(1))
            if _valid(cand3):
                return cand3

        pure_cand = _prep(l)
        if _valid(pure_cand):
            return pure_cand

    # ====== 3. 平台策略与兜底 ======
    # EN: ====== 3. Platform strategies and fallback ======
    # JA: ====== 3. プラットフォームごとの方針と最終手段 ======
    m_app = re.search(r"查看详情\s*\n\s*([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z ]{1,8})\s*\n\s*点击此处联系候选人", text)
    if m_app and _valid(_prep(m_app.group(1))):
        return _prep(m_app.group(1))

    zhilian = _extract_zhilian_name(text, filename)
    if zhilian and _valid(zhilian):
        return _prep(zhilian)

    newpage = _extract_newpage_name(text, filename)
    if newpage and _valid(newpage):
        return _prep(newpage)

    job51 = _extract_51job_name(text, filename, parsed_name)
    if job51 and _valid(job51):
        return _prep(job51)

    liepin = _extract_liepin_name(text, filename, parsed_name)
    if liepin and _valid(liepin):
        return _prep(liepin)

    m_name = re.search(r"(?:姓\s*名|氏\s*名|名\s*前|中\s*文\s*姓\s*名)\s*[:：]\s*([^\s,，。、\n\r|│<]{2,16})", text)
    if m_name:
        cand = _prep(m_name.group(1))
        if _valid(cand):
            return cand

    # ====== 4. HTML 文件名降级提炼 (最权威兜底) ======
    # EN: ====== 4. Fallback refinement from the HTML file name (the most authoritative fallback) ======
    # JA: ====== 4. HTML のファイル名からの代替の抽出（最も信頼できる最終手段）======
    stem = re.sub(r"__[a-f0-9]{8,}\.html?$", "", filename, flags=re.I)
    stem = re.sub(r"\.html?$", "", stem, flags=re.I)
    stem = re.sub(r"^(?:中文|英文|智联简历|前程无忧|个人简历|简历)[_\-\s]*", "", stem)

    # 依次分割下划线/短横线
    # EN: Split on underscores/hyphens in turn
    # JA: アンダースコア・ハイフンで順に分割する
    parts = re.split(r"[_\-\s]+", stem)
    for p in parts:
        p_clean = _prep(p)
        # —— 新增：拒绝 职位/地域/文件名垃圾 词（宁严勿松，避免「出纳/应收会计/上海...」被当名字）——
        # EN: —— New: reject position/region/file-name junk words (better too strict than too loose, so "出纳/应收会计/上海..." (cashier/accounts receivable/Shanghai) are not taken as names) ——
        # JA: —— 追加：職位・地域・ファイル名のゴミの語を拒否する（緩すぎるより厳しすぎる方がよい。「出纳／应收会计／上海...」（出納・売掛金会計・上海）を氏名にしないため）——
        if p_clean and any(bad in p_clean for bad in (
            "工程师", "经理", "主管", "总监", "专员", "助理", "代表", "老师", "教师",
            "设计师", "分析师", "顾问", "科长", "组长", "文员", "客服", "采购", "销售",
            "运营", "出纳", "会计", "财务", "人事", "行政", "前台", "秘书", "翻译",
            "日语", "英语", "韩语", "品质", "生产", "技术", "开发", "测试", "产品",
            "项目", "营业", "市场", "物流", "简历",
            "上海", "北京", "广州", "深圳", "杭州", "南京", "武汉", "成都", "苏州",
        )):
            continue
        if _valid(p_clean):
            return p_clean

    clean_p = _prep(parsed_name or "")
    if _valid(clean_p):
        return clean_p

    if single_surname_fallback:
        return single_surname_fallback

    # ====== ★第9级兜底：全文扫描 2-4 字纯中文行（避免简历真的有姓名但就是没放在 KV 标签里）======
    #    排除条件：
    #    - 章节标题关键词（工作经历/教育经历/自我评价...）
    #    - 公司/学校/机构后缀（有限公司/大学/学院/学校/医院/分行/事务所/营业部）
    #    - 职位后缀（工程师/经理/专员/助理/主管/代表/顾问）
    #    - 纯数字/日期/薪资
    #    - 常见短语（剩余下载/推荐意见/保存到我的电脑/下载简历/查看更多）
    # EN: ====== ★Level 9 fallback: scan the full text for pure Chinese lines of 2-4 characters (in case the résumé really has a name but not under a KV label) ======
    #        Exclusions:
    #        - section heading keywords (工作经历/教育经历/自我评价...: work/education/self-assessment)
    #        - company/school/institution suffixes (有限公司/大学/学院/学校/医院/分行/事务所/营业部)
    #        - position suffixes (工程师/经理/专员/助理/主管/代表/顾问)
    #        - pure digits/dates/salaries
    #        - common phrases (剩余下载/推荐意见/保存到我的电脑/下载简历/查看更多: remaining downloads/recommendation/save to my computer/download résumé/see more)
    # JA: ====== ★第 9 段階の最終手段：全文から 2〜4 文字の漢字だけの行をスキャンする（履歴書に氏名はあるが KV ラベルの下にない場合に備える）======
    #        除外条件：
    #        - 章見出しのキーワード（工作经历／教育经历／自我评价...：職歴・学歴・自己評価）
    #        - 会社・学校・機関の接尾辞（有限公司／大学／学院／学校／医院／分行／事务所／营业部）
    #        - 職位の接尾辞（工程师／经理／专员／助理／主管／代表／顾问）
    #        - 数字・日付・給与だけのもの
    #        - よくある語句（剩余下载／推荐意见／保存到我的电脑／下载简历／查看更多：残りダウンロード数・推薦意見・PC に保存・履歴書をダウンロード・もっと見る）
    _LASTRESORT_BLOCK = (
        # 章节标题（全量覆盖，避免误取）
        # EN: Section headings (full coverage, to avoid mistaken picks)
        # JA: 章見出し（誤取得を避けるため全量を網羅）
        "个人信息", "基本信息", "基本资料", "个人简历", "中文简历", "简历名称",
        "教育经历", "教育背景", "教育状况", "毕业院校", "学校", "最高学历",
        "工作经历", "工作经验", "工作履历", "社会实践", "工作情况", "职业经历", "最近工作",
        "求职意向", "求职意向及工作经历", "求职", "应聘职位", "希望职位", "意向职位", "推荐职位",
        "自我评价", "自我描述", "自我鉴定", "个人评价",
        "培训经历", "培训", "所获证书", "奖励", "获奖", "奖项", "奖项荣誉", "荣誉",
        "项目经验", "项目经历", "项目",
        "语言能力", "语言水平", "外语能力",
        "专业技能", "专业能力", "技能", "其他技能", "计算机能力", "IT技能",
        "在校情况", "校园经历", "校园活动", "学生会", "社团活动",
        "联系方式", "联系电话", "家庭地址", "住址", "邮箱",
        "下载简历", "保存到我的电脑", "收藏简历", "举报", "删除", "打印", "求职信", "查看更多", "简历动态",
        "简历信息", "操作记录", "通信记录", "剩余下载数", "下载次数", "简历下载", "进入HOUR",
        "更新时间", "更新日期", "发布时间",
        "推荐意见", "推荐理由", "基本要求", "其他要求", "备注", "说明",
        "求职中", "在职", "离职", "应届毕业生", "在校学生",
        "身份证号", "户口", "籍贯", "国籍", "民族", "政治面貌", "婚姻状况", "健康状况",
        "身高", "体重", "年龄", "出生年月", "出生日期",
        "现居住地", "居住地址", "通讯地址", "邮政编码",
        "公司性质", "公司规模", "所属行业", "公司行业", "汇报对象", "下属人数",
        "工作地点", "期望薪资", "期望月薪", "期望年薪", "期望职位", "期望行业", "到岗时间", "目前收入",
    )
    _LASTRESORT_SUFFIX_BAD = (
        # 公司/组织后缀：姓名不可能以这些结尾
        # EN: Company/organisation suffixes: a name can never end with these
        # JA: 会社・組織の接尾辞：氏名がこれらで終わることはあり得ない
        "有限公司", "股份有限公司", "有限责任公司", "集团", "公司", "工厂", "营业部", "支店", "支社",
        "事务所", "事務所", "医院", "诊所", "酒店", "超市", "银行", "分行", "支行",
        "大学", "学院", "学校", "小学", "中学", "高中", "中专", "初中",
        "工程师", "经理", "主管", "总监", "专员", "助理", "代表", "顾问", "老师", "教师", "设计师", "分析师",
        "组长", "科长", "部长", "厂长", "店长", "院长", "校长", "所长", "主任",
        "销售", "运营", "客服", "采购", "出纳", "会计", "财务", "人事", "行政", "前台", "秘书", "翻译",
        "日语", "英语", "韩语",
    )
    _LASTRESORT_PREFIX_BAD = ("ID:", "ID：", "编号", "No.", "NO:", "工号", "职位：", "岗位：", "公司：", "学校：",
                               "专业：", "学历：", "年龄：", "性别：", "电话：", "邮箱：", "地址：", "日期：")
    for ln in [x.strip() for x in (text or "").splitlines() if x.strip()][:120]:
        cand = _prep(ln)
        if not cand:
            continue
        # —— V2新增：先剥掉「姓名:」「姓 名：」这种标签前缀再判定（很多简历是 "姓名：XXX" 的一行，剥标签后值是 XXX 单条2-4字）
        # EN: —— New in V2: first strip label prefixes like "姓名:" "姓 名：" (name:) before judging (many résumés have a line "姓名：XXX"; after stripping the label the value XXX is a single 2-4 character item)
        # JA: —— V2 の追加：判定の前にまず「姓名:」「姓 名：」（氏名：）などのラベルの接頭辞を除く（多くの履歴書には「姓名：XXX」の行があり、ラベルを除くと値 XXX は 2〜4 文字の単独の項目になる）
        _label_strip_re = re.compile(r"^(?:姓\s*名|求\s*职\s*人|姓|Candidate|Name)\s*[:：]\s*", re.IGNORECASE)
        cand_stripped = _label_strip_re.sub("", cand, count=1).strip()
        if cand_stripped and cand_stripped != cand:
            # 剥完标签后的值优先判定（通常"姓名：张三"这行里值就是张三，100%可信）
            # EN: Judge the value after stripping the label first (in a line "姓名：张三" the value is 张三, 100% reliable)
            # JA: ラベルを除いた後の値を優先して判定する（「姓名：张三」の行なら値は 张三 で、100% 信頼できる）
            if 2 <= len(cand_stripped) <= 5 and re.fullmatch(r"[\u4e00-\u9fff·]{2,5}", cand_stripped):
                if cand_stripped not in _BLOCK_HEADER and cand_stripped not in _LASTRESORT_BLOCK \
                    and not any(cand_stripped.endswith(suf) for suf in _LASTRESORT_SUFFIX_BAD) \
                    and not any(tok == cand_stripped for tok in _INVALID_WORDS) \
                    and cand_stripped not in _EXCLUDE \
                    and _valid(cand_stripped):
                    return cand_stripped
            # 否则继续用原 cand 判定
            # EN: Otherwise continue judging with the original cand
            # JA: そうでなければ元の cand で判定を続ける
        # 长度 2-4 纯中文（姓1字+名1-3字 = 2-4字）
        # EN: Length 2-4, pure Chinese (1-character surname + 1-3-character given name = 2-4 characters)
        # JA: 長さ 2〜4 の漢字のみ（姓 1 文字 + 名 1〜3 文字 = 2〜4 文字）
        if not re.fullmatch(r"[\u4e00-\u9fff·]{2,5}", cand):
            continue
        # 过滤：章节标题关键词（命中任意则跳过，避免"教育背景"/"工作经历"这种2-4字纯中文被当姓名）
        # EN: Filter: section heading keywords (skip on any hit, so 2-4 character pure Chinese like "教育背景" (education background) / "工作经历" (work history) is not taken as a name)
        # JA: 除外：章見出しのキーワード（どれかにヒットしたらスキップ。「教育背景」「工作经历」のような 2〜4 文字の漢字を氏名にしないため）
        if cand in _BLOCK_HEADER or cand in _LASTRESORT_BLOCK:
            continue
        if any(kw in cand for kw in ("求职", "简历", "更新", "下载", "教育", "工作", "项目", "培训", "技能", "证书",
                                       "自我", "联系", "地址", "电话", "邮箱", "期望", "意向", "评价", "获奖", "荣誉",
                                       "专业", "学校", "公司", "职位", "薪资", "月薪", "年薪", "岗位", "部门",
                                       "下载数", "剩余", "动态", "操作", "通信", "推荐", "职位", "公司", "学校")):
            continue
        # 过滤：结尾是公司/职位后缀
        # EN: Filter: ends with a company/position suffix
        # JA: 除外：会社・職位の接尾辞で終わる
        if any(cand.endswith(suf) for suf in _LASTRESORT_SUFFIX_BAD):
            continue
        # 过滤：开头是标签前缀（ID:/编号:等）
        # EN: Filter: starts with a label prefix (ID:/编号: (number:) etc.)
        # JA: 除外：ラベルの接頭辞（ID:／编号:（番号:）など）で始まる
        if any(cand.startswith(pr) for pr in _LASTRESORT_PREFIX_BAD):
            continue
        # 过滤：包含 _INVALID_WORDS 里的英文缩写/CAD/PDF/SAP 等
        # EN: Filter: contains English abbreviations from _INVALID_WORDS / CAD / PDF / SAP etc.
        # JA: 除外：_INVALID_WORDS の英字略語や CAD／PDF／SAP などを含む
        if any(tok == cand for tok in _INVALID_WORDS):
            continue
        # 过滤：_EXCLUDE
        # EN: Filter: _EXCLUDE
        # JA: 除外：_EXCLUDE
        if cand in _EXCLUDE:
            continue
        if _valid(cand):
            return cand

    # —— V2再加：HTML title 中提取姓名（51job/猎聘很多简历 title 是「姓名_岗位_...简历.html」，<title>里也有姓名）
    # EN: —— Added again in V2: extract the name from the HTML title (many 51job/Liepin résumés have a title like "name_position_...简历.html", and <title> also contains the name)
    # JA: —— V2 でさらに追加：HTML の title から氏名を抽出する（51job／Liepin の多くの履歴書は title が「氏名_職種_...简历.html」で、<title> にも氏名がある）
    if html_text:
        _m_title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
        if _m_title:
            _tt = _m_title.group(1).strip()
            # 去掉后缀：「 - 求职简历」「 - 简历详情」「_个人简历」等
            # EN: Remove suffixes: " - 求职简历" (job-seeker résumé), " - 简历详情" (résumé details), "_个人简历" (personal résumé), etc.
            # JA: 接尾辞を除く：「 - 求职简历」（求職履歴書）、「 - 简历详情」（履歴書詳細）、「_个人简历」（個人履歴書）など
            _tt = re.sub(r"[\s\-_\|｜–—].*?(?:简历|求职|resume|个人资料|个人简历|招聘).*$", "", _tt, count=1, flags=re.IGNORECASE).strip()
            # 取第一段纯中文（2-5字）
            # EN: Take the first pure Chinese segment (2-5 characters)
            # JA: 最初の漢字だけの部分（2〜5 文字）を取る
            _m_name = re.search(r"([\u4e00-\u9fff·]{2,5})", _tt)
            if _m_name:
                _c = _m_name.group(1).strip()
                if _c and _c not in _BLOCK_HEADER and _c not in _LASTRESORT_BLOCK \
                    and not any(_c.endswith(suf) for suf in _LASTRESORT_SUFFIX_BAD) \
                    and not any(tok == _c for tok in _INVALID_WORDS) \
                    and _c not in _EXCLUDE \
                    and _valid(_c):
                    return _c

    return "未知"


# =============================================================================
# 语言能力通用纯文本解析器
# =============================================================================
# EN: =============================================================================
#     General plain-text parser for language skills
#     =============================================================================
# JA: =============================================================================
#     語学力の汎用プレーンテキストパーサー
#     =============================================================================

_LANG_NAMES_SET = {"英语", "日语", "韩语", "法语", "德语", "俄语", "西班牙语", "葡萄牙语", "意大利语", "阿拉伯语", "粤语", "普通话", "英文", "日文", "中文", "汉语"}
_LANG_NAME_NORMALIZE = {
    "英文": "英语", "日文": "日语", "中文": "普通话", "汉语": "普通话",
    "Japanese": "日语", "English": "英语", "German": "德语", "French": "法语", "Korean": "韩语",
}
_LANG_LEVEL_MAP = {
    "精通": "精通", "熟练": "熟练", "良好": "良好", "一般": "一般",
    "母语": "精通", "流利": "熟练", "基础": "一般", "初学者": "一般",
}
# CET/TEM/JLPT 级别 对应 语言 能力 描述（language_level 用 原 描述，语言_certificate 取 证书 名）
# EN: Language-ability descriptions for CET/TEM/JLPT levels (language_level uses the original description, language_certificate takes the certificate name)
# JA: CET／TEM／JLPT のレベルに対応する語学力の説明（language_level には元の説明を使い、language_certificate には資格名を入れる）
_LANG_CERT_TOKENS = (
    # 英语
    # EN: English
    # JA: 英語
    "CET-4", "CET4", "大学英语四级", "英语四级",
    "CET-6", "CET6", "大学英语六级", "英语六级",
    "TEM-4", "TEM4", "专业英语四级", "专四",
    "TEM-8", "TEM8", "专业英语八级", "专八",
    "TOEIC", "TOEFL", "IELTS", "雅思", "托福",
    "GRE", "GMAT", "BEC",
    # 日语
    # EN: Japanese
    # JA: 日本語
    "JLPT N1", "JLPT N2", "JLPT N3",
    "N1", "N2", "N3",
    "日语能力一级", "日语能力二级", "日语能力三级",
    "日语一级", "日语二级", "日语三级",
    "一级", "二级", "三级",
    # 泛证书词（兜底，尽量 不 作为 主要 命中）
    # EN: Generic certificate words (fallback, avoid using them as the main hit)
    # JA: 汎用的な資格の語（最終手段。できるだけ主なヒットにはしない）
    "CET", "TEM", "JLPT", "能力考", "能力考试",
)

def parse_languages_from_raw_text(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _norm_lang_name(name: str) -> str:
        name = (name or "").strip()
        if name in _LANG_NAME_NORMALIZE:
            return _LANG_NAME_NORMALIZE[name]
        # 模糊 归一：含 英 → 英语；含 日 → 日语 等
        # EN: Fuzzy normalisation: contains 英 → 英语 (English); contains 日 → 日语 (Japanese), etc.
        # JA: あいまいな正規化：「英」を含む → 英语（英語）、「日」を含む → 日语（日本語）など
        for kw, nn in (("英", "英语"), ("日", "日语"), ("韩", "韩语"), ("法", "法语"),
                        ("德", "德语"), ("俄", "俄语"), ("粤", "粤语"), ("普通话", "普通话"), ("汉", "普通话")):
            if kw in name and nn in _LANG_NAMES_SET:
                return nn
        return name

    def _cert_in(level: str) -> tuple[str, str]:
        """从 level 提取 (语言_证书名, 去除_证书_后 的 纯 等级 描述)。

        EN: Extract (language certificate name, pure level description with the certificate removed) from level.

        JA: level から (語学資格名, 資格を除いた純粋なレベルの説明) を抽出する。
        """
        if not level:
            return "", ""
        s = str(level)
        # 常见 证书 短语 优先 提取
        # EN: Extract common certificate phrases first
        # JA: よくある資格の語句を優先して抽出する
        explicit_cert = ""
        for tok in (
            "大学英语六级", "大学英语四级", "英语六级", "英语四级",
            "专业英语八级", "专业英语四级", "专八", "专四",
            "日语能力一级", "日语能力二级", "日语能力三级",
            "日语一级", "日语二级", "日语三级",
            "JLPT N1", "JLPT N2", "JLPT N3",
            "CET-4", "CET4", "CET-6", "CET6",
            "TEM-4", "TEM4", "TEM-8", "TEM8",
            "TOEIC", "TOEFL", "IELTS", "雅思", "托福",
            "GRE", "GMAT", "BEC",
            "N1", "N2", "N3",
        ):
            if tok in s:
                explicit_cert = tok
                break
        tokens_hit: list[str] = []
        if not explicit_cert:
            for ct in _LANG_CERT_TOKENS:
                if re.search(rf"(?<![a-zA-Z]){re.escape(ct)}(?![a-zA-Z])", s, re.I):
                    tokens_hit.append(ct)
            if tokens_hit:
                explicit_cert = " ".join(tokens_hit[:1])  # 只 取 第 1 个 最 强 匹配
                # EN: Take only the first, strongest match
                # JA: 最初の最も強いマッチだけを取る
        # 提取 纯 等级 描述：优先 等级 词；否则 保留 原 描述（去 证书 词）
        # EN: Extract a pure level description: prefer level words; otherwise keep the original description (minus certificate words)
        # JA: 純粋なレベルの説明を抽出する：レベルの語を優先し、なければ元の説明を残す（資格の語は除く）
        lvl_only = ""
        level_kw_order = ("精通", "母语", "流利", "熟练", "良好", "一般", "基础")
        for kw in level_kw_order:
            if kw in s:
                lvl_only = kw
                break
        if not lvl_only:
            # 把 证书 词 从 s 里 去掉，剩余 部分 若 有 内容 且 长度 合适，作为 等级
            # EN: Remove the certificate words from s; if the remainder has content of suitable length, use it as the level
            # JA: s から資格の語を除き、残りに適切な長さの内容があればレベルとして使う
            remain = s
            if explicit_cert:
                # 按 长 token 优先 去掉
                # EN: Remove longer tokens first
                # JA: 長いトークンから先に除く
                for ct in sorted(_LANG_CERT_TOKENS, key=lambda x: -len(x)):
                    remain = re.sub(rf"(?<![a-zA-Z]){re.escape(ct)}(?![a-zA-Z])", " ", remain, flags=re.I)
                remain = re.sub(r"[\s:：,，|｜/／()（）【】\[\]、·•\-—_・<《>》]+", " ", remain).strip()
                if remain and len(remain) <= 20:
                    # 若 剩 下 的 只是 数字/标点/噪声 → 空
                    # EN: If what remains is only digits/punctuation/noise → empty
                    # JA: 残りが数字・句読点・ノイズだけなら → 空
                    if re.search(r"[\u4e00-\u9fffA-Za-z]", remain):
                        lvl_only = remain
        return explicit_cert, lvl_only

    def _clean_level_text(level: str) -> str:
        """清理 level 文本：去 首尾 标点 空 白；过滤 DOE 等 纯 非 语言 描述。

        EN: Clean level text: remove leading/trailing punctuation and whitespace; filter pure non-language descriptions such as DOE.

        JA: level のテキストを整理する：先頭・末尾の句読点と空白を除き、DOE など語学以外だけの説明を除外する。
        """
        s = (level or "").strip(" ：:|｜/／,，、()（）【】[]")
        return s[:120]

    def _add_lang(name: str, level: str = ""):
        norm_name = _norm_lang_name(name)
        if not norm_name:
            return
        key = norm_name
        if key in seen:
            return
        lvl_clean = _clean_level_text(level)
        # 先 从 lvl_clean 拆 成 「证书 名」 与 「纯 等级 描述」
        # EN: First split lvl_clean into "certificate name" and "pure level description"
        # JA: まず lvl_clean を「資格名」と「純粋なレベルの説明」に分ける
        cert_name, lvl_only = _cert_in(lvl_clean)
        final_level = lvl_only
        final_cert = cert_name
        # 语言 等级 / 证书 都 空（既 不 是 等级 词，也 无 证书 命中，且 含 DOE 等 明显 技能/方法 名）→ 视为 垃圾 输入，不 加
        # EN: Language level / certificate both empty (neither a level word nor a certificate hit, and it contains obvious skill/method names like DOE) → treat as junk input, do not add
        # JA: 語学のレベルも資格も空（レベルの語でも資格のヒットでもなく、DOE などの明らかなスキル・手法の名前を含む）→ ゴミの入力とみなして追加しない
        if not final_level and not final_cert:
            # 判断 lvl_clean 是 否 为 纯 技能/缩写/大 写 英文（不 是 语言 描述）→ 过滤
            # EN: Decide whether lvl_clean is a pure skill/abbreviation/uppercase English (not a language description) → filter
            # JA: lvl_clean が純粋なスキル・略語・大文字の英語（語学の説明ではない）かを判定する → 除外
            s = (lvl_clean or "").strip()
            is_noise = False
            if s:
                if len(s) <= 20 and re.fullmatch(r"[A-Za-z0-9_\- /（）()]+", s):
                    # 检查 是 否 有 常见 等级/证书 关键词（命中 则 保留）
                    # EN: Check for common level/certificate keywords (keep on a hit)
                    # JA: よくあるレベル・資格のキーワードがあるかを確認する（ヒットすれば残す）
                    has_lang_token = bool(re.search(r"精通|熟练|良好|一般|流利|母语|基础|CET|TEM|JLPT|TOEFL|IELTS|TOEIC|BEC|GRE|GMAT|四级|六级|八级|一级|二级|三级|N[123]|日语|英语|能力", s, re.I))
                    if not has_lang_token:
                        is_noise = True
                # 中文 长 度 > 3 且 不 含 任何 等级/证书 关键词（如 只 是 DOE / MSA / 六西格玛 等 中文）
                # EN: Chinese length > 3 and no level/certificate keyword at all (e.g. only DOE / MSA / Six Sigma in Chinese)
                # JA: 中国語の長さが 3 超で、レベル・資格のキーワードがまったくない（例：DOE／MSA／六西格玛 などの中国語だけ）
                if not is_noise and len(s) <= 40 and not re.search(r"精通|熟练|良好|一般|流利|母语|基础|CET|TEM|JLPT|TOEFL|IELTS|TOEIC|BEC|GRE|GMAT|四级|六级|八级|一级|二级|三级|N[123]|能力|等级", s, re.I):
                    # 明显 的 技能/方法/证书 名（MSA、DOE、六西格玛、FMEA ...）或 单 个 技能 词 → 过滤
                    # EN: Obvious skill/method/certificate names (MSA, DOE, Six Sigma, FMEA ...) or a single skill word → filter
                    # JA: 明らかなスキル・手法・資格の名前（MSA、DOE、六西格玛、FMEA ...）や単独のスキルの語 → 除外
                    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9_\-·・]+", s) or len(s) <= 6:
                        is_noise = True
            if is_noise and norm_name == "普通话":
                return
            # 其他 语言（英语/日语 等）没 等级 没 证书 但 有 噪声，也 不 加
            # EN: Other languages (English/Japanese etc.) with no level, no certificate but noise are not added either
            # JA: その他の言語（英語・日本語など）でレベルも資格もなくノイズだけのものも追加しない
            if is_noise:
                return
        # 若 等级 清 空 了 且 名字 是 普通话 且 也 无 证书（普通话: DOE → 当 无 价值 条目，不 加）
        # EN: If the level was cleared, the name is 普通话 (Mandarin) and there is no certificate (普通话: DOE → a worthless entry, do not add)
        # JA: レベルが空になり、名前が普通话（標準中国語）で資格もない場合（普通话: DOE → 価値のない項目なので追加しない）
        if not final_level and not final_cert and norm_name == "普通话":
            return
        # 若 普通话 有 等级（精通/熟练），保留；否则 普通话 通常 不必 写（默认 会）
        # EN: If Mandarin has a level (精通/熟练: expert/proficient), keep it; otherwise Mandarin usually need not be written (it is spoken by default)
        # JA: 標準中国語にレベル（精通／熟练：精通・堪能）があれば残す。なければ通常書く必要はない（話せるのが前提）
        if norm_name == "普通话" and final_level in ("一般", "良好"):
            return  # 普通话 一般/良好 信息 价值 低，不 填
            # EN: Mandarin "一般/良好" (basic/good) has low information value, do not fill it
            # JA: 標準中国語の「一般／良好」（普通・良好）は情報価値が低いので入れない
        # 语言 既 没 等级 也 没 证书，信息 不足 → 不 加（避免 「普通话」无 描述、「英语」空 条目 污染 结果）
        # EN: A language with neither level nor certificate has too little information → do not add (to avoid "普通话" with no description or empty "英语" entries polluting the result)
        # JA: レベルも資格もない言語は情報が不足 → 追加しない（説明のない「普通话」や空の「英语」の項目が結果を汚染しないため）
        if not final_level and not final_cert:
            return
        seen.add(key)
        results.append({
            "language_name": norm_name,
            "language_level": final_level,
            "language_certificate": final_cert,
            "language_certificate_time": "",
        })

    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    in_lang_block = False
    # 语言 板块 开始 信号（多 匹配）
    # EN: Signals for the start of the language section (multiple matches)
    # JA: 語学欄の開始の合図（複数マッチ）
    LANG_HEADERS = ("语言能力", "技能/语言", "语言水平", "外语能力", "语言技能", "语言与技能", "语言特长", "外语水平")
    # 语言 板块 结束 信号
    # EN: Signals for the end of the language section
    # JA: 語学欄の終了の合図
    STOP_HEADERS = ("工作经历", "教育经历", "项目经历", "自我评价", "所获证书", "培训经历", "求职意向",
                    "工作经验", "教育背景", "项目经验", "技能", "IT技能", "专业技能")

    # ========== 1) 先 扫 「语言 板块 内」逐行 解析 ==========
    # EN: ========== 1) First scan "inside the language section" and parse line by line ==========
    # JA: ========== 1) まず「語学欄の中」をスキャンして行ごとに解析する ==========
    i = 0
    while i < len(lines):
        l = lines[i]
        # 进入 语言 板块
        # EN: Enter the language section
        # JA: 語学欄に入る
        if any(h in l for h in LANG_HEADERS):
            in_lang_block = True
            i += 1
            continue
        if in_lang_block and any(h in l for h in STOP_HEADERS):
            in_lang_block = False
        if not in_lang_block:
            # 跨 出 语言 板块，尝试 下 一 行 可能 是 板块 头
            # EN: Left the language section; the next line may be a section header
            # JA: 語学欄から出た。次の行はセクション見出しかもしれない
            i += 1
            continue

        # 语言 板块 内：逐行 扫描
        # A. 单独 一行 纯 语言 名
        # EN: Inside the language section: scan line by line
        #     A. A line containing only a language name
        # JA: 語学欄の中：行ごとにスキャンする
        #     A. 言語名だけの行
        if l in _LANG_NAMES_SET or l in _LANG_NAME_NORMALIZE:
            next_l = lines[i + 1].strip() if i + 1 < len(lines) else ""
            # 下 一 行 若 也 是 语言 名 → 说明 本行 等级 空
            # EN: If the next line is also a language name → this line has an empty level
            # JA: 次の行も言語名なら → この行のレベルは空
            if next_l in _LANG_NAMES_SET or next_l in _LANG_NAME_NORMALIZE or any(h in next_l for h in LANG_HEADERS + STOP_HEADERS):
                _add_lang(l, "")
            else:
                _add_lang(l, next_l)
            i += 1
            continue

        # B. 同行 语言名 : 等级（英语：CET-6 / 英语（熟练） / 英语：熟练：听 说 读 写 ...）
        # EN: B. Language name : level on the same line (英语：CET-6 / 英语（熟练） / 英语：熟练：听 说 读 写 ...)
        # JA: B. 同じ行に 言語名：レベル（英语：CET-6 / 英语（熟练） / 英语：熟练：听 说 读 写 ...）
        m_colon = re.match(
            r"^\s*(英语|英文|日语|日文|韩语|法语|德语|俄语|西班牙语|葡萄牙语|意大利语|阿拉伯语|粤语|普通话|中文|汉语|Japanese|English|German|French|Korean)\s*[（(]?\s*([^:：)）]*)[)）]?\s*[:：]\s*(.*)$",
            l, re.I
        )
        if m_colon:
            nm = m_colon.group(1)
            part1 = (m_colon.group(2) or "").strip()
            part2 = (m_colon.group(3) or "").strip()
            # 等级 = 括号 内 + 冒号 后
            # EN: Level = inside the brackets + after the colon
            # JA: レベル = 括弧内 + コロンの後
            level_text = " ".join([x for x in (part1, part2) if x]).strip()
            # 读 后续 行，直到 碰 下 一 个 语言 或 板块 头（猎聘/51job 跨 多 行 描述）；若 后续 行 是 无 关 内容（下 一 行 又 是 一个 新 的 语言:X / 板块 头），立刻 停
            # EN: Read the following lines until the next language or section header (Liepin/51job descriptions span several lines); if a following line is unrelated content (the next line is a new "language: X" / section header), stop immediately
            # JA: 次の言語かセクション見出しまで後続の行を読む（Liepin／51job の説明は複数行にわたる）。後続の行が無関係な内容（次の行が新たな「言語:X」やセクション見出し）なら、すぐに止める
            j = i + 1
            while j < len(lines):
                nl = lines[j]
                if re.match(
                    r"^\s*(英语|英文|日语|日文|韩语|法语|德语|俄语|西班牙语|葡萄牙语|意大利语|阿拉伯语|粤语|普通话|中文|汉语|Japanese|English|German|French|Korean)\s*[（(]?\s*[^:：)）]*[)）]?\s*[:：]",
                    nl, re.I
                ):
                    break
                if any(h in nl for h in STOP_HEADERS):
                    break
                # 若 后续 行 不 含 任何 等级/证书 相关 词，且 不 以 常用 连词 起头，说明 可能 是 下 一 个 语言 描述 或 其他 内容 → 不 追加（避免 把 DOE / 技能 词 塞进 等级）
                # EN: If a following line contains no level/certificate-related words and does not start with a common conjunction, it may be the next language description or other content → do not append (to avoid stuffing DOE / skill words into the level)
                # JA: 後続の行にレベル・資格に関する語がなく、よく使う接続詞で始まらない場合は、次の言語の説明か別の内容の可能性がある → 追加しない（DOE やスキルの語をレベルに詰め込まないため）
                if not level_text:
                    level_text = nl
                else:
                    if re.search(r"精通|熟练|良好|一般|流利|母语|基础|CET|TEM|JLPT|TOEFL|IELTS|TOEIC|BEC|GRE|GMAT|四级|六级|八级|一级|二级|三级|N[1-3]", nl, re.I):
                        level_text += "，" + nl
                    # 否则：不 追加（避免 把 DOE、技能 说明 等 非 语言 描述 合并 进来）
                    # EN: Otherwise: do not append (to avoid merging non-language descriptions such as DOE or skill notes)
                    # JA: それ以外：追加しない（DOE やスキルの説明など語学以外の説明を混ぜないため）
                j += 1
            _add_lang(nm, level_text)
            i = j
            continue

        # C. 英语 CET-4 / 日语一级 这种 没 冒号 的 短语
        # EN: C. Phrases without a colon like 英语 CET-4 / 日语一级
        # JA: C. 英语 CET-4／日语一级 のようなコロンのない語句
        m_shorthand = re.search(
            r"(英语|英文|日语|日文|韩语|法语|德语|俄语|普通话|粤语|中文|汉语)\s*((?:CET|TEM|JLPT)?[\s\-]*[0-9一二三四五六七八九十]+级?|(?:N|JLPT\s*N)\s*[123]|一级|二级|三级|四级|六级|八级|CET|TOEIC|TOEFL|IELTS|BEC|精通|熟练|良好|一般|流利|母语|基础)",
            l, re.I
        )
        if m_shorthand:
            _add_lang(m_shorthand.group(1), m_shorthand.group(2))  # 只 拿 第 2 组（等级/证书 部分），不 拿 整 段 match
            # EN: Take only group 2 (the level/certificate part), not the whole match
            # JA: 第 2 グループ（レベル・資格の部分）だけを取り、マッチ全体は取らない
            i += 1
            continue

        # D. 语言 板块 内 若 单独 是 等级 词（前面 没 识别 但 上 一 行 已 有 语言名，这里 是 换行 等级）—— 此 模式 已 在 A 覆盖，这里 跳过
        # EN: D. Within the language section, a standalone level word (not recognised before, but the previous line already has a language name; this is a wrapped level) — this pattern is already covered by A, skip here
        # JA: D. 語学欄の中で単独のレベルの語（前では認識されなかったが、前の行に言語名があり、改行されたレベル）— このパターンは A で処理済みなのでここではスキップ
        i += 1

    # ========== 2) 兜底：全文 正则 扫 （language 板块 没 找到 或 未 切 出来 的 简历） ==========
    # EN: ========== 2) Fallback: full-text regex scan (résumés where the language section was not found or not split out) ==========
    # JA: ========== 2) 最終手段：全文の正規表現スキャン（語学欄が見つからない・切り出せなかった履歴書）==========
    if not results:
        for l in lines:
            # 跳过 明显 是 工作/项目 描述 行
            # EN: Skip lines that are obviously work/project descriptions
            # JA: 明らかに職歴・プロジェクトの説明の行はスキップする
            if re.search(r"工作描述|工作职责|项目简介|负责|职责|业绩|成就", l, re.I):
                continue
            # 同行 语言名 + 冒号 + 描述
            # EN: Language name + colon + description on the same line
            # JA: 同じ行に 言語名 + コロン + 説明
            m_colon = re.match(
                r"^\s*(英语|英文|日语|日文|韩语|法语|德语|俄语|西班牙语|粤语|普通话|中文|汉语)\s*[（(]?\s*([^:：)）]*)[)）]?\s*[:：]?\s*(.*)$",
                l, re.I
            )
            if m_colon and (m_colon.group(2) or m_colon.group(3)):
                nm = m_colon.group(1)
                level_text = " ".join([x for x in (m_colon.group(2), m_colon.group(3)) if x]).strip()
                _add_lang(nm, level_text)
                continue
            # 英语 CET-6 / 日语 N1
            # EN: 英语 CET-6 / 日语 N1
            # JA: 英语 CET-6 / 日语 N1
            m_sh = re.search(
                r"(英语|英文|日语|日文|韩语|法语|德语|俄语|普通话|粤语)\s*((?:CET|TEM|JLPT)?[\s\-]*[0-9一二三四五六七八九十]+级?|(?:N|JLPT\s*N)\s*[123]|一级|二级|三级|四级|六级|八级|CET|TOEIC|TOEFL|IELTS|BEC|精通|熟练|良好|一般|流利|母语|基础)",
                l, re.I
            )
            if m_sh:
                _add_lang(m_sh.group(1), m_sh.group(2))
                continue

    return results


# =============================================================================
# 联系方式 + expected_info 8 字段补齐
# =============================================================================
# EN: =============================================================================
#     Contact details + completing the 8 expected_info fields
#     =============================================================================
# JA: =============================================================================
#     連絡先 + expected_info の 8 フィールドの補完
#     =============================================================================

def extract_contacts_all(text: str) -> dict[str, str]:
    contact = {"mobile": "", "email": "", "wechat": ""}
    m_mob = re.search(r"(?:手机|电话|Mobile|Tel)[：:\s]*([\d\s-]{11,15})", text, re.I)
    if m_mob:
        digits = re.sub(r"[^\d]", "", m_mob.group(1))
        if len(digits) >= 11:
            contact["mobile"] = digits[:11]
    if not contact["mobile"]:
        m_mob2 = re.search(r"\b1[3-9]\d{9}\b", text)
        if m_mob2:
            contact["mobile"] = m_mob2.group(0)
    m_em_link = re.search(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if m_em_link:
        contact["email"] = m_em_link.group(1)
    else:
        m_em = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', text)
        if m_em and "HYPERLINK" not in m_em.group(0):
            contact["email"] = m_em.group(0)
    glued = re.fullmatch(r"(1[3-9]\d{9})([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", contact["email"])
    if glued:
        contact["mobile"] = contact["mobile"] or glued.group(1)
        contact["email"] = glued.group(2)
    m_wx = re.search(r"(?:微信|WX|WeChat)[：:\s]*([a-zA-Z0-9_-]{6,30})", text, re.I)
    if m_wx:
        contact["wechat"] = m_wx.group(1).strip()
    return contact


def _zhilian_extract_expected_start(text: str) -> str:
    m = re.search(r"目前状况[：:]\s*([^\n]+)", text)
    if not m:
        return ""
    status = m.group(1).strip()
    if "立即上岗" in status or "立刻到岗" in status or "随时" in status or "即刻" in status:
        return "随时到岗"
    m_weeks = re.search(r"(?:(\d+)\s*个月?左右|(\d+)\s*周|(\d+)\s*天)", status)
    if m_weeks:
        mo, wk, dy = m_weeks.groups()
        if mo:
            return f"{int(mo)}个月内到岗"
        if wk:
            return f"{int(wk)}周内到岗"
        if dy:
            return f"{int(dy)}天内到岗"
    if "一个月" in status or "1月" in status or "30天" in status:
        return "1个月内到岗"
    if "两周" in status or "半月" in status:
        return "2周内到岗"
    # “在职/应届毕业生/离职”是当前求职状态，不等于到岗承诺。没有明确的
    # 时间表达时必须留空，不能为了补字段而臆造“1个月内/随时到岗”。
    # EN: "在职/应届毕业生/离职" (employed / new graduate / left) is the current job-search status, not a start-date commitment. Without an explicit
    #     time expression it must be left empty; never invent "1个月内/随时到岗" (within a month / available any time) just to fill the field.
    # JA: 「在职／应届毕业生／离职」（在職中・新卒・退職済み）は現在の求職状況であり、入社可能時期の約束ではない。明確な
    #     時期の表現がなければ空にしなければならず、フィールドを埋めるために「1个月内／随时到岗」（1 か月以内／いつでも可）を作り出してはならない。
    return ""


def complete_expected_info(
    expected_info_list: list[dict[str, Any]] | dict[str, Any] | Any,
    text: str,
) -> dict[str, Any]:
    """将 expected_info 归一为单个对象，补齐 CONTEXT.md 7.2 要求的 8 个字段。

    EN: Normalise expected_info into a single object and complete the 8 fields required by CONTEXT.md 7.2.

    JA: expected_info を単一のオブジェクトに正規化し、CONTEXT.md 7.2 が求める 8 フィールドを補完する。
    """
    REQUIRED_FIELDS = (
        "expected_city", "expected_position", "expected_salary",
        "expected_annual_salary_min", "expected_annual_salary_max",
        "expected_industry", "expected_employment_type", "expected_start_date",
    )

    def _as_dict(o: Any) -> dict[str, Any]:
        if isinstance(o, dict):
            return o
        if isinstance(o, list) and o:
            return _as_dict(o[0])
        return {}

    src = _as_dict(expected_info_list)
    result: dict[str, Any] = {f: "" for f in REQUIRED_FIELDS}

    # **前置 过滤：明显 无效 的 值（表格 列名、section header、纯 日期 等） 直接 当作 空，避免 DOM parser 塞 进来 的 脏 数据 污染**
    # EN: **Pre-filter: treat obviously invalid values (table column names, section headers, pure dates, etc.) as empty, so dirty data stuffed in by the DOM parser does not pollute the result**
    # JA: **事前フィルター：明らかに無効な値（表の列名・セクション見出し・日付だけなど）は空として扱い、DOM パーサーが詰め込んだ汚れたデータで結果が汚染されないようにする**
    BAD_LABEL_TOKENS = (
        # 表格 列名 / section header / 明显 不 是 期望 职位 的 标签
        # EN: Table column names / section headers / labels that are obviously not desired positions
        # JA: 表の列名・セクション見出し・明らかに希望職位ではないラベル
        "时间", "任职公司", "职位", "所属行业", "公司", "公司名称", "行业", "行业类别", "学历", "专业", "日期",
        "简介", "描述", "职责", "负责", "协助", "参与", "制定", "管理", "工作描述", "工作内容",
        "工作经历", "工作经验", "教育经历", "教育背景", "项目经历", "项目经验", "培训经历", "语言能力",
        "专业技能", "技能", "证书", "所获证书", "自我评价", "姓名", "性别", "年龄", "民族", "电话",
        "居住地", "地址", "籍贯", "政治面貌", "婚姻状况", "身高", "体重", "邮箱", "QQ", "微信",
        "学校", "毕业学校", "院系", "入学时间", "毕业时间", "学历学位", "最高学历",
        "公司性质", "公司规模", "企业性质", "企业规模", "月薪", "月薪范围", "职位月薪范围", "薪资", "待遇", "税前", "税后",
        "工作地点", "工作性质", "招聘人数", "发布日期", "到岗时间", "到职日期", "入职时间",
        "PAGE", "page", "简历", "基本信息", "个人信息", "联系方式",
    )
    _DATE_PREFIX_RE = re.compile(r"^(?:(?:19|20)\d{2})[\-./年]|^至今$|^现在$")
    def _has_comp_sign(t: str) -> bool:
        # 含 公司 主体 相关 特征 词（非 职位 常见 结构）
        # EN: Contains words typical of a company entity (not a common position structure)
        # JA: 会社主体に特有の語を含む（職位によくある構造ではない）
        return any(tok in t for tok in ("股份", "有限", "集团", "公司", "厂", "制造", "科技", "贸易", "投资", "咨询", "中心", "医院", "学校", "大学", "学院", "研究所", "研究院", "事业部", "分公司"))
    def _is_really_valid(field: str, val: str) -> bool:
        if not val: return False
        s = str(val).strip()
        if not s: return False
        compact = re.sub(r"[\s|｜:：#\-—_()（）\[\]【】<>《》,，.。;；/\\]+", "", s).casefold()
        # 1) 完全 等于 黑名单 token（case-insensitive）
        # EN: 1) Exactly equals a blacklisted token (case-insensitive)
        # JA: 1) ブラックリストのトークンと完全に一致する（大文字小文字を区別しない）
        if compact in {re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", t.casefold()) for t in BAD_LABEL_TOKENS}:
            return False
        # 2) 仅 日期（如 "2004-2006"） → 不 能 当 职位/行业
        # EN: 2) Only a date (e.g. "2004-2006") → cannot be a position/industry
        # JA: 2) 日付だけ（例："2004-2006"）→ 職位・業界にはなり得ない
        if field in ("expected_position", "expected_industry", "expected_city") and _DATE_PREFIX_RE.search(s):
            return False
        # 3) 全 数字 或 日期 符号 → 无效
        # EN: 3) All digits or date symbols → invalid
        # JA: 3) 数字や日付の記号だけ → 無効
        if re.fullmatch(r"[\d\-—~～至到年月.，,/\\|｜\s]+", s):
            return False
        # 4) expected_position / expected_industry：若 嵌 有 完整 日期 段（如 2009.2.1-2011.7）→ 无效
        # EN: 4) expected_position / expected_industry: if a complete date range is embedded (e.g. 2009.2.1-2011.7) → invalid
        # JA: 4) expected_position / expected_industry：完全な期間（例：2009.2.1-2011.7）が埋め込まれていれば → 無効
        if field in ("expected_position", "expected_industry"):
            if re.search(r"(?:19|20)\d{2}[.年/-]\s*\d{1,2}(?:[.月/-]\s*\d{1,2})?\s*[\-—–~～至到]\s*(?:19|20|至今|现在)", s):
                return False
            # 5) 职位/行业 太长 且 含 句子 标点 → 大概率 描述 文字 误 填
            # EN: 5) Position/industry too long and containing sentence punctuation → most likely descriptive text filled in by mistake
            # JA: 5) 職位・業界が長すぎて文の句読点を含む → 説明文が誤って入った可能性が高い
            if len(s) > 40 and any(c in s for c in "，,。.；;、"):
                return False
            # 6) 含 明显 章节/描述 词（非 职位 词）
            # EN: 6) Contains obvious section/description words (not position words)
            # JA: 6) 明らかな章・説明の語（職位の語ではない）を含む
            if any(bad in compact for bad in ("工作能力", "工作经验", "个人简介", "教育经历", "项目经验", "培训经历", "自我介绍", "自我评价")):
                return False
            # 7) 含 公司 后缀（公司/集团/厂/有限/股份/贸易 等） → 不是 职位
            # EN: 7) Contains company suffixes (公司/集团/厂/有限/股份/贸易 etc.) → not a position
            # JA: 7) 会社の接尾辞（公司／集团／厂／有限／股份／贸易 など）を含む → 職位ではない
            if field == "expected_position":
                if re.search(r"(?:有限公司|股份有限公司|集团|有限责任公司|制造厂|制造厂|工厂|公司|事业部|中心|医院|学校|大学|学院|研究所|研究院)\s*$", s):
                    return False
                # 职位 通常 不 会 有 (城市) 括号 地域 修饰（那 是 公司 写法）
                # EN: Positions usually do not have a bracketed (city) regional qualifier (that is how companies are written)
                # JA: 職位には通常（都市）のような括弧付きの地域の修飾はない（それは会社名の書き方）
                if re.search(r"[（(][\u4e00-\u9fff]{2,4}[)）]", s) and _has_comp_sign(s):
                    return False
        return True

    for k in REQUIRED_FIELDS:
        if k in src and src[k] and _is_really_valid(k, src[k]):
            result[k] = str(src[k]).strip()

    if not result["expected_city"]:
        m = re.search(r"期望(?:工作)?地区\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            result["expected_city"] = m.group(1).strip()
    if not result["expected_city"]:
        m = re.search(r"(?:求职意向[\s\S]{0,800}?)?地点\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            city_value = m.group(1).strip()
            if len(city_value) <= 40 and not any(token in city_value for token in ("培训", "项目", "公司", "学校")):
                result["expected_city"] = city_value

    if not result["expected_position"]:
        m = re.search(r"(?:期望(?:从事)?职业|期望职位|应聘职位|目标职位|求职意向)\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            pos = m.group(1).strip()
            compact = re.sub(r"[\s|｜:：#]+", "", pos).casefold()
            if compact not in {"申请表", "职位申请表", "applicationform", "申请职位", "姓名", "目标"}:
                result["expected_position"] = pos

    if not result["expected_salary"]:
        m = re.search(r"(?:期望月薪|期望薪资|期望工资|待遇要求)\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            result["expected_salary"] = m.group(1).strip()

    if not result["expected_annual_salary_min"] or not result["expected_annual_salary_max"]:
        raw = result["expected_salary"]
        nums = [int(n) for n in re.findall(r"\d+", raw or "")]
        # 已明确标注“元/年、年薪”的值本身就是年薪，不能再乘 12。
        # EN: A value explicitly marked "元/年、年薪" (yuan/year, annual salary) is already annual and must not be multiplied by 12 again.
        # JA: 「元/年、年薪」（元／年、年収）と明記された値はそれ自体が年収なので、さらに 12 を掛けてはならない。
        if nums and re.search(r"(?:元\s*/\s*年|年薪|元每年)", raw or ""):
            result["expected_annual_salary_min"] = str(nums[0])
            if len(nums) > 1:
                result["expected_annual_salary_max"] = str(nums[1])
        elif "万" in (raw or "") and nums:
            annual = [n * 10000 for n in nums]
            result["expected_annual_salary_min"] = str(annual[0])
            if len(annual) > 1:
                result["expected_annual_salary_max"] = str(annual[1])
        elif "千" in (raw or "") and nums:
            monthly = [n * 1000 for n in nums]
            result["expected_annual_salary_min"] = str(monthly[0] * 12)
            if len(monthly) > 1:
                result["expected_annual_salary_max"] = str(monthly[1] * 12)
        elif nums:
            # 假定是月薪
            # EN: Assume monthly salary
            # JA: 月給とみなす
            result["expected_annual_salary_min"] = str(nums[0] * 12)
            if len(nums) > 1:
                result["expected_annual_salary_max"] = str(nums[1] * 12)

    if not result["expected_industry"]:
        m = re.search(r"期望(?:从事)?行业\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            result["expected_industry"] = m.group(1).strip()

    if not result["expected_employment_type"]:
        m = re.search(r"期望(?:工作)?性质\s*[:：]\s*([^\n,，|│]+)", text)
        if m:
            result["expected_employment_type"] = m.group(1).strip()

    # 到岗时间必须有源文本里的明确证据。DOM 错位得到的值不继承，也不能从
    # “应届毕业生/在职/离职”等求职状态推导。
    # EN: The start date must have explicit evidence in the source text. Values obtained from DOM misalignment are not inherited, nor can it be derived from
    #     job-search statuses like "应届毕业生/在职/离职" (new graduate / employed / left).
    # JA: 入社可能時期には原文中の明確な根拠が必要。DOM のずれで得た値は引き継がず、
    #     「应届毕业生／在职／离职」（新卒・在職中・退職済み）などの求職状況から導いてもならない。
    explicit_start = ""
    m = re.search(r"(?:到岗时间|到职日期|可到岗时间|入职时间)\s*[:：]\s*([^\n,，|│]+)", text)
    if m:
        explicit_start = m.group(1).strip()
    if not explicit_start:
        explicit_start = _zhilian_extract_expected_start(text)
    result["expected_start_date"] = explicit_start

    # 到岗时间最终归范化（避免「即时」/「1周内」这类混乱）
    # EN: Final normalisation of the start date (to avoid messy values like "即时" (immediately) / "1周内" (within a week))
    # JA: 入社可能時期の最終的な正規化（「即时」（即時）／「1周内」（1 週間以内）などのばらつきを避ける）
    _sd = str(result.get("expected_start_date") or "").strip()
    if _sd:
        _sd_norm = None
        # 优先匹配具体值
        # EN: Prefer matching specific values
        # JA: 具体的な値のマッチを優先する
        if any(x in _sd for x in ("立即", "立刻", "随时", "即刻", "即时", "马上")):
            _sd_norm = "随时到岗"
        else:
            m_wd = re.search(r"(\d+)\s*(个?月|周|天|星期)", _sd)
            if m_wd:
                num, unit = m_wd.group(1), m_wd.group(2)
                n = int(num)
                if unit in ("月", "个月"):
                    _sd_norm = f"{n}个月内到岗"
                elif unit in ("周", "星期"):
                    # 保留具体周数（1周、2周、3周...）
                    # EN: Keep specific week counts (1周、2周、3周...: 1 week, 2 weeks, 3 weeks...)
                    # JA: 具体的な週数（1周、2周、3周...）を残す
                    _sd_norm = f"{n}周内到岗"
                else:  # 天
                # EN: Days
                # JA: 日
                    dy = n
                    if dy <= 3:
                        _sd_norm = "随时到岗"
                    elif dy <= 7:
                        _sd_norm = "1周内到岗"
                    elif dy <= 15:
                        _sd_norm = "2周内到岗"
                    else:
                        _sd_norm = "1个月内到岗"
        if _sd_norm is None:
            if "一个月" in _sd or "1月" in _sd or "30天" in _sd:
                _sd_norm = "1个月内到岗"
            elif "两周" in _sd or "半月" in _sd:
                _sd_norm = "2周内到岗"
            elif "一周" in _sd or "1周" in _sd or "7天" in _sd:
                _sd_norm = "1周内到岗"
            # 求职状态不能推导到岗时间。
            # EN: The job-search status cannot be used to derive the start date.
            # JA: 求職状況から入社可能時期を導いてはならない。
        if _sd_norm:
            result["expected_start_date"] = _sd_norm
        else:
            # 都不匹配时截断前10字兜底
            # EN: When nothing matches, truncate to the first 10 characters as a fallback
            # JA: 何もマッチしない場合は最終手段として先頭 10 文字に切り詰める
            result["expected_start_date"] = _sd[:10]

    return result


# =============================================================================
# 板块切分器 + 教育/工作 提取 + 杂质清理
# =============================================================================
# EN: =============================================================================
#     Section splitter + education/work extraction + noise cleanup
#     =============================================================================
# JA: =============================================================================
#     セクション分割器 + 学歴・職歴の抽出 + 不要部分の除去
#     =============================================================================

def split_resume_sections(text: str) -> dict[str, str]:
    """通用简历文本板块切分器：
    按通用中文板块标题（教育经历、工作经历、项目经历、培训经历、求职意向、自我评价等）
    将全文切分为独立的板块字符串字典，避免各解析逻辑跨板块混淆。

    EN: Generic résumé text section splitter:
    splits the full text by generic Chinese section headings (education, work history, projects, training, job preferences, self-assessment, etc.)
    into a dictionary of independent section strings, so the parsing logic does not mix across sections.

    JA: 汎用的な履歴書テキストのセクション分割器：
    一般的な中国語のセクション見出し（学歴・職歴・プロジェクト経験・研修歴・希望条件・自己評価など）で
    全文を独立したセクションの文字列の辞書に分け、各解析ロジックがセクションをまたいで混同しないようにする。
    """
    if not text:
        return {}

    SECTION_PATTERNS = [
        # —— 关键修复：lookahead 放宽为允许 section 标题后直接跟日期数字（19xx/20xx），
        #    解决「教育背景2019.01—在读」「社会实践2015.11.19—至今」这种标题+内容粘连格式；
        #    同时补充各板块常见标题变体（教育状况/毕业学校/社会实践 等）
        # EN: —— Key fix: relax the lookahead to allow date digits (19xx/20xx) directly after a section heading,
        #        solving heading+content stuck formats like "教育背景2019.01—在读" and "社会实践2015.11.19—至今";
        #        also add common heading variants for each section (教育状况/毕业学校/社会实践 etc.)
        # JA: —— 重要な修正：先読みを緩め、セクション見出しの直後に日付の数字（19xx／20xx）が続くことを許容する。
        #        「教育背景2019.01—在读」「社会实践2015.11.19—至今」のような見出しと内容がくっついた形式に対応する。
        #        各セクションによくある見出しの別表記（教育状况／毕业学校／社会实践 など）も追加する
        ("work", r"(?:^|\n)\s*(?:\|?\s*工作经历|Work\s+Experience|工作经验|工作履历|工作情况|职业经历|社会实践|工作内容|职业经验|社会实习)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("education", r"(?:^|\n)\s*(?:\|?\s*教育经历|教育背景|教育状况|学歴|教育程度|Learning\s+Experience|Education|教育背景描述|毕业学校|在校情况|教育情况|在校学习)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("project", r"(?:^|\n)\s*(?:\|?\s*项目经历|项目经验|项目情况|Projects|Project)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("training", r"(?:^|\n)\s*(?:\|?\s*培训经历|培训课程|Training|培训|在校实践)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("expected", r"(?:^|\n)\s*(?:\|?\s*求职意向|择业意向|应聘意向|Career Objective|期望工作|目标意向|求职志愿|期望职位)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("summary", r"(?:^|\n)\s*(?:\|?\s*自我评价|个人总结|自评|Self Assessment|Self Evaluation|自我鉴定|个人评价)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("skills", r"(?:^|\n)\s*(?:\|?\s*专业技能|技能特长|技能|语言与技能|Skills|专业特长|掌握技能)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("language", r"(?:^|\n)\s*(?:\|?\s*语言能力|外语水平|语言与技能|Language|外语能力|语言)\s*(?=\s|$|[:：]|（|【|\d)"),
        ("certificates", r"(?:^|\n)\s*(?:\|?\s*证书|所获证书|Certificates?|获奖证书|资格证书)\s*(?=\s|$|[:：]|（|【|\d)"),
    ]

    matches = []
    for key, pattern in SECTION_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            matches.append((m.start(), m.end(), key))

    matches.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    if not matches:
        sections["header"] = text
        return sections

    first_start = matches[0][0]
    sections["header"] = text[:first_start].strip()

    for i, (start, end, key) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        content = text[end:next_start].strip()
        if key in sections:
            sections[key] += "\n" + content
        else:
            sections[key] = content

    return sections


def parse_education_from_raw_text(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """从纯文本中解析多段教育经历 + 培训经历（板块切割隔离版）。

    EN: Parse multiple education entries + training entries from plain text (section-isolated version).

    JA: プレーンテキストから複数の学歴 + 研修歴を解析する（セクション分離版）。
    """
    if not text:
        return [], []

    sections = split_resume_sections(text)

    # ======= 子块 1：优先取切分器拿到的 education 板块文本 =======
    # EN: ======= Sub-block 1: prefer the education section text obtained by the splitter =======
    # JA: ======= サブブロック 1：分割器で得た education セクションのテキストを優先する =======
    block_main = sections.get("education", "").strip()
    # —— 关键修复：双重 section split 的 BUG 回退。如果上层调用方传的是已经 section 化后的「教育板块切片文本」
    #    （如 build_record_from_html 中 work_sec_text / edu_sec_text 等「已经切好的 section 片段」），
    #    本函数内部再次调用 split_resume_sections 会找不到任何 section 标题，只能把整个切片内容塞进「header」键里。
    #    这种情况下，必须直接用整个文本（或 header 内容）作为 block_main，否则 block_main 为空导致 0 条解析。
    # EN: —— Key fix: rollback for the double-section-split BUG. If the upper caller passed an already sectionised "education section slice"
    #        (e.g. "already cut section fragments" such as work_sec_text / edu_sec_text in build_record_from_html),
    #        calling split_resume_sections again inside this function finds no section headings and can only stuff the whole slice into the "header" key.
    #        In that case the whole text (or the header content) must be used directly as block_main, otherwise block_main is empty and 0 entries are parsed.
    # JA: —— 重要な修正：二重のセクション分割の BUG への対処。上位の呼び出し元がすでにセクション化された「学歴セクションの切片」を渡した場合
    #        （build_record_from_html の work_sec_text / edu_sec_text などの「切り出し済みのセクション片」）、
    #        この関数内で split_resume_sections を再度呼ぶとセクション見出しが見つからず、切片全体を「header」キーに入れるしかない。
    #        その場合はテキスト全体（または header の内容）をそのまま block_main として使う必要がある。さもないと block_main が空になり 0 件しか解析されない。
    if not block_main:
        fallback_text = (sections.get("header") or "").strip() or text.strip()
        block_main = fallback_text

    # ======= 子块 2：求职申请表的教育程度段 =======
    # EN: ======= Sub-block 2: the education level section of job application forms =======
    # JA: ======= サブブロック 2：求職申込書の学歴の段落 =======
    m_edu_form_sec = re.search(
        r"教育程度\s*(?:（[^\n]*）)?\s*\n(.*?)(?=\n\s*(?:工作履历|工作经历|工作经验|工作单位名称|家庭状况|简述申请|是否有亲戚|以下内容由公司填写|\Z))",
        text, re.S,
    )
    block_edu_form = m_edu_form_sec.group(1).strip() if m_edu_form_sec else ""

    training_keywords = ("咨询", "顾问", "认证", "培训", "企业管理", "管理咨询", "研修", "进修", "课程", "内训")
    cert_keywords = ("iso", "内审员", "品管圈", "五大工具", "apqp", "ppap", "spc", "msa", "fmea", "证书", "资格", "培训", "沟通", "审员")
    # —— 新增：智联招聘 / 猎聘 / 前程无忧等 网页导出 HTML 时 常见的 UI 工具栏/右键菜单垃圾词
    # 这些行完全不是简历内容，必须在学校/专业/学位/培训/工作 所有字段中一律排除
    # EN: —— New: UI toolbar / context-menu junk words common in HTML exported from web pages of Zhaopin / Liepin / 51job etc.
    #     These lines are not résumé content at all and must be excluded from every field: school/major/degree/training/work
    # JA: —— 追加：Zhaopin／Liepin／51job などの Web ページからエクスポートした HTML によくある UI のツールバー・右クリックメニューのゴミの語
    #     これらの行は履歴書の内容ではまったくなく、学校・専攻・学位・研修・職歴のすべてのフィールドで一律に除外しなければならない
    ZHILIAN_UI_GARBAGE = (
        # —— 智联（zhaopin）的工具栏 UI 文本（整行等于 或 startswith）
        # EN: —— Zhaopin toolbar UI text (whole line equal to or startswith)
        # JA: —— Zhaopin のツールバーの UI テキスト（行全体が一致、または startswith）
        "求职信", "letter_content$", "保存到我的电脑", "转发简历到邮箱", "移到简历夹",
        "推荐职位", "保存到人才储备", "放入回收箱", "添加评语", "添加标签", "举报该简历",
        "打印简历", "相似简历", "更多靠谱人才", "查看全部", "查看全部>>", "导出简历",
        "放入回收站", "下载附件简历", "下载附件", "预览附件", "收藏", "收藏简历",
        "导出", "分享", "分享到微信", "分享到微博", "分享到钉钉", "分享到LinkedIn",
        "发消息", "邀请面试", "安排面试", "邀约", "打招呼", "交换名片",
        # —— 猎聘 / 51job 的类似
        # EN: —— Similar ones for Liepin / 51job
        # JA: —— Liepin／51job の同様のもの
        "加入人才库", "加入黑名单", "标记不合适", "标记意向", "标记看过", "收藏该简历",
        "面试反馈", "面试记录", "邀约候选人", "发起沟通", "发送面试邀请", "批量操作",
        "下载简历", "简历附件", "附件下载", "下载 PDF 简历", "下载PDF",
        # —— 其它通用 UI 噪声（整行或结尾）
        # EN: —— Other generic UI noise (whole line or ending)
        # JA: —— その他の汎用的な UI のノイズ（行全体または末尾）
        "$Nummer", "$Zertifikat$", "$Bild", "$Logo$", "INCLUDEPICTURE", "MERGEFORMAT",
        "letter_content", "resume_content$",
    )
    UI_GARBAGE_EXACT = {g for g in ZHILIAN_UI_GARBAGE if "$" not in g and len(g) <= 20}
    def _is_ui_garbage_line(s: str) -> bool:
        """判断某行/字符串本身是否就是 UI 工具栏垃圾（或完全包含 UI 字符串且无有效内容）。

        EN: Decide whether a line/string itself is UI toolbar junk (or fully contains a UI string with no valid content).

        JA: 行・文字列そのものが UI ツールバーのゴミか（または UI の文字列を完全に含み、有効な内容がないか）を判定する。
        """
        s_raw = (s or "").strip()
        if not s_raw:
            return True
        if s_raw in UI_GARBAGE_EXACT:
            return True
        for g in ZHILIAN_UI_GARBAGE:
            if not g: continue
            if "$" in g:  # 特殊含 $ 标记的，包含即算垃圾
            # EN: Special entries containing a $ marker count as junk if contained
            # JA: $ の目印を含む特別なものは、含まれていればゴミとみなす
                if g in s_raw:
                    return True
            elif len(s_raw) <= len(g) + 4:
                # 长度接近且包含 → 大概率是前后带空格/标点的 UI 串
                # EN: Similar length and contained → most likely a UI string with spaces/punctuation around it
                # JA: 長さが近く含まれている → 前後に空白・句読点の付いた UI の文字列である可能性が高い
                if g in s_raw:
                    return True
        # include picture / word field 代码
        # EN: include picture / word field codes
        # JA: include picture / Word のフィールドコード
        if "INCLUDEPICTURE" in s_raw or "MERGEFORMAT" in s_raw:
            return True
        return False

    def _has_ui_garbage(s: str) -> bool:
        s_raw = (s or "").strip()
        if not s_raw:
            return False
        for g in ZHILIAN_UI_GARBAGE:
            if not g: continue
            if g in s_raw:
                return True
        return False

    BAD_SCHOOL_TOKENS = (
        "培训经历", "培训课程", "工作经历", "工作经验", "项目经历", "项目经验", "工作业绩",
        "个人信息", "基本资料", "联系方式", "个人简历", "自我评价", "求职意向",
        "实践描述", "工作描述", "活动描述", "项目描述", "工作职责", "岗位责任",
        "技能", "专业技能", "语言能力", "语言", "证书", "所获证书", "特长", "职业目标",
        "兴趣爱好", "在校学习情况", "在校实践经历",
        # 企业属性特征词黑名单（防止工作经历被当作学校）
        # EN: Blacklist of company-attribute words (to stop work history being taken as a school)
        # JA: 会社の属性を表す語のブラックリスト（職歴を学校と誤認しないため）
        "企业性质", "公司性质", "公司规模", "企业规模", "职位月薪", "期望月薪", "月薪",
        "民营", "外商独资", "国企", "国有企业", "合资", "上市公司", "股份制",
        "1000人以上", "500-999人", "100-499人", "100人以下", "20-99人", "20人以下",
        # 职务/描述/内容行 误吸
        # EN: Position/description/content lines absorbed by mistake
        # JA: 職務・説明・内容の行の誤った取り込み
        "职务描述", "职务描述：", "职务描述:", "工作职责：", "工作职责:", "工作内容：", "工作内容:",
        "职责描述：", "职责描述:", "责任描述：", "责任描述:", "职责内容：", "职责内容:",
        "工作描述：", "工作描述:", "业绩描述：", "业绩描述:", "项目描述：", "项目描述:",
        # 职务词
        # EN: Position words
        # JA: 職位の語
        "书记", "部长", "主席", "委员", "会长", "社长", "干事", "班长", "团支书", "课代表",
        "员工", "实习生", "代表", "秘书",
        "社会实践", "社会实践部", "社会实践部成员", "学生实践", "学生干部", "学生会", "学生活动",
        "实践部", "实践活动", "学生工作", "学生社团", "兼职", "勤工助学",
        "志愿者", "志愿活动", "义工", "社团活动", "校园活动", "暑期实践",
        "OPS", "R&D", "QA", "QC", "HR", "IT", "PM", "BD", "CEO", "CTO", "CFO", "COO",
        "事业部", "研发部", "销售部", "市场部", "财务部", "人事部", "人力资源部",
        "运营部", "客服部", "采购部", "行政部", "技术部", "产品部", "项目部",
    )
    DEGREE_VALUES = ("博士后", "博士", "硕士", "本科", "大专", "专科", "高中", "中专", "职高", "初中", "小学", "修士", "大卒", "専門", "短大", "mba",
                     "在职研究生", "全日制研究生", "全日制硕士", "在职硕士", "全日制本科", "函授本科", "自考本科", "成人本科",
                     "全日制大专", "函授大专", "自考大专", "成人大专", "专升本", "专接本", "专转本", "专硕", "学硕",
                     "博士后研究生", "博士研究生", "硕士研究生", "研究生")
    SCHOOL_SIGNS = ("大学", "学院", "学校", "分校", "大学校", "university", "college", "institute",
                    "中学", "高级中学", "职业高中", "职业中学", "职业技术学院", "高等专科", "广播电视大学",
                    "党校", "研修院", "进修学院", "继续教育学院")
    WORK_PRACTICE_START = ("在", "于", "期间", "曾任", "历任")
    WORK_PRACTICE_MID = ("担任", "从事", "负责", "任职", "兼任", "教师", "老师", "专员", "助理", "经理", "主管",
                         "工程师", "主任", "总监", "代表", "实习", "任职于", "就职于", "参与", "开发", "设计",
                         "实施", "运营", "销售", "采购", "客服", "文员", "秘书", "顾问")

    # —— 关键修复：①支持「从YYYY年M月到 YYYY年M月」汉字前缀；②支持双横杠 --；③支持板块标题粘连「教育背景2019.01—」「教育时间YYYY.MM」；④分隔符含汉字「到」；
    # —— ★姜海波补：⑤支持YYYY后空格再分隔符：如 "2010 /1--至今"、"2011 .3-2013. 6"（2010后面允许\s*再跟./\-/年）；⑥支持公司名粘连「：上海大众保险(500人以上)」，日期后允许「：」公司名前的中文冒号
    # EN: —— Key fix: ① support the Chinese prefix "从YYYY年M月到 YYYY年M月" (from ... to ...); ② support the double dash --; ③ support section headings stuck on, like "教育背景2019.01—" "教育时间YYYY.MM"; ④ separators include the Chinese "到" (to);
    #     —— ★Patch for a past case: ⑤ support a space after YYYY before the separator, e.g. "2010 /1--至今", "2011 .3-2013. 6" (\s* allowed after 2010 before ./\-/年); ⑥ support a company name stuck on, like "：上海大众保险(500人以上)", allowing the Chinese colon "：" before the company name after the date
    # JA: —— 重要な修正：①「从YYYY年M月到 YYYY年M月」の漢字の接頭辞に対応、② 二重ダッシュ -- に対応、③「教育背景2019.01—」「教育时间YYYY.MM」のようなセクション見出しのくっつきに対応、④ 区切りに漢字の「到」を含める
    #     —— ★過去の事例への追加修正：⑤ YYYY の後に空白を挟んでから区切りが来る形に対応（例："2010 /1--至今"、"2011 .3-2013. 6"。2010 の後に \s* を許してから ./\-/年 が続く）、⑥「：上海大众保险(500人以上)」のような会社名のくっつきに対応し、日付の後、会社名の前に全角コロン「：」を許容する
    DATE_RANGE_STRIP_PREFIX_RE = re.compile(r"^(?:从|自|起|开始|起至|教育背景|教育时间|教育经历|在校时间|工作时间|工作经历|社会实践|实践时间|培训时间|培训经历)\s*")
    DATE_RANGE_TOKEN_RE = re.compile(
        r"((?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*"
        # 右半段：允许年/月之间 多 1-3 个 杂标点（如 2014-/9、2015-//8、2016--/7 等 HTML 格式错乱）
        # EN: Right half: allow 1-3 extra stray punctuation marks between year/month (e.g. HTML garbling like 2014-/9, 2015-//8, 2016--/7)
        # JA: 右半分：年と月の間に余分な句読点が 1〜3 個あることを許容する（例：2014-/9、2015-//8、2016--/7 などの HTML の崩れ）
        r"((?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)[./\-年/\s\-]{0,5}\d{0,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?|至今|现在|Present|Current|在读)"
    )
    DATE_YEAR_RANGE_RE = re.compile(
        r"((?:19|20)\d{2})\s*(?:[\-—–~～至到‒―〜]{1,4}|-{2,}|到|至)\s*((?:19|20)\d{2}|至今|现在|Present|Current|在读)(?!\d)"
    )
    DATE_YYYYMMYYYYMM_RE = re.compile(r"((?:19|20)\d{2})((?:19|20)\d{2})(?!\d)")
    EDU_END_HEADERS = ("工作经历", "工作经验", "工作履历", "项目经历", "项目经验", "自我评价", "培训经历", "语言能力", "技能", "专业技能", "证书", "所获证书", "在校实践经历", "工作单位名称", "家庭状况")
    EDU_FORM_RE = re.compile(
        r"(博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学|博士后)\s*"
        r"(?:\/[^ ]{2,8})?"
        r"([\u4e00-\u9fffA-Za-z·\-（）() ]{2,40}?)"
        r"((?:19|20)\d{2}\s*[\-~～至到]\s*(?:19|20)\d{2}|(?:19|20)\d{8})"
        r"([\u4e00-\u9fffA-Za-z·\-（）() ]{1,40}?)"
        r"(博士|硕士|学士|本科|专科|大专|高中|中专|职高|初中|小学|博士后|MBA|MPA|JD|MD)?",
        re.I,
    )

    edus: list[dict[str, Any]] = []
    trainings: list[dict[str, Any]] = []
    seen_edu_keys: set[tuple[str, str, str]] = set()

    def _split_pipe_or_ws(s: str) -> list[str]:
        s = s.strip(" |｜")
        if not s:
            return []
        parts = [p.strip() for p in re.split(r"[|｜]", s) if p.strip()]
        if len(parts) >= 2:
            return parts
        parts2 = [p.strip() for p in re.split(r"[ \t\xa0]{2,}", s) if p.strip()]
        return parts2 if parts2 else ([s.strip()] if s.strip() else [])

    def _valid_school(s: str) -> bool:
        s = s.strip()
        # —— 新增：UI 垃圾 → 不是 学校名
        # EN: —— New: UI junk → not a school name
        # JA: —— 追加：UI のゴミ → 学校名ではない
        if _is_ui_garbage_line(s):
            return False
        if _has_ui_garbage(s) and not any(sign in s.lower() for sign in SCHOOL_SIGNS):
            return False
        # **绝对 禁止：纯 学位 词 或 纯 学历 类型 词（本科/硕士/在职研究生） 不能 是 学校！**
        # EN: **Absolutely forbidden: pure degree words or pure education-type words (本科/硕士/在职研究生: bachelor/master/in-service postgraduate) cannot be a school!**
        # JA: **絶対禁止：純粋な学位の語や学歴区分の語（本科／硕士／在职研究生：学士・修士・在職大学院生）を学校にしてはならない！**
        if s in DEGREE_VALUES:
            return False
        if not s:
            return False
        if len(s) == 1 or len(s) > 40:
            return False
        if any(k in s for k in ("企业性质", "公司性质", "规模：", "职位月薪", "月薪：")):
            return False
        if s in BAD_SCHOOL_TOKENS or s in EDU_END_HEADERS:
            return False
        if any(b == s for b in BAD_SCHOOL_TOKENS):
            return False
        if any(b in s for b in BAD_SCHOOL_TOKENS) and not any(sign in s.lower() for sign in SCHOOL_SIGNS):
            return False
        if re.fullmatch(r"\(?\d+年\d+个月\)?", s) or re.fullmatch(r"\d+-\d+人", s):
            return False
        if re.fullmatch(r"[年月.，,\-（）()\s]+", s):
            return False
        if re.match(r"^(负责|协助|组织|开发|维护|参与|制定|管理|进行|配合|完成|建立|收集|提供|推广|推进|改善|提高|拓展|沟通|协调|设计|制作|发放|招募|选址|宣传|策划|跟进|运营|建设|预算)", s):
            return False
        if re.match(r"^(在|于|期间|曾任|历任)\s*.+(担任|从事|负责|任职|兼任|教师|老师|专员|助理|经理|主管|工程师|主任|总监|代表|实习|任职于|就职于|参与|开发|设计|实施|运营|销售|采购|客服|文员|秘书|顾问)", s):
            return False
        if any(w in s for w in WORK_PRACTICE_MID) and not any(sign in s.lower() for sign in SCHOOL_SIGNS):
            return False
        CAMPUS_ROLE_OR_CLUB_WORDS = (
            "服务队", "志愿队", "志愿者", "学生会", "社团", "俱乐部", "辩论队", "球队", "同乡会",
            "勤工助学", "队员", "队长", "副队长", "部长", "副部长", "主席", "副主席", "干事",
            "团支书", "班长", "副班长", "课代表", "组织", "活动", "协管", "辅导", "公益",
            "项目", "小组", "委员会", "党支部", "团支部", "校内职务", "在校情况", "校内实践"
        )
        if any(w in s for w in CAMPUS_ROLE_OR_CLUB_WORDS) and not any(sign in s.lower() for sign in SCHOOL_SIGNS):
            return False
        if (any(comp in s for comp in ("有限公司", "股份", "集团", "公司", "工作室", "工厂", "制造厂", "分公司", "事业部", "办事处"))
            and not any(sign in s.lower() for sign in SCHOOL_SIGNS)
            and not any(d in s for d in DEGREE_VALUES)):
            return False
        _DEPT_SUFFIXES = ("部", "室", "组", "科", "处", "课", "厅", "局", "所", "站", "院", "办")
        _POSITION_WORDS = ("担当", "主管", "经理", "工程师", "助理", "专员", "主任", "总监", "负责人",
                            "专家", "代表", "店长", "职员", "营业员", "销售", "顾问", "课长", "部长",
                            "专员", "干事", "秘书", "客服", "采购", "运营", "市场", "研究员",
                            "技师", "设计师", "分析师", "顾问师", "讲师", "教授", "研究员")
        has_school_sign = any(sign in s.lower() for sign in SCHOOL_SIGNS)
        has_degree_sign = any(d in s for d in DEGREE_VALUES)
        if len(s) < 8 and not has_school_sign and not has_degree_sign and s.endswith(_DEPT_SUFFIXES):
            return False
        if not has_school_sign and not has_degree_sign and any(p in s for p in _POSITION_WORDS):
            return False
        if len(s) < 8 and not any(sign in s.lower() for sign in SCHOOL_SIGNS) and not any(d in s for d in DEGREE_VALUES):
            return False
        return True

    def _valid_major(s: str) -> bool:
        s = s.strip()
        # —— 新增：UI 垃圾 → 不是 专业名
        # EN: —— New: UI junk → not a major name
        # JA: —— 追加：UI のゴミ → 専攻名ではない
        if _is_ui_garbage_line(s):
            return False
        if _has_ui_garbage(s):
            return False
        if not s:
            return False
        if s in DEGREE_VALUES:
            return True
        if s in BAD_SCHOOL_TOKENS or s in EDU_END_HEADERS:
            return False
        if len(s) < 2 or len(s) > 40:
            return False
        if re.match(r"^\(?\d+年\d+个月\)?$", s):
            return False
        if any(k in s for k in ("工作描述", "工作内容", "工作职责", "工作业绩", "岗位职责",
                                "岗位描述", "岗位责任", "职责描述", "主要职责", "负责", "协助",
                                "参与", "主导", "汇报对象", "下属人数", "离职原因", "薪金",
                                "公司性质", "公司规模", "税前", "奖金", "津贴")):
            return False
        _POS_WORDS = ("担当", "主管", "经理", "工程师", "助理", "专员", "主任", "总监", "负责人",
                       "专家", "代表", "店长", "职员", "营业员", "销售", "顾问", "课长", "部长",
                       "干事", "秘书", "客服", "采购", "运营", "研究员", "技师", "设计师",
                       "分析师", "讲师", "教授", "副总监", "总经理", "副总经理", "CEO", "CTO")
        if any(p in s for p in _POS_WORDS) and not any(d in s for d in DEGREE_VALUES) and "专业" not in s and "学" not in s:
            return False
        return True

    def _process_date_line(line: str, i_line: int, lines_pool: list[str]) -> None:
        # —— 关键修复：先剥离「从/自/教育背景/教育时间」等前缀，防止 DATE 正则漏匹配
        # EN: —— Key fix: first strip prefixes like "从/自/教育背景/教育时间" (from / since / education background / education period) so the DATE regex does not miss matches
        # JA: —— 重要な修正：まず「从／自／教育背景／教育时间」などの接頭辞を除き、DATE の正規表現がマッチを取りこぼさないようにする
        line_stripped = DATE_RANGE_STRIP_PREFIX_RE.sub("", line).strip()
        m_d = DATE_RANGE_TOKEN_RE.search(line_stripped)
        start_raw, end_raw = "", ""
        m_start, m_end = -1, -1
        if not m_d:
            # —— 新增 Fallback 1：短结尾日期格式，如「2014.04.15—06.30」「2014/07/25-08/31」「2014年7月25日~8月31日」
            #    仅 end 部分缺少年份（只有 M.D / M月D日），此时复用 start 的 year
            # EN: —— New Fallback 1: short-ending date formats like "2014.04.15—06.30", "2014/07/25-08/31", "2014年7月25日~8月31日"
            #        Only the end part lacks the year (only M.D / M月D日); reuse the start's year in this case
            # JA: —— 追加の Fallback 1：「2014.04.15—06.30」「2014/07/25-08/31」「2014年7月25日~8月31日」のような末尾の短い日付形式
            #        end 部分だけ年がない（M.D／M月D日 だけ）場合は、start の年を再利用する
            SHORTEND_RE = re.compile(
                r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})\s*(?:[./月\-]\s*(\d{1,2})\s*日?)?\s*"
                r"(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*"
                r"(\d{1,2})\s*[./月\-]\s*(\d{1,2})\s*日?\s*(?!\d)"
            )
            m_sh = SHORTEND_RE.search(line_stripped)
            if m_sh:
                s_y, s_m, s_d, e_m, e_d = m_sh.group(1), m_sh.group(2), (m_sh.group(3) or ""), m_sh.group(4), m_sh.group(5)
                # 伪装成 {start_raw, end_raw} 通过 _format_ym
                # EN: Disguise it as {start_raw, end_raw} and pass it through _format_ym
                # JA: {start_raw, end_raw} に見せかけて _format_ym に通す
                start_raw = f"{s_y}.{s_m}.{s_d}" if s_d else f"{s_y}.{s_m}"
                end_raw = f"{s_y}.{e_m}.{e_d}"
                m_start, m_end = m_sh.start(), m_sh.end()
            if not m_sh:
                # **Fallback**：若 带 年月 的 DATE_RANGE_TOKEN_RE 不 匹配（如 仅 年份 2011-2013），
                # 则 用 DATE_YEAR_RANGE_RE 再 试，保证 不 漏 仅 年份 格式 的 记录。
                # EN: **Fallback**: if the year-month DATE_RANGE_TOKEN_RE does not match (e.g. years only, 2011-2013),
                #     try DATE_YEAR_RANGE_RE again so records in a years-only format are not missed.
                # JA: **Fallback**：年月付きの DATE_RANGE_TOKEN_RE がマッチしない場合（例：年だけの 2011-2013）は、
                #     DATE_YEAR_RANGE_RE で再度試し、年だけの形式のレコードを取りこぼさないようにする。
                m_d = DATE_YEAR_RANGE_RE.search(line_stripped)
                if not m_d:
                    return
                start_raw, end_raw = m_d.group(1), m_d.group(2)
                m_start, m_end = m_d.start(), m_d.end()
        else:
            start_raw, end_raw = m_d.group(1), m_d.group(2)
            m_start, m_end = m_d.start(), m_d.end()
        start_ym = _format_ym(start_raw)
        # 教育板块：「在读」等同于 至今（不填 end_ym）
        # EN: Education section: "在读" (currently studying) equals 至今 (present) (do not fill end_ym)
        # JA: 学歴欄：「在读」（在学中）は 至今（現在）と同じ扱い（end_ym は入れない）
        end_ym = "" if end_raw in ("至今", "现在", "Present", "Current", "在读") else _format_ym(end_raw)

        tail = line_stripped[m_end:].strip()
        head = line_stripped[: m_start].strip()  # 与 line_stripped 保持一致
        # EN: Keep consistent with line_stripped
        # JA: line_stripped と一致させる

        school_name = ""
        major = ""
        degree = ""
        edu_type = ""

        tail_clean = tail
        if tail_clean.startswith("：") or tail_clean.startswith(":"):
            tail_clean = tail_clean[1:].strip()
        # 破折号拆分：「学校名—专业名」拆成两部分
        # EN: Split on dashes: split "school name—major name" into two parts
        # JA: ダッシュで分割する：「学校名—専攻名」を 2 つに分ける
        _DASH_SPLIT_RE = re.compile(r"^(.+?)(?:[-—–‒―〜]{1,4})\s*(.+)$")
        m_dash = _DASH_SPLIT_RE.match(tail_clean)
        if m_dash and not ("|" in tail_clean or "｜" in tail_clean):
            _left, _right = m_dash.group(1).strip(), m_dash.group(2).strip()
            if _left and _right and len(_right) <= 50 and (_valid_school(_left) or any(s in _left.lower() for s in SCHOOL_SIGNS)):
                tail_clean = f"{_left} | {_right}"

        tail_parts = _split_pipe_or_ws(tail_clean)
        head_parts = _split_pipe_or_ws(head)
        last_head = head_parts[-1] if head_parts else ""

        cand_school = ""
        cand_parts_from_tail: list[str] = []
        head_non_school_parts: list[str] = []
        # 三列表格「日期 学校 专业」：日期在最前，head_parts空，学校/专业都在 tail
        # EN: Three-column table "date school major": the date comes first, head_parts is empty, school/major are both in tail
        # JA: 3 列の表「日付 学校 専攻」：日付が先頭で head_parts は空、学校・専攻はどちらも tail にある
        if not head_parts and len(tail_parts) >= 2:
            for _i, _tp in enumerate(tail_parts):
                if _valid_school(_tp):
                    cand_school = _tp
                    cand_parts_from_tail = [tail_parts[_j] for _j in range(len(tail_parts)) if _j != _i and tail_parts[_j].strip()]
                    break
            if not cand_school and _valid_school(tail_parts[0]):
                cand_school = tail_parts[0]
                cand_parts_from_tail = tail_parts[1:]
            elif not cand_school:
                cand_parts_from_tail = tail_parts
        else:
            # 学校在日期前面（head_parts）
            # EN: The school is before the date (head_parts)
            # JA: 学校が日付の前にある（head_parts）
            if head_parts:
                for idx, hp in enumerate(head_parts):
                    if any(sign in hp.lower() for sign in SCHOOL_SIGNS) and _valid_school(hp):
                        cand_school = hp
                        head_non_school_parts = [p for i, p in enumerate(head_parts) if i != idx and p.strip()]
                        break
                if not cand_school:
                    for idx, hp in enumerate(head_parts):
                        if _valid_school(hp):
                            cand_school = hp
                            head_non_school_parts = [p for i, p in enumerate(head_parts) if i != idx and p.strip()]
                            break
                    if not cand_school and _valid_school(last_head):
                        cand_school = last_head
            if not cand_school and tail_parts:
                if _valid_school(tail_parts[0]):
                    cand_school = tail_parts[0]
                    cand_parts_from_tail = tail_parts[1:]
                else:
                    cand_parts_from_tail = tail_parts
            else:
                cand_parts_from_tail = tail_parts
            if head_non_school_parts:
                cand_parts_from_tail = list(head_non_school_parts) + list(cand_parts_from_tail)

        if not cand_school:
            # —— 先向后读 5 行找 KV（毕业学校/时间/专业/学位）
            # EN: —— First read 5 lines ahead to find KV pairs (graduated school/time/major/degree)
            # JA: —— まず後ろに 5 行読んで KV（卒業校・期間・専攻・学位）を探す
            for k in range(1, 5):
                if i_line + k >= len(lines_pool):
                    break
                nxt = lines_pool[i_line + k].strip()
                if DATE_RANGE_TOKEN_RE.search(nxt) or DATE_YEAR_RANGE_RE.search(nxt):
                    break
                if nxt in EDU_END_HEADERS or nxt in ("教育背景", "教育经历", "在校学习情况"):
                    continue
                # —— 关键修复：跳过 UI 垃圾行（求职信、保存到我的电脑等）
                # EN: —— Key fix: skip UI junk lines (cover letter, save to my computer, etc.)
                # JA: —— 重要な修正：UI のゴミの行（応募書類、PC に保存など）をスキップする
                if _is_ui_garbage_line(nxt):
                    continue
                if _has_ui_garbage(nxt):
                    continue
                # —— 修复：支持中英混合 KV 标签「毕业学校（Graduate from）：」「专业（Major）：」
                # EN: —— Fix: support mixed Chinese-English KV labels "毕业学校（Graduate from）：" and "专业（Major）："
                # JA: —— 修正：中英混在の KV ラベル「毕业学校（Graduate from）：」「专业（Major）：」に対応する
                m_sch = re.search(r"(?:院校|学校|毕业院校|Graduate\s*from|毕业学校)[^:：]*[:：]\s*([^\n/│|]+)", nxt)
                m_maj = re.search(r"(?:主修专业|专业|Major)[^:：]*[:：]\s*([^\n/│|]+)", nxt)
                m_deg = re.search(r"(?:学历|学位|Degree|最高学历)[^:：]*[:：]\s*([^\n/│|]+)", nxt)
                if m_sch:
                    cand_school = re.sub(r"[（(].*?[）)]", "", m_sch.group(1).strip()).strip()
                if m_maj:
                    major = re.sub(r"[（(].*?[）)]", "", m_maj.group(1).strip()).strip()
                if m_deg:
                    degree = re.sub(r"[（(].*?[）)]", "", m_deg.group(1).strip()).strip()
                if not cand_school and _valid_school(nxt):
                    # —— 关键：如果 nxt 是「专业：XXX」「学历：XXX」这种 KV 行（即使通过 _valid_school），也不当学校名
                    #   如「专业：日语+软件」中的冒号左侧是 KV 标签 → 跳过
                    # EN: —— Key: if nxt is a KV line like "专业：XXX" (major:) or "学历：XXX" (degree:) (even if it passes _valid_school), do not take it as a school name
                    #       e.g. in "专业：日语+软件" the left side of the colon is a KV label → skip
                    # JA: —— 重要：nxt が「专业：XXX」「学历：XXX」のような KV の行なら（_valid_school を通っても）学校名にしない
                    #       例：「专业：日语+软件」のコロンの左側は KV のラベル → スキップ
                    _is_kv_labeled = False
                    if "：" in nxt or ":" in nxt:
                        _left = re.split(r"[:：]", nxt, maxsplit=1)[0].strip()
                        if _left and re.match(r"^(专业|学历|学位|学校|是否统招|GPA|培养|类型|方式|语种|等级|证书|备注|说明|入学|毕业|时间|学制|入学方式|毕业时间|入学时间|专业类别|专业类型)$", _left):
                            _is_kv_labeled = True
                    if not _is_kv_labeled:
                        cand_school = nxt
                        if i_line + k + 1 < len(lines_pool):
                            nn = lines_pool[i_line + k + 1].strip()
                            # 下一行也过滤一次 UI 垃圾
                            # EN: Filter UI junk on the next line too
                            # JA: 次の行でも UI のゴミを除外する
                            if _is_ui_garbage_line(nn) or _has_ui_garbage(nn):
                                nn = ""
                            if nn and _valid_major(nn) and not DATE_RANGE_TOKEN_RE.search(nn) and nn not in EDU_END_HEADERS:
                                major = nn
                        break
                # —— 短行匹配：「专业：市场营销」「学历：本科」
                # EN: —— Short-line matching: "专业：市场营销" (major: marketing), "学历：本科" (degree: bachelor)
                # JA: —— 短い行のマッチ：「专业：市场营销」（専攻：マーケティング）、「学历：本科」（学歴：学士）
                if re.search(r"(?:^专业|^学历|^学位)\s*[:：]", nxt):
                    if nxt.startswith("专业"):
                        major = (nxt.split("：", 1)[-1] if "：" in nxt else nxt.split(":", 1)[-1]).strip("（）()| ")
                    elif "学历" in nxt or "学位" in nxt:
                        degree = (nxt.split("：", 1)[-1] if "：" in nxt else nxt.split(":", 1)[-1]).strip("（）()| ")
                    continue
            # —— 新增：向前读 5 行找 KV（兼容沈莉君「毕业学校」在日期行前面的多行分散 KV 格式）
            # EN: —— New: read 5 lines back to find KV pairs (for a multi-line scattered KV format in a past case where "毕业学校" (graduated school) precedes the date line)
            # JA: —— 追加：前に 5 行読んで KV を探す（過去の事例のように「毕业学校」（卒業校）が日付行の前にある複数行に散らばった KV 形式に対応）
            if not cand_school:
                # 支持「标签：值」在同一行
                # EN: Support "label: value" on the same line
                # JA: 同じ行の「ラベル：値」に対応する
                LABEL_HAS_VALUE_RE = {
                    "school": re.compile(r"(?:院校|学校|毕业院校|Graduate\s*from|毕业学校|毕业院校)[^:：]*[:：]\s*([^\n/│|]+)"),
                    "major": re.compile(r"(?:主修专业|专业|Major)[^:：]*[:：]\s*([^\n/│|]+)"),
                    "degree": re.compile(r"(?:学历|学位|Degree|最高学历)[^:：]*[:：]\s*([^\n/│|]+)"),
                }
                # 支持标签单独占一行、值在后面紧邻行（如 毕业学校 \n（Graduate from）：\n 井冈山大学&同济大学）
                # EN: Support the label on its own line with the value on an adjacent following line (e.g. 毕业学校 \n（Graduate from）：\n 井冈山大学&同济大学)
                # JA: ラベルが単独の行にあり、値がすぐ後の行にある形に対応する（例：毕业学校 \n（Graduate from）：\n 井冈山大学&同济大学）
                LABEL_BARE_RE = {
                    "school": re.compile(r"^毕业学校|^毕业院校|^院校|^学校$|^Graduate\s*from$|^\s*[（(]\s*Graduate\s*from\s*[）)]\s*[:：]?\s*$", re.I),
                    "major": re.compile(r"^专业$|^主修专业$|^Major$|^\s*[（(]\s*Major\s*[）)]\s*[:：]?\s*$", re.I),
                    "degree": re.compile(r"^学历$|^学位$|^Degree$|^\s*[（(]\s*Degree\s*[）)]\s*[:：]?\s*$", re.I),
                }
                for k in range(1, 8):
                    if i_line - k < 0:
                        break
                    prev = lines_pool[i_line - k].strip()
                    if DATE_RANGE_TOKEN_RE.search(prev) or DATE_YEAR_RANGE_RE.search(prev):
                        break
                    if prev in EDU_END_HEADERS or prev in ("教育背景", "教育经历", "在校学习情况"):
                        continue
                    if _is_ui_garbage_line(prev) or _has_ui_garbage(prev):
                        continue
                    # 情况 A：标签: 值 在同一行（通用 KV）
                    # EN: Case A: label: value on the same line (generic KV)
                    # JA: ケース A：同じ行に「ラベル：値」（汎用の KV）
                    if not cand_school:
                        m_sch_p = LABEL_HAS_VALUE_RE["school"].search(prev)
                        if m_sch_p:
                            cand_school = re.sub(r"[（(].*?[）)]", "", m_sch_p.group(1).strip()).strip()
                    if not major:
                        m_maj_p = LABEL_HAS_VALUE_RE["major"].search(prev)
                        if m_maj_p:
                            major = re.sub(r"[（(].*?[）)]", "", m_maj_p.group(1).strip()).strip()
                    if not degree:
                        m_deg_p = LABEL_HAS_VALUE_RE["degree"].search(prev)
                        if m_deg_p:
                            degree = re.sub(r"[（(].*?[）)]", "", m_deg_p.group(1).strip()).strip()
                    if re.search(r"(?:^专业|^学历|^学位)\s*[:：]", prev):
                        if prev.startswith("专业") and not major:
                            major = (prev.split("：", 1)[-1] if "：" in prev else prev.split(":", 1)[-1]).strip("（）()| ")
                        elif ("学历" in prev or "学位" in prev) and not degree:
                            degree = (prev.split("：", 1)[-1] if "：" in prev else prev.split(":", 1)[-1]).strip("（）()| ")
                    # 情况 B：prev 是纯标签行（无值）→ 向后 1..k-1 行 找最近的非标签、非日期、非空行当值
                    # EN: Case B: prev is a pure label line (no value) → look 1..k-1 lines ahead for the nearest line that is not a label, date or empty, and use it as the value
                    # JA: ケース B：prev がラベルだけの行（値なし）→ 1..k-1 行先から、ラベル・日付・空でない最も近い行を探して値にする
                    for fld, label_re in LABEL_BARE_RE.items():
                        if label_re.fullmatch(prev):
                            # 从 prev 的下一行起，扫描到当前 date 行的前一行，找最近的有效 value 行
                            # EN: Scan from the line after prev to the line before the current date line, looking for the nearest valid value line
                            # JA: prev の次の行から現在の日付行の前の行までスキャンし、最も近い有効な値の行を探す
                            for fwd in range(i_line - k + 1, i_line):
                                if fwd >= len(lines_pool):
                                    break
                                fwdline = lines_pool[fwd].strip()
                                # 跳过纯标签、日期行、空行、UI 垃圾、section header
                                # EN: Skip pure labels, date lines, empty lines, UI junk and section headers
                                # JA: ラベルだけの行・日付行・空行・UI のゴミ・セクション見出しはスキップする
                                if not fwdline:
                                    continue
                                if DATE_RANGE_TOKEN_RE.search(fwdline) or DATE_YEAR_RANGE_RE.search(fwdline):
                                    break
                                if any(LABEL_BARE_RE[f2].fullmatch(fwdline) for f2 in LABEL_BARE_RE):
                                    continue
                                if _is_ui_garbage_line(fwdline) or _has_ui_garbage(fwdline):
                                    continue
                                if fwdline in EDU_END_HEADERS:
                                    break
                                # 有效 value：去掉括号注释，按字段判断有效性
                                # EN: Valid value: remove bracketed notes and judge validity per field
                                # JA: 有効な値：括弧の注記を除き、フィールドごとに有効性を判定する
                                raw_val = re.sub(r"[（(].*?[）)]", "", fwdline).strip(" ：:，,|｜/｜-~～·・")
                                if not raw_val:
                                    continue
                                if fld == "school" and not cand_school:
                                    # 至少 2 字且含 大学/学院/学校/& 或通过 _valid_school
                                    # EN: At least 2 characters and containing 大学/学院/学校/&, or passing _valid_school
                                    # JA: 2 文字以上で 大学／学院／学校／& を含むか、_valid_school を通る
                                    if (len(raw_val) >= 2 and ("&" in raw_val or any(s in raw_val.lower() for s in SCHOOL_SIGNS))) or _valid_school(raw_val):
                                        cand_school = raw_val
                                    break
                                elif fld == "major" and not major:
                                    if _valid_major(raw_val):
                                        major = raw_val
                                    break
                                elif fld == "degree" and not degree:
                                    if raw_val in DEGREE_VALUES or len(raw_val) <= 6:
                                        degree = raw_val
                                    break
                    # —— 新增：情况 C：prev 是学校名独立行（如顾先生「大连交通大学」在日期括号前一行，无KV冒号）
                    # EN: —— New: case C: prev is a standalone school-name line (e.g. in a past case, "大连交通大学" on the line before the bracketed date, without a KV colon)
                    # JA: —— 追加：ケース C：prev が学校名だけの独立した行（過去の事例では括弧付きの日付の前の行に「大连交通大学」があり、KV のコロンがない）
                    if not cand_school:
                        # 去掉前后括号包裹（如 （大连交通大学））
                        # EN: Remove surrounding brackets (e.g. （大连交通大学）)
                        # JA: 前後を包む括弧を除く（例：（大连交通大学））
                        prev_trim = re.sub(r"^[（(]+|[）)]+$", "", prev).strip()
                        # 去掉末尾全/半角冒号
                        # EN: Remove trailing full-/half-width colons
                        # JA: 末尾の全角・半角のコロンを除く
                        prev_trim = re.sub(r"[:：]+$", "", prev_trim).strip()
                        if prev_trim and 2 <= len(prev_trim) <= 40:
                            # 必须不像句子：不含常见句子标点（，。；？！、…）
                            # EN: Must not look like a sentence: no common sentence punctuation (，。；？！、…)
                            # JA: 文のように見えてはならない：よくある文の句読点（，。；？！、…）を含まない
                            if not re.search(r"[，,。.；;？?！!、…]", prev_trim):
                                _looks_like_school = False
                                # 含 SCHOOL_SIGNS 或 valid_school 直接过
                                # EN: Contains SCHOOL_SIGNS or passes valid_school → accept directly
                                # JA: SCHOOL_SIGNS を含むか valid_school を通れば、そのまま通す
                                if any(s in prev_trim.lower() for s in SCHOOL_SIGNS) or _valid_school(prev_trim):
                                    _looks_like_school = True
                                # 兜底：2-15字符、含中文/大写英文字母开头、不含明显职位/职责词
                                # EN: Fallback: 2-15 characters, starting with Chinese or an uppercase English letter, without obvious position/duty words
                                # JA: 最終手段：2〜15 文字で、漢字か英大文字で始まり、明らかな職位・職務の語を含まない
                                elif 2 <= len(prev_trim) <= 15 and re.search(r"^[\u4e00-\u9fa5A-Z]", prev_trim):
                                    _ban_re = re.compile(r"("
                                                    r"负责|管理|开发|维护|担当|主管|经理|工程师|顾问|专员|助理|组长|主任|"
                                                    r"课长|部长|社长|会长|主席|设计师|分析师|培训|课程|项目|上线|导入|实施|"
                                                    r"咨询|服务|生产|销售|市场|采购|品质|业务|工程|技术|营业|财务|"
                                                    r"人事|行政|客服|物流|资材|制造|营业支援|生产管理|生产技术|销售管理|"
                                                    r"^\d+[元万千个名]|元/月|万/月|薪资|月薪|年薪|部门|科|部|室|课|组|系|支店|"
                                                    r"営業|経理|総務|財務|生産|品質)")
                                    if not _ban_re.search(prev_trim):
                                        _looks_like_school = True
                                if _looks_like_school:
                                    cand_school = prev_trim
        if not cand_school:
            return

        school_name = cand_school.strip()
        for part in cand_parts_from_tail:
            part = part.strip()
            if not part:
                continue
            m_md = re.match(r"^(.+?)[（(]\s*(博士后|博士|硕士|本科|大专|专科|高中|中专|职高|初中|小学|修士|大卒|専門|短大)\s*[）)]\s*$", part)
            if m_md:
                if not major:
                    major = m_md.group(1).strip("（）()| ")
                if not degree:
                    degree = m_md.group(2).strip()
                continue
            if part in DEGREE_VALUES:
                if not degree:
                    degree = part
                continue
            if part.startswith("专业：") or part.startswith("专业:"):
                major = (part.split("：", 1)[-1] if "：" in part else part.split(":", 1)[-1]).strip("（）()| ")
                continue
            if part.startswith("学历：") or part.startswith("学历:"):
                degree = (part.split("：", 1)[-1] if "：" in part else part.split(":", 1)[-1]).strip("（）()| ")
                continue
            if part.startswith("是否统招：") or part.startswith("是否统招:"):
                edu_type = "全日制大学" if "是" in part else "非全日制大学"
                continue
            if not major and _valid_major(part):
                major = part
        if "：" in school_name and not any(sign in school_name.lower() for sign in SCHOOL_SIGNS):
            left, right = school_name.split("：", 1)
            if _valid_school(right) and not _valid_school(left):
                school_name = right.strip()
        # **通用 归一化：去掉 学校名/公司名 末尾 多余 的 全/半角 冒号、分隔符（如 "复旦大学：" → "复旦大学"）**
        # EN: **Generic normalisation: remove superfluous trailing full-/half-width colons and separators from school/company names (e.g. "复旦大学：" → "复旦大学")**
        # JA: **汎用的な正規化：学校名・会社名の末尾にある余分な全角・半角のコロンや区切りを除く（例：「复旦大学：」→「复旦大学」）**
        school_name = re.sub(r"[\s:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", (school_name or "").strip())

        if not _valid_school(school_name):
            return

        key = (start_ym, end_ym, school_name)
        if key in seen_edu_keys:
            return
        seen_edu_keys.add(key)

        is_training = (any(k in school_name for k in training_keywords)
                       or any(k in (major or "").lower() for k in cert_keywords))
        if is_training and school_name:
            trainings.append({
                "sequence_no": len(trainings) + 1,
                "organization_name": school_name,
                "training_name": major or school_name,
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": major if any(k in (major or "").lower() for k in ("证书", "资格", "内审员", "证")) else "",
                "description": major,
            })
            return
        if major and "|" in major:
            m_parts = [p.strip() for p in major.split("|") if p.strip()]
            deg_cand = [p for p in m_parts if any(d in p for d in ("本科", "大专", "硕士", "博士", "专科", "中专", "高中", "学士"))]
            maj_cand = [p for p in m_parts if p not in deg_cand]
            if deg_cand and not degree:
                degree = deg_cand[0]
            if maj_cand:
                major = " | ".join(maj_cand)
        rank, etype = normalize_degree_rank(degree)
        edus.append({
            "school_name": school_name,
            "school_major_name": major or "",
            "school_degree_type": degree or "",
            "school_degree_rank": rank or "4",
            "school_education_type": etype or edu_type or "",
            "school_start_ym": start_ym,
            "school_end_ym": end_ym,
            # 顶层 education_info 快照用
            # EN: Used for the top-level education_info snapshot
            # JA: トップレベルの education_info のスナップショット用
            "school_start_date": start_ym,
            "school_end_date": end_ym,
        })

    def _add_edu_entry(school: str, major: str, degree: str, start_ym: str, end_ym: str, edu_type: str = "") -> None:
        if not _valid_school(school):
            return
        key = (start_ym, end_ym, school)
        if key in seen_edu_keys:
            return
        seen_edu_keys.add(key)
        is_training = (any(k in school for k in training_keywords)
                       or any(k in (major or "").lower() for k in cert_keywords))
        if is_training:
            trainings.append({
                "sequence_no": len(trainings) + 1,
                "organization_name": school,
                "training_name": major or school,
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": major if any(k in (major or "").lower() for k in ("证书", "资格", "内审员", "证")) else "",
                "description": major,
            })
            return
        if major and "|" in major:
            m_parts = [p.strip() for p in major.split("|") if p.strip()]
            deg_cand = [p for p in m_parts if any(d in p for d in ("本科", "大专", "硕士", "博士", "专科", "中专", "高中", "学士"))]
            maj_cand = [p for p in m_parts if p not in deg_cand]
            if deg_cand and not degree:
                degree = deg_cand[0]
            if maj_cand:
                major = " | ".join(maj_cand)
        rank, etype = normalize_degree_rank(degree)
        edus.append({
            "school_name": school,
            "school_major_name": major or "",
            "school_degree_type": degree or "",
            "school_degree_rank": rank or "4",
            "school_education_type": etype or edu_type or "",
            "school_start_ym": start_ym,
            "school_end_ym": end_ym,
            "school_start_date": start_ym,
            "school_end_date": end_ym,
        })

    # 先处理 求职申请表 EDU_FORM_RE
    # EN: First handle the job application form EDU_FORM_RE
    # JA: まず求職申込書の EDU_FORM_RE を処理する
    if block_edu_form:
        for m in EDU_FORM_RE.finditer(block_edu_form):
            _deg1, school, date_str, major, _deg2 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            school = school.strip()
            major = major.strip()
            degree = _deg2 or _deg1
            start_ym, end_ym = "", ""
            if len(date_str) == 8 and date_str.isdigit():
                start_ym = date_str[:4] + ".09"
                end_ym = date_str[4:8] + ".06"
            else:
                m_year = DATE_YEAR_RANGE_RE.search(date_str)
                if m_year:
                    start_ym = m_year.group(1) + ".09"
                    end_ym = m_year.group(2) + ".06"
            if _valid_school(school):
                _add_edu_entry(school, major, degree, start_ym, end_ym)

    # 优先用 block_main（隔离教育板块）
    # EN: Prefer block_main (the isolated education section)
    # JA: block_main（分離した学歴欄）を優先する
    if block_main:
        lines = [l.strip() for l in block_main.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line):
                _process_date_line(line, i, lines)
    else:
        # —— 修复：如果 split_resume_sections 没切出板块，fallback 到整个入参 text 逐行扫日期
        # 此时 text 已经是上层切好的 edu_sec_text，不会越界
        # EN: —— Fix: if split_resume_sections did not cut out a section, fall back to scanning the whole input text line by line for dates
        #     At this point text is already the edu_sec_text cut by the upper layer, so it will not go out of bounds
        # JA: —— 修正：split_resume_sections がセクションを切り出せなかった場合は、入力の text 全体を行ごとにスキャンして日付を探す方式に戻す
        #     この時点の text は上位で切り出し済みの edu_sec_text なので、範囲外に出ることはない
        lines_fallback = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines_fallback):
            if DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line):
                _process_date_line(line, i, lines_fallback)

    # 严禁跑全局 global_lines_pool！确保绝不出界去抓工作或项目经历。
    # EN: Never run over the global global_lines_pool! Make sure we never go out of bounds and grab work or project history.
    # JA: グローバルの global_lines_pool を走査することは厳禁！範囲外に出て職歴やプロジェクト経験を取ってしまうことが絶対にないようにする。

    # ======= 子块 4：顶部键值对补漏 =======
    # EN: ======= Sub-block 4: fill gaps from key-value pairs at the top =======
    # JA: ======= サブブロック 4：冒頭のキーと値のペアから漏れを補う =======
    def _top_kv(label: str) -> str:
        m = re.search(rf"{label}\s*[:：]?\s*([^\s☆◇◆★|│\n\r]{{2,30}})", text)
        return m.group(1).strip() if m else ""

    top_school = _top_kv(r"(?:毕业学校|学\s*校|所在学校|就\s*读\s*学\s*校)")
    top_major = _top_kv(r"专\s*业")
    top_degree = _top_kv(r"(?:学\s*历|学历学位|最高学历|最\s*高\s*学\s*历|学\s*位|学位)")
    if "|" in top_degree and not top_major:
        parts = top_degree.split("|", 1)
        if parts[0].strip() in DEGREE_VALUES:
            top_degree = parts[0].strip()
            if not top_major:
                top_major = parts[1].strip()
    if "|" in top_major and top_major.split("|")[0].strip() in DEGREE_VALUES and not top_degree:
        parts = top_major.split("|", 1)
        top_degree = parts[0].strip()
        top_major = parts[1].strip()
    top_start_ym = _top_kv(r"(?:入学时间|入校时间|开始时间)")
    top_end_ym = _top_kv(r"(?:毕业时间|离校时间|结束时间)")
    if top_school and _valid_school(top_school) and not any(
        (e.get("school_name") or "") == top_school for e in edus
    ):
        deg_clean = top_degree if top_degree in DEGREE_VALUES else ""
        _add_edu_entry(
            top_school,
            top_major if _valid_major(top_major) else "",
            deg_clean,
            _format_ym(top_start_ym) if top_start_ym else "",
            _format_ym(top_end_ym) if top_end_ym else "",
        )

    # ======= 子块 5：头部行补漏（如：郑州大学 | 电气工程及其自动化 | 本科）=======
    # EN: ======= Sub-block 5: fill gaps from header lines (e.g. 郑州大学 | 电气工程及其自动化 | 本科) =======
    # JA: ======= サブブロック 5：冒頭の行から漏れを補う（例：郑州大学 | 电气工程及其自动化 | 本科）=======
    if not edus:
        hdr = sections.get("header", "")
        for line in hdr.splitlines()[:15]:
            line = line.strip()
            if not line:
                continue
            if any(k in line for k in ("籍贯", "居住", "地址", "电话", "联系", "手机", "月薪", "期望")):
                continue
            parts = [p.strip() for p in re.split(r"[|｜]", line) if p.strip()]
            if len(parts) >= 2:
                cand_sch = parts[0]
                cand_maj = parts[1]
                cand_deg = parts[2] if len(parts) >= 3 else ""
                if any(sign in cand_sch.lower() for sign in SCHOOL_SIGNS) and _valid_school(cand_sch):
                    rank, etype = normalize_degree_rank(cand_deg)
                    deg_val = cand_deg if rank else ""
                    _add_edu_entry(cand_sch, cand_maj if _valid_major(cand_maj) else "", deg_val, "", "")
                    break

    # ======= 子块 6：培训经历表格粘连（冷峰案例：「时间地点培训内容2013.6深圳股权激励2014.8北京TTT2014.12杭州企业营销策划」）=======
    # EN: ======= Sub-block 6: stuck-together training tables (a past case: "时间地点培训内容2013.6深圳股权激励2014.8北京TTT2014.12杭州企业营销策划" (time, place, training content, ...)) =======
    # JA: ======= サブブロック 6：くっついた研修歴の表（過去の事例：「时间地点培训内容2013.6深圳股权激励2014.8北京TTT2014.12杭州企业营销策划」（期間・場所・研修内容…））=======
    def _extract_glued_trainings(tx: str):
        out: list[dict[str, Any]] = []
        date_token = r"((?:19|20)\d{2})[./年\-](\d{1,2})(?:[./年\-](\d{1,2}))?"
        for m_dt in re.finditer(date_token, tx):
            rest = tx[m_dt.end():]
            next_dt = re.search(date_token, rest)
            seg_end = (m_dt.end() + next_dt.start()) if next_dt else (m_dt.end() + len(rest))
            seg = tx[m_dt.end(): seg_end].strip().lstrip(" :：,，|│ \t")
            y, mo, d = m_dt.group(1), m_dt.group(2), (m_dt.group(3) or "")
            start_ym = _format_ym(f"{y}.{mo}" if not d else f"{y}.{mo}.{d}")
            if len(seg) >= 2:
                loc, proj = "", seg
                for loclen in (4, 3, 2):
                    if len(seg) >= loclen + 1:
                        cand_loc = seg[:loclen]
                        cand_proj = seg[loclen:].strip()
                        if cand_proj and len(cand_proj) >= 2 and not cand_proj.startswith(("年", "月")):
                            loc, proj = cand_loc, cand_proj
                            break
                proj = proj.strip(" ：:，,。.!！？?；;|│[]【】()（）")
                # —— 关键修复：拒绝明显垃圾的 training_name（短分隔符、月份残片、无汉字/英文有效词）
                # EN: —— Key fix: reject obviously junk training_name values (short separators, month fragments, no valid Chinese/English words)
                # JA: —— 重要な修正：明らかにゴミの training_name（短い区切り、月の断片、有効な漢字・英単語がないもの）を拒否する
                GARBAGE_PROJ_RE = re.compile(r"^[\-—–~～至到‒―〜\-=、·・・|│/\\()（）\[\]【】<>《》,，.。:：;；!！?？'\"` \t\n\r]+$")
                MONTH_FRAG_RE = re.compile(r"^\d*年?\d*月?(?:[~～\-—]|月?~?|～?月?)?$")
                if (not proj
                    or len(proj) <= 1
                    or GARBAGE_PROJ_RE.fullmatch(proj)
                    or MONTH_FRAG_RE.fullmatch(proj)
                    or proj in ("年", "月", "月~", "月-", "～月", "年月", "-月", "月～", "~~", "--")):
                    continue
                # 过滤纯公司/学校/部门描述（真正的培训名应该是课程/证书/训练主题）
                # EN: Filter pure company/school/department descriptions (a real training name should be a course/certificate/training topic)
                # JA: 会社・学校・部署の説明だけのものを除外する（本当の研修名はコース・資格・研修テーマであるはず）
                SMELL_ORG_NOT_TRAIN = ("有限公司", "股份公司", "集团", "事业部", "办事处",
                                       "大学", "学院", "学校", "校区", "教学点", "医院",
                                       "小学", "中学", "高中", "中专", "大专", "本科", "硕士", "博士",
                                       "技术部", "人事部", "财务部", "销售部", "市场部", "生产部", "管理部", "运营部")
                if any(k in proj for k in SMELL_ORG_NOT_TRAIN) and not any(
                    k in proj for k in ("课程", "培训", "研修", "讲座", "认证", "证书", "资格", "考试", "训练", "内训", "外训")
                ):
                    # 如果看起来像组织机构名但没培训关键词 → 跳过，避免把学校/公司当 training_name
                    # EN: If it looks like an organisation name but has no training keyword → skip, so schools/companies are not taken as training_name
                    # JA: 組織名のように見えるが研修のキーワードがない → スキップし、学校や会社を training_name にしない
                    pass
                else:
                    if proj and len(proj) >= 2 and not any(
                        (proj == (t.get("training_name") or t.get("name") or "")
                         and start_ym == (t.get("start_ym") or t.get("training_start_ym") or ""))
                        for t in trainings
                    ):
                        out.append({
                            "training_name": proj,
                            "organization_name": loc,
                            "start_ym": start_ym,
                            "end_ym": "",
                            "description": "",
                        })
        return out

    tr_block = ""
    m_tr = re.search(
        r"(?:培训经历|培训|训练|学习经历|课程经历|内训经历)\s*(?:：|:)?\s*\n?(.*?)(?=\n\s*(?:工作经历|工作经验|教育经历|项目经历|自我评价|求职意向|语言|技能|所获证书|证书|特长|语言能力|个人简历|个人评价|工作描述|个人概况|家庭状况|\Z))",
        text, re.S | re.I,
    )
    if m_tr:
        tr_block = m_tr.group(1).strip()
    all_text_lines = [l.strip() for l in text.splitlines() if l.strip()]
    # —— 关键修复：因为当前函数 text = edu_sec_text（section 化后的教育板块），其中可能含「XX 外语培训 学校」
    # 这种学校名里带"培训"的行，如果不加过滤 → 会把教育日期当 training 日期扫出来（邓艳芳 6 条垃圾）。
    # 严格限定 train_lines 必须同时满足：①含培训/证书相关关键词，②不像纯教育行（不含 大学/学院/学校/专业 等强教育标志，
    # 除非同时存在真正的培训内容关键词如 研修/认证/内训/课程名）。
    # EN: —— Key fix: since text in this function = edu_sec_text (the sectionised education section), it may contain lines like "XX 外语培训 学校" (XX foreign-language training school)
    #     whose school name includes "培训" (training); without filtering → education dates would be scanned out as training dates (6 junk entries in a past case).
    #     Strictly require train_lines to satisfy both: ① contains training/certificate-related keywords, ② does not look like a pure education line (no strong education markers like 大学/学院/学校/专业,
    #     unless real training content keywords such as 研修/认证/内训/course names are also present).
    # JA: —— 重要な修正：この関数の text = edu_sec_text（セクション化した学歴欄）なので、「XX 外语培训 学校」（XX 外国語研修学校）のように
    #     学校名に「培训」（研修）を含む行がありうる。フィルターしないと → 学歴の日付が研修の日付としてスキャンされてしまう（過去の事例ではゴミが 6 件）。
    #     train_lines には次の両方を厳格に求める：① 研修・資格に関するキーワードを含む、② 純粋な学歴の行に見えない（大学／学院／学校／专业 などの強い学歴の目印を含まない。
    #     ただし 研修／认证／内训／コース名 など本当の研修内容のキーワードも同時にある場合は除く）。
    EDU_ONLY_MARKERS = ("毕业", "专业", "系", "学院", "大学", "学校", "就读", "学历", "学位", "GPA", "成绩",
                        "主修", "辅修", "学士", "硕士", "博士", "大专", "本科", "高中", "中专", "入学", "在校")
    REAL_TRAINING_CONTENT_KW = ("培训", "研修", "内训", "外训", "讲座", "认证", "资格", "考试", "训练", "证书",
                                "课程", "学习班", "进修班", "训练营", "特训", "公开课", "在线课程", "慕课")
    def _looks_like_actual_training_line(line: str) -> bool:
        kw_hit = [k for k in REAL_TRAINING_CONTENT_KW if k in line]
        if not kw_hit:
            return False
        edu_hit = [e for e in EDU_ONLY_MARKERS if e in line]
        # 如果出现强教育标志，只有当它同时出现「真实培训内容关键词 3+」或有"证书/认证/资格"之一才放行，否则拒绝（避免培训学校污染）
        # EN: If a strong education marker appears, let it through only when it also has "3+ real training content keywords" or one of "证书/认证/资格" (certificate/certification/qualification); otherwise reject (to avoid training-school pollution)
        # JA: 強い学歴の目印がある場合は、「本当の研修内容のキーワードが 3 つ以上」あるか「证书／认证／资格」（資格・認定）のいずれかがある場合だけ通し、それ以外は拒否する（研修学校による汚染を避ける）
        if edu_hit:
            has_cert = any(k in line for k in ("证书", "认证", "资格", "考试"))
            return has_cert or len(kw_hit) >= 3
        return True
    train_lines = [l for l in all_text_lines if _looks_like_actual_training_line(l)]
    for tgt in [tr_block] + train_lines:
        if not tgt:
            continue
        gts = _extract_glued_trainings(tgt)
        for t in gts:
            tn = str(t.get("training_name") or "")
            org = str(t.get("organization_name") or "")
            sym = str(t.get("start_ym") or "")
            if not tn:
                continue
            dupe = False
            for t2 in trainings:
                if (str(t2.get("training_name") or t2.get("name") or "") == tn
                        and sym == str(t2.get("start_ym") or t2.get("training_start_ym") or "")):
                    dupe = True
                    break
            if not dupe:
                trainings.append({
                    "training_name": tn,
                    "organization_name": org,
                    "start_ym": sym,
                    "end_ym": "",
                    "description": "",
                    "sequence_no": len(trainings) + 1,
                })
    # ======= 终态清理：edus 最后一遍过滤无效条目 + 清理学校名/专业名的 KV 前缀残留 + 中文标点尾部 =======
    # EN: ======= Final cleanup: one last pass over edus to filter invalid entries + clean leftover KV prefixes in school/major names + trailing Chinese punctuation =======
    # JA: ======= 最終の整理：edus を最後にもう一度走査して無効な項目を除外 + 学校名・専攻名に残った KV の接頭辞を除去 + 末尾の中国語の句読点 =======
    EDU_UI_GARBAGE_TOK = ("Graduate", "graduated", "from", "Grad", "Graduated", "（from", "（Graduate", "from）",
                          "Name", "name", "Major", "major", "School", "school", "Degree", "degree",
                          "Time", "time", "Date", "date", "Start", "start", "End", "end")
    cleaned_edus: list[dict[str, Any]] = []
    seen_edu_keys: set[tuple[str, str, str]] = set()
    for e in edus:
        sch = str(e.get("school_name") or e.get("school") or "").strip()
        maj = str(e.get("major_name") or e.get("major") or "").strip()
        deg = str(e.get("degree_name") or e.get("degree") or "").strip()
        sym = str(e.get("school_start_date") or e.get("start_ym") or e.get("school_start_ym") or "").strip()
        eym = str(e.get("school_end_date") or e.get("end_ym") or e.get("school_end_ym") or "").strip()
        # -------- 学校名清理 --------
        # 1) 去掉 KV 表头前缀残留：「毕业学校：」「学校：」「毕业院校：」「院校：」「Name（...」「Graduate from」等
        # EN: -------- School name cleanup --------
        #     1) Remove leftover KV header prefixes: "毕业学校：" "学校：" "毕业院校：" "院校：" (graduated school / school / institution:) "Name（..." "Graduate from" etc.
        # JA: -------- 学校名の整理 --------
        #     1) KV の見出しの接頭辞の残りを除く：「毕业学校：」「学校：」「毕业院校：」「院校：」「Name（...」「Graduate from」など
        sch = re.sub(r"^[\s　]*[\(（【\[]?\s*(?:Graduate\s*from|毕业学校|毕业院校|学校名称|所在学校|学校|院校)\s*(?:[）)\]】])?\s*[:：]?\s*", "", sch, flags=re.I)
        sch = re.sub(r"^[\s　]*[\(（【\[]?\s*Name\s*\s*[:：]?\s*", "", sch, flags=re.I)
        # 2) 尾部中文标点 / 描述性后缀（，XXX 项目；「选拔交流项目」等）剥离，避免学校=「同济大学，选拔交流项目」
        #    判断：尾部如果是 [，,、；;] + 选拔/交流/访学/交换/联合培养/项目/课程/培训/实验班/基地班/创新班 开头
        #    （后面可以跟 "交流项目" 等多词组合），并且前面部分包含 SCHOOL_SIGNS → 切去尾部
        # EN: 2) Strip trailing Chinese punctuation / descriptive suffixes (，XXX 项目; "选拔交流项目" (selected exchange programme), etc.) so the school is not "同济大学，选拔交流项目"
        #        Check: the tail starts with [，,、；;] + 选拔/交流/访学/交换/联合培养/项目/课程/培训/实验班/基地班/创新班 (selection/exchange/visiting/joint training/programme/course/training/experimental class...)
        #        (which may be followed by multi-word combinations like "交流项目"), and the front part contains SCHOOL_SIGNS → cut off the tail
        # JA: 2) 末尾の中国語の句読点・説明の接尾辞（，XXX 项目、「选拔交流项目」（選抜交流プログラム）など）を除き、学校が「同济大学，选拔交流项目」にならないようにする
        #        判定：末尾が [，,、；;] + 选拔／交流／访学／交换／联合培养／项目／课程／培训／实验班／基地班／创新班 で始まり
        #        （その後に「交流项目」などの複数語の組み合わせが続いてもよい）、前の部分に SCHOOL_SIGNS がある → 末尾を切る
        sch_tail = re.search(r"^(.*?)[，,、；;]\s*("
                             r"(?:选拔|交流|访学|交换|联合培养|项目|课程|培训|实验班|基地班|创新班|"
                             r"本科|硕士|博士|专科|大专|高中|中专|初中|小学|就读|入学|毕业|学历|学位|"
                             r"全日制|函授|自考|成人|专升本|专接本|专转本|专硕|学硕|"
                             r"人才培养|计划生|卓越|国际|联合|合作|公费|自费|委培|定向)"
                             r"[\u4e00-\u9fffA-Za-z0-9（）()]*)\s*$", sch)
        if sch_tail and any(s in sch_tail.group(1).lower() for s in SCHOOL_SIGNS):
            sch = sch_tail.group(1).strip()
        # 3) 去掉尾部多余标点、空格、全角空格
        # EN: 3) Remove superfluous trailing punctuation, spaces and full-width spaces
        # JA: 3) 末尾の余分な句読点・空白・全角空白を除く
        sch = re.sub(r"[\s　:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", sch).strip()
        # -------- 专业名清理 --------
        # EN: -------- Major name cleanup --------
        # JA: -------- 専攻名の整理 --------
        maj = re.sub(r"^[\s　]*[\(（【\[]?\s*(?:Major\s*name|专业名称|所学专业|专业)\s*(?:[）)\]】])?\s*[:：]?\s*", "", maj, flags=re.I)
        maj = re.sub(r"^[\s　]*[\(（【\[]?\s*Major\s*\s*[:：]?\s*", "", maj, flags=re.I)
        maj = re.sub(r"[\s　:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", maj).strip()
        # -------- 学位名清理 --------
        # EN: -------- Degree name cleanup --------
        # JA: -------- 学位名の整理 --------
        deg = re.sub(r"^[\s　]*[\(（【\[]?\s*(?:Degree|学位|学历)\s*(?:[）)\]】])?\s*[:：]?\s*", "", deg, flags=re.I)
        deg = re.sub(r"[\s　:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", deg).strip()
        # -------- 无效条目过滤 --------
        # a) 学校名和专业名都是英文 UI 占位符垃圾（比如「Graduate」「Major」之类或太短）
        # EN: -------- Invalid entry filtering --------
        #     a) Both the school and major names are English UI placeholder junk (like "Graduate" "Major", or too short)
        # JA: -------- 無効な項目の除外 --------
        #     a) 学校名と専攻名がどちらも英語の UI のプレースホルダーのゴミ（「Graduate」「Major」などや短すぎるもの）
        sch_low = sch.lower()
        maj_low = maj.lower()
        has_edu_token_in_sch = any(s in sch_low for s in SCHOOL_SIGNS)
        has_edu_token_in_maj = any(s in maj_low for s in SCHOOL_SIGNS)
        is_garbage_sch = (
            any(g.lower() in sch_low for g in EDU_UI_GARBAGE_TOK)
            and not has_edu_token_in_sch  # 若含大学/学院等学校标志，大概率是真实学校，留着
            # EN: If it contains school markers like 大学/学院, it is most likely a real school; keep it
            # JA: 大学／学院などの学校の目印を含めば本物の学校である可能性が高いので残す
        ) or (len(sch) <= 4 and not has_edu_token_in_sch and not re.search(r"[\u4e00-\u9fff]{2}", sch))
        is_garbage_maj = (
            any(g.lower() in maj_low for g in EDU_UI_GARBAGE_TOK)
            and not has_edu_token_in_maj
        ) or (len(maj) <= 2 and not re.search(r"[\u4e00-\u9fff]{2}", maj))
        # —— 金婉婷 E5 类垃圾：学校以破折号/标点开头（如「—计算机信息管理...」），或专业是长句描述（含"期间""屡获佳奖"等句子特征）
        # EN: —— E5-type junk from a past case: the school starts with a dash/punctuation (e.g. "—计算机信息管理..."), or the major is a long descriptive sentence (with sentence features like "期间" (during), "屡获佳奖" (won many awards))
        # JA: —— 過去の事例の E5 型のゴミ：学校がダッシュや句読点で始まる（例：「—计算机信息管理...」）、または専攻が長い説明文（「期间」（期間中）「屡获佳奖」（何度も受賞）などの文の特徴がある）
        sch_starts_with_garbage = bool(re.match(r"^[\-—–~～‒―〜|｜/\\()（）\[\]【】<>《》,，.。:：;；!！?？\'\"`]", sch))
        maj_looks_like_sentence = (
            len(maj) >= 25 and any(tok in maj for tok in ("期间", "屡获", "参加", "积极", "工作", "公司", "团体", "活动",
                                                            "主要", "负责", "期间", "经历", "描述", "介绍", "进行",
                                                            "提高", "提升", "管理", "运营", "销售", "市场"))
        )
        if not has_edu_token_in_sch and not has_edu_token_in_maj:
            if sch_starts_with_garbage:
                is_garbage_sch = True
            if maj_looks_like_sentence and not any(k in maj for k in ("专业", "方向", "主修", "辅修", "系", "学位")):
                is_garbage_maj = True
        # b) 学校和专业都无有效内容，且也没日期 → 跳过
        # EN: b) Neither school nor major has valid content, and there is no date either → skip
        # JA: b) 学校にも専攻にも有効な内容がなく、日付もない → スキップ
        all_empty = ((is_garbage_sch or not sch) and (is_garbage_maj or not maj) and not sym and not eym and not deg)
        if all_empty:
            continue
        # c) 学校明显是 UI 垃圾（如 「（Graduate」）且专业也空 → 跳过
        # EN: c) The school is obviously UI junk (e.g. "（Graduate") and the major is also empty → skip
        # JA: c) 学校が明らかに UI のゴミ（例：「（Graduate」）で専攻も空 → スキップ
        if is_garbage_sch and (not maj or is_garbage_maj) and not deg:
            continue
        # 把清理后的值写回（保留原 key，同时兼容两套 key）
        # EN: Write back the cleaned values (keeping the original keys, compatible with both key sets)
        # JA: 整理した値を書き戻す（元のキーを残し、両方のキー体系に対応）
        if is_garbage_sch:
            sch = ""
        if is_garbage_maj:
            maj = ""
        e["school_name"] = sch
        e["school"] = sch
        e["major_name"] = maj
        e["major"] = maj
        e["degree_name"] = deg
        e["degree"] = deg
        if sym:
            e["school_start_date"] = sym
            e["school_start_ym"] = sym
        if eym:
            e["school_end_date"] = eym
            e["school_end_ym"] = eym
        # 去重
        # EN: Dedup
        # JA: 重複排除
        edu_key = (sch, maj, sym, eym)
        if edu_key in seen_edu_keys:
            continue
        # 学校、专业、日期全空也跳
        # EN: Also skip when school, major and dates are all empty
        # JA: 学校・専攻・日付がすべて空の場合もスキップする
        if not sch and not maj and not deg and not sym:
            continue
        seen_edu_keys.add(edu_key)
        cleaned_edus.append(e)
    edus = cleaned_edus
    return edus, trainings


def parse_explicit_education_blocks(text: str) -> list[dict[str, Any]]:
    """解析“日期范围 + 学校 + 学历|专业”的高置信教育模板，并在校内荣誉前停止。

    EN: Parse the high-confidence education template "date range + school + degree|major", stopping before campus honours.

    JA: 「期間 + 学校 + 学歴|専攻」という高信頼の学歴テンプレートを解析し、学内の栄誉の前で止める。
    """
    if not text:
        return []
    text = re.split(r"\n\s*(?:校内荣誉|校内职务|在校职务|学生会|社团活动)\s*\n", text, maxsplit=1)[0]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    date_re = re.compile(
        r"^((?:19|20)\d{2}[./年\-]\s*\d{1,2})\s*[-—–~～至到]+\s*"
        r"((?:19|20)\d{2}[./年\-]\s*\d{1,2}|至今|现在|在读)\s*(.*)$"
    )
    rows: list[dict[str, Any]] = []
    degree_rank = {"初中及以下": "1", "初中": "1", "高中": "2", "中专": "2", "大专": "3", "专科": "3", "本科": "4", "硕士": "5", "博士": "6"}
    indexes = [(idx, date_re.match(line)) for idx, line in enumerate(lines)]
    indexes = [(idx, match) for idx, match in indexes if match]
    for row_index, (line_index, match) in enumerate(indexes):
        block_end = indexes[row_index + 1][0] if row_index + 1 < len(indexes) else len(lines)
        block = lines[line_index:block_end]
        school = match.group(3).strip(" \t:：|｜")
        cursor = 1
        if not school and cursor < len(block):
            school = block[cursor]
            cursor += 1
        school = re.sub(r"海外经历\s*$", "", school).strip()
        if not school or not any(token in school for token in ("大学", "学院", "学校", "中学", "高中", "职校", "技校")):
            continue
        degree = ""
        major = ""
        for value in block[cursor:cursor + 3]:
            parts = [part.strip() for part in re.split(r"[|｜\t]", value) if part.strip()]
            for part in parts:
                matched_degree = next((name for name in degree_rank if name in part), "")
                if matched_degree and not degree:
                    degree = matched_degree
                    remainder = part.replace(matched_degree, "").strip(" /,，")
                    if remainder and not major:
                        major = remainder
                elif not major and len(part) <= 40 and not any(label in part for label in ("专业描述", "相关课程", "毕业论文")):
                    major = part
            if degree:
                break
        end_raw = match.group(2)
        rows.append({
            "school_name": school,
            "school_major_name": major,
            "school_degree_type": degree,
            "school_degree_rank": degree_rank.get(degree, ""),
            "school_education_type": "",
            "school_start_ym": _format_ym(match.group(1)),
            "school_end_ym": "" if end_raw in ("至今", "现在", "在读") else _format_ym(end_raw),
        })
    return rows


# =============================================================================
# 项目经历纯文本解析（陈佩雄/陈蒙恩 样式：日期 Tab/空格 项目名 / 所属公司 / 项目描述 / 责任描述）
# =============================================================================
# EN: =============================================================================
#     Plain-text parsing of project history (layout from past cases: date Tab/space project name / company / project description / responsibility description)
#     =============================================================================
# JA: =============================================================================
#     プロジェクト経験のプレーンテキスト解析（過去の事例の形式：日付 タブ／空白 プロジェクト名 / 所属会社 / プロジェクト説明 / 担当業務の説明）
#     =============================================================================
def parse_projects_from_raw_text(text: str) -> list[dict[str, Any]]:
    """项目经历解析：只在 split_resume_sections 切出 的 project section 内部 扫描，防止 跨 section 污染。

    支持 排版：
      - 同 行：YYYY/M-YYYY/M \t 项目名（陈佩雄）
      - 异 行：YYYY/M-YYYY/M 单独 行，下 一 行 项目名（陈蒙恩）
      - 归属 行：所属公司：\t 公司名
      - 描述 行：项目描述：\t ...  /  责任描述：\t ...

    EN: Project history parsing: scan only inside the project section cut out by split_resume_sections, to prevent cross-section pollution.

    Supported layouts:
      - same line: YYYY/M-YYYY/M 	 project name (a past case)
      - separate lines: YYYY/M-YYYY/M on its own line, project name on the next line (a past case)
      - ownership line: 所属公司：	 company name
      - description lines: 项目描述：	 ...  /  责任描述：	 ...

    JA: プロジェクト経験の解析：split_resume_sections が切り出した project セクションの中だけをスキャンし、セクションをまたぐ汚染を防ぐ。

    対応するレイアウト：
      - 同じ行：YYYY/M-YYYY/M 	 プロジェクト名（過去の事例）
      - 別の行：YYYY/M-YYYY/M が単独の行にあり、次の行にプロジェクト名（過去の事例）
      - 所属の行：所属公司：	 会社名
      - 説明の行：项目描述：	 ...  /  责任描述：	 ...
    """
    results: list[dict[str, Any]] = []
    if not text:
        return results
    # semantic_dom_section_text 已经给出独立项目章节时，直接使用完整章节。
    # 不能再次按“工作内容”等内部小标题切分，否则最后几个项目会被截掉。
    # EN: When semantic_dom_section_text already provides a separate project section, use the complete section directly.
    #     It must not be split again by internal sub-headings like "工作内容" (job content), otherwise the last few projects get cut off.
    # JA: semantic_dom_section_text がすでに独立したプロジェクトの章を返している場合は、その章全体をそのまま使う。
    #     「工作内容」（業務内容）などの内部の小見出しで再び分割してはならない。さもないと最後のいくつかのプロジェクトが切り落とされる。
    if re.match(r"^\s*(?:项目经历|项目经验|项目情况)\b", text) and re.search(r"(?:19|20)\d{2}[./年-]\d{1,2}", text):
        block_main = re.sub(r"^\s*(?:项目经历|项目经验|项目情况)\s*", "", text, count=1)
        sections = {"project": block_main}
    else:
        sections = split_resume_sections(text)
        block_main = sections.get("project") or sections.get("default") or ""
    if not block_main:
        # 兜底 正则（老 简历 没 section 标题）
        # EN: Fallback regex (old résumés without section headings)
        # JA: 最終手段の正規表現（セクション見出しのない古い履歴書）
        m_sec = re.search(
            r"(?:项目经历|项目经验|项目情况|在校实践|Project\s+Experience)\s*(?:：|:)?\s*\n?(.*?)(?=\n\s*(?:工作经历|教育经历|培训经历|语言能力|技能|自我评价|求职意向|所获证书|证书|特长|个人信息|基本资料|家庭状况|\Z))",
            text, re.S | re.I,
        )
        block_main = m_sec.group(1).strip() if m_sec else ""
    # 上层已经按 section 切片时，切片里不再含“项目经历”标题；不能再次切分后丢掉正文。
    # EN: When the upper layer has already sliced by section, the slice no longer contains the "项目经历" (project history) heading; it must not be split again and lose the body.
    # JA: 上位ですでにセクションごとに切り出している場合、切片にはもう「项目经历」（プロジェクト経験）の見出しがない。再分割して本文を失ってはならない。
    if not block_main:
        block_main = (sections.get("header") or text).strip()
    if not block_main:
        return results

    # 日期 范围：支持 DATE_RANGE_TOKEN_RE（年/月/日）+ DATE_YM_RANGE_RE（仅 年/月 如 2015/12-2018/1）+ DATE_YEAR_RANGE_RE（仅 年）
    # EN: Date ranges: support DATE_RANGE_TOKEN_RE (year/month/day) + DATE_YM_RANGE_RE (year/month only, e.g. 2015/12-2018/1) + DATE_YEAR_RANGE_RE (year only)
    # JA: 期間：DATE_RANGE_TOKEN_RE（年／月／日）+ DATE_YM_RANGE_RE（年／月のみ、例：2015/12-2018/1）+ DATE_YEAR_RANGE_RE（年のみ）に対応する
    DATE_YM_RANGE_RE = re.compile(
        r"((?:19|20)\d{2})[./年\-]\s*(\d{1,2})\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*((?:19|20)\d{2})[./年\-]\s*(\d{1,2})"
    )
    DATE_YEAR_RANGE_RE_LOCAL = re.compile(
        r"((?:19|20)\d{2})\s*[\-—–~～至到‒―〜]\s*((?:19|20)\d{2}|至今|现在|Present|Current)(?!\d)"
    )

    def _parse_range(line: str) -> tuple[str, str, int] | None:
        # 1) 强 格式（含 月/日 或 月 字）
        # EN: 1) Strong format (with month/day or the character 月)
        # JA: 1) 強い形式（月・日、または「月」の字を含む）
        m1 = re.search(
            r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*"
            r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?|至今|现在|Present|Current)",
            line,
        )
        if m1:
            end_str = m1.group(2)
            eym = "" if end_str in ("至今", "现在", "Present", "Current") else _format_ym(end_str)
            return _format_ym(m1.group(1)), eym, m1.end()
        m2 = DATE_YM_RANGE_RE.search(line)
        if m2:
            return _format_ym(f"{m2.group(1)}.{m2.group(2)}"), _format_ym(f"{m2.group(3)}.{m2.group(4)}"), m2.end()
        m3 = DATE_YEAR_RANGE_RE_LOCAL.search(line)
        if m3:
            end_str = m3.group(2)
            eym = "" if end_str in ("至今", "现在", "Present", "Current") else _format_ym(end_str + ".01")
            return _format_ym(m3.group(1) + ".01"), eym, m3.end()
        return None

    lines = [ln.rstrip() for ln in block_main.splitlines()]
    seen_keys: set[tuple[str, str, str]] = set()
    cur: dict[str, Any] | None = None

    def _flush():
        nonlocal cur
        if not cur:
            return
        title = (cur.get("project_name") or "").strip()
        if len(title) >= 2:
            key = (cur.get("start_ym", ""), cur.get("end_ym", ""), title[:50])
            if key not in seen_keys:
                seen_keys.add(key)
                cur.setdefault("project_description", "")
                cur.setdefault("project_responsibilities", "")
                cur.setdefault("project_role", "")
                cur.setdefault("company_name", "")
                cur["sequence_no"] = len(results) + 1
                results.append(cur)
        cur = None

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        # 1. 先 看 本 行 是否 是 新 日期 段（新 项目 开始）
        # EN: 1. First check whether this line is a new date range (a new project starts)
        # JA: 1. まずこの行が新しい期間（新しいプロジェクトの開始）かどうかを見る
        rng = _parse_range(s)
        if rng:
            _flush()
            sym, eym, endpos = rng
            tail = s[endpos:].strip().lstrip("\t :：|│,，")
            cur = {
                "start_ym": sym,
                "end_ym": eym,
                "project_name": tail,
                "project_description": "",
                "project_responsibilities": "",
                "project_role": "",
                "company_name": "",
            }
            # 没有 项目名？ 下 一 行 看 看
            # EN: No project name? Look at the next line
            # JA: プロジェクト名がない？ 次の行を見る
            if not tail and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                nr = _parse_range(nxt) if nxt else None
                if not nr and not re.match(r"^(?:所属公司|项目描述|责任描述|项目职责|项目角色|项目业绩)\s*[:：]", nxt or ""):
                    cur["project_name"] = nxt
            continue
        # 2. 属性 行：所属公司 / 项目描述 / 责任描述 / 项目角色
        # EN: 2. Attribute lines: 所属公司 / 项目描述 / 责任描述 / 项目角色 (company / project description / responsibility description / project role)
        # JA: 2. 属性の行：所属公司／项目描述／责任描述／项目角色（所属会社・プロジェクト説明・担当業務の説明・プロジェクトでの役割）
        if not cur:
            continue
        m_attr = re.match(r"^(所属公司|项目公司|公司名称|项目描述|项目简介|责任描述|项目职责|主要职责|项目角色|担任角色|项目业绩|项目成果)\s*[:：]\s*(.*)$", s)
        attr_key = None
        attr_val = ""
        if m_attr:
            attr_key = m_attr.group(1)
            attr_val = m_attr.group(2).strip()
            # 标签 行 但 同 行 没 值 → 下 一 行 当 值（陈蒙恩 样式）
            # EN: A label line with no value on the same line → use the next line as the value (layout from a past case)
            # JA: ラベルの行で同じ行に値がない → 次の行を値とする（過去の事例の形式）
            if not attr_val and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                nr = _parse_range(nxt) if nxt else None
                if not nr and not re.match(r"^(所属公司|项目公司|公司名称|项目描述|项目简介|责任描述|项目职责|主要职责|项目角色|担任角色|项目业绩|项目成果)\s*[:：]", nxt or ""):
                    attr_val = nxt
        if attr_key:
            if attr_key in ("所属公司", "项目公司", "公司名称"):
                cur["company_name"] = attr_val
            elif attr_key in ("项目描述", "项目简介"):
                cur["project_description"] = (cur.get("project_description") or "") + ("\n" if cur.get("project_description") else "") + attr_val
            elif attr_key in ("责任描述", "项目职责", "主要职责"):
                cur["project_responsibilities"] = (cur.get("project_responsibilities") or "") + ("\n" if cur.get("project_responsibilities") else "") + attr_val
            elif attr_key in ("项目角色", "担任角色"):
                cur["project_role"] = attr_val
            elif attr_key in ("项目业绩", "项目成果"):
                cur["project_description"] = (cur.get("project_description") or "") + ("\n【业绩】" if cur.get("project_description") else "【业绩】") + attr_val
            continue
        # 3. 没有 项目名 的 情况，第一 个 非 属性 非 日期 的 行 当 项目名
        # EN: 3. When there is no project name, use the first line that is neither an attribute nor a date as the project name
        # JA: 3. プロジェクト名がない場合は、属性でも日付でもない最初の行をプロジェクト名にする
        if not (cur.get("project_name") or "").strip():
            if len(s) <= 80 and not s.startswith("项目描述") and not s.startswith("责任描述"):
                cur["project_name"] = s
                continue
        # 4. 剩余 长 文本 → 缺 什么 补 什么（项目描述 先）
        # EN: 4. Remaining long text → fill whatever is missing (project description first)
        # JA: 4. 残りの長いテキスト → 欠けているものを補う（プロジェクト説明を先に）
        if len(s) > 15 and not (cur.get("project_description") or "").strip():
            cur["project_description"] = s
        elif len(s) > 15:
            cur["project_responsibilities"] = (cur.get("project_responsibilities") or "") + ("\n" if cur.get("project_responsibilities") else "") + s

    _flush()
    return results


# =============================================================================
# 培训经历纯文本解析（冷峰表格粘连：「时间地点培训内容YYYY.M地点项目YYYY.M…」）
# =============================================================================
# EN: =============================================================================
#     Plain-text parsing of training history (stuck-together table from a past case: "时间地点培训内容YYYY.M place project YYYY.M…")
#     =============================================================================
# JA: =============================================================================
#     研修歴のプレーンテキスト解析（過去の事例のくっついた表：「时间地点培训内容YYYY.M 場所 項目 YYYY.M…」）
#     =============================================================================
def parse_training_from_raw_text(text: str) -> list[dict[str, Any]]:
    """独立培训解析：
    1) 带标题的培训经历块；
    2) 「时间地点培训内容YYYY.M地点项目...」表格粘行；
    3) 仅在培训相关 section 或「培训课程/时间地点培训内容」表头后扫描；禁止全局乱扫。

    EN: Separate training parsing:
    1) training history blocks with a heading;
    2) stuck table lines like "时间地点培训内容YYYY.M place project..." (time/place/training content);
    3) scan only in training-related sections or after the "培训课程/时间地点培训内容" (training courses / time-place-content) table header; scanning arbitrarily over the whole text is forbidden.

    JA: 独立した研修の解析：
    1) 見出し付きの研修歴のブロック。
    2) 「时间地点培训内容YYYY.M 場所 項目...」（期間・場所・研修内容）のような表のくっついた行。
    3) 研修に関するセクション、または「培训课程／时间地点培训内容」（研修コース／期間・場所・研修内容）の表見出しの後だけをスキャンし、全体をむやみにスキャンすることは禁止。
    """
    results: list[dict[str, Any]] = []
    if not text:
        return results
    # 1. 培训经历块
    # EN: 1. Training history block
    # JA: 1. 研修歴のブロック
    m_sec = re.search(
        r"(?:培训经历|培训|训练|学习经历|课程经历|内训经历)\s*(?:：|:)?\s*\n?(.*?)(?=\n\s*(?:工作经历|工作经验|教育经历|项目经历|自我评价|求职意向|语言|技能|所获证书|证书|特长|语言能力|个人简历|个人评价|工作描述|个人概况|家庭状况|\Z))",
        text, re.S | re.I,
    )
    block = m_sec.group(1).strip() if m_sec else ""
    # 上层传入的 training section 切片通常不含标题，直接把切片本身作为培训块。
    # EN: A training section slice passed in from the upper layer usually has no heading; use the slice itself directly as the training block.
    # JA: 上位から渡された training セクションの切片には通常見出しがないため、切片そのものをそのまま研修ブロックとして使う。
    if not block:
        split_sections = split_resume_sections(text)
        block = (split_sections.get("training") or split_sections.get("header") or text).strip()

    # 1b. 找「时间地点培训内容」表头后的部分（可能和 block 重叠，没关系，去重处理）
    # EN: 1b. Find the part after the "时间地点培训内容" (time / place / training content) table header (it may overlap with block; that is fine, duplicates are removed)
    # JA: 1b. 「时间地点培训内容」（期間・場所・研修内容）の表見出しの後の部分を探す（block と重なってもよい。重複は除去する）
    glue_block = ""
    m_glue = re.search(
        r"时间\s*地点\s*培训\s*内容(.*?)(?=\n\s*(?:PAGE\b|工作经历|教育经历|培训经历|自我评价|求职意向|个人评价|\Z))",
        text, re.S,
    )
    if m_glue:
        glue_block = m_glue.group(1).strip()

    DATE_YM_RE = re.compile(
        r"((?:19|20)\d{2})[./年\-]\s*(\d{1,2})(?:[./年\-]\s*(\d{1,2}))?"
    )
    explicit_range_re = re.compile(
        r"^((?:19|20)\d{2}[./年\-]\s*\d{1,2})\s*[-—–~～至到]+\s*"
        r"((?:19|20)\d{2}[./年\-]\s*\d{1,2}|至今|现在|Present|Current)\s*(.*)$",
        re.I,
    )
    explicit_lines = [line.strip() for line in block.splitlines() if line.strip()]
    explicit_rows = [(idx, explicit_range_re.match(line)) for idx, line in enumerate(explicit_lines)]
    explicit_rows = [(idx, match) for idx, match in explicit_rows if match]
    if explicit_rows:
        explicit_results: list[dict[str, Any]] = []
        for row_index, (line_index, match) in enumerate(explicit_rows):
            block_end = explicit_rows[row_index + 1][0] if row_index + 1 < len(explicit_rows) else len(explicit_lines)
            chunk = explicit_lines[line_index:block_end]
            name = match.group(3).strip(" \t:：|｜")
            cursor = 1
            if not name and cursor < len(chunk):
                name = chunk[cursor]
                cursor += 1
            organization = ""
            description_lines: list[str] = []
            in_description = False
            skip_location_value = False
            expect_organization_value = False
            for value in chunk[cursor:]:
                if skip_location_value:
                    skip_location_value = False
                    continue
                if expect_organization_value:
                    organization = value.strip()
                    expect_organization_value = False
                    continue
                if re.match(r"^培训地点\s*[:：]", value):
                    skip_location_value = value.rstrip().endswith((":", "："))
                    continue
                org_match = re.match(r"^(?:培训机构|机构)\s*[:：]\s*(.*)$", value)
                if org_match:
                    organization = org_match.group(1).strip()
                    if not organization:
                        expect_organization_value = True
                    continue
                if value in ("培训机构：", "培训机构", "机构：", "机构"):
                    expect_organization_value = True
                    continue
                desc_match = re.match(r"^(?:培训描述|培训内容)\s*[:：]\s*(.*)$", value)
                if desc_match:
                    in_description = True
                    if desc_match.group(1).strip():
                        description_lines.append(desc_match.group(1).strip())
                    continue
                if value in ("培训描述：", "培训描述", "培训内容：", "培训内容"):
                    in_description = True
                    continue
                if in_description:
                    description_lines.append(value)
            end_raw = match.group(2)
            if name:
                explicit_results.append({
                    "training_name": name,
                    "organization_name": organization,
                    "start_ym": _format_ym(match.group(1)),
                    "end_ym": "" if end_raw in ("至今", "现在", "Present", "Current") else _format_ym(end_raw),
                    "description": "\n".join(description_lines).strip(),
                    "_source_confidence": "explicit_training_date_block",
                    "sequence_no": len(explicit_results) + 1,
                })
        if explicit_results:
            return explicit_results
    # 知名城市 2-4 字 + 带省/市/区/县/镇/州 后缀的，严格 city 识别
    # EN: Strict city recognition: well-known 2-4 character cities + those with 省/市/区/县/镇/州 (province/city/district/county/town/prefecture) suffixes
    # JA: 厳格な都市の識別：有名な 2〜4 文字の都市 + 省／市／区／县／镇／州 の接尾辞が付くもの
    CITY_SUFFIX = ("市", "区", "县", "省", "镇", "州")
    WELL_KNOWN_CITIES = (
        "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "西安", "天津",
        "苏州", "青岛", "大连", "厦门", "宁波", "无锡", "长沙", "郑州", "济南", "合肥", "福州",
        "东莞", "佛山", "珠海", "温州", "沈阳", "哈尔滨", "长春", "石家庄", "太原", "南昌",
        "南宁", "昆明", "贵阳", "兰州", "银川", "西宁", "海口", "三亚", "呼和浩特", "乌鲁木齐",
        "拉萨", "香港", "澳门", "台北",
    )
    BAD_PROJ_FRAGMENTS = (
        "工作描述", "工作内容", "岗位职责", "项目描述", "自我评价", "培训经历", "教育经历",
        "个人信息", "基本资料", "求职意向", "联系方式", "个人评价", "PAGE",
    )

    def add_entry(name: str, org: str, start_ym: str, end_ym: str = ""):
        if not name or len(name) < 2:
            return
        # 过滤：name 包含明显非培训内容关键词
        # EN: Filter: name contains keywords of obviously non-training content
        # JA: 除外：name に明らかに研修以外の内容のキーワードがある
        if any(k in name for k in BAD_PROJ_FRAGMENTS):
            return
        # 过滤：过长（> 120 字符）或 换行过多（> 2 行）
        # EN: Filter: too long (> 120 characters) or too many line breaks (> 2 lines)
        # JA: 除外：長すぎる（120 文字超）または改行が多すぎる（2 行超）
        if len(name) > 120 or name.count("\n") > 2:
            return
        # 过滤：org 是日期碎片（如「17/3」「月30日 ）」）
        # EN: Filter: org is a date fragment (e.g. "17/3", "月30日 ）")
        # JA: 除外：org が日付の断片（例：「17/3」「月30日 ）」）
        if org and (re.match(r"^\d{1,2}[./\-]\d{1,2}$", org) or "年" in org or "月" in org):
            org = ""
        key = (name, org, start_ym)
        for t in results:
            if key == (str(t.get("training_name") or ""), str(t.get("organization_name") or ""), str(t.get("start_ym") or "")):
                return
        results.append({
            "training_name": name,
            "organization_name": org,
            "start_ym": start_ym,
            "end_ym": end_ym,
            "description": "",
            "sequence_no": len(results) + 1,
        })

    def is_valid_city(s: str) -> bool:
        s = s.strip()
        if not s or len(s) < 2 or len(s) > 8:
            return False
        if s.endswith(CITY_SUFFIX):
            return True
        if s in WELL_KNOWN_CITIES:
            return True
        return False

    # 2. 粘行模式：YYYY.M 地点(2-6字) 项目(2-80字) YYYY.M ...
    # 仅在 block(培训经历段) 或 glue_block(时间地点培训内容段) 内扫
    # EN: 2. Stuck-line mode: YYYY.M place (2-6 characters) project (2-80 characters) YYYY.M ...
    #     Scan only inside block (the training section) or glue_block (the time/place/training-content section)
    # JA: 2. くっついた行のモード：YYYY.M 場所（2〜6 文字）項目（2〜80 文字）YYYY.M ...
    #     block（研修歴の段落）か glue_block（期間・場所・研修内容の段落）の中だけをスキャンする
    def scan_glue(src: str):
        positions = list(DATE_YM_RE.finditer(src))
        for i, mdt in enumerate(positions):
            y, mo, d = mdt.group(1), mdt.group(2), (mdt.group(3) or "")
            start_ym = _format_ym(f"{y}.{mo}" if not d else f"{y}.{mo}.{d}")
            rest_start = mdt.end()
            rest_end = positions[i + 1].start() if i + 1 < len(positions) else len(src)
            # seg 限定长度最多 200 字符，避免扫到工作段超长内容
            # EN: Limit seg to at most 200 characters so very long work content is not scanned
            # JA: seg の長さは最大 200 文字に制限し、職歴の長い内容までスキャンしないようにする
            seg_raw = src[rest_start:rest_end]
            if len(seg_raw) > 300:
                seg_raw = seg_raw[:300]
            # seg 第一行（换行之前的才是粘行），后面行当作工作职责或描述跳过
            # EN: The first line of seg (only the part before the line break is the stuck line); later lines are treated as job duties or descriptions and skipped
            # JA: seg の 1 行目（改行の前の部分だけがくっついた行）。後の行は職務や説明とみなしてスキップする
            first_line_end = seg_raw.find("\n")
            if first_line_end >= 0:
                seg = seg_raw[:first_line_end].strip().lstrip(" :：,，|│ \t()（）[]【】")
            else:
                seg = seg_raw.strip().lstrip(" :：,，|│ \t()（）[]【】")
            if len(seg) < 2:
                continue
            # 尝试 2-6 字城市前缀（严格 city）
            # EN: Try a 2-6 character city prefix (strict city)
            # JA: 2〜6 文字の都市の接頭辞を試す（厳格な都市判定）
            loc, proj = "", seg
            for loclen in (6, 5, 4, 3, 2):
                if len(seg) >= loclen + 1:
                    cand_loc = seg[:loclen].strip()
                    if is_valid_city(cand_loc):
                        cand_proj = seg[loclen:].strip(" ：:，,。.!！？?；;|│[]【】()（）")
                        if cand_proj and len(cand_proj) >= 2 and len(cand_proj) <= 100:
                            loc, proj = cand_loc, cand_proj
                            break
            # proj 仍过长（> 100 字）或含换行 → 丢弃整条，不是培训粘行
            # EN: proj still too long (> 100 characters) or contains a line break → discard the whole entry, it is not a stuck training line
            # JA: proj がまだ長すぎる（100 文字超）か改行を含む → 項目全体を破棄する。研修のくっついた行ではない
            if len(proj) > 100 or "\n" in proj:
                continue
            if any(k in proj for k in BAD_PROJ_FRAGMENTS):
                continue
            add_entry(proj.strip(), loc.strip(), start_ym)

    if block:
        scan_glue(block)
    if glue_block:
        scan_glue(glue_block)

    # 3. 在培训经历 section 内 单独 扫 行首 日期 段：
    #    主：DATE_RANGE_TOKEN_RE（带 月 或 日）
    #    Fallback：DATE_YEAR_RANGE_RE + DATE_YM_RANGE_RE（仅 年/月 格式 如 2017/3-2017/3）
    # EN: 3. Separately scan date ranges at the start of lines within the training section:
    #        main: DATE_RANGE_TOKEN_RE (with month or day)
    #        Fallback: DATE_YEAR_RANGE_RE + DATE_YM_RANGE_RE (year/month only formats, e.g. 2017/3-2017/3)
    # JA: 3. 研修歴のセクション内で行頭の期間を個別にスキャンする：
    #        主：DATE_RANGE_TOKEN_RE（月または日を含む）
    #        Fallback：DATE_YEAR_RANGE_RE + DATE_YM_RANGE_RE（年／月のみの形式、例：2017/3-2017/3）
    DATE_YM_RANGE_RE = re.compile(
        r"((?:19|20)\d{2})[./年\-]\s*(\d{1,2})\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*((?:19|20)\d{2})[./年\-]\s*(\d{1,2})"
    )
    if block:
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or len(line) > 150:
                continue
            m_d = re.search(
                r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*"
                r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?|至今|现在|Present|Current)",
                line,
            )
            start_ym = ""
            end_ym = ""
            if m_d:
                start_ym = _format_ym(m_d.group(1))
                end_str = m_d.group(2)
                end_ym = "" if end_str in ("至今", "现在", "Present", "Current") else _format_ym(end_str)
            else:
                m2 = DATE_YM_RANGE_RE.search(line)
                if not m2:
                    continue
                start_ym = _format_ym(f"{m2.group(1)}.{m2.group(2)}")
                end_ym = _format_ym(f"{m2.group(3)}.{m2.group(4)}")
            # 统一 取 tail（从 匹配 结束 位置 到 行尾）
            # EN: Uniformly take the tail (from the end of the match to the end of the line)
            # JA: 一律に tail（マッチの終了位置から行末まで）を取る
            tail_pos = (m_d.end() if m_d else m2.end()) if (m_d or m2) else 0
            tail = line[tail_pos:].strip()
            if not tail or len(tail) > 120:
                continue
            parts = [p.strip() for p in re.split(r"[ \t\xa0]{1,}|[|｜,，]", tail) if p.strip()]
            city, org, name_parts = "", "", []
            for p in parts:
                if not city and is_valid_city(p):
                    city = p
                    continue
                if not org and any(k in p for k in ("有限公司", "股份", "集团", "中心", "学院", "学校", "机构", "培训", "医疗", "大学")):
                    org = p
                    continue
                name_parts.append(p)
            tname = " ".join(name_parts) or org or city
            if tname:
                add_entry(tname, org or city, start_ym, end_ym)
    # 3b. 如果 block 来自 split_resume_sections 但 自己 的 正则 没 切 出来，重 扫
    # EN: 3b. If block came from split_resume_sections but our own regex did not cut anything, rescan
    # JA: 3b. block が split_resume_sections から来たのに自前の正規表現で何も切り出せなかった場合は再スキャンする
    if not results:
        secs_blk = split_resume_sections(text).get("training") or ""
        if secs_blk and secs_blk != block:
            sec_lines = secs_blk.splitlines()
            for i_line, raw_line in enumerate(sec_lines):
                line = raw_line.strip()
                if not line or len(line) > 150:
                    continue
                m_d = re.search(
                    r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*"
                    r"((?:19|20)\d{2}(?:年|[./\-])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2})?|至今|现在|Present|Current)",
                    line,
                )
                start_ym, end_ym = "", ""
                tail = ""
                if m_d:
                    start_ym = _format_ym(m_d.group(1))
                    es = m_d.group(2)
                    end_ym = "" if es in ("至今", "现在", "Present", "Current") else _format_ym(es)
                    tail = line[m_d.end():].strip()
                else:
                    m2 = DATE_YM_RANGE_RE.search(line)
                    if not m2:
                        continue
                    start_ym = _format_ym(f"{m2.group(1)}.{m2.group(2)}")
                    end_ym = _format_ym(f"{m2.group(3)}.{m2.group(4)}")
                    tail = line[m2.end():].strip()
                # 日期 整 行，tail 空 → 下 一 行 当 培训名
                # EN: The whole line is a date and the tail is empty → use the next line as the training name
                # JA: 行全体が日付で tail が空 → 次の行を研修名とする
                if not tail and i_line + 1 < len(sec_lines):
                    nxt = sec_lines[i_line + 1].strip()
                    nr = re.search(r"((?:19|20)\d{2})[./年\-]\s*\d{1,2}", nxt) if nxt else None
                    if not nr and not re.match(r"^(?:培训|教育|项目|工作|所属|机构|组织)\w*\s*[:：]", nxt or ""):
                        tail = nxt
                if not tail or len(tail) > 120:
                    continue
                # 再 往 后 看 2 行 找 培训机构
                # EN: Look 2 more lines ahead for the training provider
                # JA: さらに 2 行先まで研修機関を探す
                org_name = ""
                for j in range(i_line + 1, min(i_line + 5, len(sec_lines))):
                    nl = sec_lines[j].strip()
                    mo = re.match(r"^(?:培训机构|培训单位|组织单位|主办单位|授课机构)\s*[:：]\s*(.*)$", nl)
                    if mo:
                        ov = mo.group(1).strip()
                        if ov:
                            org_name = ov
                        elif j + 1 < len(sec_lines):
                            org_name = sec_lines[j + 1].strip()
                        break
                    # 或者 下 一 行 直接 写 机构 名（上 一 行 是 培训名 → 这 行 不 是 日期 → 默认 当 机构）
                    # EN: Or the next line directly states the provider name (previous line is the training name → this line is not a date → treat it as the provider by default)
                    # JA: または次の行に機関名が直接書かれている（前の行が研修名 → この行は日付ではない → 既定で機関とみなす）
                    if org_name == "" and tail and nl and not re.search(r"((?:19|20)\d{2})", nl) and j == i_line + 2:
                        if len(nl) <= 30 and any(tok in nl for tok in ("医疗","学院","学校","大学","中心","科技","股份","集团","有限","公司","教育","培训")):
                            org_name = nl
                parts = [p.strip() for p in re.split(r"[ \t\xa0]{1,}|[|｜,，]", tail) if p.strip()]
                city, org2, name_parts = "", "", []
                for p in parts:
                    if not city and is_valid_city(p):
                        city = p; continue
                    if not org2 and any(k in p for k in ("有限公司","股份","集团","中心","学院","学校","机构","培训","医疗","大学")):
                        org2 = p; continue
                    name_parts.append(p)
                tname = " ".join(name_parts) or org2 or city or tail
                org_final = org_name or org2 or city
                if tname:
                    add_entry(tname, org_final, start_ym, end_ym)
    return results


def parse_work_from_raw_text(text: str) -> list[dict[str, Any]]:
    """融合 51job / 智联 / 猎聘 / docs\\中文 的工作经历解析逻辑（板块隔离版）。

    EN: Merges the work-history parsing logic of 51job / Zhaopin / Liepin / docs\\中文 (section-isolated version).

    JA: 51job / Zhaopin / Liepin / docs\\中文 の職歴解析ロジックを統合する（セクション分離版）。
    """
    if not text:
        return []

    # DOM 已隔离出的工作章节可能在岗位描述中包含“专业技能”等普通小标题。
    # 对这种输入直接保留完整章节，避免二次 section split 把后续公司全部截断。
    # EN: A work section already isolated by the DOM may contain ordinary sub-headings like "专业技能" (professional skills) in job descriptions.
    #     For such input keep the complete section, so a second section split does not cut off all the following companies.
    # JA: DOM ですでに分離した職歴の章には、職務説明の中に「专业技能」（専門スキル）などの普通の小見出しが含まれることがある。
    #     このような入力では章全体をそのまま残し、2 回目のセクション分割で後続の会社がすべて切り落とされないようにする。
    if re.match(r"^\s*(?:工作经历|工作经验|工作履历|职业经历)\b", text) and re.search(r"(?:19|20)\d{2}[./年-]\d{1,2}", text):
        block_main = re.sub(r"^\s*(?:工作经历|工作经验|工作履历|职业经历)\s*", "", text, count=1).strip()
        sections = {"work": block_main}
    else:
        sections = split_resume_sections(text)
        block_main = sections.get("work", "").strip()

    # 若切分器未切出 work 板块，用通用正则兜底
    # EN: If the splitter did not cut out a work section, use the generic regex as a fallback
    # JA: 分割器が work セクションを切り出せなかった場合は、汎用の正規表現を最終手段として使う
    if not block_main:
        m_sec = re.search(
            r"(?:\|?\s*工作经历|Work\s+Experience|工作经验|工作履历|工作情况|职业经历)\s*\n(.*?)(?=\n\s*(?:\|?\s*教育经历|\|?\s*教育背景|\|?\s*教育程度|\|?\s*项目经历|\|?\s*项目经验|\|?\s*语言能力|\|?\s*自我评价|培训经历|Education|Project|Projects|Skills|在校实践|所获证书|专业技能|家庭状况|简述申请|\Z))",
            text, re.S | re.I,
        )
        block_main = m_sec.group(1).strip() if m_sec else ""

    # —— 关键修复：同 education 双重 section split BUG 回退。若上层传入的「已经切好的 work 板块内容」
    #    不带 section 标题，导致内部 split_resume_sections 只能看到 header 键内容，则 fallback 用整个 text 作为主内容。
    # EN: —— Key fix: same rollback for the double-section-split BUG as for education. If the "already cut work section content" passed in by the upper layer
    #        has no section heading, so the internal split_resume_sections only sees the header key content, fall back to using the whole text as the main content.
    # JA: —— 重要な修正：学歴と同じく二重のセクション分割の BUG への対処。上位から渡された「切り出し済みの work セクションの内容」に
    #        セクション見出しがなく、内部の split_resume_sections が header キーの内容しか見られない場合は、text 全体を主な内容として使う。
    if not block_main:
        fallback_text = (sections.get("header") or "").strip() or text.strip()
        _is_work_like = (
            any(tok in fallback_text for tok in
                ("公司", "有限公司", "集团", "经理", "主管", "专员", "助理", "工程师", "总监", "银行",
                 "学校", "学院", "大学", "店", "部", "中心", "事务所", "医院", "工厂"))
            or len(re.findall(r"(?:19|20)\d{2}", fallback_text)) >= 2
        )
        block_main = fallback_text if _is_work_like or len(fallback_text) >= 50 else block_main

    # ====== 求职申请表专有的 section ======
    # EN: ====== Sections specific to job application forms ======
    # JA: ====== 求職申込書に特有のセクション ======
    m_work_form_sec = re.search(
        r"工作履历\s*（[^\n]*）\s*\n(.*?)(?=\n\s*(?:教育程度|家庭状况|简述申请|是否有亲戚|以下内容由公司填写|\Z))",
        text, re.S,
    )
    block_work_form = m_work_form_sec.group(1).strip() if m_work_form_sec else ""

    # 关键改进：把工作描述末尾 和下一段「日期-公司」粘在一行的分开（例如：「。解决问题。2009.10 - 2012.09 上海万达」 → 换行切）
    # 以及：一长粘行里 多个 2009.2.1-2011.7 销售 2011.8-2013.12 经理... 这种，在每个日期段前切
    # EN: Key improvement: separate the end of a job description from the next "date-company" stuck on the same line (e.g. "。解决问题。2009.10 - 2012.09 上海万达" → split into a new line)
    #     and also: in one long stuck line with several ranges like 2009.2.1-2011.7 销售 2011.8-2013.12 经理..., split before each date range
    # JA: 重要な改善：職務説明の末尾と、同じ行にくっついた次の「日付-会社」を分ける（例：「。解决问题。2009.10 - 2012.09 上海万达」→ 改行で分ける）
    #     さらに：1 つの長い行に 2009.2.1-2011.7 销售 2011.8-2013.12 经理... のように複数の期間がくっついている場合は、各期間の前で切る
    DATE_RANGE_SPLIT_RE = re.compile(
        r"((?:19|20)\d{2}(?:年|[./\-年/])\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|--|—|～)\s*"
        # 右半段（结束年月）：允许年与月之间有多余的标点/斜杠（如 2014-/9 这种多了一个 - 的格式错乱）
        # EN: Right half (end year-month): allow extra punctuation/slashes between year and month (e.g. garbled formats like 2014-/9 with an extra -)
        # JA: 右半分（終了年月）：年と月の間に余分な句読点・スラッシュがあることを許容する（例：2014-/9 のように - が 1 つ多い崩れた形式）
        r"((?:19|20)\d{2}(?:年|[./\-年/])[./\-年/\s]*\d{0,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?|至今|现在|Present|Current)"
    )

    def _split_glued_work_lines(lines: list[str]) -> list[str]:
        out: list[str] = []
        split_re = re.compile(r"[。！？!?；;]+(?:\s*)$")
        for line in lines:
            # 1) 找出 所有 DATE_RANGE 位置，逐个在 start 之前切
            # EN: 1) Find all DATE_RANGE positions and split before each start
            # JA: 1) DATE_RANGE の位置をすべて探し、それぞれの start の前で切る
            positions = list(DATE_RANGE_SPLIT_RE.finditer(line))
            if len(positions) >= 1:
                cuts: list[int] = []
                last_end = 0
                for mdt in positions:
                    if mdt.start() > last_end + 2:  # 前面有内容
                    # EN: There is content before it
                    # JA: 前に内容がある
                        cuts.append(mdt.start())
                if cuts:
                    seg_start = 0
                    for c in cuts:
                        seg = line[seg_start:c].strip()
                        if seg:
                            # 再尝试「标点结束 紧接日期」内部再切
                            # EN: Then try splitting internally where "punctuation ends, immediately followed by a date"
                            # JA: 次に「句読点で終わりすぐに日付が続く」箇所で内部をさらに切ってみる
                            m_brk = DATE_RANGE_SPLIT_RE.search(seg, 10)
                            if m_brk and split_re.search(seg[: m_brk.start() + 1]):
                                out.append(seg[: m_brk.start()].rstrip())
                                out.append(seg[m_brk.start():].strip())
                            else:
                                out.append(seg)
                        seg_start = c
                    seg = line[seg_start:].strip()
                    if seg:
                        out.append(seg)
                    continue
            # 2) 退化为：标点结束 + 紧接日期（单个日期）切
            # EN: 2) Degrade to: split at punctuation end + immediately following date (single date)
            # JA: 2) 代替として：句読点の終わり + 直後の日付（単一の日付）で切る
            m_date = DATE_RANGE_SPLIT_RE.search(line, 10)
            if m_date and split_re.search(line[: m_date.start() + 1]):
                out.append(line[: m_date.start()].rstrip())
                out.append(line[m_date.start():].strip())
            else:
                out.append(line)
        return [l for l in out if l.strip()]

    attr_keywords = (
        "公司性质", "公司规模", "公司行业", "公司描述", "所在地区", "所在部门", "汇报对象",
        "工作地点", "下属人数", "薪酬情况", "薪酬", "月薪", "所在地",
    )
    # —— UI 工具栏垃圾词（智联/猎聘/51job 网页导出时的 UI 噪音）
    # EN: —— UI toolbar junk words (UI noise from Zhaopin/Liepin/51job web exports)
    # JA: —— UI ツールバーのゴミの語（Zhaopin／Liepin／51job の Web エクスポート時の UI のノイズ）
    ZHILIAN_UI_GARBAGE = (
        "求职信", "letter_content$", "保存到我的电脑", "转发简历到邮箱", "移到简历夹",
        "推荐职位", "保存到人才储备", "放入回收箱", "添加评语", "添加标签", "举报该简历",
        "打印简历", "相似简历", "更多靠谱人才", "查看全部", "查看全部>>", "导出简历",
        "放入回收站", "下载附件简历", "下载附件", "预览附件", "收藏", "收藏简历",
        "导出", "分享", "分享到微信", "分享到微博", "分享到钉钉", "分享到LinkedIn",
        "发消息", "邀请面试", "安排面试", "邀约", "打招呼", "交换名片",
        "加入人才库", "加入黑名单", "标记不合适", "标记意向", "标记看过", "收藏该简历",
        "面试反馈", "面试记录", "邀约候选人", "发起沟通", "发送面试邀请", "批量操作",
        "下载简历", "简历附件", "附件下载", "下载 PDF 简历", "下载PDF",
        "$Nummer", "$Zertifikat$", "$Bild", "$Logo$", "INCLUDEPICTURE", "MERGEFORMAT",
        "letter_content", "resume_content$",
    )
    UI_GARBAGE_EXACT = {g for g in ZHILIAN_UI_GARBAGE if "$" not in g and len(g) <= 20}
    def _is_ui_garbage_line(s: str) -> bool:
        s_raw = (s or "").strip()
        if not s_raw:
            return True
        if s_raw in UI_GARBAGE_EXACT:
            return True
        for g in ZHILIAN_UI_GARBAGE:
            if not g: continue
            if "$" in g:
                if g in s_raw:
                    return True
            elif len(s_raw) <= len(g) + 4:
                if g in s_raw:
                    return True
        if "INCLUDEPICTURE" in s_raw or "MERGEFORMAT" in s_raw:
            return True
        return False
    def _has_ui_garbage(s: str) -> bool:
        s_raw = (s or "").strip()
        if not s_raw:
            return False
        for g in ZHILIAN_UI_GARBAGE:
            if not g: continue
            if g in s_raw:
                return True
        return False
    BAD_COMPANY_TOKENS = (
        "培训经历", "培训课程", "教育经历", "教育背景", "项目经历", "项目经验", "自我评价",
        "专业技能", "语言能力", "语言", "证书", "所获证书", "特长", "兴趣爱好",
        "在校学习情况", "在校实践经历", "工作业绩", "工作职责", "个人信息", "基本资料",
        "联系方式", "个人简历", "求职意向", "实践描述", "工作描述", "活动描述",
        "项目描述", "岗位责任", "项目职责", "技能", "职业目标",
        "公司性质", "公司规模", "公司行业", "企业性质", "规模", "下属人数", "汇报对象",
    )
    COMP_SIGNS_STRONG = ("公司", "有限公司", "股份", "集团", "工作室", "Inc", "Co", "Ltd", "LLC", "株式会社", "制造厂",
                         "工厂", "分公司", "事业部", "办事处", "银行", "基金", "证券", "保险", "大学", "学院",
                         "研究院", "科学院", "研究所", "医院", "学校", "事务所", "控股")
    COMP_SIGNS_WEAK_SUFFIX = ("厂", "院", "局", "店", "馆", "行", "社", "所", "网", "部", "中心", "厅", "机构", "机关",
                               "单位", "广场", "大厦", "商城", "超市", "市场", "矿", "站", "队")

    def _has_comp_sign(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        if any(sign in s for sign in COMP_SIGNS_STRONG):
            return True
        if len(s) >= 3 and any(s.endswith(suf) for suf in COMP_SIGNS_WEAK_SUFFIX):
            return True
        # ★新增弱标志：外文品牌+1~3个中国城市名后缀 → 典型外企中文名格式（Polartec 上海 / 埃森哲 北京 / 西门子 苏州）
        # EN: ★New weak marker: foreign brand + suffix of 1-3 Chinese city names → typical Chinese name format of foreign companies (Polartec 上海 / 埃森哲 北京 / 西门子 苏州)
        # JA: ★追加の弱い目印：外国ブランド + 中国の都市名 1〜3 個の接尾辞 → 外資系企業の典型的な中国語名の形式（Polartec 上海 / 埃森哲 北京 / 西门子 苏州）
        _CHINA_CITIES = ("北京", "上海", "广州", "深圳", "苏州", "杭州", "南京", "成都", "武汉", "西安",
                         "天津", "重庆", "青岛", "大连", "宁波", "无锡", "长沙", "沈阳", "郑州",
                         "济南", "厦门", "福州", "合肥", "哈尔滨", "长春", "石家庄", "南昌",
                         "昆明", "南宁", "佛山", "东莞", "珠海", "中山", "惠州", "常州",
                         "温州", "绍兴", "嘉兴", "金华", "泉州", "南通", "徐州", "烟台",
                         "潍坊", "洛阳", "太原", "贵阳", "海口", "兰州", "乌鲁木齐", "呼和浩特",
                         "银川", "西宁", "拉萨", "澳门", "香港", "台湾")
        _FOREIGN_BRAND_CITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&.+\- ]{1,30}[ \t\xa0]+(?:" + "|".join(_CHINA_CITIES) + r")$")
        if len(s) <= 50 and _FOREIGN_BRAND_CITY_RE.match(s):
            return True
        # ★再补：中文 2~4字 城市名 + "分公司/办事处/代表处/事业部" 已经在强标志中；这里再加「英文字母品牌词+（中文城市名）」带括号的格式
        # EN: ★Further: Chinese 2-4 character city name + "分公司/办事处/代表处/事业部" (branch/office/representative office/division) is already a strong marker; here also add the bracketed format "English brand word + (Chinese city name)"
        # JA: ★さらに：中国語 2〜4 文字の都市名 +「分公司／办事处／代表处／事业部」（支社・事務所・駐在員事務所・事業部）はすでに強い目印にある。ここでは「英字のブランド名 +（中国語の都市名）」の括弧付きの形式も加える
        _FOREIGN_BRAND_CITY_PAREN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&.+\- ]{1,30}\s*[（(]\s*(?:" + "|".join(_CHINA_CITIES) + r")\s*[)）]\s*$")
        if len(s) <= 55 and _FOREIGN_BRAND_CITY_PAREN_RE.match(s):
            return True
        return False
    INVALID_COMP_PREFIX_VERBS = (
        "负责", "协助", "组织", "开发", "维护", "参与", "制定", "管理", "进行", "配合",
        "完成", "建立", "收集", "提供", "推广", "推进", "改善", "提高", "拓展", "沟通",
        "协调", "设计", "制作", "发放", "招募", "选址", "宣传", "策划", "跟进", "运营",
        "建设", "预算", "负责解决", "参加", "支持", "调研", "分析",
        "在这", "在我", "期间", "主要", "其中", "包括",
    )
    # —— 关键修复：与教育板块一致，支持「从/自」前缀、双横杠--、汉字「到/至」分隔、「在读」结束状态
    # —— ★姜海波补：支持YYYY后空格再分隔符（如 "2010 /1--至今"、"2011 .3-2013"）；DATE_RANGE_PREFIX_INLINE同步
    # EN: —— Key fix: consistent with the education section, support "从/自" prefixes, the double dash --, Chinese "到/至" separators, and the "在读" end state
    #     —— ★Patch for a past case: support a space after YYYY before the separator (e.g. "2010 /1--至今", "2011 .3-2013"); DATE_RANGE_PREFIX_INLINE synced
    # JA: —— 重要な修正：学歴欄と同様に「从／自」の接頭辞、二重ダッシュ --、漢字の「到／至」の区切り、「在读」の終了状態に対応する
    #     —— ★過去の事例への追加修正：YYYY の後に空白を挟んでから区切りが来る形に対応（例："2010 /1--至今"、"2011 .3-2013"）。DATE_RANGE_PREFIX_INLINE も同期
    DATE_RANGE_STRIP_PREFIX_RE = re.compile(r"^(?:从|自|起|开始|起至|教育背景|教育时间|教育经历|在校时间|工作时间|工作经历|社会实践|实践时间|培训时间|培训经历)\s*")
    DATE_RANGE_TOKEN_RE = re.compile(
        r"((?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?)\s*(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*"
        # 右半段：允许年/月之间 多 1-3 个 杂标点（如 2014-/9、2015-//8、2016--/7 等 HTML 格式错乱）
        # EN: Right half: allow 1-3 extra stray punctuation marks between year/month (e.g. HTML garbling like 2014-/9, 2015-//8, 2016--/7)
        # JA: 右半分：年と月の間に余分な句読点が 1〜3 個あることを許容する（例：2014-/9、2015-//8、2016--/7 などの HTML の崩れ）
        r"((?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)[./\-年/\s\-]{0,5}\d{0,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?|至今|现在|Present|Current|在读)"
    )
    # **仅 年份 格式** fallback：匹配 2011-2013 / 2008-至今 这种 没有 月/日 的 日期段
    # EN: **Year-only format** fallback: matches date ranges without month/day like 2011-2013 / 2008-至今
    # JA: **年だけの形式**の最終手段：2011-2013 / 2008-至今 のような月・日のない期間にマッチする
    DATE_YEAR_RANGE_RE = re.compile(
        r"((?:19|20)\d{2})\s*(?:[\-—–~～至到‒―〜]{1,4}|-{2,}|到|至)\s*((?:19|20)\d{2}|至今|现在|Present|Current|在读)(?!\d)"
    )
    DATE_RANGE_PREFIX_INLINE = re.compile(
        r"^((?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?\s*(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*"
        r"(?:(?:19|20)\d{2}\s*(?:年|[./\-年/]|年/)\s*\d{1,2}(?:月|[./\-]\s*\d{1,2}日?|[./\-]\s*\d{1,2}|/\s*\d{1,2}日?|/\s*\d{1,2})?|至今|现在|Present|Current|在读))"
    )
    # 求职申请表格式：年/月之间有空格且用「至」而没有横杠
    # EN: Job application form format: a space between year/month and "至" (to) instead of a dash
    # JA: 求職申込書の形式：年と月の間に空白があり、ダッシュの代わりに「至」を使う
    DATE_RANGE_CN_FORM_RE = re.compile(
        r"((?:19|20)\d{2})年\s*(\d{1,2})月\s*至\s*((?:19|20)\d{2})年\s*(\d{1,2})月"
    )
    DATE_SPLIT_RE = r"[\-—–~～至到‒―〜]{1,4}"
    STOP_HEADERS = ("教育经历", "教育背景", "项目经历", "项目经验", "自我评价", "培训经历", "语言能力",
                    "专业技能", "证书", "所获证书", "在校实践经历", "工作业绩", "工作单位名称")
    # 求职申请表格式：「工作单位名称XXX 部门YYY 职位ZZZ 工作时间 ...」
    # 统一的 员工规模 正则：匹配 少于50人/50人以下/150-500人/10000人以上/500人 等 所有 变体
    # EN: Job application form format: "工作单位名称XXX 部门YYY 职位ZZZ 工作时间 ..." (employer XXX, department YYY, position ZZZ, work period ...)
    #     Unified employee-size regex: matches all variants such as 少于50人/50人以下/150-500人/10000人以上/500人
    # JA: 求職申込書の形式：「工作单位名称XXX 部门YYY 职位ZZZ 工作时间 ...」（勤務先 XXX 部署 YYY 職位 ZZZ 勤務期間 …）
    #     統一した従業員規模の正規表現：少于50人／50人以下／150-500人／10000人以上／500人 などのすべての変種にマッチする
    EMPLOYEE_RE_STR = r"(?:(?:少于|小于|低于|不超过|不足|不到)?\s*\d+(?:\s*[-–~～至到]\s*\d+)?\s*(?:人以下|人以内|人以上|人)|(?:\d+(?:\s*[-–~～至到]\s*\d+)?\s*人))"

    WORK_FORM_RE = re.compile(
        r"工作单位名称\s*(.*?)\s*部\s*门\s*(.*?)\s*职\s*位\s*(.*?)\s*工作时间\s*([\s\S]{0,80}?)(?=公司性质|薪金|税前|奖金|工作职责|工作单位名称|$)"
    )

    def _is_duration_text(s: str) -> bool:
        s2 = re.sub(r"[\s\u3000\xa0]", "", s or "")
        return bool(re.search(r"^[（(]?\d+年?\d*个?月?[）)]?$", s2))

    def _clean_industry_str(ind: str) -> str:
        parts = [p.strip() for p in re.split(r"[|｜]", ind or "") if p.strip()]
        cleaned = [p for p in parts if not re.fullmatch(r"(?:民营|外资|合资|国企|上市公司|股份制|外商独资|中外合营|私营|民营企业|央企|事业机关|港澳台|民营公司|外资公司|合资公司|国企公司)[\w·\s]*$", p)]
        return " | ".join(cleaned)

    works: list[dict[str, Any]] = []
    seen_work_keys: set[tuple[str, str, str]] = set()

    def _process_work_form(m) -> dict[str, Any] | None:
        company = (m.group(1) or "").strip()
        dept = (m.group(2) or "").strip()
        position = (m.group(3) or "").strip()
        time_str = (m.group(4) or "").strip()
        if not _valid_company(company):
            return None
        start_ym, end_ym, status = "", "", "离职"
        m_d = DATE_RANGE_CN_FORM_RE.search(time_str)
        if m_d:
            s_y, s_mo, e_y, e_mo = m_d.group(1), m_d.group(2), m_d.group(3), m_d.group(4)
            start_ym = _format_ym(f"{s_y}年{s_mo}月")
            end_ym = _format_ym(f"{e_y}年{e_mo}月")
        # 安全网：检测 dept/position 是不是 属性行（行业|规模|性质）
        # EN: Safety net: detect whether dept/position is an attribute line (industry|size|type)
        # JA: 安全網：dept／position が属性の行（業界|規模|性質）かどうかを検出する
        comp_industry, comp_employees = "", ""
        def _try_attrs_local(s: str):
            nonlocal comp_industry, comp_employees
            if not ("|" in s or "｜" in s):
                return s
            parts = [p.strip() for p in re.split(r"[|｜]", s) if p.strip()]
            if len(parts) < 2:
                return s
            _EMP_RE_LOCAL = re.compile(EMPLOYEE_RE_STR)
            has_emp = any(bool(_EMP_RE_LOCAL.search(p)) for p in parts)
            has_nat = any(any(kw in p for kw in ("外资", "民营", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "非欧美", "中外", "外商")) for p in parts)
            if not (has_emp or has_nat):
                return s
            if _has_comp_sign(parts[0]):
                return s
            emps = ""
            for p in parts:
                m_e = _EMP_RE_LOCAL.search(p)
                if m_e:
                    emps = m_e.group(0); break
            inds = [p for p in parts if not _EMP_RE_LOCAL.search(p)]
            if emps and not comp_employees:
                comp_employees = emps
            if inds and not comp_industry:
                comp_industry = " | ".join(inds)
            return ""
        position = _try_attrs_local(position)
        dept = _try_attrs_local(dept)
        # 尝试拿工作职责作为 position_responsibilities（后处理时补，这里留空）
        # EN: Try taking the job duties as position_responsibilities (filled during post-processing; left empty here)
        # JA: 職務を position_responsibilities として取ることを試みる（後処理で補うので、ここでは空のまま）
        key = (start_ym, end_ym, company)
        if key in seen_work_keys:
            return None
        seen_work_keys.add(key)
        return {
            "company_name": company,
            "company_employees": comp_employees,
            "company_industry": comp_industry,
            "position": position,
            "position_type": "",
            "position_salary": "",
            "position_dept": dept,
            "position_report_to": "",
            "position_subordinate": "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": status,
            "position_start": start_ym,
            "position_resigned": end_ym,
            "resigned_reason": "",
            "position_responsibilities": "",
            "position_achievements": "",
        }

    # —— 职位词/职位后缀黑名单：用于 _valid_company / _classify 中 判定 某 字符串是不是 纯职位（绝不可能是公司名）
    # EN: —— Blacklist of position words/suffixes: used in _valid_company / _classify to decide whether a string is a pure position (which can never be a company name)
    # JA: —— 職位の語・接尾辞のブラックリスト：_valid_company / _classify で、文字列が純粋な職位（会社名には決してなり得ない）かを判定するのに使う
    POSITION_TOKENS_EXACT = (
        # 职位 常见 后缀 （不 含 公司 后缀 时 匹配）
        # EN: Common position suffixes (matched when there is no company suffix)
        # JA: よくある職位の接尾辞（会社の接尾辞がない場合にマッチさせる）
        "经理", "主管", "主任", "总监", "专员", "助理", "顾问", "销售", "代表", "会计", "出纳",
        "文员", "秘书", "行政", "人事", "财务", "组长", "科长", "部长", "营业员", "导购",
        "业务员", "BD", "培训师", "讲师", "编辑", "记者", "校长", "院长", "所长", "设计师",
        "技术员", "分析师", "工程师", "总经理", "副总经理", "副经理", "厂长", "副厂长", "店长",
        "董事长", "总裁", "总经理助理", "总监助理", "业务经理", "销售经理", "产品经理", "项目经理",
        "运营经理", "市场经理", "客户经理", "人事经理", "财务经理", "技术经理", "区域经理",
        "销售总监", "技术总监", "软件工程师", "硬件工程师", "测试工程师", "质量工程师",
        "工艺工程师", "研发工程师", "助理工程师", "高级工程师", "产品总监", "运营总监",
        "财务总监", "人事总监", "前台接待", "前台接待员", "地勤人员", "实习生", "接待生",
        "总机接待生", "招聘专员", "行政专员", "人事专员", "销售专员", "售后", "售后服务",
        "外贸担当", "售后服务担当", "经理助理", "秘书", "翻译", "程序员", "测试员",
        "数据分析师", "产品运营", "新媒体运营", "文案策划", "市场策划", "渠道经理", "招商经理",
    )
    POSITION_TOKENS_ANY = ("经理助理", "经理", "主管", "总监", "专员", "助理", "工程师", "设计师",
                           "顾问", "代表", "业务员", "讲师", "培训师", "分析师", "出纳", "会计",
                           "文员", "秘书", "行政", "人事", "财务", "销售", "组长", "科长",
                           "部长", "店长", "厂长", "总裁", "院长", "校长", "所长", "技术员",
                           "实习生", "担当", "接待")

    def _looks_pure_position(s: str, has_comp_sign: bool) -> bool:
        """判断字符串 s 是否「本质上是纯职位词」，不应作为公司名。
        规则：
          1) 没有任何 公司标志（公司/有限/集团/银行...）；
          2) 并且 完全等于 某个 职位词，或者 以「... /  ... ｜ ...」切分后每一段都是职位后缀结尾，
             或者 包含 「经理/主管/总监/专员/助理/工程师/代表/业务员/担当/实习生/接待」等 职位特征词
             且 不含 任何 公司/学院/银行 等 公司后缀。

        EN: Decide whether string s is "essentially a pure position word" that should not be used as a company name.
        Rules:
          1) no company marker at all (公司/有限/集团/银行...);
          2) and it exactly equals some position word, or after splitting on "... /  ... ｜ ..." every segment ends with a position suffix,
             or it contains position feature words such as "经理/主管/总监/专员/助理/工程师/代表/业务员/担当/实习生/接待" (manager/supervisor/director/specialist/assistant/engineer/representative/salesperson/in charge/intern/receptionist)
             and contains no company/college/bank or other company suffix.

        JA: 文字列 s が「本質的に職位の語だけ」であり、会社名にすべきでないかを判定する。
        ルール：
          1) 会社の目印（公司／有限／集团／银行...）がまったくない。
          2) かつ、ある職位の語と完全に一致する、または「... /  ... ｜ ...」で分割した各部分がすべて職位の接尾辞で終わる、
             または「经理／主管／总监／专员／助理／工程师／代表／业务员／担当／实习生／接待」などの職位の特徴語を含み、
             会社・学院・銀行などの会社の接尾辞を一切含まない。
        """
        if has_comp_sign:
            return False
        s = (s or "").strip()
        if not s or len(s) <= 1:
            return False
        # 先看 整体（或 |/｜切分后 每段）是不是 结尾 职位词
        # EN: First check whether the whole (or each segment after splitting on |/｜) ends with a position word
        # JA: まず全体（または |／｜ で分割した各部分）が職位の語で終わるかを見る
        parts = [p.strip() for p in re.split(r"[\/|｜\s&·&]+", s) if p.strip()]
        def _seg_pos(pos_seg: str) -> bool:
            if not pos_seg:
                return False
            if pos_seg in POSITION_TOKENS_EXACT:
                return True
            for suf in POSITION_TOKENS_EXACT:
                if pos_seg.endswith(suf) and len(pos_seg) - len(suf) <= 14:
                    # 后缀前面 顶多 14 个 字 的职位前缀（如 电子商务经理/主管 等）
                    # EN: A position prefix of at most 14 characters before the suffix (e.g. 电子商务经理/主管 (e-commerce manager/supervisor))
                    # JA: 接尾辞の前の最大 14 文字の職位の接頭部分（例：电子商务经理／主管（EC マネージャー／主任））
                    return True
            # 包含 职位词任意一个，且 长度 <= 20
            # EN: Contains any position word, and length <= 20
            # JA: いずれかの職位の語を含み、長さ 20 以下
            if any(tok in pos_seg for tok in POSITION_TOKENS_ANY) and len(pos_seg) <= 22:
                return True
            return False
        if all(_seg_pos(p) for p in parts) and parts:
            return True
        # 兜底：整串 里 只有 职位词（没有公司标志）且 长度 <= 22
        # EN: Fallback: the whole string contains only position words (no company marker) and length <= 22
        # JA: 最終手段：文字列全体が職位の語だけ（会社の目印なし）で、長さ 22 以下
        if len(s) <= 22 and any(tok in s for tok in POSITION_TOKENS_ANY) and not has_comp_sign:
            return True
        return False

    def _valid_company(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        if s in {"其他", "其它", "无", "无工作经历", "工作描述", "工作内容"}:
            return False
        # —— 合法「经营主体」短名白名单（程泽 case：自营）
        # EN: —— Whitelist of legitimate short "business entity" names (a past case: 自营 (self-employed))
        # JA: —— 正当な短い「事業主体」名のホワイトリスト（過去の事例：自营（自営））
        LEGAL_SHORT_COMPANY = ("自营", "个体", "个体户", "自由职业", "创业", "个人", "个人工作室", "SOHO", "自由职业者",
                               "家族企业", "私营", "民营企业", "私人经营", "私人", "独立经营")
        if s in LEGAL_SHORT_COMPANY:
            return True
        # —— ★雷审旗补：1~3字母的纯大写ASCII字符串（如 PD / IT / HR / BD / QA / RD ）→ 99.9%是部门/职位缩写，绝不可能是公司名
        # EN: —— ★Patch for a past case: pure uppercase ASCII strings of 1-3 letters (e.g. PD / IT / HR / BD / QA / RD) → 99.9% department/position abbreviations, never a company name
        # JA: —— ★過去の事例への追加修正：1〜3 文字の大文字 ASCII だけの文字列（例：PD / IT / HR / BD / QA / RD）→ 99.9% 部署・職位の略語で、会社名には決してならない
        if re.fullmatch(r"[A-Z]{1,3}", s):
            return False
        # —— ★再补：以「部/组/科/课/室/站/所/队/中心」结尾的2~5字短词（即使不含其他职位词）→ 典型部门名，不是公司名
        # EN: —— ★Further: short 2-5 character words ending with "部/组/科/课/室/站/所/队/中心" (department/group/section/class/room/station/office/team/centre) (even without other position words) → typical department names, not company names
        # JA: —— ★さらに：「部／组／科／课／室／站／所／队／中心」で終わる 2〜5 文字の短い語（他の職位の語を含まなくても）→ 典型的な部署名で、会社名ではない
        if 2 <= len(s) <= 5 and s[-1] in ("部", "组", "科", "课", "室", "站", "所", "队"):
            return False
        # —— ★宁严勿松★：2~4字纯「公司性质形容词」 → 绝对不是公司名
        #    （陈丹妮 case：工作块里"公司性质：民营企业"换行拆成 2 行，第 2 行单独"企业"被误当 company_name）
        # EN: —— ★Better too strict than too loose★: 2-4 character pure "company-type adjectives" → never a company name
        #        (a past case: in a work block, "公司性质：民营企业" (company type: private enterprise) was split over 2 lines, and the second line "企业" alone was taken as company_name)
        # JA: —— ★緩すぎるより厳しすぎる方がよい★：2〜4 文字の純粋な「会社の性質を表す形容語」→ 決して会社名ではない
        #        （過去の事例：職歴ブロックで「公司性质：民营企业」（会社の性質：民間企業）が 2 行に分かれ、2 行目の「企业」だけが company_name と誤認された）
        PURE_NATURE_WORDS_EXACT = {
            "企业", "民营", "外资", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "外商",
            "外商独资", "中外合营", "民营企业", "外资企业", "合资企业", "国有企业", "私营企业", "股份制企业",
            "上市公司", "民营企业", "央企", "事业机关", "事业单位", "政府机关",
        }
        if s in PURE_NATURE_WORDS_EXACT:
            return False
        if 2 <= len(s) <= 4 and not _has_comp_sign(s):
            # 2-4 个字 又没有公司标志 → 大概率是性质/部门词，不是公司名
            # EN: 2-4 characters with no company marker → most likely a type/department word, not a company name
            # JA: 2〜4 文字で会社の目印がない → 性質・部署の語である可能性が高く、会社名ではない
            if s in ("民营", "外资", "合资", "国企", "私营", "内资", "独资", "合伙", "股份", "集体"):
                return False
        # —— 新增：UI 垃圾 → 绝对不是公司名
        # EN: —— New: UI junk → never a company name
        # JA: —— 追加：UI のゴミ → 決して会社名ではない
        if _is_ui_garbage_line(s):
            return False
        if _has_ui_garbage(s) and not _has_comp_sign(s):
            return False
        if len(s) == 1 or len(s) > 60:
            return False
        if all(c in r"：:，,|｜·\-\-—–~～()（） \t" for c in s):
            return False
        # —— 新增：先 看 有没有 公司 强/弱 标志
        # EN: —— New: first check whether there are strong/weak company markers
        # JA: —— 追加：まず会社の強い・弱い目印があるかを見る
        s_has_comp_sign = _has_comp_sign(s)
        # —— 新增：纯职位词（无公司标志）直接 False
        # EN: —— New: pure position words (no company marker) → False directly
        # JA: —— 追加：純粋な職位の語（会社の目印なし）→ そのまま False
        if _looks_pure_position(s, s_has_comp_sign):
            return False
        if any(sign in s for sign in ("大学", "学院", "职业技术学院",
                                       "高等专科学校", "高等专科学校",
                                        "中专", "职校", "技校",
                                        "小学", "中学", "高中", "初中", "九年一贯制", "九年制", "外国语学校",
                                        "实验学校", "第一中学", "第二中学", "第三中学", "第四中学", "第五中学",
                                        "育才中学", "实验中学", "附属中学", "完全中学", "初级中学", "高级中学",
                                        "少年宫", "幼儿园", "保育院", "托儿所", "K12")) and not s_has_comp_sign:
            return False
        if any(deg in s for deg in ("本科", "大专", "硕士", "博士", "专科", "中专", "学士")):
            return False
        if s in BAD_COMPANY_TOKENS or s in STOP_HEADERS:
            return False
        if any(b in s for b in BAD_COMPANY_TOKENS) and not s_has_comp_sign:
            return False
        # 纯公司规模/企业性质 行 → 不是公司名
        # EN: A pure company-size / enterprise-type line → not a company name
        # JA: 会社規模・企業の性質だけの行 → 会社名ではない
        if re.fullmatch(r"(?:民营|外资|合资|国企|上市公司|股份制|外商独资|中外合营|私营|民营企业|央企|事业机关|港澳台)[\w·\s]*$", s):
            return False
        if re.fullmatch(r"\d+-\d+人", s):
            return False
        if re.fullmatch(r"[（(]\s*\d+年(?:\s*\d+个?月)?\s*[）)]", s):
            return False
        if re.fullmatch(r"\(?\d+个月\)?", s):
            return False
        if re.match(r"^(?:" + "|".join(INVALID_COMP_PREFIX_VERBS) + r")", s) and not s_has_comp_sign:
            return False
        # —— 新增：KV 表头行 （如「所属行业：」）→ 肯定不是公司名
        # EN: —— New: KV header lines (e.g. "所属行业：" (industry:)) → definitely not a company name
        # JA: —— 追加：KV の見出しの行（例：「所属行业：」（所属業界：））→ 明らかに会社名ではない
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{1,12}[：:]", s):
            return False
        # 多标点 句子 → 大概率 工作 描述 而非 公司名
        # EN: Sentences with many punctuation marks → most likely a job description rather than a company name
        # JA: 句読点の多い文 → 会社名ではなく職務説明である可能性が高い
        if not s_has_comp_sign:
            n_punc = sum(s.count(c) for c in "，,。.!！?？；;、")
            if n_punc >= 1 and len(s) >= 10:
                return False
        # 长句基本描述 → 不是公司名
        # EN: Long basic descriptive sentences → not a company name
        # JA: 長い説明文 → 会社名ではない
        if len(s) > 20 and not s_has_comp_sign:
            return False
        return True

    # —— KV 表头行检测：识别「所属行业：」「所在部门：」这种 本身是 key 、下一行才是 value 的行
    # EN: —— KV header line detection: recognise lines like "所属行业：" "所在部门：" (industry: / department:) that are themselves keys, with the value on the next line
    # JA: —— KV の見出し行の検出：「所属行业：」「所在部门：」（業界：／部署：）のように、それ自体がキーで次の行が値になる行を識別する
    KV_HEADER_PREFS = (
        "公司性质", "公司规模", "公司行业", "企业性质", "企业规模", "规模",
        "所属行业", "所在行业", "行业",
        "公司", "单位", "企业", "所属公司", "所在公司", "所属单位", "任职单位", "任职公司",
        "部门", "所属部门", "所在部门", "任职部门",
        "职位", "岗位", "担任职位", "任职岗位", "担任岗位", "职务",
        "工作地点", "工作地点", "工作性质", "工作类型",
        "汇报对象", "下属人数", "直接下属", "下属",
        "月薪", "薪酬", "薪资", "税前月薪", "税后月薪", "年收入",
        "开发工具", "技术栈", "技能名称",
    )
    def _is_kv_header_line(s: str) -> bool:
        """单行是不是 KV 表头（「所属行业：」「所在部门：」这种 key-only 行，下一行才是 value）。

        EN: Whether a single line is a KV header (a key-only line like "所属行业：" / "所在部门：", with the value on the next line).

        JA: 1 行が KV の見出しか（「所属行业：」「所在部门：」のような key だけの行で、次の行が値）を判定する。
        """
        s = (s or "").strip()
        if not s or len(s) > 25:
            return False
        # 1) 最严格：「key：」「key:」 格式 且 key 在已知词表中
        # EN: 1) Strictest: "key：" / "key:" format with key in the known vocabulary
        # JA: 1) 最も厳格：「key：」「key:」の形式で、key が既知の語彙にある
        m_colon = re.fullmatch(r"([\u4e00-\u9fffA-Za-z0-9]{1,12})\s*[:：]\s*", s)
        if m_colon:
            key = m_colon.group(1)
            if any(pref == key or key.startswith(pref) for pref in KV_HEADER_PREFS):
                return True
            # 即便 key 不在词表，如果是「1~4 字 + 冒号」这种短表头，也不能作为 company/position 填
            # EN: Even if key is not in the vocabulary, a short "1-4 characters + colon" header must not be filled in as company/position
            # JA: key が語彙になくても、「1〜4 文字 + コロン」のような短い見出しを company／position として入れてはならない
            if len(key) <= 4:
                return True
        return False

    def _kv_split(s: str) -> tuple[str | None, str]:
        """如果 s 本身就是 "key：value" 格式，返回 (key, value)；否则 (None, s)。

        EN: If s itself is in "key：value" format, return (key, value); otherwise (None, s).

        JA: s 自体が「key：value」の形式なら (key, value) を返し、そうでなければ (None, s) を返す。
        """
        s = (s or "").strip()
        if not s:
            return None, ""
        m = re.match(r"([\u4e00-\u9fffA-Za-z0-9]{1,12})\s*[:：]\s*", s)
        if not m:
            return None, s
        key = m.group(1)
        if not any(pref == key or key.startswith(pref) for pref in KV_HEADER_PREFS):
            return None, s
        val = s[m.end():].strip()
        return key, val

    def _process_date_in_line(line: str, i_line: int, lines_pool: list[str]) -> dict[str, Any] | None:
        # —— 先剥离「从/自/工作时间/工作经历/社会实践」前缀
        # EN: —— First strip prefixes "从/自/工作时间/工作经历/社会实践" (from / since / work period / work history / social practice)
        # JA: —— まず「从／自／工作时间／工作经历／社会实践」（〜から・勤務期間・職歴・社会実践）の接頭辞を除く
        line_stripped = DATE_RANGE_STRIP_PREFIX_RE.sub("", line).strip()
        m_d = DATE_RANGE_TOKEN_RE.search(line_stripped)
        start_raw, end_raw = "", ""
        m_start, m_end = -1, -1
        if not m_d:
            # —— Fallback 1：短结尾日期格式，如「2014.04.15—06.30」「2014/07/25-08/31」「2014年7月25日~8月31日」
            # EN: —— Fallback 1: short-ending date formats like "2014.04.15—06.30", "2014/07/25-08/31", "2014年7月25日~8月31日"
            # JA: —— Fallback 1：「2014.04.15—06.30」「2014/07/25-08/31」「2014年7月25日~8月31日」のような末尾の短い日付形式
            SHORTEND_RE = re.compile(
                r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})\s*(?:[./月\-]\s*(\d{1,2})\s*日?)?\s*"
                r"(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*"
                r"(\d{1,2})\s*[./月\-]\s*(\d{1,2})\s*日?\s*(?!\d)"
            )
            m_sh = SHORTEND_RE.search(line_stripped)
            if m_sh:
                s_y, s_m, s_d, e_m, e_d = m_sh.group(1), m_sh.group(2), (m_sh.group(3) or ""), m_sh.group(4), m_sh.group(5)
                start_raw = f"{s_y}.{s_m}.{s_d}" if s_d else f"{s_y}.{s_m}"
                end_raw = f"{s_y}.{e_m}.{e_d}"
                m_start, m_end = m_sh.start(), m_sh.end()
            if not m_sh:
                # **Fallback**：仅 年份 格式（如 2004-2006 / 2008-至今）用 DATE_YEAR_RANGE_RE
                # EN: **Fallback**: year-only formats (e.g. 2004-2006 / 2008-至今) use DATE_YEAR_RANGE_RE
                # JA: **Fallback**：年だけの形式（例：2004-2006 / 2008-至今）には DATE_YEAR_RANGE_RE を使う
                m_d = DATE_YEAR_RANGE_RE.search(line_stripped)
                if not m_d:
                    return None
                start_raw, end_raw = m_d.group(1), m_d.group(2)
                m_start, m_end = m_d.start(), m_d.end()
        else:
            start_raw, end_raw = m_d.group(1), m_d.group(2)
            m_start, m_end = m_d.start(), m_d.end()
        start_ym = _format_ym(start_raw)
        end_ym = "" if end_raw in ("至今", "现在", "Present", "Current", "在读") else _format_ym(end_raw)
        status = "在职" if end_raw in ("至今", "现在", "Present", "Current", "在读") else "离职"

        tail = line_stripped[m_end:].strip()
        head = line_stripped[: m_start].strip()

        # —— 关键修复：日期段后紧跟冒号「2001年9月~2004年3月:深圳市中国昭工表壳制品厂（日资）生产管理担当」
        #    解析：tail = 公司名（属性）职位名 → 需要把 公司名、属性、职位 分别拆开
        # EN: —— Key fix: a colon right after the date range, "2001年9月~2004年3月:深圳市中国昭工表壳制品厂（日资）生产管理担当"
        #        Parse: tail = company name (attribute) position name → company name, attribute and position must be split apart
        # JA: —— 重要な修正：期間の直後にコロンが続く場合「2001年9月~2004年3月:深圳市中国昭工表壳制品厂（日资）生产管理担当」
        #        解析：tail = 会社名（属性）職位名 → 会社名・属性・職位をそれぞれ分ける必要がある
        if tail and (tail[0] == "：" or tail[0] == ":"):
            tail = tail[1:].strip()
        # ====== 增强 1：多括号处理（东陶（上海）有限公司（财务）/ 格之（北京）科技有限公司（HR 专员） 等）======
        #    策略：当 tail 中含 2 组或以上 「（...）」 时，识别 最后一组 括号的内容 为 职位/部门，
        #    前面的内容（包括 前面若干括号里的 子公司/城市 信息）整体 视为 公司名。
        # EN: ====== Enhancement 1: multiple brackets (东陶（上海）有限公司（财务） / 格之（北京）科技有限公司（HR 专员） etc.) ======
        #        Strategy: when tail contains 2 or more "（...）" groups, take the content of the last bracket group as the position/department,
        #        and treat everything before it (including subsidiary/city info in the earlier brackets) as the company name.
        # JA: ====== 強化 1：複数の括弧の処理（东陶（上海）有限公司（财务）／格之（北京）科技有限公司（HR 专员）など）======
        #        方針：tail に「（...）」が 2 組以上ある場合、最後の括弧の内容を職位・部署とし、
        #        その前の内容（前の括弧にある子会社・都市の情報を含む）全体を会社名とみなす。
        _paren_pairs_all = list(re.finditer(r"[（(][^）)]*[）)]", tail))
        if len(_paren_pairs_all) >= 2:
            _last = _paren_pairs_all[-1]
            _comp_multi = tail[:_last.start()].strip()
            _pos_dept_multi = _last.group().strip("（()）").strip()
            # 验证：_comp_multi 必须像公司名（含公司标志）
            # EN: Validation: _comp_multi must look like a company name (with a company marker)
            # JA: 検証：_comp_multi は会社名らしく（会社の目印を含む）なければならない
            if _has_comp_sign(_comp_multi) or _valid_company(_comp_multi):
                head = (head + " " + _comp_multi).strip() if head else _comp_multi
                # 最后一组括号内容 → 先当 position，后面 parts 逻辑再拆分部门/职位
                # EN: The content of the last bracket group → first used as position; the later parts logic splits department/position
                # JA: 最後の括弧の内容 → まず position とし、後の parts のロジックで部署と職位に分ける
                tail = _pos_dept_multi if _pos_dept_multi else ""
            _paren_pairs_all = []  # 清空，避免下面的 单括号逻辑 再 重复处理
            # EN: Clear it so the single-bracket logic below does not process it again
            # JA: 空にして、下の単一括弧のロジックが重複して処理しないようにする
        # ====== 增强 2：单括号处理（公司名（属性）职位）======
        #    注意：只有当 _paren_pairs_all 未被清空（即真的是单括号，len==1）时才执行，避免与多括号冲突
        # EN: ====== Enhancement 2: single bracket (company name (attribute) position) ======
        #        Note: run only when _paren_pairs_all was not cleared (i.e. really a single bracket, len==1), to avoid conflicting with the multi-bracket case
        # JA: ====== 強化 2：単一の括弧の処理（会社名（属性）職位）======
        #        注意：_paren_pairs_all が空にされていない（つまり本当に単一の括弧で len==1）場合だけ実行し、複数括弧の処理と衝突しないようにする
        if tail and _paren_pairs_all and ("（" in tail or "(" in tail):
            # 匹配：「深圳市中国昭工表壳制品厂（日资）生产管理担当」
            # EN: Matches: "深圳市中国昭工表壳制品厂（日资）生产管理担当"
            # JA: マッチ例：「深圳市中国昭工表壳制品厂（日资）生产管理担当」
            m_paren = re.match(r"^([^（(]+)[（(]([^）)]*)[）)]\s*(.*)$", tail)
            if m_paren:
                _comp, _attr, _pos = m_paren.group(1).strip(), m_paren.group(2).strip(), m_paren.group(3).strip()
                # 放宽条件：
                #   A) 前面 _comp 本身就像公司名（含标志/valid） → 用
                #   B) 或者 后面 _pos 含明确职位词（专员/经理/调达/担当...）且 _comp 长度合理 → 也认为是 公司名
                # EN: Relaxed conditions:
                #       A) the preceding _comp itself looks like a company name (marker/valid) → use it
                #       B) or the following _pos contains an explicit position word (专员/经理/调达/担当...: specialist/manager/procurement/in charge) and _comp has a reasonable length → also treat it as the company name
                # JA: 緩めた条件：
                #       A) 前の _comp 自体が会社名らしい（目印あり・valid）→ 使う
                #       B) または後ろの _pos に明確な職位の語（专员／经理／调达／担当...）があり、_comp の長さが妥当 → これも会社名とみなす
                _COMP_OK = _valid_company(_comp) or _has_comp_sign(_comp)
                _POSITION_SUFF_QUICK = ("专员", "助理", "经理", "主管", "总监", "组长", "科长", "部长", "主任",
                                        "工程师", "设计师", "顾问", "代表", "销售", "会计", "出纳", "文员",
                                        "秘书", "行政", "人事", "财务", "讲师", "培训师", "编辑", "记者",
                                        "校长", "院长", "所长", "调达", "店长", "担当", "开发", "运营",
                                        "策划", "设计", "分析", "工程师", "程序员", "测试")
                _POS_OK = (len(_pos) <= 25 and len(_pos) >= 1 and any(suf in _pos for suf in _POSITION_SUFF_QUICK))
                _ATTR_OK = (len(_attr) <= 15 and len(_attr) >= 1 and any(
                    k in _attr for k in ("日资", "外资", "合资", "国企", "民营", "上市", "股份", "独资", "美资",
                                         "欧资", "港资", "台资", "合资", "民营", "私营", "政府", "事业")))
                # —— 关键修复：如果 _pos 不是职位词，反而是纯公司后缀（有限公司/集团/银行...），
                #    且 _comp 本身也不含任何职位词 → 整串（_comp(_attr)_pos）就是公司名，不要拆！
                # EN: —— Key fix: if _pos is not a position word but a pure company suffix (有限公司/集团/银行...: Ltd./group/bank),
                #        and _comp itself contains no position word → the whole string (_comp(_attr)_pos) is the company name, do not split!
                # JA: —— 重要な修正：_pos が職位の語ではなく純粋な会社の接尾辞（有限公司／集团／银行...）で、
                #        _comp 自体も職位の語を含まない → 文字列全体（_comp(_attr)_pos）が会社名なので分割しない！
                _COMP_ONLY_SUFF_RE = re.compile(
                    r"^(有限公司|股份有限公司|有限责任公司|集团(?:有限)?公司|集团公司|银行股份有限公司|"
                    r"银行|事务所|研究院|研究所|医院|酒店|宾馆|旅行社|出版社|电视台|广播电台|"
                    r"株式会社|合资会社|独资会社|外资会社|分公司|办事处|有限公司\s*分公司)$"
                )
                _pos_has_any_pos_sign = _POS_OK or any(suf in _pos for suf in _POSITION_SUFF_QUICK)
                _pos_is_pure_comp_suffix = bool(_pos) and (
                    _COMP_ONLY_SUFF_RE.match(_pos.strip()) is not None
                    or (
                        _has_comp_sign(_pos) and not _pos_has_any_pos_sign
                        and any(
                            strong in _pos
                            for strong in ("有限公司", "股份公司", "股份有限", "集团", "银行", "事务所", "医院",
                                           "大学", "学院", "学校", "研究院", "研究所")
                        )
                    )
                )
                _comp_also_has_pos = any(suf in _comp for suf in _POSITION_SUFF_QUICK)
                _abort_single_paren_split = (
                    _pos_is_pure_comp_suffix and not _pos_has_any_pos_sign and (not _comp_also_has_pos)
                )
                if (not _abort_single_paren_split) and (_COMP_OK or (_POS_OK and len(_comp) >= 2) or (_ATTR_OK and len(_comp) >= 4)):
                    head_comp_cand = _comp  # 公司名从这里优先拿
                    # EN: Take the company name from here first
                    # JA: 会社名はここから優先して取る
                    # attr 通常是「日资/民营/外资/合资/国企」等公司性质，不作行业，跳过
                    # 剩下的 _pos 是职位（也可能包含部门，放在后面 parts 逻辑拆）
                    # EN: attr is usually a company type like "日资/民营/外资/合资/国企" (Japanese-owned/private/foreign/joint venture/state-owned), not an industry; skip it
                    #     The remaining _pos is the position (it may also contain a department, split by the parts logic later)
                    # JA: attr は通常「日资／民营／外资／合资／国企」（日系・民間・外資・合弁・国有）などの会社の性質で、業界ではないのでスキップする
                    #     残りの _pos が職位（部署を含むこともあり、後の parts のロジックで分ける）
                    if _pos:
                        tail = f"{_pos}"
                    else:
                        tail = ""
                    head = (head + " " + head_comp_cand).strip() if head else head_comp_cand
        # —— 关键修复2：日期段前面或后面包含「小学/中学/学校/大学/学院」且没有任何公司标志（公司/有限/银行）→ 直接跳过，避免教育被当 work
        # EN: —— Key fix 2: the text before or after the date range contains "小学/中学/学校/大学/学院" (school words) and has no company marker at all (公司/有限/银行) → skip directly, so education is not taken as work
        # JA: —— 重要な修正 2：期間の前後に「小学／中学／学校／大学／学院」があり、会社の目印（公司／有限／银行）がまったくない → そのままスキップし、学歴を職歴にしない
        _all_parts_check = (tail + " " + head).strip()
        _edu_like = any(s in _all_parts_check for s in ("小学", "中学", "职业学校", "一中", "二中", "三中", "四中", "五中", "六中", "七中", "八中", "九中", "实验学校", "外国语学校"))
        _comp_like = _has_comp_sign(_all_parts_check) or ("银行" in _all_parts_check) or ("医院" in _all_parts_check)
        if _edu_like and not _comp_like:
            return None

        company = ""
        position = ""
        pos_dept = ""
        comp_employees = ""
        comp_industry = ""
        resp_lines: list[str] = []

        # —— 新增：统一的 KV 行处理助手（支持「所属行业：value」、「所属行业」+ 下一行 value 两种格式）
        # EN: —— New: unified KV-line helper (supports both "所属行业：value" and "所属行业" + value on the next line)
        # JA: —— 追加：統一した KV 行の処理ヘルパー（「所属行业：値」と「所属行业」+ 次の行に値、の 2 つの形式に対応）
        def _dispatch_kv(s: str) -> bool:
            """把形如「所属行业：互联网/电子商务」的行拆分后填到正确字段；如果是「所属行业：」单独一行则不处理。
            成功处理返回 True，需要跳过该 value 行时由调用方自行从下一行读取。

            EN: Split a line like "所属行业：互联网/电子商务" (industry: internet/e-commerce) and fill the correct field; a standalone "所属行业：" line is not processed.
            Returns True on success; when the value line must be skipped, the caller reads it from the next line itself.

            JA: 「所属行业：互联网/电子商务」（所属業界：インターネット／EC）のような行を分割して正しいフィールドに入れる。「所属行业：」だけの行は処理しない。
            成功したら True を返す。値の行をスキップする必要がある場合は、呼び出し元が自分で次の行から読む。
            """
            nonlocal company, position, pos_dept, comp_employees, comp_industry
            s_raw = (s or "").strip()
            if not s_raw:
                return False
            # 情况 A：「key：value」 行内 KV
            # EN: Case A: in-line KV "key：value"
            # JA: ケース A：行内の KV「key：value」
            k, v = _kv_split(s_raw)
            if k is not None:
                if v:
                    k_low = k  # 已经是中文前缀
                    # EN: Already a Chinese prefix
                    # JA: すでに中国語の接頭辞
                    if any(k_low.startswith(pref) for pref in ("公司规模", "规模", "下属人数", "直接下属", "下属")):
                        m_e = re.search(r"(" + EMPLOYEE_RE_STR + r")", v)
                        if m_e and not comp_employees:
                            comp_employees = m_e.group(1)
                    if any(k_low.startswith(pref) for pref in ("公司行业", "所属行业", "所在行业", "行业")):
                        if v and not comp_industry:
                            comp_industry = v.strip(" |｜")
                    if any(k_low.startswith(pref) for pref in ("所属部门", "所在部门", "任职部门", "部门")):
                        if v and not pos_dept:
                            pos_dept = v.strip(" |｜")
                    if any(k_low.startswith(pref) for pref in ("职位", "岗位", "担任职位", "任职岗位", "担任岗位", "职务")):
                        if v and not position:
                            # 但要注意 v 不能是「行业|规模」这种属性行，需要再拆一次
                            # EN: But note v must not be an attribute line like "industry|size"; split it once more
                            # JA: ただし v が「業界|規模」のような属性の行であってはならないので、もう一度分割する
                            ok, ind_tmp, emp_tmp = _try_extract_attrs(v)
                            if not ok:
                                # 非属性行 → 作为职位
                                # EN: Not an attribute line → treat as the position
                                # JA: 属性の行ではない → 職位とする
                                if _looks_pure_position(v, _has_comp_sign(v)) or len(v) <= 30:
                                    position = v.strip(" |｜")
                            else:
                                if ind_tmp and not comp_industry:
                                    comp_industry = ind_tmp
                                if emp_tmp and not comp_employees:
                                    comp_employees = emp_tmp
                    if any(k_low.startswith(pref) for pref in ("公司", "单位", "企业", "所属公司", "所在公司", "所属单位", "任职单位", "任职公司")):
                        if v and not company and _valid_company(v):
                            company = v.strip(" |｜")
                    if any(k_low.startswith(pref) for pref in ("月薪", "薪酬", "薪资")):
                        # 不单独存职位薪资，仅跳过该行
                        # EN: The position salary is not stored separately; just skip the line
                        # JA: 職位の給与は個別に保存せず、その行をスキップするだけ
                        pass
                return True
            # 情况 B：单独的 KV 表头行 （如「所属行业：」）→ 也返回 True 让调用方知道不是 company/position 值
            # EN: Case B: a standalone KV header line (e.g. "所属行业：") → also return True so the caller knows it is not a company/position value
            # JA: ケース B：独立した KV の見出し行（例：「所属行业：」）→ これも True を返し、呼び出し元に company／position の値ではないことを知らせる
            if _is_kv_header_line(s_raw):
                return True
            return False

        def _peek_next_value(start: int, key: str) -> tuple[str, int]:
            """读取 KV 表头（如「所属行业：」）后的 value 行。返回 (value, 已经读过的附加行数)。

            EN: Read the value line after a KV header (e.g. "所属行业："). Returns (value, number of extra lines already read).

            JA: KV の見出し（例：「所属行业：」）の後の値の行を読む。戻り値：(value, すでに読んだ追加の行数)。
            """
            if start >= len(lines_pool):
                return "", 0
            nxt = lines_pool[start].strip()
            if not nxt:
                return "", 0
            # 如果下一行又是 KV 表头 → 没有 value
            # EN: If the next line is another KV header → there is no value
            # JA: 次の行がまた KV の見出しなら → 値はない
            if _is_kv_header_line(nxt) or DATE_RANGE_TOKEN_RE.search(nxt) or nxt in STOP_HEADERS:
                return "", 0
            return nxt, 1

        # Helper: 把 「医疗设备/器械|500-1000人|外资(非欧美)」这种属性行 拆成 industry + employees
        # EN: Helper: split attribute lines like "医疗设备/器械|500-1000人|外资(非欧美)" (medical devices | 500-1000 people | foreign-owned (non-Western)) into industry + employees
        # JA: ヘルパー：「医疗设备/器械|500-1000人|外资(非欧美)」（医療機器｜500〜1000 人｜外資（欧米以外））のような属性の行を industry + employees に分ける
        _IND_NAT_KW = ("外资", "民营", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "非欧美", "中外", "外商",
                       "上市公司", "民营企业", "外资企业", "合资企业", "国有企业", "集体企业", "个体经营")
        _EMP_RE = re.compile(r"(" + EMPLOYEE_RE_STR + r")")
        def _try_extract_attrs(s: str) -> tuple[bool, str, str]:
            s2 = s.strip()
            if not ("|" in s2 or "｜" in s2):
                return False, "", ""
            parts = [p.strip() for p in re.split(r"[|｜]", s2) if p.strip()]
            if not parts or len(parts) < 2:
                return False, "", ""
            # 必须 有 员工数 或者 公司性质关键词
            # EN: Must have a number of employees or a company-type keyword
            # JA: 従業員数か会社の性質のキーワードが必要
            has_emp = any(bool(_EMP_RE.search(p)) for p in parts)
            has_nat = any(any(kw in p for kw in _IND_NAT_KW) for p in parts)
            if not (has_emp or has_nat):
                return False, "", ""
            # 第一个 part 不能 有 公司标志（公司/有限/集团 等）
            # EN: The first part must not have a company marker (公司/有限/集团 etc.)
            # JA: 最初の part には会社の目印（公司／有限／集团 など）があってはならない
            if _has_comp_sign(parts[0]):
                return False, "", ""
            emps = ""
            for p in parts:
                m = _EMP_RE.search(p)
                if m:
                    emps = m.group(1)
                    break
            ind_parts = [p for p in parts if not _EMP_RE.search(p)]
            ind = " | ".join(ind_parts)
            return True, ind, emps

        # 1) 先从 tail 拿公司（日期段后面 直接是公司名/机构名）
        # 尾部可能含「（X年X个月）」，先剥掉
        # EN: 1) First take the company from the tail (the company/organisation name directly after the date range)
        #     The tail may contain "（X年X个月）" (X years X months); strip it first
        # JA: 1) まず tail から会社を取る（期間の直後にある会社名・機関名）
        #     末尾に「（X年X个月）」（X 年 X か月）が付いていることがあるので先に除く
        tail_wo_dur = re.sub(r"[（(]\s*\d+年\s*\d+个?月\s*[）)]\s*$", "", tail).strip()
        tail_wo_dur = re.sub(r"[（(]\s*\d+个月\s*[）)]\s*$", "", tail_wo_dur).strip()

        # 特殊处理：日期 + 职位/公司 直接粘连（无空格无分隔），如 2009.2.1-2011.7销售业务经理...
        # 先尝试：tail 开头以职位词结尾，最长 10 位前缀 + 职位词（后缀只保留明确的职位词，排除易与工作内容混淆的词如策划/推广/开发/研发等）
        # EN: Special handling: date + position/company stuck directly together (no space or separator), e.g. 2009.2.1-2011.7销售业务经理...
        #     First try: the start of tail ends with a position word — a prefix of at most 10 characters + position word (suffixes keep only explicit position words, excluding words easily confused with job content such as 策划/推广/开发/研发: planning/promotion/development/R&D)
        # JA: 特別処理：日付 + 職位・会社が直接くっついている（空白も区切りもない）場合。例：2009.2.1-2011.7销售业务经理...
        #     まず試す：tail の先頭が職位の語で終わる — 最大 10 文字の接頭部分 + 職位の語（接尾辞は明確な職位の語だけを残し、策划／推广／开发／研发（企画・販促・開発・研究開発）など業務内容と混同しやすい語は除く）
        _POSITION_SUFFIXES = (
            # 复合职位词，优先匹配（长的）
            # EN: Compound position words, matched first (longer ones)
            # JA: 複合した職位の語。長いものを優先してマッチさせる
            "经理助理", "总监助理", "业务经理", "销售经理", "产品经理", "项目经理", "运营经理", "市场经理",
            "客户经理", "人事经理", "财务经理", "技术经理", "区域经理", "销售总监", "技术总监",
            "软件工程师", "硬件工程师", "测试工程师", "质量工程师", "工艺工程师", "研发工程师",
            "助理工程师", "高级工程师", "产品总监", "运营总监", "财务总监", "人事总监",
            "工程师", "设计师", "技术员", "分析师",
            "总经理助理", "总经理", "副总经理", "副经理", "厂长", "副厂长", "店长",
            # 单个职位词
            # EN: Single position words
            # JA: 単独の職位の語
            "经理", "主管", "主任", "总监", "专员", "助理", "顾问", "销售", "代表", "会计", "出纳",
            "文员", "秘书", "行政", "人事", "财务", "组长", "科长", "部长",
            "董事长", "总裁", "营业员", "导购", "业务员", "BD",
            "培训师", "讲师", "编辑", "记者", "校长", "院长", "所长",
        )
        _POSITION_ALT = "|".join(re.escape(suf) for suf in sorted(_POSITION_SUFFIXES, key=len, reverse=True))
        glued_re = re.compile(
            r"^([\u4e00-\u9fffA-Za-z0-9]{0,10}(?:" + _POSITION_ALT + r"))"
            r"(?!部|科|组|课|室|站|所|队|中心|学院|大学|学校|医院|公司|集团|银行|基金|证券|保险|事务所|企业|厂)"
            r"(.*)$"
        )
        glued_pos_company_m = glued_re.match(tail_wo_dur)
        if glued_pos_company_m:
            _pos_cand, _rest = glued_pos_company_m.group(1), glued_pos_company_m.group(2)
            if _pos_cand and len(_pos_cand) <= 18:
                # —— 关键修复：如果 _rest 本身以强公司后缀结束（如「有限公司」「（上海）有限公司」等）
                #    说明 整个 tail_wo_dur 才是公司名（前缀被 glued 正则误判为职位），此时 跳过 split
                # EN: —— Key fix: if _rest itself ends with a strong company suffix (e.g. "有限公司", "（上海）有限公司")
                #        then the whole tail_wo_dur is the company name (the prefix was misjudged as a position by the glued regex); skip the split in this case
                # JA: —— 重要な修正：_rest 自体が強い会社の接尾辞（「有限公司」「（上海）有限公司」など）で終わる場合、
                #        tail_wo_dur 全体が会社名である（接頭部分が glued の正規表現で職位と誤判定された）。この場合は分割をスキップする
                _comp_suffix_re = re.compile(
                    r"(有限公司|股份有限公司|有限责任公司|集团(?:有限)?公司|集团|银行|事务所|研究院|研究所|医院|大学|学院|学校|连锁酒店|(?:株式|合资|独资|外资)会社)"
                )
                _combined = (_pos_cand + _rest).strip()
                _abort_split = False
                if _comp_suffix_re.search(_rest.strip()) and _comp_suffix_re.search(_combined):
                    # _rest 包含公司后缀 且 合并后也包含 → 整体当公司名，不拆分
                    # EN: _rest contains a company suffix and so does the merged string → treat the whole as the company name, do not split
                    # JA: _rest に会社の接尾辞があり、結合後にもある → 全体を会社名として分割しない
                    _abort_split = True
                # 再保险：如果 _pos_cand 末 2 字符 并非「职位后缀词」的最后一个词（即 _pos_cand 只是前缀+后缀粘连，但后缀匹配 是 因为某个 巧合的子串 ），
                #        而 _pos_cand 长度 > 5 且 合并后 _valid_company → 也 abort
                # EN: Extra safety: if the last 2 characters of _pos_cand are not the last word of a "position suffix" (i.e. _pos_cand is just prefix+suffix stuck together, but the suffix matched because of some coincidental substring),
                #            and _pos_cand length > 5 and the merged string is _valid_company → also abort
                # JA: さらなる保険：_pos_cand の末尾 2 文字が「職位の接尾語」の最後の語ではない場合（つまり _pos_cand は接頭部分と接尾辞がくっついただけで、接尾辞のマッチは偶然の部分文字列によるもの）、
                #            かつ _pos_cand の長さが 5 超で結合後が _valid_company → これも中止する
                if (not _abort_split) and (len(_pos_cand) >= 5) and _valid_company(_combined):
                    # 检查 _pos_cand 最后 1-2 个字符是否 确实是 职位 后缀（否则 可能是 正则 「碰巧」匹配上了 某个 非 职位 子串）
                    # EN: Check whether the last 1-2 characters of _pos_cand really are a position suffix (otherwise the regex may have "happened" to match some non-position substring)
                    # JA: _pos_cand の最後の 1〜2 文字が本当に職位の接尾辞かを確認する（そうでなければ正規表現が偶然に職位以外の部分文字列にマッチしたのかもしれない）
                    _pos_last2 = _pos_cand[-2:] if len(_pos_cand) >= 2 else ""
                    _pos_last1 = _pos_cand[-1:] if len(_pos_cand) >= 1 else ""
                    if _pos_last2 not in _POSITION_SUFFIXES and _pos_last1 not in _POSITION_SUFFIXES:
                        _abort_split = True
                if not _abort_split:
                    # 判定：_pos_cand 有没有 公司后缀/公司标志（公司、集团、银行等）→ 如果有 就 不当作 职位；否则 当作 职位（因为 glued 正则 保证 后缀是职位词）
                    # EN: Decide: does _pos_cand have a company suffix/marker (公司, 集团, 银行 etc.) → if so do not treat it as a position; otherwise treat it as a position (the glued regex guarantees the suffix is a position word)
                    # JA: 判定：_pos_cand に会社の接尾辞・目印（公司・集团・银行 など）があるか → あれば職位として扱わない。なければ職位として扱う（glued の正規表現により接尾辞が職位の語であることは保証されている）
                    if not _has_comp_sign(_pos_cand):
                        # 且 如果 _rest 前面没有紧跟 公司标志，那先把 _pos_cand 放 position
                        # EN: And if _rest is not immediately preceded by a company marker, first put _pos_cand into position
                        # JA: さらに _rest の直前に会社の目印がなければ、まず _pos_cand を position に入れる
                        if not position:
                            position = _pos_cand
                        # 剩下的 _rest 再尝试找公司（前面去掉 _pos_cand）
                        # EN: Then try finding the company in the remaining _rest (with _pos_cand removed from the front)
                        # JA: 次に残った _rest（先頭の _pos_cand を除いたもの）から会社を探してみる
                        tail_wo_dur = _rest.strip()
            else:
                pass

        # tail 里可能有「公司 | 部门 | 职位 | 月薪」这种，先拆分再拿第一个作公司
        # EN: tail may contain "company | department | position | monthly salary"; split first, then take the first as the company
        # JA: tail に「会社 | 部署 | 職位 | 月給」のようなものが含まれることがあるので、先に分割してから最初のものを会社とする
        tail_parts = [p.strip() for p in re.split(r"[|｜]", tail_wo_dur) if p.strip()]
        if not tail_parts:
            # 按多空格切
            # EN: Split on multiple spaces
            # JA: 複数の空白で分割する
            tail_parts = [p.strip() for p in re.split(r"[ \t\xa0]{2,}", tail_wo_dur) if p.strip()]
            if not tail_parts and tail_wo_dur:
                tail_parts = [tail_wo_dur]

        head_parts = [p.strip() for p in re.split(r"[|｜]", head) if p.strip()]
        if not head_parts:
            head_parts = [p.strip() for p in re.split(r"[ \t\xa0]{2,}", head) if p.strip()]
            if not head_parts and head:
                head_parts = [head]

        found_comp = ""
        found_idx = -1
        for idx_tp, tp in enumerate(tail_parts):
            # === 修复A（陈熙）：先剥掉 tp 尾部括号包裹的员工规模，避免 (少于50人) 被正则吃进公司名 ===
            # EN: === Fix A (a past case): first strip a bracketed employee size from the end of tp, so (少于50人) is not eaten into the company name by the regex ===
            # JA: === 修正 A（過去の事例）：まず tp の末尾にある括弧付きの従業員規模を除き、(少于50人) が正規表現で会社名に取り込まれないようにする ===
            tp_clean = re.sub(r"[\s（(]*(?:少于|小于|低于|不超过|不足|不到|约|近)?\s*\d+\s*[-–~～至到]?\s*\d*\s*(?:人以下|人以上|人以内|人)\s*[）)]*\s*$", "", tp).strip()
            if not tp_clean:
                tp_clean = tp
            m_c = re.search(r"([\u4e00-\u9fffA-Za-z0-9()（）]{2,30}(?:有限责任公司|股份有限公司|有限公司|股份|集团|办事处|分公司|事业部|工厂|制造厂|工作室|店|行))", tp_clean)
            if m_c:
                found_comp = m_c.group(1).strip(" ()（）")
                found_idx = idx_tp
                break
            elif _valid_company(tp_clean) and not any(tp_clean.endswith(suf) for suf in ("专员", "经理", "主管", "总监", "助理", "顾问", "工程师", "人员")):
                found_comp = tp_clean.strip(" ()（）")
                found_idx = idx_tp
                break

        # === 修复B（丁嘉颖）：日期行的 head/tail 都没找到公司 → 向前搜1-2行（公司名单独在日期上一行的情况）===
        # EN: === Fix B (a past case): neither head nor tail of the date line yields a company → search 1-2 lines back (the case where the company name is alone on the line above the date) ===
        # JA: === 修正 B（過去の事例）：日付行の head にも tail にも会社が見つからない → 1〜2 行前を探す（会社名が日付の 1 行上に単独である場合）===
        if not found_comp and not company:
            LOOKBACK = 2
            _lb_lines_pool = lines_pool
            for _lb_k in range(1, LOOKBACK + 1):
                _lb_i = i_line - _lb_k
                if _lb_i < 0 or _lb_i >= len(_lb_lines_pool):
                    break
                _lb_line = _lb_lines_pool[_lb_i].strip()
                if not _lb_line or DATE_RANGE_TOKEN_RE.search(_lb_line) or _lb_line in STOP_HEADERS:
                    break
                # 向前行不能是 KV 表头 / 描述行（含「职责|工作内容|业绩」等）
                # EN: The preceding line must not be a KV header / description line (containing "职责|工作内容|业绩" (duties|job content|results) etc.)
                # JA: 前の行は KV の見出しや説明の行（「职责|工作内容|业绩」（職務・業務内容・実績）などを含む）であってはならない
                if _is_kv_header_line(_lb_line) or "：" in _lb_line[:15]:
                    # 如果是「公司：XXX」这种 KV 行，提取 value 作为公司
                    # EN: If it is a KV line like "公司：XXX" (company: XXX), extract the value as the company
                    # JA: 「公司：XXX」（会社：XXX）のような KV の行なら、値を会社として抽出する
                    _lb_kv_k, _lb_kv_v = _kv_split(_lb_line)
                    if _lb_kv_k and _lb_kv_v and _lb_kv_k in ("公司", "单位", "企业", "所属公司", "所在公司", "所属单位", "任职单位", "任职公司"):
                        if _valid_company(_lb_kv_v):
                            found_comp = _lb_kv_v
                            break
                    continue
                if any(tok in _lb_line for tok in ("职责", "工作内容", "业绩", "描述", "项目", "经历")):
                    break
                if _valid_company(_lb_line):
                    found_comp = _lb_line
                    break
                # 再尝试：向前行按 |/多空格 拆，第一个含强公司标志的片段
                # EN: Then try: split the preceding line on |/multiple spaces and take the first fragment with a strong company marker
                # JA: 次に試す：前の行を |／複数の空白で分割し、強い会社の目印を含む最初の断片を取る
                _lb_parts = [p.strip() for p in re.split(r"[|｜ \t\xa0]{2,}", _lb_line) if p.strip()]
                for _lb_p in _lb_parts[:2]:
                    if _valid_company(_lb_p):
                        found_comp = _lb_p
                        break
                if found_comp:
                    break

        if found_comp:
            # ★雷审旗补：不要无条件覆盖已有company；只有新公司更像公司（有标志/更长）或旧company本身不可信（短、无公司标志）才替换
            # EN: ★Patch for a past case: do not unconditionally overwrite an existing company; replace only if the new company looks more like a company (marker/longer) or the old company itself is unreliable (short, no company marker)
            # JA: ★過去の事例への追加修正：既存の company を無条件に上書きしない。新しい会社の方が会社らしい（目印あり・より長い）か、旧 company 自体が信頼できない（短い・会社の目印なし）場合だけ置き換える
            def _company_confidence(cand: str, existing: str) -> bool:
                """返回 True 表示 cand 应该替换 existing。

                EN: Returns True if cand should replace existing.

                JA: cand で existing を置き換えるべきなら True を返す。
                """
                cand = (cand or "").strip(); existing = (existing or "").strip()
                if not existing:
                    return True
                if not cand:
                    return False
                c_new = (2 if _has_comp_sign(cand) else 0) + (1 if len(cand) >= 6 else 0)
                c_old = (2 if _has_comp_sign(existing) else 0) + (1 if len(existing) >= 6 else 0)
                # 旧company有强标志 → 只有新的也有强标志且更长才换
                # EN: The old company has a strong marker → replace only if the new one also has a strong marker and is longer
                # JA: 旧 company に強い目印がある → 新しいものにも強い目印があり、かつより長い場合だけ置き換える
                if _has_comp_sign(existing) and not _has_comp_sign(cand):
                    return False
                # 新候选置信度严格高于旧的才换
                # EN: Replace only if the new candidate's confidence is strictly higher than the old one
                # JA: 新しい候補の信頼度が旧いものより厳密に高い場合だけ置き換える
                return c_new > c_old
            if _company_confidence(found_comp, company):
                company = found_comp
            rest_tail = [tp for idx_tp, tp in enumerate(tail_parts) if idx_tp != found_idx]
            for part in rest_tail:
                if not part:
                    continue
                m_emp = re.search(r"(" + EMPLOYEE_RE_STR + r")", part)
                if m_emp:
                    comp_employees = m_emp.group(1)
                    remain = re.sub(r"\s*" + EMPLOYEE_RE_STR + r"\s*", "", part).strip(" |｜，,")
                    if remain and not comp_industry:
                        comp_industry = remain
                    continue
                if not position and len(part) <= 40 and not _is_duration_text(part) and not any(k in part for k in ("经历", "职责", "描述", "主要", "项目", "业绩")) and not part.endswith(("性质", "规模")):
                    ok, ind, emp = _try_extract_attrs(part)
                    if ok:
                        if ind and not comp_industry:
                            comp_industry = ind
                        if emp and not comp_employees:
                            comp_employees = emp
                        continue
                    if ("部" in part or "组" in part or "科" in part or "中心" in part or "事业部" in part or "分公司" in part or "办事处" in part) and not pos_dept and len(part) <= 20:
                        pos_dept = part
                    else:
                        if not position:
                            position = part
                        elif not pos_dept and len(part) <= 12:
                            pos_dept = part
        elif head_parts and _valid_company(head_parts[-1]):
            company = head_parts[-1]

        # 2) 如果 tail/head 都不像公司，就向下面最多 5 行搜公司名、职位、行业、规模
        # EN: 2) If neither tail nor head looks like a company, search up to 5 lines below for company name, position, industry and size
        # JA: 2) tail も head も会社らしくなければ、下の最大 5 行から会社名・職位・業界・規模を探す
        if not company:
            INDUSTRY_COMPANY_NATURE_KW = ("外资", "民营", "合资", "国企", "上市", "股份制", "私营", "港澳台", "欧美", "非欧美", "中外", "外商")
            for k in range(1, 6):
                if i_line + k >= len(lines_pool):
                    break
                nxt = lines_pool[i_line + k].strip()
                if DATE_RANGE_TOKEN_RE.search(nxt) or nxt in STOP_HEADERS:
                    break
                if nxt == "|":
                    continue
                # ====== 统一 KV 分发（公司性质/规模/行业/部门/职位/汇报对象等） ======
                # EN: ====== Unified KV dispatch (company type/size/industry/department/position/reports to, etc.) ======
                # JA: ====== 統一した KV の振り分け（会社の性質・規模・業界・部署・職位・報告先など）======
                if _dispatch_kv(nxt):
                    # key-only（如「所属行业：」）下一行是 value → 尝试再读一行 value
                    # EN: key-only (e.g. "所属行业：") with the value on the next line → try reading one more line as the value
                    # JA: key だけ（例：「所属行业：」）で次の行が値 → もう 1 行読んで値とすることを試みる
                    key_only_check = re.fullmatch(r"([\u4e00-\u9fffA-Za-z0-9]{1,12})\s*[:：]\s*", nxt)
                    if key_only_check and (i_line + k + 1) < len(lines_pool):
                        v_line = lines_pool[i_line + k + 1].strip()
                        if v_line and not _is_kv_header_line(v_line) and not DATE_RANGE_TOKEN_RE.search(v_line) and v_line not in STOP_HEADERS:
                            # 「key: value」合并后重新分发一次，正确写入字段
                            # EN: Merge into "key: value" and dispatch once more, writing the field correctly
                            # JA: 「key: value」に結合してもう一度振り分け、フィールドに正しく書き込む
                            _dispatch_kv(f"{key_only_check.group(1)}：{v_line}")
                    continue
                m_emp = re.search(r"(" + EMPLOYEE_RE_STR + r")", nxt)
                nxt_has_pipe = ("|" in nxt or "｜" in nxt)
                nxt_parts = [p.strip() for p in re.split(r"[|｜]", nxt) if p.strip()]
                is_attr_line = False
                if nxt_parts:
                    _c1 = nxt_has_pipe and len(nxt) <= 80
                    _c2 = (m_emp is not None
                           or any(kw in nxt for kw in INDUSTRY_COMPANY_NATURE_KW)
                           or (len(nxt_parts) >= 2 and all(p and len(p) <= 30 for p in nxt_parts)))
                    _c3 = not _has_comp_sign(nxt_parts[0])
                    is_attr_line = _c1 and _c2 and _c3
                if m_emp and not comp_employees:
                    comp_employees = m_emp.group(1)
                if is_attr_line:
                    if not comp_industry and nxt_parts:
                        inds = [p for p in nxt_parts if "人" not in p]
                        if inds:
                            comp_industry = " | ".join(inds)
                    continue
                if not nxt_parts and nxt:
                    nxt_parts = [nxt]
                cand_company = ""
                if nxt_parts and _valid_company(nxt_parts[0]):
                    cand_company = nxt_parts[0]
                elif _valid_company(nxt):
                    cand_company = nxt
                if cand_company:
                    # ★雷审旗补：只有新公司更有说服力（有强公司标志/更长）才覆盖旧company（防止"Polartec 上海"被下一行"PD"覆盖）
                    # EN: ★Patch for a past case: overwrite the old company only when the new one is more convincing (strong company marker / longer) (to prevent "Polartec 上海" being overwritten by "PD" on the next line)
                    # JA: ★過去の事例への追加修正：新しい会社の方が説得力がある（強い会社の目印あり・より長い）場合だけ旧 company を上書きする（「Polartec 上海」が次の行の「PD」で上書きされるのを防ぐ）
                    c_new_score = (2 if _has_comp_sign(cand_company) else 0) + (1 if len(cand_company) >= 6 else 0)
                    c_old_score = (2 if _has_comp_sign(company) else 0) + (1 if len(company) >= 6 else 0)
                    _should_replace = (not company) or (c_new_score > c_old_score and not (_has_comp_sign(company) and not _has_comp_sign(cand_company)))
                    if _should_replace:
                        company = cand_company
                    if nxt_parts and cand_company == nxt_parts[0]:
                        for part in nxt_parts[1:]:
                            if not part:
                                continue
                            # 先检测是不是属性行（「行业|规模|性质」）
                            # EN: First detect whether it is an attribute line ("industry|size|type")
                            # JA: まず属性の行（「業界|規模|性質」）かどうかを検出する
                            ok, ind, emp = _try_extract_attrs(part)
                            if ok:
                                if ind and not comp_industry:
                                    comp_industry = ind
                                if emp and not comp_employees:
                                    comp_employees = emp
                                continue
                            part_is_position = _looks_pure_position(part, _has_comp_sign(part))
                            if part_is_position:
                                # “公司 | 行政人事 | 人事专员”：先读到的泛职能移到部门，
                                # 后读到的明确职位作为 position，避免两者颠倒。
                                # EN: "company | 行政人事 | 人事专员" (company | admin & HR | HR specialist): move the generic function read first into department,
                                #     and use the explicit position read later as position, so the two are not reversed.
                                # JA: 「会社 | 行政人事 | 人事专员」（会社 | 総務人事 | 人事担当）：先に読んだ一般的な職能は部署に移し、
                                #     後に読んだ明確な職位を position とし、両者が逆にならないようにする。
                                if position and not pos_dept and len(position) <= 20:
                                    pos_dept = position
                                position = part
                            elif ("部" in part or "组" in part or "科" in part or "中心" in part or "事业部" in part or "分公司" in part or "办事处" in part) and not pos_dept and len(part) <= 20:
                                if not _is_kv_header_line(part) and not _dispatch_kv(part) and not _looks_pure_position(part, _has_comp_sign(part)):
                                    pos_dept = part
                            elif not position and len(part) <= 25 and not any(tok in part for tok in ("经历", "职责", "描述", "性质", "规模", "元/月")):
                                # —— 新增：跳过 KV 表头 / KV 行内 key-value
                                # EN: —— New: skip KV headers / in-line key-value pairs
                                # JA: —— 追加：KV の見出し・行内の key-value をスキップする
                                if _dispatch_kv(part):
                                    continue
                                if _is_kv_header_line(part):
                                    continue
                                position = part
                            elif not pos_dept and len(part) <= 12:
                                if _dispatch_kv(part):
                                    continue
                                if _is_kv_header_line(part):
                                    continue
                                pos_dept = part
                    # 找到公司后，再向下最多 3 行填：行业/规模/部门/职位（不再覆盖 company）
                    # EN: After finding the company, fill industry/size/department/position from at most 3 lines below (company is no longer overwritten)
                    # JA: 会社が見つかったら、下の最大 3 行から業界・規模・部署・職位を埋める（company はもう上書きしない）
                    for kk in range(k + 1, k + 4):
                        if i_line + kk >= len(lines_pool):
                            break
                        nn = lines_pool[i_line + kk].strip()
                        if not nn or nn == "|" or DATE_RANGE_TOKEN_RE.search(nn) or nn in STOP_HEADERS:
                            break
                        # ====== 统一 KV 分发 ======
                        # EN: ====== Unified KV dispatch ======
                        # JA: ====== 統一した KV の振り分け ======
                        if _dispatch_kv(nn):
                            # 同 上：如果是 key-only，try 下一行 value
                            # EN: Same as above: if key-only, try the next line as the value
                            # JA: 上と同じ：key だけなら、次の行を値として試す
                            key_only_check2 = re.fullmatch(r"([\u4e00-\u9fffA-Za-z0-9]{1,12})\s*[:：]\s*", nn)
                            if key_only_check2 and (i_line + kk + 1) < len(lines_pool):
                                vv = lines_pool[i_line + kk + 1].strip()
                                if vv and not _is_kv_header_line(vv) and not DATE_RANGE_TOKEN_RE.search(vv) and vv not in STOP_HEADERS:
                                    _dispatch_kv(f"{key_only_check2.group(1)}：{vv}")
                            continue
                        m_emp_nn = re.search(r"(" + EMPLOYEE_RE_STR + r")", nn)
                        nn_pipe = ("|" in nn or "｜" in nn)
                        nn_parts = [p.strip() for p in re.split(r"[|｜]", nn) if p.strip()]
                        is_attr_nn = False
                        if nn_parts:
                            _c1n = nn_pipe and len(nn) <= 80
                            _c2n = (m_emp_nn is not None
                                    or any(kw in nn for kw in INDUSTRY_COMPANY_NATURE_KW)
                                    or (len(nn_parts) >= 2 and all(p and len(p) <= 30 for p in nn_parts)))
                            _c3n = not _has_comp_sign(nn_parts[0])
                            is_attr_nn = _c1n and _c2n and _c3n
                        if m_emp_nn and not comp_employees:
                            comp_employees = m_emp_nn.group(1)
                        if is_attr_nn:
                            if not comp_industry and nn_parts:
                                inds_nn = [p for p in nn_parts if "人" not in p]
                                if inds_nn:
                                    comp_industry = " | ".join(inds_nn)
                            continue
                        if ("部" in nn or "组" in nn or "科" in nn or "中心" in nn or "事业部" in nn
                                or "分公司" in nn or "办事处" in nn) and not pos_dept and len(nn) <= 20:
                            if not _dispatch_kv(nn) and not _is_kv_header_line(nn):
                                pos_dept = nn
                            continue
                        if not position and len(nn) <= 25 and not _is_duration_text(nn) and not any(tok in nn for tok in ("经历", "职责", "描述", "性质", "规模", "元/月", "工作描述",
                                                                                             "分公司", "办事处")):
                            if _dispatch_kv(nn):
                                continue
                            if _is_kv_header_line(nn):
                                continue
                            position = nn
                            continue
                    break  # 关键：找到公司后必须跳出，避免后续 k 值 覆盖 company！
                    # EN: Key: break out after finding the company, so later k values do not overwrite company!
                    # JA: 重要：会社が見つかったら必ずループを抜け、後続の k の値が company を上書きしないようにする！
                # 不是公司、不是属性 → 尝试作职位；先 再 检测 一次 是不是 属性行（「|」分隔 行业/规模/性质）
                # EN: Not a company, not an attribute → try it as a position; first detect once more whether it is an attribute line ("|"-separated industry/size/type)
                # JA: 会社でも属性でもない → 職位として試す。その前にもう一度属性の行（「|」区切りの業界・規模・性質）かどうかを確認する
                if not position and not _is_duration_text(nxt) and not _has_comp_sign(nxt):
                    ok, ind, emp = _try_extract_attrs(nxt)
                    if ok:
                        if ind and not comp_industry:
                            comp_industry = ind
                        if emp and not comp_employees:
                            comp_employees = emp
                        continue
                    # —— 新增：KV 表头 / KV 行内分发
                    # EN: —— New: dispatch KV headers / in-line KV
                    # JA: —— 追加：KV の見出し・行内の KV の振り分け
                    if _dispatch_kv(nxt):
                        continue
                    if _is_kv_header_line(nxt):
                        continue
                    # —— 新增：纯职位词检测（如「行政专员/助理」无公司标志）→ 直接填 position
                    # EN: —— New: pure position word detection (e.g. "行政专员/助理" (admin specialist/assistant) without a company marker) → fill position directly
                    # JA: —— 追加：純粋な職位の語の検出（例：会社の目印のない「行政专员／助理」（総務担当／アシスタント））→ そのまま position に入れる
                    as_pos = _looks_pure_position(nxt, False)
                    if len(nxt) <= 25 and not any(k in nxt for k in ("经历", "职责", "描述", "业绩")):
                        if as_pos or len(nxt) <= 15:
                            position = nxt
                            continue

        # 3) position 还没有时：日期段同一行 tail_parts 剩余内容里挑一个
        # EN: 3) When there is still no position: pick one from the remaining tail_parts on the same line as the date range
        # JA: 3) まだ position がない場合：期間と同じ行の残りの tail_parts から 1 つ選ぶ
        if not position:
            # 看这行 tail 有没有月薪
            # EN: Check whether this line's tail has a monthly salary
            # JA: この行の tail に月給があるかを見る
            if tail_parts:
                # —— 关键修复：跳过已经作为 found_comp 取走的那个 part（避免公司名被再次塞入 position）
                #    顾先生案例：tail_parts[0]='歩雷软件科技（上海）有限公司' 已被 found_comp 拿走，
                #    这里如果再遍历 tail_parts 全量，就会把公司名塞回 position，彻底错位。
                # EN: —— Key fix: skip the part already taken as found_comp (so the company name is not stuffed into position again)
                #        A past case: tail_parts[0]='歩雷软件科技（上海）有限公司' was already taken by found_comp;
                #        iterating over all of tail_parts here again would stuff the company name back into position, completely misplacing it.
                # JA: —— 重要な修正：すでに found_comp として取った part はスキップする（会社名が再び position に入るのを防ぐ）
                #        過去の事例：tail_parts[0]='歩雷软件科技（上海）有限公司' はすでに found_comp が取っていたが、
                #        ここで再び tail_parts 全体を走査すると会社名が position に戻され、完全にずれてしまう。
                for idx_p, p in enumerate(tail_parts):
                    if found_idx >= 0 and idx_p == found_idx:
                        # 已经用 found_comp 作为 company_name 取走了 → 不再塞到 position
                        # EN: Already taken as company_name via found_comp → do not put it into position again
                        # JA: すでに found_comp として company_name に取った → もう position には入れない
                        continue
                    if "元/月" in p:
                        continue
                    if p and len(p) <= 40 and not any(k in p for k in ("经历", "职责", "描述", "业绩", "性质", "规模")):
                        # —— 额外：如果 p 有强公司标志（股份/有限/集团/公司等），明显是错位的公司名 → 不当职位
                        # EN: —— Extra: if p has a strong company marker (股份/有限/集团/公司 etc.), it is obviously a misplaced company name → not a position
                        # JA: —— 追加：p に強い会社の目印（股份／有限／集团／公司 など）があれば、明らかにずれた会社名 → 職位ではない
                        if _has_comp_sign(p):
                            # 可以作为 company 的 fallback（如果当前 company 是纯后缀/空）
                            # EN: Can be used as a company fallback (if the current company is a pure suffix/empty)
                            # JA: company の代替として使える（現在の company が接尾辞だけか空の場合）
                            if not company or company in ("有限公司", "股份有限公司", "有限责任公司"):
                                company = p
                            continue
                        ok, ind, emp = _try_extract_attrs(p)
                        if ok:
                            if ind and not comp_industry:
                                comp_industry = ind
                            if emp and not comp_employees:
                                comp_employees = emp
                            continue
                        if p.endswith("人"):
                            continue
                        # —— 新增 KV 分发
                        # EN: —— New KV dispatch
                        # JA: —— 追加の KV の振り分け
                        if _dispatch_kv(p):
                            continue
                        if _is_kv_header_line(p):
                            continue
                        if not position:
                            position = p
                        elif not pos_dept and len(p) <= 12:
                            pos_dept = p
            if not position and head_parts:
                # head_parts 同理：排除已经通过 head_parts[-1] 作为 company 取走的 part
                # EN: Same for head_parts: exclude the part already taken as company via head_parts[-1]
                # JA: head_parts も同様：head_parts[-1] ですでに company として取った part を除く
                for idx_hp, hp in enumerate(reversed(head_parts)):
                    real_idx = len(head_parts) - 1 - idx_hp
                    if not company and len(head_parts) >= 1 and real_idx == len(head_parts) - 1 and _valid_company(head_parts[-1]):
                        # 已经在 L3851 (elif head_parts and _valid_company(head_parts[-1])) 作为 company 取走 → 跳过
                        # EN: Already taken as company at L3851 (elif head_parts and _valid_company(head_parts[-1])) → skip
                        # JA: L3851（elif head_parts and _valid_company(head_parts[-1])）ですでに company として取った → スキップ
                        continue
                    if hp and len(hp) <= 40 and not any(k in hp for k in ("经历", "职责", "描述", "业绩", "性质", "规模")):
                        # 如果 hp 有强公司标志（有限/股份/公司等），是错位公司名 → 不当职位
                        # EN: If hp has a strong company marker (有限/股份/公司 etc.), it is a misplaced company name → not a position
                        # JA: hp に強い会社の目印（有限／股份／公司 など）があれば、ずれた会社名 → 職位ではない
                        if _has_comp_sign(hp):
                            if not company or company in ("有限公司", "股份有限公司", "有限责任公司"):
                                company = hp
                            continue
                        ok, ind, emp = _try_extract_attrs(hp)
                        if ok:
                            if ind and not comp_industry:
                                comp_industry = ind
                            if emp and not comp_employees:
                                comp_employees = emp
                            continue
                        if hp.endswith("人"):
                            continue
                        # —— 新增 KV 分发
                        # EN: —— New KV dispatch
                        # JA: —— 追加の KV の振り分け
                        if _dispatch_kv(hp):
                            continue
                        if _is_kv_header_line(hp):
                            continue
                        position = hp
                        break

        # 4) 描述/职责：从 i_line + 公司/职位读取行数 到下一个 DATE 或 STOP_HEADER 之间
        # EN: 4) Description/duties: read from i_line + the lines read for company/position up to the next DATE or STOP_HEADER
        # JA: 4) 説明・職務：i_line + 会社・職位のために読んだ行数の位置から、次の DATE か STOP_HEADER までを読む
        start_j = i_line + 1
        # 如果这一行就带了日期+公司，且 tail_parts[0] 已经像公司（已经读完），就从下一行
        # 跳过 i_line+1~i_line+6 之间已经读取过的公司/职位属性行数（最多扫 2 行就进 break，由 STOP_HEADERS 控制）
        # EN: If this line already carries date + company and tail_parts[0] already looks like a company (already read), start from the next line
        #     Skip the company/position attribute lines already read between i_line+1 and i_line+6 (scan at most 2 lines before break, controlled by STOP_HEADERS)
        # JA: この行にすでに日付 + 会社があり、tail_parts[0] がすでに会社らしい（読み終えた）なら、次の行から始める
        #     i_line+1〜i_line+6 の間で読んだ会社・職位の属性の行はスキップする（最大 2 行スキャンして break。STOP_HEADERS で制御）
        j = start_j
        while j < len(lines_pool):
            cur = lines_pool[j].strip()
            if not cur:
                j += 1
                continue
            if DATE_RANGE_TOKEN_RE.search(cur):
                break
            if cur in STOP_HEADERS:
                break
            if any(cur.startswith(h + "：") or cur.startswith(h + ":") for h in ("工作经历", "培训经历", "教育经历", "项目经历", "自我评价")):
                break
            if cur == "|":
                j += 1
                continue
            # ====== 统一 KV 行处理（公司性质/规模/行业/部门/职位/汇报/下属/月薪 等） ======
            # EN: ====== Unified KV line handling (company type/size/industry/department/position/reports to/subordinates/monthly salary, etc.) ======
            # JA: ====== 統一した KV 行の処理（会社の性質・規模・業界・部署・職位・報告先・部下・月給など）======
            if _dispatch_kv(cur):
                # key-only：try 下一行 value
                # EN: key-only: try the next line as the value
                # JA: key だけ：次の行を値として試す
                key_only_chk = re.fullmatch(r"([\u4e00-\u9fffA-Za-z0-9]{1,12})\s*[:：]\s*", cur)
                if key_only_chk and (j + 1) < len(lines_pool):
                    next_line = lines_pool[j + 1].strip()
                    if next_line and not _is_kv_header_line(next_line) and not DATE_RANGE_TOKEN_RE.search(next_line) and next_line not in STOP_HEADERS:
                        _dispatch_kv(f"{key_only_chk.group(1)}：{next_line}")
                        j += 1  # 跳过下一行（已被当作 value）
                        # EN: Skip the next line (already used as the value)
                        # JA: 次の行をスキップする（すでに値として使った）
                j += 1
                continue
            # 行业/规模/性质 组合行
            # EN: Combined industry/size/type line
            # JA: 業界・規模・性質の組み合わせの行
            m_emp = re.search(r"(" + EMPLOYEE_RE_STR + r")", cur)
            if m_emp and any(mark in cur for mark in ("性质", "企业", "外商", "民营", "合资", "国企", "上市公司")):
                if not comp_employees:
                    comp_employees = m_emp.group(1)
                ind_part = re.sub(r"\s*" + EMPLOYEE_RE_STR + r"\s*", "", cur).strip(" |｜，,")
                if ind_part and not comp_industry and not any(ind_part.startswith(pref) for pref in ("工作描述", "工作内容", "业绩描述", "职责描述")):
                    # 必须包含行业特征词才认为是行业；同时排除部门/岗位通用词
                    # EN: Treat it as an industry only if it contains industry feature words; also exclude generic department/post words
                    # JA: 業界の特徴語を含む場合だけ業界とみなし、部署・ポストの一般的な語は除く
                    _BAD_IND_KW = ("售后", "营业", "客户服务", "客户支持", "技术支持", "技术服务", "行政", "人事",
                                   "财务", "销售", "市场", "运营", "客服", "采购", "物流", "生产", "品保",
                                   "质检", "研发", "设计", "工程", "业务", "商务", "会计", "出纳", "招聘")
                    if not any(bk in ind_part for bk in _BAD_IND_KW) and \
                       any(mark in ind_part for mark in ("行业", "贸易", "制造", "服务业", "IT", "互联网", "电子", "金融", "医药", "能源", "房地产", "传媒", "咨询", "零售", "物流", "消费", "汽车", "教育", "医疗")):
                        comp_industry = ind_part
                j += 1
                continue
            # 行业 行（不包含性质/规模的，必须包含行业特征词，且排除公司名和职位名）
            # EN: Industry line (without type/size; must contain industry feature words and exclude company and position names)
            # JA: 業界の行（性質・規模を含まないもの。業界の特徴語を必ず含み、会社名と職位名は除く）
            if not comp_industry and ("|" in cur or "｜" in cur) and len(cur) <= 60:
                parts = [p.strip() for p in re.split(r"[|｜]", cur) if p.strip()]
                # 剔除公司名与职位名与部门名部分
                # EN: Remove the company name, position name and department name parts
                # JA: 会社名・職位名・部署名の部分を取り除く
                ind_parts = []
                # 部门/岗位通用词：命中则该 part 是具体部门/岗位，不是行业
                # EN: Generic department/post words: on a hit the part is a specific department/post, not an industry
                # JA: 部署・ポストの一般的な語：ヒットすればその part は具体的な部署・ポストであり、業界ではない
                DEPT_OR_ROLE_KW = (
                    "售后", "营业", "客户服务", "客户支持", "技术支持", "技术服务", "行政", "人事",
                    "财务", "销售", "市场", "运营", "客服", "采购", "物流", "生产", "品保",
                    "质检", "研发", "设计", "工程", "服务工程师", "业务", "商务", "会计",
                    "出纳", "招聘", "培训师", "专员", "助理", "经理", "主管", "工程师"
                )
                for p in parts:
                    if p.endswith("人") or _has_comp_sign(p):
                        continue
                    if any(pos_suf in p for pos_suf in ("工程师", "技术员", "专员", "助理", "经理", "主管", "总监", "代表", "领班", "装配", "工人")):
                        continue
                    if any(dk in p for dk in DEPT_OR_ROLE_KW):
                        continue
                    ind_parts.append(p)
                if ind_parts:
                    cand_ind = " | ".join(ind_parts)
                    if any(mark in cand_ind for mark in ("行业", "贸易", "制造", "服务业", "IT", "互联网", "电子", "金融", "医药", "能源", "房地产", "传媒", "咨询", "零售", "物流", "消费", "汽车", "教育", "医疗", "半导体", "通信", "机械", "加工", "化工")):
                        comp_industry = cand_ind
                    j += 1
                    continue
            # 不是 STOP HEADER 且不是属性 → 描述
            # EN: Not a STOP HEADER and not an attribute → description
            # JA: STOP HEADER でも属性でもない → 説明
            if any(cur.startswith(pref) for pref in ("工作描述：", "工作描述:", "工作内容：", "工作内容:", "职责描述：", "职责描述:",
                                                       "业绩描述：", "业绩描述:", "项目描述：", "项目描述:",
                                                       "责任描述：", "责任描述:", "职责内容：", "职责内容:")):
                val = (cur.split("：", 1)[-1] if "：" in cur else cur.split(":", 1)[-1]).strip()
                if val:
                    resp_lines.append(val)
                j += 1
                while j < len(lines_pool):
                    cc = lines_pool[j].strip()
                    if DATE_RANGE_TOKEN_RE.search(cc) or cc in STOP_HEADERS:
                        break
                    if any(cc.startswith(pref) for pref in ("工作经历", "培训经历", "教育经历", "项目经历", "自我评价")):
                        break
                    resp_lines.append(cc)
                    j += 1
                continue
            resp_lines.append(cur)
            j += 1

        # 最后再 company 校验：若 company 不是合法公司名 且 position 也空 → 丢弃；否则保留（后续 fallback 会补 company）
        # EN: Final company check: if company is not a valid company name and position is also empty → discard; otherwise keep (the later fallback fills company)
        # JA: 最後の company の確認：company が正当な会社名でなく position も空 → 破棄。それ以外は残す（後の最終手段で company を補う）
        if not _valid_company(company) and not position and not pos_dept:
            return None

        # ======================================================================
        # ====== [TOP PRIORITY: FIRST RUN] company/position 反向填入的 SANITY SWAP ======
        #    必须在 position-reset / company-clean 之前跑！否则 position 被先清空，swap 判断就失效。
        # ======================================================================
        # EN: ======================================================================
        #     ====== [TOP PRIORITY: FIRST RUN] SANITY SWAP for company/position filled in reverse ======
        #        Must run before position-reset / company-clean! Otherwise position is cleared first and the swap check stops working.
        #     ======================================================================
        # JA: ======================================================================
        #     ====== [最優先：最初に実行] company/position が逆に入っている場合の SANITY SWAP ======
        #        position-reset / company-clean より前に必ず実行すること！さもないと先に position が空にされ、入れ替えの判定が効かなくなる。
        #     ======================================================================
        _COMP_MARKS_SWAP = ("公司", "有限公司", "有限责任公司", "股份", "集团", "银行", "基金", "证券", "保险",
                            "事务所", "工厂", "制造厂", "工作室", "医院", "分公司", "事业部", "办事处",
                            "Inc", "Ltd", "Co", "LLC", "株式会社")
        _POS_SUFF_SWAP = ("专员", "助理", "经理", "主管", "总监", "组长", "科长", "部长", "主任", "工程师",
                          "设计师", "顾问", "代表", "销售", "会计", "出纳", "文员", "秘书", "行政", "人事",
                          "财务", "讲师", "培训师", "编辑", "记者", "校长", "院长", "所长", "调达", "店长")
        _sl_cmp = _valid_company(company) or any(m in company for m in _COMP_MARKS_SWAP)
        _sl_pos = _valid_company(position) or any(m in position for m in _COMP_MARKS_SWAP)
        _cp_looks_pos = (len(company) <= 12 and any(suf in company for suf in _POS_SUFF_SWAP)) or (
            len(company) <= 10 and not _sl_cmp)
        # 额外：company 是描述行/职责行（以"1.""开头或包含动词且很长），position 像公司名 → 也 swap
        # EN: Extra: company is a description/duty line (starting with "1." or containing verbs and very long) and position looks like a company name → also swap
        # JA: 追加：company が説明・職務の行（「1.」で始まる、または動詞を含み非常に長い）で、position が会社名らしい → これも入れ替える
        _cp_looks_garbage_desc = (
            bool(re.match(r"^(?:\s*\d+[\.、)）]\s*)+", company))  # starts with list markers like "1. 2. "
            or (len(company) >= 20 and not _sl_cmp and any(v in company for v in ("负责", "组织", "协调", "管理", "描述", "职责", "工作", "业绩")))
        )
        _should_swap = False
        if (not _sl_cmp and _sl_pos) and (_cp_looks_pos or _cp_looks_garbage_desc):
            _should_swap = True
        # 兜底：沈莉君 W1 这种 case—— company 前面是 "1. 每天..." 明显 garbage，position 是 "爱婴室门店组长..." 有职位后缀
        # EN: Fallback for cases like W1 in a past case — company starts with "1. 每天..." (1. every day ...), obviously garbage, while position is "爱婴室门店组长..." (store team leader ...) with a position suffix
        # JA: 過去の事例の W1 のようなケースの最終手段 — company が「1. 每天...」（1. 毎日…）で始まる明らかなゴミで、position が職位の接尾辞を持つ「爱婴室门店组长...」（店舗チームリーダー…）
        if not _should_swap and _cp_looks_garbage_desc and any(suf in position for suf in _POS_SUFF_SWAP):
            _should_swap = True
        if _should_swap:
            company, position = position, company
            # swap 后清理前置冒号
            # EN: Clean a leading colon after the swap
            # JA: 入れ替え後に先頭のコロンを除く
            company = re.sub(r"^\s*[:：]\s*", "", (company or "").strip())
            position = re.sub(r"^\s*[:：]\s*", "", (position or "").strip())

        # 额外过滤：纯学校/大学（公司名含大学/学院/学校且没有公司后缀）不应算工作
        # EN: Extra filter: pure schools/universities (company name contains 大学/学院/学校 without a company suffix) should not count as work
        # JA: 追加の除外：純粋な学校・大学（会社名に大学／学院／学校を含み、会社の接尾辞がない）は職歴に数えない
        PURE_SCHOOL_TOKENS = ("大学", "学院", "学校", "中学", "职业高中", "党校", "专业：", "学历：")
        COMPANY_SUFFIX_OR_STRONG = ("公司", "有限", "股份", "集团", "分公司", "工厂", "制造厂", "工作室",
                                    "Inc", "Ltd", "Co", "LLC", "株式会社", "事业部", "办事处",
                                    "银行", "基金", "证券", "保险", "事务所", "企业", "控股", "医院")
        comp_pos_comb = f"{company}|{position}"
        is_school_only = (any(t in comp_pos_comb for t in PURE_SCHOOL_TOKENS)
                          and not any(s in comp_pos_comb for s in COMPANY_SUFFIX_OR_STRONG))
        if is_school_only:
            return None

        # 再过滤：学生组织 / 培训内容 / 社会实践 不应当作工作（没有强公司标志时）
        # EN: Further filter: student organisations / training content / social practice should not be taken as work (when there is no strong company marker)
        # JA: さらなる除外：学生団体・研修内容・社会実践は職歴としない（強い会社の目印がない場合）
        BAD_SCHOOL_WORK_TOKENS = (
            "社会实践部", "学生会", "社团", "班委", "班长", "团支书", "社长", "副社长", "部长", "副部长",
            "主席", "副主席", "志愿者", "义工", "培训描述", "培训机构", "培训内容", "课程描述",
            "在校期间", "学生实践", "学生社团", "团总支", "团支部", "学习部", "宣传部", "外联部",
            "体育部", "文艺部", "生活部", "纪检部", "组织部", "学生组织", "学生社联", "学联",
            "青年志愿者协会", "志愿者协会", "校友会", "同乡会", "联谊会", "联谊", "协会",
            "校内职务", "校园活动", "在校任职", "课代表", "课程代表", "指导老师", "导师",
        )
        has_strong_company_sign = any(s in company for s in COMPANY_SUFFIX_OR_STRONG)
        if not has_strong_company_sign:
            comp_pos_all = f"{company}|{position}|{pos_dept}"
            if any(tok in comp_pos_all for tok in BAD_SCHOOL_WORK_TOKENS):
                return None
        # 培训课程名/安装调试这种（动词短语开头且无公司标志）也不进 work
        # EN: Training course names / installation & commissioning (starting with a verb phrase and without a company marker) do not go into work either
        # JA: 研修コース名・据え付け調整のようなもの（動詞句で始まり会社の目印がない）も work に入れない
        if not has_strong_company_sign and len(company) >= 6 and not position:
            if re.match(r"^[负责协助组织开发维护参与制定管理进行配合完成建立收集提供推广推进改善提高拓展沟通协调设计制作发放招募选址宣传策划跟进运营建设预算参加支持调研分析]", company):
                return None
        # 「X线机的安装与调试」这种课程培训名：有「的」且无公司标志 → 不进 work
        # EN: Training course names like "X线机的安装与调试" (installation and commissioning of X-ray machines): contains "的" and no company marker → not into work
        # JA: 「X线机的安装与调试」（X 線装置の据え付けと調整）のような研修コース名：「的」を含み会社の目印がない → work に入れない
        if not has_strong_company_sign and "的" in company and len(company) >= 6:
            return None

        # 最终 安全网：如果 position 还是 「行业|规模|性质」这种 属性行，最后 再 拆一次！
        # EN: Final safety net: if position is still an "industry|size|type" attribute line, split it once more at the end!
        # JA: 最後の安全網：position がまだ「業界|規模|性質」の属性の行なら、最後にもう一度分割する！
        if position:
            ok, ind, emp = _try_extract_attrs(position)
            if ok:
                if ind and not comp_industry:
                    comp_industry = ind
                if emp and not comp_employees:
                    comp_employees = emp
                position = ""
        # 安全网2：如果 pos_dept 也是 属性行
        # EN: Safety net 2: if pos_dept is also an attribute line
        # JA: 安全網 2：pos_dept も属性の行の場合
        if pos_dept:
            ok, ind, emp = _try_extract_attrs(pos_dept)
            if ok:
                if ind and not comp_industry:
                    comp_industry = ind
                if emp and not comp_employees:
                    comp_employees = emp
                pos_dept = ""

        if position:
            position = re.sub(r"^(?:职务|职位|岗位)\s*[:：]?\s*", "", position).strip()
            position = position.lstrip(":： ").strip()
        if pos_dept and (len(pos_dept) > 15 or any(k in pos_dept for k in ("描述", "职责", "负责", "1.", "2.", "3.", "组织", "协调", "管理"))):
            pos_dept = ""

        if position and (any(k in position for k in ("元/月", "元/年", "千/月", "万/月", "000-", "元")) or _has_comp_sign(position) or position == company or (len(position) >= 8 and (company in position or position in company))):
            position = ""

        # —— 最终清洗：position 不应该含完整公司名；如果现在 position 还有「XX有限公司」等，切掉（防止 swap 前 position 里就有公司尾）
        # EN: —— Final cleaning: position should not contain a full company name; if position still has "XX有限公司" etc., cut it off (in case position had a company tail before the swap)
        # JA: —— 最後のクレンジング：position に完全な会社名が入っていてはならない。まだ「XX有限公司」などがあれば切り落とす（入れ替え前から position に会社名の末尾があった場合に備える）
        if position and _has_comp_sign(position):
            _POS_SUFF_F = ("专员", "助理", "经理", "主管", "总监", "组长", "科长", "部长", "主任", "工程师",
                           "设计师", "顾问", "代表", "销售", "会计", "出纳", "文员", "秘书", "行政", "人事",
                           "财务", "讲师", "培训师", "编辑", "记者", "校长", "院长", "所长", "调达", "店长")
            _cp = re.match(r"^(.*?)\s*(?:[\(（].*?[\)）]?\s*)?(" +
                           r"|".join(re.escape(m) for m in ["有限公司", "有限责任公司", "股份有限公司", "公司", "集团",
                                                            "分公司", "事业部", "办事处", "工厂", "制造厂", "银行",
                                                            "事务所", "医院", "工作室", "研究院"]) +
                           r")\s*(.*)$", position)
            if _cp:
                _bef, _mark, _aft = _cp.group(1).strip(), _cp.group(2).strip(), _cp.group(3).strip()
                if _bef and (any(suf in _bef for suf in _POS_SUFF_F) or len(_bef) <= 8):
                    position = _bef
                elif _aft and any(suf in _aft for suf in _POS_SUFF_F):
                    position = _aft
                else:
                    position = _aft or _bef

        # 若 position 为空或被跳过，从 resp_lines 前两行提取短职位名（如 公共关系 / 医疗器械注册）
        # EN: If position is empty or was skipped, extract a short position name from the first two lines of resp_lines (e.g. 公共关系 / 医疗器械注册: public relations / medical device registration)
        # JA: position が空かスキップされた場合は、resp_lines の最初の 2 行から短い職位名を抽出する（例：公共关系／医疗器械注册（広報／医療機器登録））
        if not position and resp_lines:
            cand_p = resp_lines[0].strip()
            cand_p = re.sub(r"^(?:职务|职位|岗位)\s*[:：]?\s*", "", cand_p).strip()
            if cand_p and len(cand_p) <= 20 and not _is_duration_text(cand_p) and not any(k in cand_p for k in ("描述", "职责", "负责", "项目")):
                position = cand_p
                resp_lines = resp_lines[1:]
                if not pos_dept and resp_lines:
                    cand_d = resp_lines[0].strip()
                    if cand_d and len(cand_d) <= 15 and not _is_duration_text(cand_d) and not any(k in cand_d for k in ("描述", "职责", "负责")):
                        pos_dept = cand_d
                        resp_lines = resp_lines[1:]

        comp_industry = _clean_industry_str(comp_industry)

        # 去重 key 归一化：去掉 公司名 末尾 多余 的 冒号/空格 标点，避免 "上海科胜制药有限公司" 和 "上海科胜制药有限公司：" 被 当作 两个 公司
        # EN: Normalise the dedup key: remove superfluous trailing colons/spaces/punctuation from the company name, so "上海科胜制药有限公司" and "上海科胜制药有限公司：" are not treated as two companies
        # JA: 重複排除のキーを正規化する：会社名の末尾の余分なコロン・空白・句読点を除き、「上海科胜制药有限公司」と「上海科胜制药有限公司：」を 2 つの会社として扱わないようにする
        _norm_company = re.sub(r"[\s:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", (company or "").strip())
        key = (start_ym, end_ym, _norm_company)
        if key in seen_work_keys:
            return None
        seen_work_keys.add(key)
        # ====== 最终：company / position / dept / resp_lines 的 a)/b)/c)/数字. 等列表标记 + 前导冒号 清理 ======
        # EN: ====== Final: clean list markers like a)/b)/c)/numbers. and leading colons from company / position / dept / resp_lines ======
        # JA: ====== 最後：company / position / dept / resp_lines から a)/b)/c)/数字. などのリスト記号と先頭のコロンを除去する ======
        _LIST_MARK_WORK_RE = re.compile(
            r"^\s*(?:[a-zA-Z０-９\d一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{1,3}\s*[)）.、.．]\s*|\d+\s*[.、]\s*)"
        )
        def _strip_work_list_marks(s: str) -> str:
            if not s: return ""
            s2 = s.strip()
            s2 = _LIST_MARK_WORK_RE.sub("", s2, count=1).strip()
            while s2 and _LIST_MARK_WORK_RE.match(s2):
                s2 = _LIST_MARK_WORK_RE.sub("", s2, count=1).strip()
            s2 = re.sub(r"^\s*[:：]\s*", "", s2).strip()
            return s2
        company = _strip_work_list_marks(company)
        position = _strip_work_list_marks(position)
        pos_dept = _strip_work_list_marks(pos_dept)
        resp_lines = [_strip_work_list_marks(l) for l in resp_lines if _strip_work_list_marks(l)]
        work = {
            "company_name": company,
            "company_employees": comp_employees,
            "company_industry": comp_industry,
            "position": position,
            "position_type": "",
            "position_salary": "",
            "position_dept": pos_dept,
            "position_report_to": "",
            "position_subordinate": "",
            "employment_type": "全职",
            "annual_salary_min": "",
            "annual_salary_max": "",
            "status": status,
            "position_start": start_ym,
            "position_resigned": end_ym,
            "resigned_reason": "",
            "position_responsibilities": "\n".join(resp_lines).strip(),
            "position_achievements": "",
        }
        return work

    # 先在 block_main 上扫（若存在），再在 block_work_form 扫，最后在全局扫去重
    # 提取 header 里的公司名 fallback（如 冷峰：工作经验：京青仲信（北京）科技有限公司）
    # EN: Scan block_main first (if present), then block_work_form, and finally scan globally with dedup
    #     Extract a fallback company name from the header (e.g. a past case: 工作经验：京青仲信（北京）科技有限公司)
    # JA: まず block_main（あれば）をスキャンし、次に block_work_form、最後に全体をスキャンして重複を除く
    #     ヘッダーから会社名の代替を抽出する（例：過去の事例 工作经验：京青仲信（北京）科技有限公司）
    header_fallback_company = ""
    # 宽松匹配：PAGE/个人概况 后面的 工作经验：XXX
    # EN: Loose matching: 工作经验：XXX (work experience: XXX) after PAGE/个人概况 (personal overview)
    # JA: 緩いマッチ：PAGE／个人概况（個人の概要）の後の 工作经验：XXX（職歴：XXX）
    m_hc = re.search(r"(?:工作经验|工作单位|现单位|在职公司|当前公司)\s*[：:]\s*([^\n|｜，,。]{2,80})", text)
    if m_hc:
        cand = m_hc.group(1).strip(" 　\t|｜，,。.")
        if _valid_company(cand):
            header_fallback_company = cand
    def _apply_header_fallback(w: dict[str, Any]) -> None:
        nonlocal header_fallback_company
        if not header_fallback_company:
            return
        cur_comp = (w.get("company_name") or "").strip()
        if not cur_comp:
            w["company_name"] = header_fallback_company
            return
        if not _valid_company(cur_comp) or len(cur_comp) >= 40:
            # 当前公司名过长或无效 → 用 fallback
            # EN: The current company name is too long or invalid → use the fallback
            # JA: 現在の会社名が長すぎるか無効 → 代替を使う
            w["company_name"] = header_fallback_company
            return
        # 如果 cur_comp 是 动词短语开头（如「参与制定...」中间有「公司」两个字但不是公司名），或者 没有 真正的公司后缀 且 很长 → 替换
        # EN: If cur_comp starts with a verb phrase (e.g. "参与制定..." (took part in drafting...) contains the two characters "公司" in the middle but is not a company name), or has no real company suffix and is very long → replace
        # JA: cur_comp が動詞句で始まる（例：「参与制定...」（〜の策定に参加）は途中に「公司」の 2 文字があるが会社名ではない）か、本当の会社の接尾辞がなく非常に長い → 置き換える
        INVALID_START_RE = re.compile(r"^(?:" + "|".join(INVALID_COMP_PREFIX_VERBS) + r")")
        starts_with_verb = bool(INVALID_START_RE.match(cur_comp))
        has_real_comp_suffix = any(cur_comp.endswith(suf) for suf in ("公司", "有限公司", "股份有限公司", "集团", "集团有限公司", "分公司", "工厂", "制造厂", "工作室", "Inc", "Ltd", "Co", "LLC", "株式会社", "事业部", "办事处", "银行", "基金", "证券", "保险", "事务所", "企业", "控股", "医院", "学校", "大学", "学院", "研究院", "厂", "院", "局", "店", "行", "社", "所", "网", "部", "中心", "厅", "机构", "机关", "单位", "广场", "大厦", "商城", "超市", "市场", "矿", "站", "队"))
        if starts_with_verb and len(cur_comp) >= 15:
            w["company_name"] = header_fallback_company
            return
        if not has_real_comp_suffix:
            if len(cur_comp) >= 15 or starts_with_verb:
                w["company_name"] = header_fallback_company
    if block_main:
        lines = _split_glued_work_lines([l.strip() for l in block_main.splitlines() if l.strip()])
        for i, line in enumerate(lines):
            if DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line):
                res = _process_date_in_line(line, i, lines)
                if res:
                    works.append(res)
    else:
        # —— 修复：split_resume_sections 没切出板块时，fallback 到整个入参 text（上层已切好的 work_sec_text）
        # EN: —— Fix: when split_resume_sections did not cut out a section, fall back to the whole input text (the work_sec_text already cut by the upper layer)
        # JA: —— 修正：split_resume_sections がセクションを切り出せなかった場合は、入力の text 全体（上位で切り出し済みの work_sec_text）に戻す
        lines_fb = _split_glued_work_lines([l.strip() for l in text.splitlines() if l.strip()])
        for i, line in enumerate(lines_fb):
            if DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line):
                res = _process_date_in_line(line, i, lines_fb)
                if res:
                    works.append(res)
    if block_work_form:
        lines_wf = _split_glued_work_lines([l.strip() for l in block_work_form.splitlines() if l.strip()])
        # 先整段找 WORK_FORM_RE
        # EN: First look for WORK_FORM_RE over the whole block
        # JA: まずブロック全体で WORK_FORM_RE を探す
        for m in WORK_FORM_RE.finditer(block_work_form):
            res = _process_work_form(m)
            if res:
                works.append(res)
        for i, line in enumerate(lines_wf):
            if DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line):
                res = _process_date_in_line(line, i, lines_wf)
                if res:
                    works.append(res)
    # 全局扫（仅当已有 work 列表为空时进行低优先级补漏）
    # EN: Global scan (only as a low-priority gap fill when the work list is still empty)
    # JA: 全体のスキャン（work のリストが空の場合だけ、優先度の低い補完として行う）
    if not works:
        global_lines = _split_glued_work_lines([l.strip() for l in text.splitlines() if l.strip()])
        # 先全局 WORK_FORM
        # EN: First the global WORK_FORM
        # JA: まず全体の WORK_FORM
        for m in WORK_FORM_RE.finditer(text):
            res = _process_work_form(m)
            if res:
                works.append(res)
        # section header 判断：全局扫时，如果当前 i 处于 教育/培训/在校实践/自我评价/技能/证书/项目 section，且后面行无强公司标志 → 跳过
        # EN: Section header check: during the global scan, if the current i is in an education/training/campus practice/self-assessment/skills/certificates/projects section and the following lines have no strong company marker → skip
        # JA: セクション見出しの判定：全体のスキャン中に現在の i が学歴・研修・在学中の実践・自己評価・スキル・資格・プロジェクトのセクションにあり、後続の行に強い会社の目印がない → スキップ
        NON_WORK_SECTIONS = ("教育经历", "教育背景", "培训经历", "培训", "在校实践经历", "社会实践", "自我评价",
                             "专业技能", "技能", "语言能力", "证书", "所获证书", "特长", "兴趣爱好",
                             "项目经历", "项目经验", "Projects", "Project",
                             "Education", "Training", "Skills", "Certificates", "Self-Assessment", "自我评价")
        STRONG_COMPANY_SIGNS_GLOBAL = ("公司", "有限公司", "股份", "集团", "分公司", "工厂", "制造厂",
                                       "工作室", "Inc", "Ltd", "Co", "LLC", "株式会社", "事业部",
                                       "办事处", "银行", "基金", "证券", "保险", "事务所", "企业",
                                       "控股", "医院", "学校", "大学", "学院", "研究院")
        for i, line in enumerate(global_lines):
            # —— 关键修复：包含 DATE 或 SHORTEND 日期格式的行才进入检查/处理（短结尾格式也要走 section 过滤）
            # EN: —— Key fix: only lines containing a DATE or SHORTEND date format go into checking/processing (short-ending formats must also go through the section filter)
            # JA: —— 重要な修正：DATE か SHORTEND の日付形式を含む行だけをチェック・処理の対象にする（末尾の短い形式もセクションのフィルターを通す必要がある）
            has_any_date = bool(DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line))
            if not has_any_date:
                # —— 新增：尝试 short-end 格式（2014.04.15-06.30）是否存在，若有也需走过滤
                # EN: —— New: check whether a short-end format (2014.04.15-06.30) is present; if so it must also be filtered
                # JA: —— 追加：末尾の短い形式（2014.04.15-06.30）があるかを確認し、あればこれもフィルターを通す
                SHORTEND_CHECK_RE = re.compile(
                    r"(?:19|20)\d{2}\s*[./年\-]\s*\d{1,2}\s*(?:[./月\-]\s*\d{1,2}\s*日?)?\s*"
                    r"(?:[\-—–~～至到‒―〜-]{1,4}|-{2,}|—|～|到|至)\s*\d{1,2}\s*[./月\-]\s*\d{1,2}\s*日?"
                )
                has_any_date = bool(SHORTEND_CHECK_RE.search(line))
            if has_any_date:
                # 找 i 前面最近的 section header
                # EN: Find the nearest section header before i
                # JA: i の前で最も近いセクション見出しを探す
                last_section = ""
                for back in range(max(0, i - 200), i):
                    lb = global_lines[back].strip()
                    if lb in NON_WORK_SECTIONS or (len(lb) <= 12 and any(lb.startswith(s) for s in NON_WORK_SECTIONS)):
                        last_section = lb
                        break
                skip_this = False
                if last_section:
                    look_has = False
                    for look in range(i + 1, min(i + 5, len(global_lines))):
                        if DATE_RANGE_TOKEN_RE.search(global_lines[look]) or DATE_YEAR_RANGE_RE.search(global_lines[look]): break
                        if any(s in global_lines[look] for s in STRONG_COMPANY_SIGNS_GLOBAL):
                            look_has = True; break
                    if not look_has:
                        m_d_tmp = DATE_RANGE_TOKEN_RE.search(line) or DATE_YEAR_RANGE_RE.search(line)
                        if not m_d_tmp:
                            # SHORTEND 格式的临时 match，仅用于取 tail_head
                            # EN: Temporary match for the SHORTEND format, only used to get tail_head
                            # JA: SHORTEND 形式の一時的な match。tail_head を取るためだけに使う
                            m_d_tmp = SHORTEND_CHECK_RE.search(line) if 'SHORTEND_CHECK_RE' in locals() else None
                        if m_d_tmp:
                            tail_head = line[m_d_tmp.end():] + line[:m_d_tmp.start()]
                            if not any(s in tail_head for s in STRONG_COMPANY_SIGNS_GLOBAL):
                                skip_this = True
                if skip_this:
                    continue
                res = _process_date_in_line(line, i, global_lines)
                if res:
                    works.append(res)
    # 先对每条 work 应用 header_fallback_company（如果 company 无效/过长/假）
    # EN: First apply header_fallback_company to each work entry (if company is invalid/too long/fake)
    # JA: まず各 work に header_fallback_company を適用する（company が無効・長すぎ・偽物の場合）
    for w in works:
        _apply_header_fallback(w)
    # 最后统一去重：① 全量 key（start+end+公司全名 归一）；② 二级 主体 名 去重（防 同公司 异写 如 "杜邦研发管理有限公司：" vs "杜邦中国研发（管理）有限公司"）
    # EN: Finally dedup uniformly: ① full key (start + end + normalised full company name); ② second-level dedup by entity name (to catch the same company written differently, e.g. "杜邦研发管理有限公司：" vs "杜邦中国研发（管理）有限公司")
    # JA: 最後にまとめて重複排除する：① 全体のキー（start + end + 正規化した会社の正式名）、② 第 2 段階の主体名による重複排除（同じ会社の異なる表記、例：「杜邦研发管理有限公司：」と「杜邦中国研发（管理）有限公司」を防ぐ）
    def _corp_body(name: str) -> str:
        """提取 公司 主体 名：去掉 标点/公司后缀/地域/修饰 词，保留 核心 词。

        EN: Extract the company's entity name: remove punctuation/company suffixes/regions/modifiers, keeping the core words.

        JA: 会社の主体名を抽出する：句読点・会社の接尾辞・地域・修飾語を除き、中核の語を残す。
        """
        n = re.sub(r"[\s:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+", "", name.strip())
        # 去掉 常见 公司 后缀（大 → 小 顺序）
        # EN: Remove common company suffixes (from long to short)
        # JA: よくある会社の接尾辞を除く（長いものから短いものの順）
        for suffix in ("股份有限公司", "有限责任公司", "有限公司", "集团", "公司"):
            if n.endswith(suffix) and len(n) > len(suffix):
                n = n[: -len(suffix)]
        # 去掉 中国/ 地域 前缀/子串
        # EN: Remove 中国 (China) / regional prefixes/substrings
        # JA: 中国・地域の接頭辞や部分文字列を除く
        for token in ("中国", "上海", "北京", "深圳", "广州", "杭州", "南京", "苏州", "北京"):
            n = n.replace(token, "")
        return n

    deduped_raw: list[dict[str, Any]] = []
    seen_full: set[tuple[str, str, str]] = set()
    seen_body: set[tuple[str, str, str]] = set()
    for w in works:
        # —— 关键修复：只接受 dict 类型，防止 str 等垃圾值混入导致 w.get() 炸 AttributeError
        # EN: —— Key fix: accept only dict types, to prevent junk values like str from causing w.get() to blow up with AttributeError
        # JA: —— 重要な修正：dict 型だけを受け付け、str などのゴミの値が混じって w.get() が AttributeError で落ちるのを防ぐ
        if not isinstance(w, dict):
            continue
        _norm_c = re.sub(r"[\s:：,，、；;・·•·\-—_()（）\[\]【】<>《》]+$", "", str(w.get("company_name") or "").strip())
        # 空 公司名 → 跳过（可能 是 工作 描述 里 的 日期 误 抓）
        # EN: Empty company name → skip (it may be a date grabbed by mistake from a job description)
        # JA: 会社名が空 → スキップ（職務説明内の日付を誤って取った可能性がある）
        if not _norm_c:
            continue
        s_key = str(w.get("position_start") or "")
        e_key = str(w.get("position_resigned") or "")
        key_full = (s_key, e_key, _norm_c)
        if key_full in seen_full:
            continue
        # 主体 去重：同 start, 同 end, 主体 名 相同 → 保留 先 遇到 的（通常 更 完整）
        # EN: Entity dedup: same start, same end, same entity name → keep the one seen first (usually more complete)
        # JA: 主体による重複排除：start・end・主体名が同じ → 先に現れたもの（通常はより完全）を残す
        _body = _corp_body(_norm_c)
        key_body = (s_key, e_key, _body)
        if key_body in seen_body and _body:
            continue
        seen_full.add(key_full)
        seen_body.add(key_body)
        w["company_name"] = _norm_c  # 统一 去掉 末尾 冒号 等
        # EN: Uniformly remove trailing colons etc.
        # JA: 末尾のコロンなどを一律に除く
        deduped_raw.append(w)
    deduped = deduped_raw

    # 高置信度模板覆盖：很多 51job/智联导出采用
    # “日期范围 + 公司（同行或下一行）+ 属性 + 部门/职位 + 工作描述”结构。
    # 旧的宽松分类器容易把描述中的短语当公司；这里按日期块边界确定字段。
    # EN: High-confidence template override: many 51job/Zhaopin exports use the structure
    #     "date range + company (same or next line) + attributes + department/position + job description".
    #     The old loose classifier easily took phrases in the description as companies; here fields are determined by date-block boundaries.
    # JA: 高信頼のテンプレートによる上書き：51job／Zhaopin の多くのエクスポートは
    #     「期間 + 会社（同じ行または次の行）+ 属性 + 部署／職位 + 職務説明」の構造を使っている。
    #     旧来の緩い分類器は説明中の語句を会社と誤認しやすいため、ここでは日付ブロックの境界に基づいてフィールドを決める。
    def _parse_explicit_work_blocks(source: str) -> list[dict[str, Any]]:
        source_lines = [line.strip() for line in source.splitlines() if line.strip()]
        date_rows: list[tuple[int, Any]] = []
        for line_index, source_line in enumerate(source_lines):
            match = DATE_RANGE_TOKEN_RE.search(source_line) or DATE_YEAR_RANGE_RE.search(source_line)
            if match and match.start() <= 3:
                date_rows.append((line_index, match))
        parsed: list[dict[str, Any]] = []
        for row_index, (line_index, match) in enumerate(date_rows):
            block_end = date_rows[row_index + 1][0] if row_index + 1 < len(date_rows) else len(source_lines)
            block = source_lines[line_index:block_end]
            first_line = block[0]
            company = first_line[match.end():].strip(" \t:：|｜")
            company = re.sub(r"\s*[（(]\s*\d+\s*(?:年|个?月|天)[^）)]*[）)]\s*$", "", company).strip()
            cursor = 1
            if not company and cursor < len(block):
                company = block[cursor].strip(" \t:：|｜")
                company = re.sub(r"\s*[（(]\s*\d+\s*(?:年|个?月|天)[^）)]*[）)]\s*$", "", company).strip()
                cursor += 1
            if (not company or len(company) > 80
                    or any(company.startswith(v) for v in INVALID_COMP_PREFIX_VERBS)
                    or company in STOP_HEADERS):
                continue

            start_raw, end_raw = match.group(1), match.group(2)
            start_date = _format_ym(start_raw)
            end_date = "" if end_raw in ("至今", "现在", "Present", "Current", "在读") else _format_ym(end_raw)
            pre_description: list[str] = []
            description_lines: list[str] = []
            in_description = False
            for value in block[cursor:]:
                if re.match(r"^(?:工作描述|工作职责|职责描述|主要职责)\s*[:：]?", value):
                    in_description = True
                    remainder = re.sub(r"^(?:工作描述|工作职责|职责描述|主要职责)\s*[:：]?\s*", "", value).strip()
                    if remainder:
                        description_lines.append(remainder)
                    continue
                (description_lines if in_description else pre_description).append(value)

            company_industry = ""
            company_employees = ""
            position = ""
            department = ""
            for value in pre_description:
                if any(token in value for token in ("公司性质", "企业性质", "民营公司", "外资", "合资", "国企")) or re.search(EMPLOYEE_RE_STR, value):
                    parts = [part.strip() for part in re.split(r"[|｜]", value) if part.strip()]
                    for part in parts:
                        employee_match = re.search(EMPLOYEE_RE_STR, part)
                        if employee_match and not company_employees:
                            company_employees = employee_match.group(0)
                        elif not any(token in part for token in ("民营", "外资", "合资", "国企", "上市", "股份制")) and not company_industry:
                            company_industry = part
                    continue
                value = re.sub(r"\s*\|\s*\d+(?:-\d+)?\s*(?:元|千|万)\s*/\s*(?:月|年).*$", "", value).strip()
                pieces = [part.strip() for part in re.split(r"\t+|\s{2,}|[|｜]", value) if part.strip()]
                if len(pieces) >= 2:
                    department = department or pieces[0]
                    position = position or pieces[-1]
                elif pieces:
                    candidate = pieces[0]
                    if any(token in candidate for token in POSITION_TOKENS_ANY) or "兼职" in candidate:
                        position = position or candidate
                    elif not department and len(candidate) <= 20:
                        department = candidate
            parsed.append({
                "_source_confidence": "explicit_date_block",
                "company_name": company,
                "company_employees": company_employees,
                "company_industry": company_industry,
                "position": position,
                "position_type": "",
                "position_salary": "",
                "position_dept": department,
                "position_report_to": "",
                "position_subordinate": "",
                "employment_type": "全职",
                "annual_salary_min": "",
                "annual_salary_max": "",
                "status": "离职" if end_date else "在职",
                "position_start": start_date,
                "position_resigned": end_date,
                "resigned_reason": "",
                "position_responsibilities": "\n".join(description_lines).strip(),
                "position_achievements": "",
            })
        return parsed

    explicit_works = _parse_explicit_work_blocks(block_main or text)
    def _organization_score(rows: list[dict[str, Any]]) -> int:
        marks = ("公司", "集团", "银行", "工厂", "厂", "株式会社", "事务所", "研究所", "研究院", "医院", "学校", "大学", "学院", "有限", "股份")
        return sum(any(mark in str((row or {}).get("company_name") or "") for mark in marks) for row in rows)
    if explicit_works and _organization_score(explicit_works) >= _organization_score(deduped):
        deduped = explicit_works

    # 针对「公司/描述前置，日期/职位在后」排版的对齐解构逻辑：
    # EN: Alignment/deconstruction logic for layouts with "company/description first, dates/position after":
    # JA: 「会社・説明が先、日付・職位が後」というレイアウトのための対応付け・分解のロジック：
    sec_work_lines = [l.strip() for l in (block_main or text).splitlines() if l.strip()]
    standalone_date_positions: list[tuple[str, str, str]] = []
    for idx_line, line in enumerate(sec_work_lines):
        line_stripped = DATE_RANGE_STRIP_PREFIX_RE.sub("", line).strip()
        m_d = DATE_RANGE_TOKEN_RE.search(line_stripped) or DATE_YEAR_RANGE_RE.search(line_stripped)
        if m_d:
            start_raw, end_raw = m_d.group(1), m_d.group(2)
            s_ym = _format_ym(start_raw)
            e_ym = "" if end_raw in ("至今", "现在", "Present", "Current", "在读") else _format_ym(end_raw)
            tail = line_stripped[m_d.end():].strip()
            pos_cand = tail
            if not pos_cand and idx_line + 1 < len(sec_work_lines):
                nn = sec_work_lines[idx_line + 1].strip()
                if nn and len(nn) <= 20 and not (DATE_RANGE_TOKEN_RE.search(nn) or DATE_YEAR_RANGE_RE.search(nn)):
                    pos_cand = nn
            standalone_date_positions.append((s_ym, e_ym, pos_cand))

    if len(deduped) > 1 and len(deduped) == len(standalone_date_positions):
        for idx, w in enumerate(deduped):
            s_ym, e_ym, p_cand = standalone_date_positions[idx]
            if not w.get("position_start"):
                w["position_start"] = s_ym
                w["position_resigned"] = e_ym
                w["status"] = "离职" if e_ym else "在职"
            if not w.get("position") and p_cand:
                w["position"] = p_cand

    # ================================================================
    # ★Top顽疾修复：全部规则跑完 work仍为空 → 兜底走「叙述式/压缩式」regex
    #    覆盖：余泽龙/吴先亮/吴思峣/奚文青/周军 等parser漏掉的格式
    # ================================================================
    # EN: ================================================================
    #     ★Fix for the top stubborn issue: work is still empty after all rules → fall back to "narrative/compressed" regexes
    #        Covers formats the parser missed in several past cases
    #     ================================================================
    # JA: ================================================================
    #     ★最も手強い問題への修正：すべてのルールを実行しても work が空 → 「叙述式・圧縮式」の正規表現にフォールバックする
    #        過去の複数の事例でパーサーが取りこぼした形式をカバーする
    #     ================================================================
    if not deduped:
        _fallback_src = (block_main or text or "")[:10000]
        _fb_works: list[dict[str, Any]] = []

        # ---- ① NARR叙述式：YYYY年M月[起] [至|-至今] [期间] 在[公司]任/担任[职位]一职 ----
        # EN: ---- ① NARR narrative: YYYY年M月[起] [至|-至今] [期间] 在[company]任/担任[position]一职 (from month M of year YYYY [to | - present] served as [position] at [company]) ----
        # JA: ---- ① NARR 叙述式：YYYY年M月[起] [至|-至今] [期间] 在[会社]任/担任[職位]一职（YYYY 年 M 月から［〜まで／現在まで］［会社］で［職位］を務める）----
        _NARR_RE = re.compile(
            r"(?:^|[\n\r/。；;.!！?？]|\s{0,4}(?:\d+[.、)）]\s*))"
            r"((?:19|20)\d{2})\s*[./年\-]\s*(\d{1,2})?\s*(?:月)?\s*(?:起)?\s*"
            r"(?:-{1,4}|~+|至{1,2}|到{1,2})\s*"
            r"(至今|现在|今|(?:19|20)\d{2})\s*[./年]?\s*(\d{1,2})?\s*(?:月)?\s*"
            r"(?:期间)?\s*(?:在|于|就职于)?\s*"
            r"([\u4e00-\u9fffA-Za-z0-9（）() &.\-·]{2,60}?)"
            r"(?:任|担任|出任|任职|任职于|作为|当|一职|岗位为)"
            r"([\u4e00-\u9fffA-Za-z0-9·\- ]{2,30}?)"
            r"(?:\s|,|，|。|；|;|一|$)",
        )
        for m in _NARR_RE.finditer(_fallback_src):
            sy, sm, ey, em, co, po = m.groups()
            s_ym = _format_ym(sy + ("年" + sm if sm else ""))
            if ey in ("至今", "现在", "今"):
                e_ym = ""; st = "在职"
            else:
                e_ym = _format_ym(ey + ("年" + em if em else "")); st = "离职"
            co = co.strip(); po = po.strip()
            if co and len(co) >= 2 and (len(co) <= 40) and (
                _has_comp_sign_global(co) or 2 <= len(co) <= 25
            ):
                _fb_works.append({
                    "company_name": co,
                    "position": po if po else "",
                    "position_start": s_ym,
                    "position_resigned": e_ym,
                    "status": st,
                    "position_dept": "",
                    "responsibilities": "",
                    "company_industry": "",
                    "company_nature": "",
                    "company_size": "",
                    "report_to": "",
                    "subordinates": "",
                    "salary": "",
                    "work_city": "",
                })

        # ---- ② COMPACT压缩式：YYYYMM / YYYY.M / YYYY-M / MM  [-~至—―] YYYYMM/至今/MM [公司+职位] ----
        # EN: ---- ② COMPACT compressed: YYYYMM / YYYY.M / YYYY-M / MM  [-~至—―] YYYYMM/至今/MM [company + position] ----
        # JA: ---- ② COMPACT 圧縮式：YYYYMM / YYYY.M / YYYY-M / MM  [-~至—―] YYYYMM/至今/MM [会社 + 職位] ----
        _COMPACT_RE = re.compile(
            r"(?:^|[\n\r/]|[^0-9A-Za-z\u4e00-\u9fff（）()])"
            r"((?:19|20)\d{2}\s*\d{2}|(?:19|20)\d{2}\s*[./\-年]\s*\d{1,2}|\d{1,2})\s*(?:月)?"
            r"\s*(?:-{1,4}|—{1,3}|–|~{1,3}|～{1,3}|至{1,2}|到|‒|―|〜)\s*"
            r"(至今|现在|今|(?:19|20)\d{2}\s*\d{2}|(?:19|20)\d{2}\s*[./\-年]\s*\d{0,2}|\d{1,2})\s*(?:月)?"
            r"[\s　:：,，、\|\-—]*"
            r"([^\n\r/]{2,100}?)"
            r"(?=\s*(?:\n|\r|/|$|(?:19|20)\d{2}\s*(?:\d{2}|[./年\-]))|$)",
        )
        def _fb_split_company_position(tail: str) -> tuple[str, str]:
            """压缩式tail拆分：有「有限公司/集团」等后缀则截取到后缀，后视为职位。

            EN: Compressed tail splitting: if there is a suffix like "有限公司/集团", cut at the suffix and treat the rest as the position.

            JA: 圧縮式の tail の分割：「有限公司／集团」などの接尾辞があればそこまでを取り、残りを職位とみなす。
            """
            t = tail.strip().rstrip("，,。；;、|:：-— ")
            # 先找公司标志截断
            # EN: First truncate at a company marker
            # JA: まず会社の目印で切る
            _m = re.search(
                r"(^[\u4e00-\u9fffA-Za-z0-9（）() &.\-·]{2,40}?"
                r"(?:有限责任公司|股份有限公司|有限公司|股份公司|集团公司|集团|制造厂|工厂|分公司|办事处|代表处|事业部|银行|基金|证券|保险|事务所|研究院|研究所|医院|学校|大学|学院|控股|公司|中心|工作室|店|部))",
                t,
            )
            if _m:
                c = _m.group(1)
                p = t[_m.end():].strip() if _m.end() < len(t) else ""
                return c, p
            # 无明确标志：按长度划分(前60%公司后40%职位)，或2-12字公司后职位
            # EN: No explicit marker: split by length (first 60% company, last 40% position), or a 2-12 character company followed by the position
            # JA: 明確な目印がない：長さで分ける（前 60% が会社、後 40% が職位）、または 2〜12 文字の会社の後に職位
            tokens = t.split()
            if len(tokens) == 1:
                return tokens[0][:min(len(tokens[0]), 20)], ""
            if len(tokens) >= 2:
                c = " ".join(tokens[: max(1, (len(tokens) * 2) // 3)]).strip()
                p = " ".join(tokens[max(1, (len(tokens) * 2) // 3):]).strip()
                return c[:30], p[:30]
            return t[:25], ""
        for m in _COMPACT_RE.finditer(_fallback_src):
            s_raw, e_raw, tail = m.groups()
            # 过滤纯薪资范围：2001-4000 这种 s_raw=2001 e_raw=4000 → 非日期
            # EN: Filter pure salary ranges: 2001-4000 gives s_raw=2001 e_raw=4000 → not a date
            # JA: 給与範囲だけのものを除外する：2001-4000 は s_raw=2001 e_raw=4000 → 日付ではない
            if re.fullmatch(r"\d{4}", s_raw or "") and re.fullmatch(r"\d{4}", e_raw or ""):
                if 1000 <= int(s_raw) <= 99999 and 1000 <= int(e_raw) <= 99999:
                    continue  # 是薪资不是日期
                    # EN: It is a salary, not a date
                    # JA: 日付ではなく給与である
            s_ym = _format_ym(s_raw)
            if e_raw in ("至今", "现在", "今"):
                e_ym = ""; st = "在职"
            else:
                # 同年缺省年：如果s_raw是2017.8且e_raw是11 → 年继承
                # EN: Missing year in the same year: if s_raw is 2017.8 and e_raw is 11 → inherit the year
                # JA: 同じ年で年が省略されている：s_raw が 2017.8 で e_raw が 11 → 年を引き継ぐ
                _ye = re.match(r"(?:19|20)\d{2}", s_raw or "")
                if _ye and re.fullmatch(r"\d{1,2}", e_raw or ""):
                    e_raw_full = f"{_ye.group(0)}年{e_raw}"
                    e_ym = _format_ym(e_raw_full)
                else:
                    e_ym = _format_ym(e_raw)
                st = "离职"
            if not s_ym:
                continue
            co, po = _fb_split_company_position(tail)
            co = re.sub(r"[\s:：,，、；;・·•·\-—_()（）]+$", "", co.strip())
            if not co or len(co) < 2:
                continue
            # 公司名像"在XX担任XX"这种动词开头 → 跳过
            # EN: Company name starting with a verb like "在XX担任XX" (served as XX at XX) → skip
            # JA: 「在XX担任XX」（XX で XX を担当）のように動詞で始まる会社名 → スキップ
            if re.match(r"^(?:在|于|担任|任|期间|地点)", co) and not _has_comp_sign_global(co):
                continue
            _fb_works.append({
                "company_name": co,
                "position": po if po else "",
                "position_start": s_ym,
                "position_resigned": e_ym,
                "status": st,
                "position_dept": "",
                "responsibilities": "",
                "company_industry": "",
                "company_nature": "",
                "company_size": "",
                "report_to": "",
                "subordinates": "",
                "salary": "",
                "work_city": "",
            })

        # ---- ③ 合并去重 + 校验公司名有效性 ----
        # EN: ---- ③ Merge + dedup + validate the company name ----
        # JA: ---- ③ 統合 + 重複排除 + 会社名の妥当性の検証 ----
        if _fb_works:
            _fb_deduped: list[dict[str, Any]] = []
            _seen: set[tuple[str, str, str]] = set()
            for w in _fb_works:
                c = w.get("company_name") or ""
                if not _valid_company(c):
                    continue
                key = (w.get("position_start") or "", w.get("position_resigned") or "", c)
                if key in _seen:
                    continue
                _seen.add(key)
                _fb_deduped.append(w)
            if _fb_deduped:
                deduped = _fb_deduped

    return deduped


def repair_explicit_pipe_work_headers(text: str, works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用“日期下一行：公司 | 部门 | 职位”的显式结构校正旧解析结果。

    该格式的信息强度高于职责文本推断，只覆盖同一日期段的三个表头字段，
    其余薪资、职责、业绩等保留旧解析结果。

    EN: Correct old parse results using the explicit structure "line after the date: company | department | position".

    This format carries stronger information than inference from duty text; it overrides only the three header fields of the same date range,
    and keeps the old parse results for salary, duties, achievements, etc.

    JA: 「日付の次の行：会社 | 部署 | 職位」という明示的な構造で旧来の解析結果を補正する。

    この形式の情報は職務テキストからの推定より強いため、同じ期間の 3 つの見出しフィールドだけを上書きし、
    給与・職務・実績などは旧来の解析結果を残す。
    """
    if not text or not works:
        return works
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    date_re = re.compile(
        r"((?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2})\s*(?:--|[-—–~～至到]{1,4})\s*"
        r"((?:19|20)\d{2}\s*(?:年|[./-])\s*\d{1,2}|至今|现在|Present|Current)",
        re.I,
    )
    work_by_dates: dict[tuple[str, str], dict[str, Any]] = {}
    for work in works:
        start = normalize_schema_date(work.get("position_start"))
        end = normalize_schema_date(work.get("position_resigned"))
        work_by_dates.setdefault((start, end), work)

    for index, line in enumerate(lines):
        match = date_re.search(line)
        if not match:
            continue
        start = normalize_schema_date(match.group(1))
        end = "" if re.search(r"至今|现在|Present|Current", match.group(2), re.I) else normalize_schema_date(match.group(2))
        target = work_by_dates.get((start, end))
        if target is None:
            continue
        for candidate in lines[index + 1:index + 4]:
            if date_re.search(candidate):
                break
            parts = [part.strip() for part in re.split(r"[|｜]", candidate) if part.strip()]
            if len(parts) < 2:
                continue
            company = parts[0].strip(" :：,，")
            if not (2 <= len(company) <= 60) or any(token in company for token in ("工作描述", "工作内容", "公司性质", "公司规模")):
                continue
            target["company_name"] = company
            if len(parts) >= 3:
                target["position_dept"] = parts[-2].strip()
                target["position"] = parts[-1].strip()
            else:
                target["position"] = parts[1].strip()
            break
    return works


def _clean_training_list_legacy(trainings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """增强版：擦除前缀杂质/强力模糊去重/去非培训内容。

    EN: Enhanced version: erase prefix noise / aggressive fuzzy dedup / remove non-training content.

    JA: 強化版：接頭辞の不要部分の除去・強力なあいまい重複排除・研修以外の内容の除去。
    """
    invalid_kw = ("技能", "语言", "特长", "IT技能", "成绩")
    non_training_kw = ("实践描述", "工作描述", "工作内容", "项目描述", "岗位职责", "岗位责任", "项目职责", "工作职责",
                       "业绩描述", "主要职责", "责任描述", "项目责任", "职责内容")
    WORK_OR_PROJECT_SMELL_KW = (
        "招投标", "签单", "客户维护", "销售目标", "市场推广", "渠道拓展", "客户拜访",
        "商务谈判", "合同签订", "回款", "KPI", "业绩", "营收", "利润", "成本控制",
        "团队管理", "招聘", "晋升", "薪酬", "绩效", "面试", "培训下属",
        "负责", "管理", "协助", "跟进", "推进", "制定", "主导", "参与", "分析", "设计",
    )
    # 垃圾 training_name 关键词（单个标点/纯分隔符/薪资/短月份）
    # EN: Junk training_name keywords (single punctuation / pure separators / salaries / short months)
    # JA: ゴミの training_name のキーワード（単独の句読点・区切りだけ・給与・短い月）
    GARBAGE_NAME_KW = ("--", "~~", "==", "-", "~", "月", "月~", "元/月", "元", "万/月", "年薪", "月薪", "年")

    def _ym_invalid(ym: str) -> bool:
        """判断 start_ym/end_ym 是否非法（月份 0 或 > 12、日期 0 或 > 31、乱填如「40月」）

        EN: Decide whether start_ym/end_ym is invalid (month 0 or > 12, day 0 or > 31, nonsense like "40月")

        JA: start_ym/end_ym が不正か（月が 0 か 12 超、日が 0 か 31 超、「40月」のようなでたらめ）を判定する
        """
        if not ym:
            return False
        m_ym = re.match(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?", ym)
        if not m_ym:
            return False  # 格式不一致，不判断
            # EN: Inconsistent format, do not judge
            # JA: 形式が一致しないので判定しない
        y, mo = int(m_ym.group(1)), int(m_ym.group(2))
        d = int(m_ym.group(3)) if m_ym.group(3) else 1
        if mo < 1 or mo > 12 or d < 1 or d > 31 or y < 1940 or y > 2100:
            return True
        return False

    seen: set[tuple[str, str, str]] = set()
    clean_t: list[dict[str, Any]] = []
    for idx, t in enumerate(trainings or []):
        # 只接受 dict 类型
        # EN: Accept only dict types
        # JA: dict 型だけを受け付ける
        if not isinstance(t, dict):
            continue
        org = str(t.get("organization_name") or "").strip()
        t_name = str(t.get("training_name") or "").strip()
        start_ym = str(t.get("start_ym") or "").strip()
        end_ym = str(t.get("end_ym") or "").strip()
        desc = str(t.get("description") or "").strip()

        # 擦除冒号/数字/序号前缀（如 2：湖南长沙... -> 湖南长沙...）
        # EN: Erase colon/number/sequence prefixes (e.g. 2：湖南长沙... -> 湖南长沙...)
        # JA: コロン・数字・通し番号の接頭辞を消す（例：2：湖南长沙... -> 湖南长沙...）
        org = re.sub(r"^[\s:：\d.]+", "", org).strip()
        t_name = re.sub(r"^[\s:：\d.]+", "", t_name).strip()
        t_name = re.sub(r"^(?:培训课程|课程|培训机构|机构)\s*[:：]?\s*", "", t_name).strip()

        # —— 过滤1：t_name 或 org 是纯垃圾（--/月~/元/月 等）
        # EN: —— Filter 1: t_name or org is pure junk (--/月~/元/月 etc.)
        # JA: —— フィルター 1：t_name か org が純粋なゴミ（--／月~／元/月 など）
        if t_name and (len(t_name) <= 2 and any(t_name.strip() == g for g in GARBAGE_NAME_KW)):
            continue
        if org and (len(org) <= 2 and any(org.strip() == g for g in GARBAGE_NAME_KW)):
            continue
        if t_name and any(g in t_name for g in GARBAGE_NAME_KW if len(g) >= 2):
            continue
        # —— 过滤2：非法日期（「2001年40月」这种乱填）
        # EN: —— Filter 2: invalid dates (nonsense like "2001年40月")
        # JA: —— フィルター 2：不正な日付（「2001年40月」のようなでたらめな値）
        if _ym_invalid(start_ym) or _ym_invalid(end_ym):
            continue
        # —— 过滤3：包含工作/项目描述动词
        # EN: —— Filter 3: contains work/project description verbs
        # JA: —— フィルター 3：職務・プロジェクトの説明の動詞を含む
        all_text_smell = f"{org}|{t_name}|{desc}"
        if any(k in all_text_smell for k in WORK_OR_PROJECT_SMELL_KW) and \
           not any(k in (org + t_name) for k in ("培训", "认证", "证书", "课程", "研修", "进修")):
            continue

        if any(k in org for k in invalid_kw) or any(k in t_name for k in invalid_kw):
            continue
        if (not t_name) and (not org):
            continue

        if not org and t_name and any(k in t_name for k in ("机构", "学校", "大学", "学院", "中心", "新东方")):
            org = t_name
            t_name = ""
        if not t_name and org and any(k in org for k in ("课程", "口语", "会话", "班", "演讲")):
            t_name = org
            org = ""

        all_text = f"{org}|{t_name}|{desc}"
        if any(k in all_text for k in non_training_kw) and not any(k in (org + t_name) for k in ("培训", "认证", "证书", "机构", "课程", "中心", "大学", "学院", "学校")):
            continue

        norm_org = org[:15]
        norm_t = t_name[:15]
        norm_start = start_ym[:7] if start_ym else ""
        key = (norm_org, norm_t, norm_start)

        if key in seen:
            continue
        seen.add(key)

        nt = dict(t)
        nt["organization_name"] = org
        nt["training_name"] = t_name
        nt.setdefault("sequence_no", len(clean_t) + 1)
        clean_t.append(nt)

    for i, t in enumerate(clean_t, 1):
        t["sequence_no"] = i
    return clean_t


# =============================================================================
# 智联招聘：在校实践经历（→training_list）+ 证书解析（板块终止符+日期范围过滤）
# =============================================================================
# EN: =============================================================================
#     Zhaopin: campus practice experience (→ training_list) + certificate parsing (section terminators + date-range filtering)
#     =============================================================================
# JA: =============================================================================
#     Zhaopin：在学中の実践経験（→ training_list）+ 資格の解析（セクションの終端 + 期間によるフィルター）
#     =============================================================================

def _parse_zhilian_practice_simple(text: str) -> list[dict[str, Any]]:
    """从纯文本解析在校实践经历，合并到 training_list。

    EN: Parse campus practice experience from plain text and merge it into training_list.

    JA: プレーンテキストから在学中の実践経験を解析し、training_list に統合する。
    """
    block = _section_block(
        text,
        ["在校实践经历", "社会实践", "实习经历", "Internship", "Practice"],
        ["语言能力", "技能", "自我评价", "专业技能", "证书", "所获", "教育经历", "项目经历", "工作经历",
         "在校学习情况", "活动描述", "兴趣爱好", "培训经历",
         "Language", "Self-Assessment", "Skills", "Certificates", "Awards",
         "Education", "Project", "Work Experience", "Training"],
    )
    if not block:
        return []
    practices: list[dict[str, Any]] = []
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    date_range_re = re.compile(
        r"((?:19|20)\d{2}[./\-]\d{1,2})\s*[\-\u2010-\u2015~～至到]{1,4}\s*"
        r"((?:19|20)\d{2}[./\-]\d{1,2}|至今|现在|目前)"
    )
    i = 0
    while i < len(lines):
        line = lines[i]
        m_date = date_range_re.search(line)
        if m_date:
            start_ym = _format_ym(m_date.group(1))
            end_raw = m_date.group(2)
            end_ym = "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw)
            org_name = line[m_date.end():].strip()
            org_name = re.sub(r"[（(]\s*\d+年\s*\d+个月\s*[）)]", "", org_name)
            org_name = re.sub(r"[（(]\s*\d+个月\s*[）)]", "", org_name)
            org_name = re.sub(r"[（(]\s*\d+年\s*[）)]", "", org_name)
            org_name = org_name.strip(" 　\t\n-—–*·")
            description = ""
            j = i + 1
            while j < len(lines):
                c = lines[j]
                if date_range_re.search(c):
                    break
                if c.startswith("实践描述"):
                    val = re.sub(r"^实践描述[：:]?\s*", "", c)
                    if val:
                        description = val
                    k = j + 1
                    while k < len(lines) and not date_range_re.search(lines[k]):
                        nxt = lines[k]
                        if nxt.startswith("实践"):
                            break
                        description += "\n" + nxt
                        k += 1
                    j = k
                    continue
                j += 1
            description = _TRAILING_SECTION_RE.sub("", description.strip())
            practices.append({
                "sequence_no": 0,
                "organization_name": org_name,
                "training_name": "在校实践经历",
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": "",
                "description": description,
            })
            i = j
        else:
            i += 1
    return practices


def _parse_zhilian_certificates_simple(text: str) -> list[dict[str, Any]]:
    """纯文本解析证书：板块终止符含在校实践经历等，跳过日期范围行。

    EN: Plain-text certificate parsing: section terminators include campus practice experience etc.; date-range lines are skipped.

    JA: プレーンテキストの資格解析：セクションの終端には在学中の実践経験などを含み、期間の行はスキップする。
    """
    certificates: list[dict[str, Any]] = []
    # Word 常用分散字标题“证    书”，先归一化后再按章节解析。
    # EN: Word often uses spaced-out headings like "证    书" (certificates); normalise them first, then parse by section.
    # JA: Word では「证    书」（資格）のように文字を離した見出しがよく使われるため、先に正規化してから章ごとに解析する。
    text = re.sub(r"证[\s　]{1,8}书", "证书", text or "")
    block = _section_block(
        text,
        ["证书", "所获证书", "所获", "Certificates", "Awards"],
        ["语言能力", "专业技能", "自我评价", "培训经历", "项目经历", "教育经历", "工作经历",
         "特长", "职业目标", "在校学习情况", "在校实践经历", "活动描述", "兴趣爱好",
         "Language", "Skills", "Self-Assessment", "Training", "Project", "Education", "Work Experience"],
    )
    if not block:
        return certificates
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    merged_lines: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if re.match(r"^((?:19|20)\d{2})[./\-年](\d{1,2})月?$", line) and idx + 1 < len(lines):
            merged_lines.append(f"{line} {lines[idx + 1]}")
            idx += 2
        else:
            merged_lines.append(line)
            idx += 1
    for line in merged_lines:
        if re.search(r"^\d{4}[./\-年]\d{1,2}\s*[\-\u2010-\u2015~～至到]", line):
            continue
        m = re.match(r"((?:19|20)\d{2})[./\-年](\d{1,2})月?\s+(.+)", line)
        if m:
            cert_time = f"{m.group(1)}年{int(m.group(2)):02d}月01日"
            cert_name = m.group(3).strip()
            if (cert_name
                    and cert_name not in ("证书说明", "证书名", "分数")
                    and len(cert_name) < 80
                    and not re.match(r"^\d{4}[./\-年]\d{1,2}", cert_name)):
                certificates.append({
                    "certificate_name": cert_name,
                    "certificate_type": "证书",
                    "certificate_time": cert_time,
                })
    if not certificates:
        for m in re.finditer(r"([^\n]+?)\n(\d{4}年\d{1,2}月(?:获得|取得))", text):
            cert_name = m.group(1).strip()
            time_str = m.group(2).replace("获得", "").replace("取得", "").strip()
            if cert_name and len(cert_name) < 60:
                certificates.append({
                    "certificate_name": cert_name,
                    "certificate_type": "证书",
                    "certificate_time": _format_ym(time_str),
                })
    return certificates


_NON_BUSINESS_ORG_TOKENS = (
    "学生会", "学生社联", "学生组织", "学联", "社团", "协会", "俱乐部", "同乡会",
    "联谊会", "联谊", "校友会", "团总支", "团支部", "青年志愿者", "志愿者协会",
)
_NON_BUSINESS_ROLE_TOKENS = (
    "校内职务", "在校任职", "社团任职", "班委", "班长", "团支书", "课代表", "课程代表",
    "社长", "副社长", "会长", "副会长", "学生干部", "干事",
)


def _strip_non_business_resume_details(value: Any) -> str:
    """从描述字段删除不属于目标 Schema 的校园组织/导师类明细。

    EN: Remove campus-organisation / supervisor details that do not belong to the target schema from description fields.

    JA: 説明フィールドから、対象スキーマに属さない学内組織・指導教員などの明細を削除する。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    kept: list[str] = []
    for part in re.split(r"(?<=。)|[\r\n]+", text):
        line = part.strip()
        if not line:
            continue
        if re.search(r"(?:导师|指导老师|指导教师|班主任)\s*[:：]", line):
            continue
        if any(tok in line for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _clean_certificate_list(certs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清理 certificate_list：移除板块标题、实践描述、工作描述等非证书条目。

    EN: Clean certificate_list: remove non-certificate entries such as section headings, practice descriptions and job descriptions.

    JA: certificate_list の整理：セクション見出し・実践の説明・職務説明など資格でない項目を除く。
    """
    _NON_CERT_NAMES = {"在校实践经历", "在校学习情况", "活动描述", "兴趣爱好", "社会实践",
                       "社会活动", "特长职业目标", "职业目标", "自我评价", "所获证书",
                       "实践描述：", "实践描述", "证书说明：", "证书说明", "证书名",
                       "工作描述：", "工作描述", "分数", "证书", "培训经历", "项目经历", "社会认证",
                       "至今", "现在", "培训机构", "培训机构：", "培训地点", "培训地点：", "培训描述", "培训描述："}
    _NON_CERT_KEYWORDS = ("实践描述", "工作描述", "项目描述", "责任描述", "培训描述",
                          "奖项描述", "活动描述", "协会", "成员", "理事", "会员", "同乡会", "俱乐部", "联谊",
                          "学生会", "社团", "校内职务", "在校任职", "导师", "指导老师")
    _NON_CERT_ACHIEVEMENTS = (
        "奖学金", "演讲比赛", "朗读比赛", "竞赛", "优秀毕业生", "亲善大使",
        "项目助理", "调研队", "队长", "党员", "入选", "称号", "二等奖", "三等奖",
    )
    # —— 黑名单关键词：含「裁判/协会/俱乐部」但前面/后面紧跟「证书/资格/等级/一级/二级/三级」→ 是真证书，放通
    # EN: —— Blacklist keywords: contains "裁判/协会/俱乐部" (referee/association/club) but directly preceded/followed by "证书/资格/等级/一级/二级/三级" (certificate/qualification/level/first/second/third class) → a real certificate, let it through
    # JA: —— ブラックリストのキーワード：「裁判／协会／俱乐部」（審判・協会・クラブ）を含むが、前後に「证书／资格／等级／一级／二级／三级」（資格・等級・1〜3 級）が直接続く → 本当の資格なので通す
    _CERT_POSITIVE_KW = ("证书", "资格", "等级", "一级", "二级", "三级", "A级", "B级", "国家级", "省级", "市级", "初级", "中级", "高级")
    cleaned: list[dict[str, Any]] = []
    for c in certs:
        cname = (c.get("certificate_name") or "").strip()
        if not cname:
            continue
        if cname in _NON_CERT_NAMES:
            continue
        # 荣誉、校园职务和政治身份不属于证书字段；即使文本中出现“称号/等级”也舍弃。
        # EN: Honours, campus posts and political status do not belong in the certificate field; discard them even if "称号/等级" (title/level) appears in the text.
        # JA: 栄誉・学内の役職・政治的身分は資格のフィールドに属さない。テキストに「称号／等级」（称号・等級）があっても捨てる。
        if any(kw in cname for kw in _NON_CERT_ACHIEVEMENTS):
            continue
        # 含黑名单但同时含「证书关键词」→ 放通（如「羽毛球项目国家二级裁判员」含「裁判」但也含「二级」→ 是真证书）
        # EN: Contains a blacklisted word but also a "certificate keyword" → let it through (e.g. "羽毛球项目国家二级裁判员" (national second-class badminton referee) contains "裁判" but also "二级" → a real certificate)
        # JA: ブラックリストの語を含むが「資格のキーワード」も含む → 通す（例：「羽毛球项目国家二级裁判员」（バドミントン国家二級審判員）は「裁判」を含むが「二级」もある → 本当の資格）
        has_black_kw = any(kw in cname for kw in _NON_CERT_KEYWORDS)
        has_positive = any(kw in cname for kw in _CERT_POSITIVE_KW)
        if has_black_kw and not has_positive:
            continue
        # 额外：「裁判」单独出现且短（<=6字）且无等级词 → 过滤，但「XX裁判员」带项目名的长度一般>6 → 放通
        # EN: Extra: "裁判" (referee) alone, short (<=6 characters) and without a level word → filter; but "XX裁判员" with a sport name is usually >6 → let through
        # JA: 追加：「裁判」が単独で短く（6 文字以内）レベルの語がない → 除外。ただし種目名の付いた「XX裁判员」は通常 6 文字超 → 通す
        if 2 <= len(cname) <= 6 and "裁判" in cname and not has_positive and "项目" not in cname and "国家" not in cname and "级" not in cname:
            continue
        if cname.startswith("- "):
            cname = cname[2:].strip()
            c["certificate_name"] = cname
        if len(cname) < 2 or len(cname) > 80:
            continue
        if re.match(r"^\d{4}[./\-]\d{1,2}$", cname):
            continue
        cleaned.append(c)
    return cleaned


# =============================================================================
# 个人素质关键词过滤（skills_list → base_info.pr）
# =============================================================================
# EN: =============================================================================
#     Personal-quality keyword filtering (skills_list → base_info.pr)
#     =============================================================================
# JA: =============================================================================
#     個人の資質を表すキーワードのフィルタリング（skills_list → base_info.pr）
#     =============================================================================

def _is_personal_quality(skill_name: str) -> bool:
    """判断 skill 是否是个人素质（软素质）关键词而非硬技能。

    EN: Decide whether a skill is a personal-quality (soft skill) keyword rather than a hard skill.

    JA: スキルがハードスキルではなく個人の資質（ソフトスキル）のキーワードかどうかを判定する。
    """
    s = (skill_name or "").strip()
    if not s:
        return False
    s_cmp_zh = s.replace("能力", "").replace("性", "").replace("感", "").strip()
    for kw in PERSONAL_QUALITY_KEYWORDS_ZH:
        kw_cmp = kw.replace("能力", "").replace("性", "").replace("感", "").strip()
        if s_cmp_zh and (kw_cmp == s_cmp_zh or (kw_cmp and kw_cmp in s_cmp_zh)):
            return True
    s_lower = s.lower()
    for kw in PERSONAL_QUALITY_KEYWORDS_EN:
        kw_lower = kw.lower()
        if s_lower == kw_lower or kw_lower in s_lower:
            return True
    return False


def _filter_skills_extract_pr(
    skills_list: list[dict[str, Any]],
    base_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """将 skills_list 中的个人素质条目移到 base_info.pr，返回过滤后的 skills。

    EN: Move personal-quality entries from skills_list into base_info.pr and return the filtered skills.

    JA: skills_list の個人の資質の項目を base_info.pr に移し、フィルター後の skills を返す。
    """
    if not skills_list:
        return []
    pr_items: list[str] = []
    filtered_skills: list[dict[str, Any]] = []
    for s in skills_list:
        name = (s.get("skill_name") or s.get("name") or "").strip()
        if _is_personal_quality(name):
            if name and name not in pr_items:
                pr_items.append(name)
        else:
            # 附加过滤：排除动作短语（负责…、每天…、上交给…等）
            # EN: Additional filter: exclude action phrases (负责… / 每天… / 上交给…: responsible for… / every day… / handed over to…)
            # JA: 追加の除外：動作の語句（负责…／每天…／上交给…：〜を担当／毎日〜／〜に提出）を除く
            if re.search(r"^(负责|每天|上交|汇报|完成|协助|配合|跟进|处理|管理|组织|制定|提供|支持|推进)", name):
                continue
            # 附加过滤：排除纯句子（含逗号句号≥1且字符≥15）
            # EN: Additional filter: exclude pure sentences (≥1 comma/full stop and ≥15 characters)
            # JA: 追加の除外：文そのもの（読点・句点が 1 つ以上で 15 文字以上）を除く
            if len(name) >= 15 and re.search(r"[，。,.;；]", name):
                continue
            filtered_skills.append(s)
    if pr_items:
        existing_pr = str(base_info.get("pr") or "").strip()
        if existing_pr:
            merged = existing_pr + "、" + "、".join(pr_items)
        else:
            merged = "、".join(pr_items)
        # 去重
        # EN: Dedup
        # JA: 重複排除
        seen: set[str] = set()
        dedup = []
        for part in re.split(r"[、,，;；\s]+", merged):
            p = part.strip()
            if p and p not in seen:
                seen.add(p)
                dedup.append(p)
        base_info["pr"] = "、".join(dedup)
    return filtered_skills


def _clean_training_list(trainings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清理 training_list：强过滤无效条目 + 强力模糊去重 + 擦除前缀杂质。

    EN: Clean training_list: strong filtering of invalid entries + aggressive fuzzy dedup + erasing prefix noise.

    JA: training_list の整理：無効な項目の強力な除外 + 強力なあいまい重複排除 + 接頭辞の不要部分の除去。
    """
    # ---- 无效内容黑名单（命中则整条丢弃）----
    # EN: ---- Invalid content blacklist (discard the whole entry on a hit) ----
    # JA: ---- 無効な内容のブラックリスト（ヒットしたら項目全体を破棄）----
    INVALID_TITLE_KW = ("技能", "语言", "特长", "IT技能", "成绩", "工作经历", "工作经验",
                        "教育经历", "项目经历", "项目经验", "自我评价", "求职意向", "基本信息",
                        "联系方式", "个人简历", "个人信息", "基本资料")
    NON_TRAINING_DESC_KW = ("实践描述", "工作描述", "工作内容", "项目描述", "岗位职责",
                            "岗位责任", "项目职责", "工作职责", "业绩描述", "主要职责",
                            "责任描述", "项目责任", "职责内容", "工作业绩", "汇报对象",
                            "下属人数", "离职原因")
    # 纯项目/销售工作强特征词：无培训关键词+无日期时，命中则整段丢弃
    # EN: Strong feature words of pure project/sales work: with no training keyword and no date, discard the whole section on a hit
    # JA: 純粋なプロジェクト・営業業務の強い特徴語：研修のキーワードも日付もなく、これにヒットしたら段落全体を破棄する
    WORK_OR_PROJECT_SMELL_KW = (
        "招投标", "签单", "回款", "报价", "跟单", "售后", "客户需求", "技术资料",
        "公关", "价格协调", "方案设计", "市场开拓", "客户维护", "跟进项目",
        "了解客户需求", "招投标项目", "实验室改造", "设备更新", "客户",
        "区域的市场", "开拓工作", "签单回款", "实验室设备",
    )
    # 动词/句子开头：纯工作描述格式，不含培训关键词则丢弃
    # EN: Starting with a verb/sentence: pure job-description format; discard if it contains no training keyword
    # JA: 動詞や文で始まる：純粋な職務説明の形式で、研修のキーワードがなければ破棄する
    VERB_START_RE = re.compile(
        r"^(?:负责|协助|组织|开发|维护|参与|制定|管理|进行|配合|完成|建立|收集|提供|推广|推进|改善|提高|拓展|沟通|协调|设计|制作|发放|招募|选址|宣传|策划|跟进|运营|建设|预算|支持|调研|分析|主导|编制|优化|梳理|对接|落实|执行|实施|跟进|搭建|统筹)"
    )
    # 有效培训关键词（training_name 或 organization_name 命中任一 或 有明确日期 才允许进入）
    # EN: Valid training keywords (allowed in only if training_name or organization_name hits one, or there is an explicit date)
    # JA: 有効な研修のキーワード（training_name か organization_name がどれかにヒットするか、明確な日付がある場合だけ通す）
    TRAINING_VALID_KW = (
        "培训", "认证", "证书", "资格", "课程", "内训", "研修", "进修", "学习", "训练",
        "机构", "学校", "大学", "学院", "中心", "新东方", "网校", "研修班",
        "iso", "内审", "apqp", "ppap", "spc", "msa", "fmea", "qms", "ts16949",
        "cet", "tem", "ielts", "toefl", "toeic", "计算机", "等级考", "资格考",
        "cpa", "cfa", "pmp", "frm", "acca", "司法", "教资", "注会",
    )
    # 公司后缀黑名单：training_name / organization_name 如果只包含纯公司名（无培训关键词+含公司后缀）则丢弃
    # EN: Company suffix blacklist: if training_name / organization_name contains only a pure company name (no training keyword + a company suffix), discard
    # JA: 会社の接尾辞のブラックリスト：training_name / organization_name が会社名だけ（研修のキーワードなし + 会社の接尾辞あり）なら破棄する
    COMPANY_SUFFIX_KW = ("有限公司", "有限责任公司", "股份", "集团", "分公司", "办事处",
                         "事务所", "工作室", "工厂", "制造厂", "银行", "基金", "证券", "保险",
                         "医院", "企业", "控股", "Inc", "Ltd", "Co", "LLC", "株式会社")

    def _ym_invalid(ym: str) -> bool:
        """月份>12/日期>31/年份离谱等 → 无效日期（肯定是错把 work/垃圾数据解析成培训了）

        EN: Month > 12 / day > 31 / absurd year etc. → invalid date (definitely work/junk data misparsed as training)

        JA: 月が 12 超・日が 31 超・年がおかしいなど → 不正な日付（work やゴミのデータを研修として誤って解析したもの）
        """
        if not ym:
            return False
        m_ym = re.match(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?", ym)
        if not m_ym:
            return False
        try:
            y, mo = int(m_ym.group(1)), int(m_ym.group(2))
            d = int(m_ym.group(3)) if m_ym.group(3) else 1
            if mo < 1 or mo > 12 or d < 1 or d > 31 or y < 1940 or y > 2100:
                return True
        except Exception:
            return True
        return False

    seen_keys: set[tuple[str, str, str]] = set()
    cleaned: list[dict[str, Any]] = []

    for t in (trainings or []):
        org = str(t.get("organization_name") or "").strip()
        tname = str(t.get("training_name") or "").strip()
        start_ym = str(t.get("start_ym") or "").strip()
        end_ym = str(t.get("end_ym") or "").strip()
        desc = str(t.get("description") or "").strip()

        # 校内社团、协会、联谊组织和任职不是培训数据，直接舍弃。
        # EN: Campus clubs, associations, social organisations and posts in them are not training data; discard them directly.
        # JA: 学内のサークル・協会・親睦団体とその役職は研修のデータではないので、そのまま捨てる。
        if t.get("_source_confidence") != "explicit_training_date_block" and any(tok in (org + "|" + tname) for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
            continue
        desc = _strip_non_business_resume_details(desc)
        t["description"] = desc

        # ---- 擦除冒号/数字/序号前缀 ----
        # EN: ---- Erase colon/number/sequence prefixes ----
        # JA: ---- コロン・数字・通し番号の接頭辞を消す ----
        org = re.sub(r"^[\s:：\d.]+", "", org).strip()
        tname = re.sub(r"^[\s:：\d.]+", "", tname).strip()
        tname = re.sub(r"^(?:培训课程|课程|培训机构|机构)\s*[:：]?\s*", "", tname).strip()
        org = re.sub(r"^(?:培训机构|机构)\s*[:：]?\s*", "", org).strip()

        # 来自独立 training DOM 章节、且具有明确日期范围的条目是高置信培训数据。
        # 不再让描述中的“负责/管理/技能”等普通词触发工作经历误杀。
        # EN: Entries coming from a separate training DOM section with an explicit date range are high-confidence training data.
        #     Ordinary words in the description like "负责/管理/技能" (responsible/manage/skills) no longer trigger wrongly rejecting them as work history.
        # JA: 独立した training の DOM の章から来て明確な期間を持つ項目は、信頼度の高い研修データである。
        #     説明中の「负责／管理／技能」（担当・管理・スキル）などの普通の語で、職歴として誤って弾かれることはもうない。
        if t.get("_source_confidence") == "explicit_training_date_block" and tname and (start_ym or end_ym):
            nt = dict(t)
            nt["organization_name"] = org
            nt["training_name"] = tname
            nt.pop("_source_confidence", None)
            key = (
                re.sub(r"\W+", "", org)[:12],
                re.sub(r"\W+", "", tname)[:12],
                start_ym[:7],
            )
            if key not in seen_keys:
                seen_keys.add(key)
                cleaned.append(nt)
            continue

        # ---- ★新增C：先清理括号不完整内容（陈丹妮 case）----
        #    规则：
        #    1) 如果串以 左括号开头但不闭合 → 剥掉左括号到串尾；或
        #    2) 如果串以 左括号结尾（如「...语言学校 （法语强化课程」这种后半段括号没内容/没闭合）→ 剥掉尾部括号及内部
        #    3) 如果串只有闭合的右括号（开头缺失左括号）→ 剥掉右括号到串头
        # EN: ---- ★New C: first clean incomplete bracket content (a past case) ----
        #        Rules:
        #        1) if the string starts with an opening bracket that is not closed → strip from the opening bracket to the end; or
        #        2) if the string ends with an opening bracket (like "...语言学校 （法语强化课程", where the bracketed second half has no content / is not closed) → strip the trailing bracket and its content
        #        3) if the string has only a closing bracket (the opening bracket at the start is missing) → strip from the closing bracket to the start
        # JA: ---- ★追加 C：まず不完全な括弧の内容を整理する（過去の事例）----
        #        ルール：
        #        1) 文字列が開き括弧で始まって閉じていない → 開き括弧から末尾までを除く。または
        #        2) 文字列が開き括弧で終わる（「...语言学校 （法语强化课程」のように後半の括弧に中身がない・閉じていない）→ 末尾の括弧とその中身を除く
        #        3) 文字列に閉じ括弧だけがある（先頭の開き括弧が欠けている）→ 閉じ括弧から先頭までを除く
        def _strip_unbalanced_paren(s: str) -> str:
            s = s.strip()
            if not s:
                return ""
            # 只含括号字符的尾部：末尾是左括号（后面无内容）→ 剥掉
            # EN: A tail containing only bracket characters: ends with an opening bracket (nothing after it) → strip
            # JA: 括弧の文字だけの末尾：開き括弧で終わる（後ろに何もない）→ 除く
            s = re.sub(r"[\s（(（]+$", "", s).rstrip()
            # 末尾是「（...」 形式（只有左括号开头没有右括号闭合）
            # EN: Ends in the form "（..." (only an opening bracket, never closed)
            # JA: 「（...」の形で終わる（開き括弧だけで閉じていない）
            if s.count("（") != s.count("）"):
                # 左括号多：剥掉最后一个左括号及之后全部
                # EN: More opening brackets: strip the last opening bracket and everything after it
                # JA: 開き括弧が多い：最後の開き括弧とその後をすべて除く
                lp_last = s.rfind("（")
                lp2_last = s.rfind("(")
                cut_idx = -1
                if lp_last >= 0 and lp_last > lp2_last:
                    if s.count("）") < s.count("（"):
                        cut_idx = lp_last
                elif lp2_last >= 0:
                    if s.count(")") < s.count("("):
                        cut_idx = lp2_last
                if cut_idx > 0:  # >0（不截开头仅有的）
                # EN: >0 (do not cut when it is the only one at the start)
                # JA: >0（先頭にしかない場合は切らない）
                    s = s[:cut_idx].rstrip()
            # 反过来：右括号多（开头缺少左括号）→ 剥掉第一个右括号及之前
            # EN: Conversely: more closing brackets (the opening bracket at the start is missing) → strip the first closing bracket and everything before it
            # JA: 逆に：閉じ括弧が多い（先頭の開き括弧が欠けている）→ 最初の閉じ括弧とその前をすべて除く
            if s and s.count("）") > s.count("（"):
                rp_first = s.find("）")
                if rp_first >= 0 and rp_first < len(s) - 1:
                    s = s[rp_first + 1:].lstrip()
            if s and s.count(")") > s.count("("):
                rp_first = s.find(")")
                if rp_first >= 0 and rp_first < len(s) - 1:
                    s = s[rp_first + 1:].lstrip()
            return s.strip()
        org = _strip_unbalanced_paren(org)
        tname = _strip_unbalanced_paren(tname)
        desc = _strip_unbalanced_paren(desc)
        # ---- ★新增D：纯学位/学历词（陈丹妮 case training[1]）→ 整条删 ----
        #    去掉括号/空白后，若所有字符都来自于「本科/大专/硕士/自考/全日制/专升本/学历/学位/统招」词表 → 必然是教育经历误判，非培训
        # EN: ---- ★New D: pure degree/education words (a past case, training[1]) → delete the whole entry ----
        #        After removing brackets/whitespace, if all characters come from the vocabulary "本科/大专/硕士/自考/全日制/专升本/学历/学位/统招" (bachelor/junior college/master/self-study/full-time/college-to-bachelor/degree/unified enrolment) → it must be misjudged education history, not training
        # JA: ---- ★追加 D：純粋な学位・学歴の語（過去の事例 training[1]）→ 項目全体を削除 ----
        #        括弧・空白を除いた後、すべての文字が「本科／大专／硕士／自考／全日制／专升本／学历／学位／统招」の語彙から来ている → 学歴の誤判定であり研修ではない
        PURE_EDU_DEG_TOK = ("本科", "大专", "专科", "硕士", "博士", "研究生", "高中", "中专", "职高", "初中",
                            "全日制", "自考", "专升本", "学历", "学位", "统招", "应届", "往届", "成人", "函授",
                            "业余", "脱产", "夜大", "电大", "在职", "网络", "硕士学位", "学士学位", "博士学位",
                            "专科学位", "本科学位")
        def _all_pure_edu_tokens(text: str) -> bool:
            remaining = re.sub(r"[\s（(（)）），,。.；;：:、·/\-]+", "", (text or ""))
            if not remaining:
                return True
            for tok in PURE_EDU_DEG_TOK:
                remaining = remaining.replace(tok, "")
            return not remaining
        if _all_pure_edu_tokens(org + tname + desc):
            continue

        # ---- 空条目 ----
        # EN: ---- Empty entries ----
        # JA: ---- 空の項目 ----
        if not tname and not org:
            continue
        # 日期碎片（如 13/12）
        # EN: Date fragments (e.g. 13/12)
        # JA: 日付の断片（例：13/12）
        if re.fullmatch(r"\d{1,4}[/\-.]\d{1,2}", tname):
            continue
        # 过短且无任何上下文
        # EN: Too short and without any context
        # JA: 短すぎて文脈がまったくない
        if len(tname) <= 2 and not org and not desc and not start_ym:
            continue
        # ---- 新增：纯符号碎片 / 薪资碎片 / 纯语言名 / UI垃圾 丢弃 ----
        # 1) 纯符号/日期碎片（--、~、-、～、——、月~、~月、xxx 元/月等）
        # EN: ---- New: discard pure symbol fragments / salary fragments / pure language names / UI junk ----
        #     1) Pure symbol/date fragments (--, ~, -, ～, ——, 月~, ~月, xxx 元/月, etc.)
        # JA: ---- 追加：記号だけの断片・給与の断片・言語名だけ・UI のゴミを破棄する ----
        #     1) 記号・日付だけの断片（--、~、-、～、——、月~、~月、xxx 元/月 など）
        if re.fullmatch(r"[\-—–~～―〜\s月/年\.日，,：:元万薪资]*", tname or ""):
            continue
        if tname and any(s in tname for s in ("元/月", "万/月", "千/月", "元/年", "万/年", "月薪", "年薪", "薪资", "薪酬")):
            continue
        # 2) UI垃圾（求职信/保存到我的电脑等）
        # EN: 2) UI junk (求职信/保存到我的电脑: cover letter / save to my computer, etc.)
        # JA: 2) UI のゴミ（求职信／保存到我的电脑：応募書類・PC に保存など）
        if tname and any(s in tname for s in ("求职信", "保存到我的电脑", "简历模板", "简历下载", "保存简历", "打印简历")):
            continue
        # 3) 纯语言名（且无机构/无培训关键词/无日期）→ 应该在language_list，不是培训
        # EN: 3) Pure language names (and no provider / no training keyword / no date) → belong in language_list, not training
        # JA: 3) 言語名だけ（かつ機関・研修のキーワード・日付がない）→ language_list に入れるべきもので研修ではない
        PURE_LANG_NAMES = ("普通话", "国语", "粤语", "日语", "英语", "韩语", "法语", "德语", "西班牙语", "俄语",
                           "意大利语", "葡萄牙语", "阿拉伯语", "泰语", "越南语", "中文", "汉语", "日文", "英文", "韩文")
        if (tname.strip() in PURE_LANG_NAMES) and not org and not start_ym and not any(k in (org + tname).lower() for k in TRAINING_VALID_KW):
            continue
        # 4) 仅 "一级/二级/三级/四级/六级/八级" 这种纯等级名（无考试名/无培训关键词）→ 应该在证书，不是培训
        # EN: 4) Only pure level names like "一级/二级/三级/四级/六级/八级" (levels 1/2/3/4/6/8) (no exam name / no training keyword) → belong in certificates, not training
        # JA: 4) 「一级／二级／三级／四级／六级／八级」（1・2・3・4・6・8 級）のようなレベル名だけ（試験名・研修のキーワードなし）→ 資格に入れるべきもので研修ではない
        if re.fullmatch(r"[一二三四五六七八九十]{1,2}\s*级", tname.strip()) and not org and not start_ym:
            continue
        # 5) 无效日期（月份 40、日期 99 这种） → 必然是错把 work/project section 当 training 解析了，直接丢
        # EN: 5) Invalid dates (month 40, day 99, etc.) → certainly a work/project section misparsed as training; drop directly
        # JA: 5) 不正な日付（月が 40、日が 99 など）→ work／project のセクションを研修として誤って解析したものなので、そのまま捨てる
        if _ym_invalid(start_ym) or _ym_invalid(end_ym):
            continue
        # 6) ★宁严勿松：括号不平衡（不完整括号，如「（法语强化课程」）+ 2字段都没明确培训关键词 → 整条删
        # EN: 6) ★Better too strict than too loose: unbalanced brackets (incomplete, like "（法语强化课程") + neither field has an explicit training keyword → delete the whole entry
        # JA: 6) ★緩すぎるより厳しすぎる方がよい：括弧の不均衡（「（法语强化课程」のような不完全な括弧）+ 2 つのフィールドのどちらにも明確な研修のキーワードがない → 項目全体を削除
        def _paren_unbalanced(s: str) -> bool:
            if not s: return False
            return (s.count("（") != s.count("）")) or (s.count("(") != s.count(")"))
        if _paren_unbalanced(org) or _paren_unbalanced(tname):
            if not any(k in (org + tname).lower() for k in TRAINING_VALID_KW):
                continue
        # 7) 纯学位/学历词（本科/大专/硕士/自考/专升本/全日制等） → 这是教育经历内容，不是培训 → 整条删
        # EN: 7) Pure degree/education words (本科/大专/硕士/自考/专升本/全日制 etc.) → this is education history content, not training → delete the whole entry
        # JA: 7) 純粋な学位・学歴の語（本科／大专／硕士／自考／专升本／全日制 など）→ 学歴の内容であり研修ではない → 項目全体を削除
        PURE_DEGREE_ONLY = ("本科", "大专", "专科", "硕士", "博士", "研究生", "高中", "中专", "职高", "初中",
                            "全日制", "自考", "专升本", "全日制本科", "全日制专科", "全日制大专", "全日制研究生",
                            "全日制硕士", "全日制博士", "全日制专升本", "（本科）", "（专科）", "（大专）", "（硕士）",
                            "（博士）", "（专升本）")
        t_stripped = re.sub(r"[\s（(（)））]+", "", (tname or "") + (org or ""))
        if t_stripped in {re.sub(r"[\s（(（)））]+", "", x) for x in PURE_DEGREE_ONLY}:
            continue
        # 8) 字符串首字符是括号「（(（」且根本没有合法培训内容 → 如「（法语强化课程）」「（本科）全日制自考」这种纯括号开头的碎片
        # EN: 8) The first character is a bracket "（(（" and there is no valid training content at all → fragments starting with brackets like "（法语强化课程）" "（本科）全日制自考"
        # JA: 8) 先頭の文字が括弧「（(（」で、正当な研修の内容がまったくない →「（法语强化课程）」「（本科）全日制自考」のような括弧で始まる断片
        if (tname + org).strip() and re.match(r"^[\s（(（]+$", (tname + org).strip()[:3]) and not any(k in (org + tname).lower() for k in TRAINING_VALID_KW):
            continue
        # 板块标题类碎片
        # EN: Section-heading-like fragments
        # JA: セクション見出しのような断片
        if not (start_ym or end_ym) and any(k in (org + "|" + tname) for k in INVALID_TITLE_KW) and not any(k.lower() in (org + tname).lower() for k in TRAINING_VALID_KW):
            continue
        # 纯工作/项目/职责描述类内容：除非含培训关键词
        # EN: Pure work/project/duty descriptions: unless they contain training keywords
        # JA: 純粋な職務・プロジェクト・職責の説明：研修のキーワードを含まない限り
        all_text = f"{org}|{tname}|{desc}"
        if not (start_ym or end_ym) and any(k in all_text for k in NON_TRAINING_DESC_KW) and not any(k.lower() in (org + tname).lower() for k in TRAINING_VALID_KW):
            continue

        # ---- 培训名 vs 机构名 纠偏 ----
        # EN: ---- Correct training name vs provider name ----
        # JA: ---- 研修名と機関名の補正 ----
        if not org and tname and any(k in tname for k in ("机构", "学校", "大学", "学院", "中心", "新东方")) and "课程" not in tname and "培训" not in tname:
            org_cand = tname
            tname_cand = ""
            org, tname = org_cand, tname_cand
        if not tname and org and any(k in org for k in ("课程", "口语", "会话", "班", "演讲", "研修")):
            tname_cand, org_cand = org, ""
            tname, org = tname_cand, org_cand

        main_text = (org + tname).lower()

        # ---- 动词短语开头：纯工作描述、非培训 ----
        # EN: ---- Starting with a verb phrase: pure job description, not training ----
        # JA: ---- 動詞句で始まる：純粋な職務説明であり研修ではない ----
        if not start_ym and not any(k in main_text for k in TRAINING_VALID_KW):
            if VERB_START_RE.match(tname) or VERB_START_RE.match(org):
                continue

        # ---- 纯公司名（不含培训关键词）→ 丢弃 ----
        #   即使有 start_ym：只要 全字段 都没任何培训关键词，且 tname/org 是纯公司后缀，那也是错解析
        # EN: ---- Pure company name (no training keyword) → discard ----
        #       Even with start_ym: if no field has any training keyword and tname/org is a pure company suffix, it is a misparse
        # JA: ---- 会社名だけ（研修のキーワードなし）→ 破棄 ----
        #       start_ym があっても：どのフィールドにも研修のキーワードがなく、tname/org が会社の接尾辞だけなら誤った解析である
        def _is_pure_company(s: str) -> bool:
            if not s:
                return False
            return any(cs in s for cs in COMPANY_SUFFIX_KW)

        _any_training_mark = (
            any(k in main_text for k in TRAINING_VALID_KW)
            or bool(org and any(k in org for k in ("机构", "学校", "大学", "学院", "中心", "新东方", "网校")))
        )
        if not _any_training_mark:
            # 全字段没一个培训/学习/认证/学校 关键词 → 高度疑似垃圾
            # EN: Not a single training/study/certification/school keyword in any field → highly suspected junk
            # JA: どのフィールドにも研修・学習・認定・学校のキーワードが 1 つもない → ゴミの疑いが強い
            if _is_pure_company(tname) or _is_pure_company(org):
                continue
            # tname 是纯职位（经理/助理/工程师） → 丢弃
            # EN: tname is a pure position (经理/助理/工程师: manager/assistant/engineer) → discard
            # JA: tname が職位だけ（经理／助理／工程师：マネージャー・アシスタント・エンジニア）→ 破棄
            _PURE_POS_SUFF = ("经理", "主管", "主任", "总监", "专员", "助理", "顾问", "工程师",
                              "设计师", "代表", "销售", "会计", "出纳", "文员", "秘书",
                              "行政", "人事", "财务", "组长", "科长", "部长", "总裁",
                              "业务员", "培训师", "讲师", "编辑", "记者", "校长", "院长", "所长")
            def _looks_pure_pos(s: str) -> bool:
                if not s: return False
                if len(s) > 40: return False
                return any(suf in s for suf in _PURE_POS_SUFF) and not _is_pure_company(s)
            if _looks_pure_pos(tname):
                continue

        # 提前定义这些标记变量（后面多处会用到）
        # EN: Define these flag variables in advance (used in several places later)
        # JA: これらのフラグ変数を前もって定義する（後で何か所かで使う）
        has_date = bool(start_ym or end_ym)
        org_is_training_body = bool(org) and any(k in org for k in ("机构", "学校", "大学", "学院", "中心", "新东方", "网校"))
        has_valid_training_mark = any(k in main_text for k in TRAINING_VALID_KW)

        # ---- 项目/销售工作强特征：无培训关键词 或 无日期+非培训主体 → 丢弃（如「招投标项目」「签单回款」「售后报价」等）
        # EN: ---- Strong features of project/sales work: no training keyword, or no date + not a training entity → discard (e.g. "招投标项目" (bidding project), "签单回款" (closing deals and collecting payment), "售后报价" (after-sales quotation))
        # JA: ---- プロジェクト・営業業務の強い特徴：研修のキーワードがない、または日付がなく研修の主体でもない → 破棄（例：「招投标项目」（入札案件）、「签单回款」（受注と入金回収）、「售后报价」（アフターサービスの見積もり））
        def _smells_work_or_project(text_blob: str) -> bool:
            return any(kw in text_blob for kw in WORK_OR_PROJECT_SMELL_KW)
        full_blob = f"{tname} {org} {desc}"
        if not has_date and not has_valid_training_mark and _smells_work_or_project(full_blob):
            continue
        if not has_date and not org_is_training_body and _smells_work_or_project(full_blob):
            continue

        # ---- 关键规则：无明确日期 且 无任何培训关键词 且 非明确培训机构 → 高度疑似垃圾，丢弃 ----
        # EN: ---- Key rule: no explicit date, no training keyword at all and not an explicit training provider → highly suspected junk, discard ----
        # JA: ---- 重要なルール：明確な日付がなく、研修のキーワードもまったくなく、明確な研修機関でもない → ゴミの疑いが強いので破棄 ----
        if not has_date and not any(k in main_text for k in TRAINING_VALID_KW) and not org_is_training_body:
            continue

        # ---- 去重 ----
        # EN: ---- Dedup ----
        # JA: ---- 重複排除 ----
        norm_org = re.sub(r"[\s:：,，.。、|｜()（）\[\]【】]+", "", org)[:12]
        norm_t = re.sub(r"[\s:：,，.。、|｜()（）\[\]【】]+", "", tname)[:12]
        norm_start = start_ym[:7] if start_ym else ""
        key = (norm_org, norm_t, norm_start)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # ---- 入列 ----
        # EN: ---- Enqueue ----
        # JA: ---- リストに追加 ----
        nt = dict(t)
        nt["organization_name"] = org
        nt["training_name"] = tname
        cleaned.append(nt)

    for i, t in enumerate(cleaned, 1):
        t["sequence_no"] = i
    return cleaned


def _clean_work_responsibilities(resp_str: str, comp_name: str, pos_name: str) -> str:
    """清理工作描述顶部的元数据行，并裁切尾部混入的项目经历、教育背景、家庭情况、期望薪资等杂质行。

    EN: Clean metadata lines at the top of job descriptions, and trim noise lines mixed in at the end such as project history, education background, family situation and expected salary.

    JA: 職務説明の先頭のメタデータ行を除き、末尾に混入したプロジェクト経験・学歴・家族状況・希望給与などの不要な行を切り落とす。
    """
    if not resp_str:
        return ""
    lines = [l.strip() for l in resp_str.splitlines() if l.strip()]
    if not lines:
        return ""
    
    start_idx = 0
    for i in range(min(5, len(lines))):
        ln = lines[i]
        if comp_name and comp_name in ln:
            start_idx = i + 1
            continue
        if _is_duration_text_global(ln) or re.search(r"\(?\s*\d+年\s*\d*个?月?\s*\)?", ln):
            start_idx = i + 1
            continue
        if "|" in ln or "｜" in ln:
            ok, ind, emp = _try_extract_attrs_global(ln)
            if ok:
                start_idx = i + 1
                continue
        if pos_name and (pos_name == ln or pos_name in ln):
            start_idx = i + 1
            continue
        if any(dept in ln for dept in ("部门", "销售部", "市场部", "研发部", "技术部", "行政部", "财务部", "注册部", "后勤部")) and len(ln) <= 12:
            start_idx = i + 1
            continue
        break

    cleaned_lines = lines[start_idx:]

    END_STOP_KEYWORDS = (
        "项目经历", "项目经验", "教育背景", "教育经历", "自我评价", "求职意向",
        "在校经历", "获奖情况", "语言能力", "专业技能", "所获证书", "培训经历",
        "家庭情况", "Family situation", "到岗时间", "期望Package", "期望月薪", "求职状态",
        "离职原因", "猜你喜欢", "推荐信", "个人作品"
    )
    end_idx = len(cleaned_lines)
    for i, ln in enumerate(cleaned_lines):
        if any(kw in ln for kw in END_STOP_KEYWORDS):
            end_idx = i
            break

    final_lines = cleaned_lines[:end_idx]
    res_text = "\n".join(final_lines).strip()
    if len(res_text) > 1200:
        res_text = res_text[:1200].rsplit("\n", 1)[0].strip()
    return res_text


# =============================================================================
# 项目经历：描述/职责分离 + 培训名→项目名兜底映射
# =============================================================================
# EN: =============================================================================
#     Project history: separate description/duties + fallback mapping from training name → project name
#     =============================================================================
# JA: =============================================================================
#     プロジェクト経験：説明と担当業務の分離 + 研修名 → プロジェクト名への最終手段の対応付け
#     =============================================================================

def _separate_project_desc_resp(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按关键词将项目 description 中的「责任描述/职责」拆到 responsibilities，
    「项目描述/项目介绍」保留在 description。

    EN: Split "责任描述/职责" (responsibility description / duties) out of project description into responsibilities by keyword,
    keeping "项目描述/项目介绍" (project description / introduction) in description.

    JA: キーワードに従い、プロジェクトの description から「责任描述／职责」（担当業務の説明・職責）を responsibilities に分け、
    「项目描述／项目介绍」（プロジェクトの説明・紹介）は description に残す。
    """
    if not projects:
        return []
    for p in projects:
        desc = str(p.get("description") or "").strip()
        if not desc:
            continue
        lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
        desc_parts: list[str] = []
        resp_parts: list[str] = []
        current = "desc"
        for ln in lines:
            if re.match(r"^(?:责任描述|职责|岗位职责|项目职责|工作职责|主要职责|负责内容)\s*[：:]?\s*", ln):
                val = re.sub(r"^(?:责任描述|职责|岗位职责|项目职责|工作职责|主要职责|负责内容)\s*[：:]?\s*", "", ln)
                if val:
                    resp_parts.append(val)
                current = "resp"
                continue
            if re.match(r"^(?:项目描述|项目介绍|项目简介|项目背景)\s*[：:]?\s*", ln):
                val = re.sub(r"^(?:项目描述|项目介绍|项目简介|项目背景)\s*[：:]?\s*", "", ln)
                if val:
                    desc_parts.append(val)
                current = "desc"
                continue
            if current == "resp":
                resp_parts.append(ln)
            else:
                desc_parts.append(ln)
        new_desc = "\n".join(desc_parts).strip()
        new_resp = "\n".join(resp_parts).strip()
        if new_desc:
            p["description"] = new_desc
        if new_resp:
            old_resp = str(p.get("responsibilities") or p.get("position_responsibilities") or "").strip()
            if old_resp and old_resp not in new_resp:
                p["responsibilities"] = old_resp + "\n" + new_resp
            else:
                p["responsibilities"] = new_resp
    return projects


def _fix_project_training_name(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """若 training_name 有值但 project_name 为空，映射 training_name 到 project_name。

    EN: If training_name has a value but project_name is empty, map training_name to project_name.

    JA: training_name に値があり project_name が空なら、training_name を project_name に対応付ける。
    """
    if not projects:
        return []
    for p in projects:
        pname = str(p.get("project_name") or "").strip()
        tname = str(p.get("training_name") or "").strip()
        if not pname and tname:
            p["project_name"] = tname
    return projects


# =============================================================================
# 51job 专属：板块限定范围的工作/教育/技能提取（避免跨板块污染）
# =============================================================================
# EN: =============================================================================
#     51job-specific: section-scoped extraction of work/education/skills (to avoid cross-section pollution)
#     =============================================================================
# JA: =============================================================================
#     51job 専用：セクションに範囲を限定した職歴・学歴・スキルの抽出（セクションをまたぐ汚染を避ける）
#     =============================================================================

def _51job_text_section(text: str, section_name: str, stop_names: list[str]) -> str:
    """提取 51job 的板块文本（限定范围避免跨板块）。

    EN: Extract 51job section text (scope-limited to avoid crossing sections).

    JA: 51job のセクションのテキストを抽出する（セクションをまたがないよう範囲を限定）。
    """
    return _section_block(text, [section_name], stop_names)


def _fix_education_school_major(edu_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    major_keywords = {"专业", "文学", "工程", "管理", "科学", "艺术", "技术", "系", "方向", "学", "工艺", "政治"}
    school_keywords = {"大学", "学院", "学校", "分校", "大学院", "短大", "专科学校", "University", "College", "School", "Institute"}
    degree_keywords = {"博士后", "博士", "硕士", "本科", "大专", "专科", "高中", "中专", "职高", "初中", "小学"}
    invalid_school_kw = ("学生会", "部长", "主席", "社团", "班长", "委员", "团支书", "志愿者", "大赛", "荣誉", "职务")

    cleaned_list = []
    for edu in edu_list:
        sch = str(edu.get("school_name") or "").strip()
        maj = str(edu.get("school_major_name") or "").strip()
        deg = str(edu.get("school_degree_type") or "").strip()
        if any(k in sch for k in invalid_school_kw):
            continue
        sch = re.sub(r"^[0-9]+[\s\xa0\.\,\-\_]*", "", sch)
        sch = re.sub(r"\s*(?:\d+年(?:\s*\d+个?月)?|至今|现在)\s*$", "", sch).strip()
        parts = [p.strip() for p in re.split(r"[\s\xa0\|│\t]+", sch) if p.strip()]
        if len(parts) >= 2:
            ex_sch, ex_maj, ex_deg = "", "", ""
            for p in parts:
                if not ex_sch and any(k in p for k in school_keywords):
                    ex_sch = p
                elif p in degree_keywords or any(k in p for k in degree_keywords):
                    ex_deg = p
                elif not ex_maj:
                    ex_maj = p
            if ex_sch:
                sch = ex_sch
            if ex_maj and (not maj or maj in (")", "(", "）", "（")):
                maj = ex_maj
            if ex_deg:
                deg = ex_deg
        if maj in (")", "(", "）", "（", "语言能力", "专业", "未填写"):
            maj = ""
        sch_is_major = any(k in sch for k in major_keywords) and not any(k in sch for k in school_keywords)
        maj_is_school = any(k in maj for k in school_keywords)
        if sch_is_major and maj_is_school:
            sch, maj = maj, sch
        if any(k in sch for k in invalid_school_kw):
            continue
        edu["school_name"] = sch
        edu["school_major_name"] = maj
        if deg:
            edu["school_degree_type"] = deg
        cleaned_list.append(edu)
    return cleaned_list


# =============================================================================
# 顶层 空对象构造器
# =============================================================================
# EN: =============================================================================
#     Top-level empty object constructors
#     =============================================================================
# JA: =============================================================================
#     トップレベルの空オブジェクトの生成関数
#     =============================================================================

def _build_empty_education_info() -> dict[str, str]:
    # 严格 7 字段（对齐 CONTEXT §8.3 标准：education_info 与 education_list 条目相同）
    # EN: Strictly 7 fields (aligned with CONTEXT §8.3: education_info is the same as an education_list entry)
    # JA: 厳密に 7 フィールド（CONTEXT §8.3 の標準に合わせる：education_info は education_list の項目と同じ）
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
    # 严格 16 字段（对齐 CONTEXT §8.1 标准：current_info 快照，去掉别名：start_date/end_date/department
    # EN: Strictly 16 fields (aligned with CONTEXT §8.1: current_info snapshot, with aliases start_date/end_date/department removed
    # JA: 厳密に 16 フィールド（CONTEXT §8.1 の標準に合わせる：current_info のスナップショット。別名 start_date/end_date/department は除く
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


# =============================================================================
# 单文件主处理函数（docs\\中文 专用：统一应用四大平台的后处理工具函数）
# =============================================================================
# EN: =============================================================================
#     Main per-file processing function (for docs\\中文 (Chinese) only: applies the post-processing helpers of the four major platforms uniformly)
#     =============================================================================
# JA: =============================================================================
#     単一ファイルのメイン処理関数（docs\\中文（中国語）専用：4 大プラットフォームの後処理ツール関数を一括で適用）
#     =============================================================================

def build_record_from_html(
    html_path: Path,
    parser: CodexGeminiHtmlSchemaParser,
    classifier: DocumentClassifier,
) -> tuple[dict[str, Any] | None, str]:
    """返回 (record 或 None, 状态)。platform_from 统一写「中文」。

    EN: Returns (record or None, status). platform_from is uniformly written as "中文" (Chinese).

    JA: 戻り値：(record または None, 状態)。platform_from には一律に「中文」（中国語）と書く。
    """
    # 1. 统一 HTML 解码 → 统一 plain_text 预处理（四大平台预处理已合并到 html_to_plain_text）
    # EN: 1. Unified HTML decoding → unified plain_text pre-processing (the pre-processing of the four major platforms is merged into html_to_plain_text)
    # JA: 1. HTML のデコードを統一 → plain_text の前処理を統一（4 大プラットフォームの前処理は html_to_plain_text に統合済み）
    try:
        html_text = read_html_text(html_path)
    except Exception as exc:
        return None, f"read_error:{exc}"

    text = html_to_plain_text(html_text)
    if len(text) < 10:
        return None, "empty_text"

    try:
        classification = classifier.classify(text, filename=html_path.name)
    except Exception:
        classification = type("C", (), {"document_type": "ambiguous_resume", "reason": "classifier_exception"})()

    if classification.document_type not in {"resume", "ambiguous_resume"}:
        return None, f"non_resume:{classification.document_type}"

    fake_source_path = str(html_path.resolve())
    original_source_path = extract_original_source_path(html_text, fake_source_path)
    try:
        parsed = parser.parse(html_text, filename=html_path.name, source_path=fake_source_path)
    except Exception as exc:
        return None, f"parser_error:{exc}"

    structured_data = parsed or {}

    # === 基础设计思路：先按 10 大标题做 Section 化，再做各 Module 的 Block 隔离充填 ===
    # EN: === Basic design: first sectionise by the 10 main headings, then fill each module's isolated block ===
    # JA: === 基本設計の考え方：まず 10 の大見出しでセクション化し、その後各モジュールの分離したブロックを埋める ===
    sections = parse_resume_sections(text)
    header_sec_text = sections.get("header") or text
    work_sec_text = sections.get("work_experience") or text
    edu_sec_text = sections.get("education") or text
    job_sec_text = sections.get("job_intention") or text
    train_sec_text = sections.get("trainings") or ""
    proj_sec_text = sections.get("project_experience") or ""
    # 生成器已经提供稳定的 data-section-type；优先按 DOM 章节取值，避免正文中的
    # “专业技能/项目经历”等普通短语把教育或工作章节误切断。
    # EN: The generator already provides a stable data-section-type; prefer taking values by DOM section, so ordinary phrases in the body
    #     like "专业技能/项目经历" (professional skills / project history) do not cut the education or work section short by mistake.
    # JA: 生成器はすでに安定した data-section-type を提供している。DOM の章ごとに値を取ることを優先し、本文中の
    #     「专业技能／项目经历」（専門スキル・プロジェクト経験）などの普通の語句で学歴や職歴の章が誤って切られないようにする。
    dom_sections = {
        "header": semantic_dom_section_text(html_text, ("base_info", "document-body")),
        "job": semantic_dom_section_text(html_text, ("expected_list",)),
        "work": semantic_dom_section_text(html_text, ("work_experiences",)),
        "education": semantic_dom_section_text(html_text, ("education_list",)),
        "training": semantic_dom_section_text(html_text, ("training_list",)),
        "project": semantic_dom_section_text(html_text, ("project_list",)),
    }
    header_sec_text = dom_sections["header"] or header_sec_text
    if dom_sections["job"] and len(dom_sections["job"]) <= 3000:
        job_sec_text = dom_sections["job"]
    work_sec_text = dom_sections["work"] or work_sec_text
    edu_sec_text = dom_sections["education"] or edu_sec_text
    train_sec_text = dom_sections["training"] or train_sec_text
    proj_sec_text = dom_sections["project"] or proj_sec_text

    # 1. 姓名提取（强限定在 header Section 内提取，绝不侵入工作经历）
    # EN: 1. Name extraction (strictly limited to the header section, never intruding into work history)
    # JA: 1. 氏名の抽出（header セクション内に厳格に限定し、職歴には決して入り込まない）
    if not structured_data.get("base_info"):
        structured_data["base_info"] = {}
    parsed_fn = (structured_data.get("base_info") or {}).get("full_name", "")
    correct_fn = extract_candidate_name(header_sec_text, html_path.name, parsed_fn, html_text)
    # —— 关键修复：fallback。像金婉婷这种 姓名不在 header，而在 footer（求职人：XXX）尾部 / 简历尾部的情况，
    #    必须用 full raw_text 重新 extract。
    # EN: —— Key fix: fallback. In cases like a past one where the name is not in the header but in the footer (求职人：XXX (job seeker: XXX)) at the end / the end of the résumé,
    #        the full raw_text must be used to extract again.
    # JA: —— 重要な修正：fallback。過去の事例のように氏名が header ではなく footer（求职人：XXX（求職者：XXX））の末尾や履歴書の末尾にある場合は、
    #        完全な raw_text で改めて抽出する必要がある。
    _bad_name_markers = {"", "未知", "未公开", "无关联", "简历", "个人简历", "中文简历", "网简"}
    if (correct_fn in _bad_name_markers) or len(correct_fn) > 12 or (
        correct_fn.endswith(("先生", "女士", "小姐", "同志")) and len(correct_fn) <= 4
    ):
        correct_fn2 = extract_candidate_name(text, html_path.name, parsed_fn, html_text)
        if correct_fn2 and correct_fn2 not in _bad_name_markers and len(correct_fn2) <= 12:
            correct_fn = correct_fn2
    if correct_fn.endswith(("先生", "女士", "小姐", "同志")):
        m_real = re.search(r"(?:姓名|候选人|应聘者)[\s:：]+([\u4e00-\u9fff]{2,4})", text)
        if m_real and not any(m_real.group(1).endswith(suf) for suf in ("先生", "女士", "小姐")):
            correct_fn = m_real.group(1)
        else:
            m_self = re.search(r"我是([\u4e00-\u9fff]{2,4})", text)
            if m_self:
                correct_fn = m_self.group(1)
            else:
                m_g = re.search(r"([\u4e00-\u9fff]{2,4})\s*(?:求职|简历|个人简历)", text)
                if (
                    m_g
                    and m_g.group(1) not in {"猎聘网", "智联招聘", "前程无忧", "个人", "中文", "英文"}
                    and not any(m_g.group(1).endswith(suf) for suf in ("先生", "女士", "小姐"))
                ):
                    correct_fn = m_g.group(1)
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}的", correct_fn or ""):
        correct_fn = correct_fn[:-1]
    # 内容被匿名化或误抓为“全职”时，只接受文件名中非常明确的姓名形态作为兜底。
    # EN: When the content is anonymised or mis-grabbed as "全职" (full-time), accept only very explicit name forms in the file name as a fallback.
    # JA: 内容が匿名化されているか「全职」（正社員）と誤って取られた場合は、ファイル名にある非常に明確な氏名の形だけを最終手段として受け入れる。
    if correct_fn in {"", "未知", "全职", "兼职", "实习", "简历"} or "采集" in (correct_fn or ""):
        filename_stem = re.sub(r"_[0-9a-f]{12}$", "", html_path.stem, flags=re.I).strip()
        filename_name = ""
        direct_name = re.fullmatch(r"([\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{2,8})?)(?:简历)?", filename_stem)
        named_resume = re.search(r"([\u4e00-\u9fff]{2,4})的中文简历", filename_stem)
        platform_name = re.search(r"(?:51job|智联招聘)[ _-]+([\u4e00-\u9fff]{2,4})(?=[(_（]|[_ -]|$)", filename_stem, re.I)
        platform_latin_name = re.search(r"(?:51job|智联招聘)[ _-]+([A-Za-z][A-Za-z0-9.'-]{1,20})(?=[(_（]|[_ -]|$)", filename_stem, re.I)
        resume_name = re.search(r"(?:个人简历|中文简历)[ _-]*([\u4e00-\u9fff]{2,4})|([\u4e00-\u9fff]{2,4})(?:个人简历|的简历|[ _-]+简历)", filename_stem)
        anonymized_name = re.search(r"([A-Za-z\u4e00-\u9fff]{1,2}(?:先生|女士|小姐))", filename_stem, re.I)
        if direct_name:
            filename_name = direct_name.group(1)
        elif named_resume:
            filename_name = named_resume.group(1)
        elif platform_name:
            filename_name = platform_name.group(1)
        elif resume_name:
            filename_name = resume_name.group(1) or resume_name.group(2)
        elif anonymized_name:
            filename_name = anonymized_name.group(1)
        if filename_name and filename_name not in {"个人简历", "中文简历", "求职申请", "招聘简历"}:
            correct_fn = filename_name
        if correct_fn in {"", "未知", "全职", "兼职", "实习", "简历"} or "采集" in (correct_fn or ""):
            contextual_name = source_context_name(original_source_path)
            if contextual_name:
                correct_fn = contextual_name
            elif platform_latin_name:
                correct_fn = platform_latin_name.group(1)
    structured_data["base_info"]["full_name"] = correct_fn
    structured_data["base_info"]["name"] = correct_fn  # 同步 name 字段（消费端常用）
    # EN: Sync the name field (commonly used by consumers)
    # JA: name フィールドを同期する（利用側でよく使われる）

    # 联系方式（mailto 优先，避开 HYPERLINK 宏残留）
    # EN: Contact details (mailto first, avoiding leftover HYPERLINK macros)
    # JA: 連絡先（mailto を優先し、HYPERLINK マクロの残骸を避ける）
    contacts = extract_contacts_all(header_sec_text)
    enhanced_email = _extract_email_enhanced(header_sec_text)
    if contacts["mobile"]:
        structured_data["base_info"]["phone"] = contacts["mobile"]
    if enhanced_email:
        structured_data["base_info"]["email"] = enhanced_email
    elif contacts["email"]:
        structured_data["base_info"]["email"] = contacts["email"]
    # 匿名平台常把邮箱导出为 ********@domain；这不是可用联系方式，也不能进入文件名。
    # EN: Anonymising platforms often export e-mails as ********@domain; this is not a usable contact and must not go into the file name either.
    # JA: 匿名化するプラットフォームはメールを ********@domain として出力することが多い。これは使える連絡先ではなく、ファイル名にも使ってはならない。
    current_email = str(structured_data["base_info"].get("email") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", current_email) or "*" in current_email:
        structured_data["base_info"]["email"] = ""

    # 基础信息补增强：出生年月(带空格兼容)、身高、体重、城市前缀
    # EN: Enhance basic info: birth date (compatible with spaces), height, weight, city prefix
    # JA: 基本情報の強化：生年月日（空白入りにも対応）、身長、体重、都市の接頭辞
    base_info = structured_data["base_info"]
    if not base_info.get("birth_year") or not base_info.get("birth_date"):
        m_birth = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月", text)
        if m_birth:
            y, m = m_birth.group(1), int(m_birth.group(2))
            base_info["birth_year"] = y
            base_info["birth_date"] = f"{y}-{m:02d}"
    if not base_info.get("height_cm"):
        m_h = re.search(r"(\d{2,3})\s*cm", text, re.I)
        if m_h:
            base_info["height_cm"] = m_h.group(1)
    if not base_info.get("weight_kg"):
        m_w = re.search(r"(\d{2,3})\s*kg", text, re.I)
        if m_w:
            base_info["weight_kg"] = m_w.group(1)
    if base_info.get("city") and base_info["city"].startswith("于"):
        base_info["city"] = base_info["city"].lstrip("于").strip()
    # —— 关键修复：清理 base_info.city / residence_city 等字段中的明显垃圾值（不是合法 2-6 字城市名、
    # 或包含学校/公司/部门/学历等非地理关键词）
    # EN: —— Key fix: clean obviously junk values in fields like base_info.city / residence_city (not a valid 2-6 character city name,
    #     or containing non-geographic keywords such as school/company/department/degree)
    # JA: —— 重要な修正：base_info.city / residence_city などのフィールドにある明らかなゴミ値を除去する（正当な 2〜6 文字の都市名でない、
    #     または学校・会社・部署・学歴などの地理以外のキーワードを含むもの）
    GEO_CITY_VALID_SUFFIXES = ("省", "市", "区", "县", "镇", "乡", "州", "盟", "地区", "特别行政区", "自治州", "自治区")
    INVALID_CITY_KW = ("学校", "学院", "大学", "小学", "中学", "公司", "有限公司", "集团", "部", "科", "处",
                       "本科", "硕士", "博士", "专业", "学历", "职位", "薪资", "月薪", "年薪", "培训", "证书",
                       "简历", "经理", "主管", "总监", "专员", "助理", "工程师", "技术", "科技", "管理")
    for fld in ("city", "residence_city", "hukou_city"):
        raw = base_info.get(fld, "")
        if not raw:
            continue
        v = str(raw).strip().strip("|｜-~～，,。.：:；;、/ ")
        # 明显非城市特征的关键词
        # EN: Keywords obviously not typical of cities
        # JA: 明らかに都市の特徴ではないキーワード
        if any(k in v for k in INVALID_CITY_KW) and not any(
            v.endswith(s) or s in v for s in GEO_CITY_VALID_SUFFIXES if len(v) <= 12
        ):
            base_info[fld] = ""
            continue
        # 长度异常（中文城市名一般 2-8 字，含后缀顶多 10 字；超过 12 字基本是描述串）
        # EN: Abnormal length (Chinese city names are generally 2-8 characters, at most 10 with a suffix; over 12 is basically a descriptive string)
        # JA: 異常な長さ（中国の都市名は通常 2〜8 文字、接尾辞込みでも最大 10 文字。12 文字を超えるものはほぼ説明の文字列）
        if len(v) > 12 or len(v) < 2:
            base_info[fld] = ""
            continue
        # 全标点/全数字
        # EN: All punctuation / all digits
        # JA: すべて句読点・すべて数字
        if re.fullmatch(r"[\W\d_]+", v):
            base_info[fld] = ""
            continue
        # 结尾为地理后缀的，前缀至少 1-8 字；否则直接 2-6 字的裸名（如"上海"）也可
        # EN: Names ending in a geographic suffix need a prefix of at least 1-8 characters; otherwise a bare 2-6 character name (e.g. "上海") is also fine
        # JA: 地理的な接尾辞で終わるものは前に 1〜8 文字以上が必要。そうでなければ 2〜6 文字の裸の名前（例：「上海」）でもよい
        has_geo_suffix = any(v.endswith(s) for s in GEO_CITY_VALID_SUFFIXES)
        if not has_geo_suffix and not (2 <= len(v) <= 6 and bool(re.search(r"[\u4e00-\u9fff]", v))):
            base_info[fld] = ""
            continue
        base_info[fld] = v

    # 2. expected_info 补齐 8 字段（含「目前状况」→ 到岗时间）
    # EN: 2. Complete the 8 expected_info fields (including "目前状况" (current status) → start date)
    # JA: 2. expected_info の 8 フィールドを補完する（「目前状况」（現在の状況）→ 入社可能時期を含む）
    raw_expected = structured_data.get("expected_info") or (
        structured_data.get("resumes") or [{}]
    )[0].get("expected_info") if structured_data.get("resumes") else []
    structured_data["expected_info"] = complete_expected_info(raw_expected, text)
    exp_info = structured_data.get("expected_info") or {}
    def _dom_label_value(labels: tuple[str, ...]) -> str:
        label_pattern = "|".join(re.escape(label) for label in labels)
        stop_labels = r"期望薪资|地点|职能/职位|期望职位|行业|到岗时间|工作类型|工作性质|期望工作性质|希望"
        match = re.search(
            rf"(?:{label_pattern})\s*[：:]\s*(.+?)(?=\s*(?:{stop_labels})\s*[：:]|$)",
            job_sec_text,
            re.I | re.S,
        )
        if not match:
            return ""
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        value = re.sub(r"\s+(?:期望从事|期望|希望)$", "", value).strip()
        return value

    explicit_expected = {
        "expected_city": _dom_label_value(("地点", "期望工作地区", "期望地区")),
        "expected_position": _dom_label_value(("职能/职位", "期望职位", "期望从事职业")),
        "expected_industry": _dom_label_value(("行业", "期望从事行业")),
        "expected_start_date": _dom_label_value(("到岗时间",)),
        "expected_employment_type": _dom_label_value(("工作类型", "期望工作性质")),
    }
    for field, value in explicit_expected.items():
        if value:
            exp_info[field] = value
    for fld in ("expected_salary", "expected_start_date", "expected_employment_type"):
        value = str(exp_info.get(fld) or "").strip()
        value = re.split(r"\s+(?:地点|职能/职位|期望职位|工作类型|工作性质|期望工作性质|行业|希望)\s*[：:]?", value, maxsplit=1)[0].strip()
        exp_info[fld] = value
    employment_raw = str(exp_info.get("expected_employment_type") or "").strip()
    if employment_raw:
        # 工作性质是枚举字段，绝不能把后续自我评价/工作经历整段吞进来。
        # EN: The employment type is an enum field; it must never swallow whole following paragraphs of self-assessment / work history.
        # JA: 雇用形態は列挙型のフィールドであり、後続の自己評価や職歴の段落をまるごと取り込んではならない。
        prefix = re.match(
            r"^(?:全职|兼职|实习|劳务|派遣|合同制|临时)(?:\s*[、,，/和及]\s*(?:全职|兼职|实习|劳务|派遣|合同制|临时))*",
            employment_raw,
        )
        kinds = re.findall(r"全职|兼职|实习|劳务|派遣|合同制|临时", prefix.group(0) if prefix else "")
        exp_info["expected_employment_type"] = "、".join(dict.fromkeys(kinds))
    for fld in ("expected_city", "expected_position", "expected_industry"):
        val = str(exp_info.get(fld) or "").strip()
        val = re.split(r"\s+(?:期望月薪|期望薪资|目前状况|工作类型|工作性质|到岗时间|自我评价)\s*[：:]?", val, maxsplit=1)[0].strip()
        exp_info[fld] = val
        if any(k in val for k in ("未婚", "已婚", "男", "女", "应届", "离职", "在职", "未填写", "听说", "读写", "能力", "良好", "一般", "熟练", "流利")):
            exp_info[fld] = ""
    structured_data["expected_info"] = exp_info

    # 3. 教育经历 + 培训经历（强绑定属于 EDUCATION 的 Block 文本，切断误判）
    # EN: 3. Education history + training history (strongly bound to the block text belonging to EDUCATION, cutting off misjudgements)
    # JA: 3. 学歴 + 研修歴（EDUCATION に属するブロックのテキストに強く限定し、誤判定を断つ）
    raw_edus, raw_trainings = parse_education_from_raw_text(edu_sec_text)
    explicit_edus = parse_explicit_education_blocks(edu_sec_text)
    if explicit_edus:
        raw_edus = explicit_edus
    # —— 修复：直接用板块隔离解析的 raw_edus 替换所有 LLM 结果，避免保留「求职信/保存到我的电脑」这种垃圾
    # EN: —— Fix: directly replace all LLM results with raw_edus from section-isolated parsing, to avoid keeping junk like "求职信/保存到我的电脑" (cover letter / save to my computer)
    # JA: —— 修正：セクションを分離して解析した raw_edus で LLM の結果をすべて置き換え、「求职信／保存到我的电脑」（応募書類・PC に保存）などのゴミが残らないようにする
    if raw_edus:
        edus = raw_edus
    else:
        edus = structured_data.get("education_list") or []
        # 即使 fallback 用 LLM 结果，也再过滤一遍 UI 垃圾
        # EN: Even when falling back to the LLM results, filter UI junk once more
        # JA: LLM の結果にフォールバックした場合でも、もう一度 UI のゴミを除外する
        edus = [e for e in edus if e.get("school_name") and not (
            "求职信" in e["school_name"] or "保存到我的电脑" in e["school_name"]
        )]
    if edus:
        edus = _fix_education_school_major(edus)
        structured_data["education_list"] = normalize_education_list(edus, edu_sec_text)
    else:
        structured_data["education_list"] = []

    # 工作经历：优先用板块隔离解析的 raw_works，更可靠
    # EN: Work history: prefer raw_works from section-isolated parsing, which is more reliable
    # JA: 職歴：セクションを分離して解析した raw_works の方が信頼できるので優先する
    res0 = (structured_data.get("resumes") or [{}])[0]
    dom_works = res0.get("work_experiences") or structured_data.get("work_experiences") or []
    raw_works = parse_work_from_raw_text(work_sec_text)
    semantic_raw_works = copy.deepcopy(raw_works)
    if not (raw_works and all(isinstance(row, dict) and row.get("_source_confidence") == "explicit_date_block" for row in raw_works)):
        repaired_works = repair_explicit_pipe_work_headers(work_sec_text, raw_works)
        org_suffix_re = re.compile(r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院|商社|公司)$")
        def _org_score(rows: list[dict[str, Any]]) -> int:
            score = 0
            for row in rows or []:
                name = _clean_company_name(str(row.get("company_name") or ""))
                if org_suffix_re.search(name):
                    score += 1
            return score
        if _org_score(repaired_works) >= _org_score(raw_works):
            raw_works = repaired_works
    trusted_explicit_works = (
        copy.deepcopy(raw_works)
        if raw_works and all(isinstance(row, dict) and row.get("_source_confidence") == "explicit_date_block" for row in raw_works)
        else []
    )
    # —— 修复：raw_works 非空直接用，dom_works 仅作兜底；避免保留 LLM 垃圾段
    # EN: —— Fix: use raw_works directly when non-empty; dom_works is only a fallback; avoid keeping LLM junk entries
    # JA: —— 修正：raw_works が空でなければそのまま使い、dom_works は最終手段だけにする。LLM のゴミの項目を残さない
    if raw_works:
        final_works = raw_works
    else:
        final_works = dom_works
    if final_works:
        for w in final_works:
            if w.get("company_name"):
                w["company_name"] = _clean_company_name(w["company_name"])
            # === 增强 A：a)/b)/c) 列表标记垃圾清理（邓艳芳 W1/W2）===
            #   规则：公司名/职位/部门 如果以 [a-zA-Z0-9一二三四五六七八九十] + [).、]  + 空格 开头 → 去掉列表前缀
            # EN: === Enhancement A: clean a)/b)/c) list-marker junk (a past case, W1/W2) ===
            #       Rule: if company name/position/department starts with [a-zA-Z0-9一二三四五六七八九十] + [).、] + space → remove the list prefix
            # JA: === 強化 A：a)/b)/c) のリスト記号のゴミを除去する（過去の事例 W1/W2）===
            #       ルール：会社名・職位・部署が [a-zA-Z0-9一二三四五六七八九十] + [).、] + 空白 で始まる → リストの接頭辞を除く
            _LIST_MARK_RE = re.compile(
                r"^\s*[a-zA-Z０-９\d一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{1,3}\s*[)）.、.．]\s+"
            )
            for fld in ("company_name", "position", "position_dept"):
                val = str(w.get(fld) or "").strip()
                if not val:
                    continue
                new_val = _LIST_MARK_RE.sub("", val, count=1).strip()
                # 连续匹配多次（罕见但可能有  "a ) ..." 再被误判补 其他前缀的情况）
                # EN: Match repeatedly (rare, but "a ) ..." may be followed by other misjudged prefixes)
                # JA: 何度も続けてマッチさせる（まれだが「a ) ...」の後にさらに別の接頭辞が誤って付いていることがある）
                while new_val and _LIST_MARK_RE.match(new_val):
                    new_val = _LIST_MARK_RE.sub("", new_val, count=1).strip()
                if new_val != val:
                    w[fld] = new_val
            # === 增强 B：position 中「[:：] 公司名（属性） 职位」重复前缀清理（邓艳芳 W3/W4）===
            # EN: === Enhancement B: clean the repeated prefix "[:：] company name (attribute) position" in position (a past case, W3/W4) ===
            # JA: === 強化 B：position 内の「[:：] 会社名（属性） 職位」の重複した接頭辞を除去する（過去の事例 W3/W4）===
            pos = str(w.get("position") or "").strip()
            cname = str(w.get("company_name") or "").strip()
            if pos and cname and len(pos) > 6:
                # 情况 1：position 以 :或：开头 + cname + 可能的括号属性 + 空格 → 切掉
                # EN: Case 1: position starts with : or ： + cname + possible bracketed attribute + space → cut it off
                # JA: ケース 1：position が : か ： + cname + 括弧付きの属性（あれば）+ 空白 で始まる → 切り落とす
                m_dup = re.match(r"^\s*[:：]\s*" + re.escape(cname) + r"\s*(?:[（(][^）)]*[）)])?\s*", pos)
                if m_dup and len(m_dup.group(0)) < len(pos):
                    w["position"] = pos[len(m_dup.group(0)):].strip()
                    pos = w["position"]
                # 情况 2：cname 以括号结尾但公司名是「XX有限公司」（括号是城市，如「东陶（上海）有限公司」），
                #         position 可能是「：东陶（上海）有限公司（属性）XXX」，尝试模糊匹配
                # EN: Case 2: cname ends with a bracket but the company name is "XX有限公司" (the bracket is a city, e.g. "东陶（上海）有限公司"),
                #             position may be "：东陶（上海）有限公司（attribute）XXX"; try fuzzy matching
                # JA: ケース 2：cname が括弧で終わるが会社名は「XX有限公司」（括弧は都市。例：「东陶（上海）有限公司」）、
                #             position が「：东陶（上海）有限公司（属性）XXX」となっている場合は、あいまいマッチを試みる
                if not m_dup and pos and pos[0] in ":：" and cname:
                    # 从 position 正文中搜索 cname 的出现位置（去掉括号后的核心关键词）
                    # EN: Search the position text for where cname appears (the core keyword with brackets removed)
                    # JA: position の本文から cname の出現位置を探す（括弧を除いた中核のキーワード）
                    cname_core = re.sub(r"[（(][^）)]*[）)]", "", cname).strip()
                    if cname_core and cname_core in pos:
                        idx = pos.find(cname_core)
                        # 找到 cname_core 后，定位到 公司完整串 末尾，再 再找后面的 职位
                        # 简单方法：从 cname_core 开始向后找 30 字符，尝试切分
                        # EN: After finding cname_core, locate the end of the full company string, then look for the position after it
                        #     Simple approach: look 30 characters ahead from cname_core and try to split
                        # JA: cname_core が見つかったら、会社名全体の末尾を特定し、その後ろの職位を探す
                        #     簡単な方法：cname_core から 30 文字先まで見て分割を試みる
                        tail = pos[idx:]
                        # 查找第一个空格+非括号字符的位置（括号可能是公司属性）
                        # 尝试去掉 pos[:尾部]
                        # EN: Find the position of the first space + non-bracket character (brackets may be company attributes)
                        #     Try removing pos[:tail]
                        # JA: 最初の「空白 + 括弧以外の文字」の位置を探す（括弧は会社の属性かもしれない）
                        #     pos[:末尾] の除去を試みる
                        rest = pos[idx + len(cname_core):]
                        # 跳过公司后缀括号（如果 cname_core 后面还有 属性括号，需要跳过）
                        # EN: Skip company-suffix brackets (if there is still an attribute bracket after cname_core, it must be skipped)
                        # JA: 会社の接尾辞の括弧をスキップする（cname_core の後にまだ属性の括弧があればスキップする必要がある）
                        m_attr = re.match(r"\s*[（(][^）)]*[）)]\s*", rest)
                        if m_attr:
                            rest = rest[len(m_attr.group()):]
                        # 还有公司后缀（有限公司/股份...）没跳过的，再去掉
                        # EN: Remove any company suffix (有限公司/股份...) not yet skipped
                        # JA: まだスキップしていない会社の接尾辞（有限公司／股份…）があれば除く
                        rest = re.sub(r"^(?:有限公司|股份有限公司|有限责任公司|集团|公司)\s*", "", rest).strip()
                        if rest:
                            w["position"] = rest
                            pos = rest
            # 再清理一次 position 中残留的 前导冒号
            # EN: Clean leftover leading colons in position once more
            # JA: position に残った先頭のコロンをもう一度除く
            if w.get("position"):
                w["position"] = re.sub(r"^\s*[:：]\s*", "", w["position"].strip()).strip()
            if w.get("position_dept"):
                w["position_dept"] = re.sub(r"^\s*[:：]\s*", "", w["position_dept"].strip()).strip()
            # === 增强 C：字段同步：position_start→start_date，position_resigned→end_date，position_dept→department ===
            # EN: === Enhancement C: field sync: position_start→start_date, position_resigned→end_date, position_dept→department ===
            # JA: === 強化 C：フィールドの同期：position_start→start_date、position_resigned→end_date、position_dept→department ===
            if not w.get("start_date"):
                ps = w.get("position_start") or w.get("onboard_date") or ""
                if ps:
                    w["start_date"] = ps
            if not w.get("end_date"):
                pr = w.get("position_resigned") or w.get("resign_date") or w.get("dimission_date") or ""
                if pr:
                    w["end_date"] = pr
            if not w.get("department") and w.get("position_dept"):
                w["department"] = w["position_dept"]
            # === 增强 D：公司名如果等于职位名，且有职位后缀 → 清空公司名（避免 swap 失效的漏网情况）===
            # EN: === Enhancement D: if the company name equals the position name and has a position suffix → clear the company name (catching cases that slip through when the swap fails) ===
            # JA: === 強化 D：会社名が職位名と同じで職位の接尾辞がある → 会社名を空にする（入れ替えが効かずに漏れたケースを防ぐ）===
            c2 = w.get("company_name") or ""
            p2 = w.get("position") or ""
            if c2 and p2 and c2 == p2 and any(suf in p2 for suf in ("经理", "主管", "专员", "助理", "调达", "工程师")):
                w["company_name"] = ""
        structured_data["work_experiences"] = _postprocess_work_attrs(final_works)
    else:
        structured_data["work_experiences"] = []

    resumes = structured_data.get("resumes") or []
    if not resumes:
        resumes = [{
            "resume_language": "zh",
            "base_info": {},
            "expected_info": {},
            "work_experiences": [],
            "education_list": [],
            "certificate_list": [],
            "language_list": [],
            "skills_list": [],
            "training_list": [],
            "project_list": [],
            "communication_list": [],
        }]

    # expected_info 同步到 resume[0]
    # EN: Sync expected_info into resume[0]
    # JA: expected_info を resume[0] に同期する
    resumes[0]["expected_info"] = copy.deepcopy(structured_data["expected_info"])

    for r in resumes:
        r.setdefault("base_info", {})
        r["base_info"].setdefault("platform_from", PLAT_DEFAULT)
        # 无论 源 parser 是否 产生了 work_experiences，先 统一 做 postprocess（拆 position 的 属性行组合）
        # EN: Whether or not the source parser produced work_experiences, first run postprocess uniformly (splitting attribute-line combinations in position)
        # JA: 元のパーサーが work_experiences を生成したかどうかに関係なく、まず一律に postprocess を行う（position にある属性の行の組み合わせを分割）
        r.setdefault("work_experiences", [])
        try:
            r["work_experiences"] = _postprocess_work_attrs(r["work_experiences"])
        except Exception:
            pass
        # 若 顶层 raw_text 解析器（parse_work_from_raw_text）有 补充 的 work_experiences，以 它 为准 覆盖（再 后处理 一次 以防万一）
        # EN: If the top-level raw_text parser (parse_work_from_raw_text) has supplementary work_experiences, they take precedence and override (post-processed once more just in case)
        # JA: トップレベルの raw_text パーサー（parse_work_from_raw_text）に補足の work_experiences があれば、それを正として上書きする（念のためもう一度後処理する）
        if structured_data.get("work_experiences"):
            r["work_experiences"] = _postprocess_work_attrs(copy.deepcopy(structured_data.get("work_experiences")))
        r.setdefault("work_experiences", [])
        valid_works = []
        transferred_projects = []
        for w in r.get("work_experiences", []):
            if w.get("company_name"):
                w["company_name"] = re.sub(r"^(?:公司名称|公司名|单位名称|单位名|公司|名)\s*[:：]?\s*", "", w["company_name"]).strip()
            cname = _clean_company_name(w.get("company_name", ""))
            if not cname:
                continue

            resp = str(w.get("position_responsibilities") or "").strip()
            if (any(k in cname for k in ("资质办理", "采购项目", "建设项目")) or "项目描述" in resp or "项目职责" in resp or cname.endswith("项目")):
                transferred_projects.append({
                    "project_name": cname,
                    "project_role": w.get("position", ""),
                    "project_start": w.get("position_start", ""),
                    "project_end": w.get("position_resigned", ""),
                    "project_description": resp,
                    "project_responsibilities": "",
                    "company_name": "",
                })
                continue

            w["company_name"] = cname
            if w.get("position"):
                w["position"] = re.sub(r"\s*\d+(?:-\d+)?\s*(?:元|千|万)\s*/\s*月.*$", "", w["position"]).strip()
                w["position"] = w["position"].strip(" :：|｜-，,。.；;")
                if any(k in w["position"] for k in ("元/月", "000-", "元/年")):
                    w["position"] = ""
            if w.get("position") and (w["position"] == w.get("company_name") or _has_comp_sign_global(w["position"])):
                w["position"] = ""
            if w.get("position_responsibilities"):
                w["position_responsibilities"] = _clean_work_responsibilities(
                    w["position_responsibilities"],
                    w.get("company_name", ""),
                    w.get("position", "")
                )
                # “担任售后维修工程师”是显式职位陈述，强于误抓到的“维修工作/管理工作”。
                # EN: "担任售后维修工程师" (served as after-sales maintenance engineer) is an explicit position statement, stronger than a mis-grabbed "维修工作/管理工作" (maintenance work / management work).
                # JA: 「担任售后维修工程师」（アフターサービスの保守エンジニアを担当）は明示的な職位の記述であり、誤って取った「维修工作／管理工作」（保守業務・管理業務）より強い。
                current_position = str(w.get("position") or "").strip()
                explicit_position = re.search(
                    r"(?:担任|任职为|职位为)\s*([^，,。；;\n]{1,20}?(?:工程师|经理|主管|主任|总监|专员|助理|顾问|会计|出纳|文员|秘书|翻译|担当|销售|代表|店长|厂长|教师|老师|分析师|设计师))",
                    w["position_responsibilities"],
                )
                if explicit_position and (not current_position or current_position.endswith("工作")):
                    w["position"] = explicit_position.group(1).strip()
            valid_works.append(w)

        # ====== 新增 A：相同 position_start 的「两段式」合并（修复 51job 每段工作打印两次相同日期的 pattern：公司段 + 职位段）
        # 顾先生案例：3段工作 → 被识别成 6 段（每段打印两次相同日期）
        # EN: ====== New A: merge "two-part" entries with the same position_start (fixes the 51job pattern of printing each job twice with the same dates: a company part + a position part)
        #     A past case: 3 jobs → recognised as 6 (each printed twice with the same dates)
        # JA: ====== 追加 A：同じ position_start を持つ「2 段構成」の項目を統合する（51job が各職歴を同じ日付で 2 回出力するパターン：会社の段 + 職位の段 を修正）
        #     過去の事例：3 件の職歴 → 6 件と認識された（各件が同じ日付で 2 回出力）
        merged_works: list[dict[str, Any]] = []
        i = 0
        # 垃圾公司名关键词：这些是明显不是公司名（纯职位、薪资、职责片段）
        # EN: Junk company-name keywords: these are obviously not company names (pure positions, salaries, duty fragments)
        # JA: ゴミの会社名のキーワード：これらは明らかに会社名ではない（職位だけ・給与・職務の断片）
        BAD_COMPANY_HINTS_RE = re.compile(
            r"(参观工厂|^\d+\s*(元|千|万)\s*/\s*月$|^\d+\s*(元|千|万)\s*/\s*年$|薪资|月薪|年薪|下属人数|\brespon|\bwork\b|职责|负责|担当|管理|开发|维护|顾问|专员|助理|工程师|经理|主管|课长|部长|组长|主任|社长|会长|主席|设计师|分析师|实施|咨询|服务|业务)$", re.I
        )
        def _company_name_usable(c: str) -> bool:
            c = (c or "").strip()
            if not c:
                return False
            # 纯「有限公司」「股份有限公司」（前面没有实际公司名前缀）→ 不 usable，但允许合并时作为 fallback（不算 unusable garbage）
            # EN: A bare "有限公司" / "股份有限公司" (Ltd. / joint-stock Ltd.) (with no real company name before it) → not usable, but allowed as a fallback when merging (not counted as unusable garbage)
            # JA: 「有限公司」「股份有限公司」だけ（前に実際の会社名がない）→ 使えないが、統合時の最終手段としては許可する（使えないゴミには数えない）
            if c in ("有限公司", "股份有限公司", "有限责任公司"):
                return True
            if BAD_COMPANY_HINTS_RE.search(c):
                return False
            if len(c) <= 2 and c not in ("华为", "小米", "腾讯", "百度", "京东", "阿里", "美团"):
                return False
            return True
        def _position_name_usable(p: str) -> bool:
            p = (p or "").strip()
            if not p:
                return False
            if len(p) <= 1:
                return False
            return True

        while i < len(valid_works):
            w_a = valid_works[i]
            a_start = str(w_a.get("position_start") or "").strip()
            a_end = str(w_a.get("position_resigned") or "").strip()
            if i + 1 < len(valid_works) and a_start:
                w_b = valid_works[i + 1]
                b_start = str(w_b.get("position_start") or "").strip()
                b_end = str(w_b.get("position_resigned") or "").strip()
                # 相同 position_start 且 结束日期也相同（才是两段式）
                # EN: Same position_start and also the same end date (only then is it a two-part entry)
                # JA: position_start が同じで、終了日も同じ（その場合だけ 2 段構成とみなす）
                if (b_start == a_start) and (b_end == a_end):
                    a_com = str(w_a.get("company_name") or "").strip()
                    b_com = str(w_b.get("company_name") or "").strip()
                    a_pos = str(w_a.get("position") or "").strip()
                    b_pos = str(w_b.get("position") or "").strip()
                    # —— 预处理：如果 A/B 的 company_name 明显是职位词（BAD_COMPANY_HINTS_RE 匹配），且 position 为空，则视为「被错位到 company 的职位」，临时借用为 position
                    # EN: —— Pre-processing: if A/B's company_name is obviously a position word (matching BAD_COMPANY_HINTS_RE) and position is empty, treat it as "a position misplaced into company" and temporarily borrow it as position
                    # JA: —— 前処理：A／B の company_name が明らかに職位の語（BAD_COMPANY_HINTS_RE にマッチ）で position が空なら、「company にずれて入った職位」とみなして一時的に position として借りる
                    a_pos_eff = a_pos
                    if not a_pos_eff and a_com and BAD_COMPANY_HINTS_RE.search(a_com):
                        a_pos_eff = a_com  # 借用为职位（临时用于判断 can_merge，实际字段会 merge 纠正）
                        # EN: Borrowed as the position (temporarily, to decide can_merge; the actual fields are corrected by merge)
                        # JA: 職位として借りる（can_merge の判定のための一時的なもので、実際のフィールドは merge で補正する）
                    b_pos_eff = b_pos
                    if not b_pos_eff and b_com and BAD_COMPANY_HINTS_RE.search(b_com):
                        b_pos_eff = b_com
                    # 同理：如果 position_usable，且 company_usable，但另一侧 company 是职位词错位，我们依然可以 merge（merge 会把错位的位置写到 position）
                    # EN: Likewise: if position_usable and company_usable, but the other side's company is a misplaced position word, we can still merge (merge writes the misplaced value into position)
                    # JA: 同様に：position_usable かつ company_usable だが、もう一方の company が職位の語のずれである場合でも統合できる（merge がずれた値を position に書く）
                    a_com_ok = _company_name_usable(a_com)
                    b_com_ok = _company_name_usable(b_com)
                    a_pos_ok = _position_name_usable(a_pos_eff)
                    b_pos_ok = _position_name_usable(b_pos_eff)
                    # can_merge 更宽松：只要有至少一段有公司名，且至少一段有职位（含借位的职位词 company），或两段 company 都 ok（即使没有职位也合并）
                    # EN: can_merge is more lenient: as long as at least one part has a company name and at least one part has a position (including a borrowed position word in company), or both companies are ok (merge even without a position)
                    # JA: can_merge はより緩い：少なくとも一方に会社名があり、少なくとも一方に職位がある（company に借りた職位の語も含む）、または両方の company が問題なければ（職位がなくても）統合する
                    can_merge = (
                        (a_com_ok and b_pos_ok) or (b_com_ok and a_pos_ok)
                        or (a_com_ok and not a_pos_ok and b_pos_ok)
                        or (b_com_ok and not b_pos_ok and a_pos_ok)
                        or (a_com_ok and (not b_com))
                        or (b_com_ok and (not a_com))
                        or (a_com_ok and b_com_ok and len(a_com) >= 5 and len(b_com) >= 5)
                    )
                    if can_merge:
                        # 选「有 usable 公司」那一侧作为 good_company 侧
                        # EN: Choose the side with a "usable company" as the good_company side
                        # JA: 「使える会社」がある側を good_company 側とする
                        if a_com_ok:
                            good_company = w_a
                            good_pos = w_b
                        else:
                            good_company = w_b
                            good_pos = w_a
                        merged: dict[str, Any] = copy.deepcopy(good_company)
                        # —— 修复：两侧 company/position 4 个值里，选择"最像公司的"作为 company，
                        #    "最像职位的"作为 position，避免顾先生案例的错位
                        # EN: —— Fix: among the 4 company/position values of both sides, choose "the most company-like" as company
                        #        and "the most position-like" as position, to avoid the misplacement in a past case
                        # JA: —— 修正：両側の company／position の 4 つの値から「最も会社らしいもの」を company に、
                        #        「最も職位らしいもの」を position に選び、過去の事例のようなずれを防ぐ
                        _comp_marks = ("股份", "有限", "集团", "公司", "厂", "制造", "科技", "贸易", "投资", "咨询", "中心", "医院", "事业部", "分公司", "办事处", "工作室")
                        _pos_suffs = ("专员", "助理", "经理", "主管", "总监", "组长", "科长", "部长", "主任", "工程师",
                                      "设计师", "顾问", "代表", "销售", "会计", "出纳", "文员", "秘书", "行政", "人事",
                                      "财务", "讲师", "培训师", "编辑", "记者", "校长", "院长", "所长", "调达", "店长",
                                      "总经理", "副总经理", "厂长", "副厂长", "业务员", "营业员", "BD")
                        def _score_company(candidate: str) -> tuple[int, int, str]:
                            """打分：越高越像公司名。返回 (含后缀分, 长度分, 原始值)

                            EN: Scoring: higher means more company-like. Returns (suffix score, length score, original value)

                            JA: 採点：高いほど会社名らしい。戻り値：(接尾辞の点, 長さの点, 元の値)
                            """
                            s = (candidate or "").strip()
                            if not s: return (-1, -1, s)
                            score_marks = sum(1 for m in _comp_marks if m in s)
                            # BAD hints 直接扣分到负
                            # EN: BAD hints are scored directly to negative
                            # JA: BAD hints はそのままマイナスに減点する
                            if BAD_COMPANY_HINTS_RE.search(s) and not any(m in s for m in _comp_marks):
                                score_marks -= 100
                            # 月薪行
                            # EN: Monthly salary line
                            # JA: 月給の行
                            if re.search(r"(\d+)\s*(元|千|万)\s*/\s*(月|年)", s):
                                score_marks -= 100
                            return (score_marks, len(s), s)
                        def _score_position(candidate: str) -> tuple[int, int, str]:
                            """打分：越高越像职位名。返回 (含后缀分, 长度分, 原始值)

                            EN: Scoring: higher means more position-like. Returns (suffix score, length score, original value)

                            JA: 採点：高いほど職位名らしい。戻り値：(接尾辞の点, 長さの点, 元の値)
                            """
                            s = (candidate or "").strip()
                            if not s: return (-1, -1, s)
                            score = 0
                            for suf in _pos_suffs:
                                if s.endswith(suf):
                                    score += 10
                                    break
                            # SAP/技术术语加分
                            # EN: Bonus for SAP/technical terms
                            # JA: SAP や技術用語には加点する
                            if any(tok in s.lower() for tok in ("abap", "sap")):
                                score += 5
                            # 公司标志大幅减分（公司名被塞到 position 里）
                            # EN: Large penalty for company markers (a company name stuffed into position)
                            # JA: 会社の目印は大きく減点する（会社名が position に詰め込まれている）
                            if any(m in s for m in _comp_marks):
                                score -= 50
                            # BAD hints（参观工厂/负责...）无公司标志的话，合并到 position_responsibilities，这里减分避免当 position
                            # EN: BAD hints (参观工厂/负责...: factory visit / responsible for...) without a company marker are merged into position_responsibilities; penalise here so they are not used as position
                            # JA: 会社の目印のない BAD hints（参观工厂／负责...：工場見学・〜を担当）は position_responsibilities に統合する。position にしないようここで減点する
                            if BAD_COMPANY_HINTS_RE.fullmatch(s):
                                score -= 30
                            # 月薪
                            # EN: Monthly salary
                            # JA: 月給
                            if re.search(r"(\d+)\s*(元|千|万)\s*/\s*(月|年)", s):
                                score -= 100
                            return (score, -len(s), s)
                        # 4 candidates: (a_com, a_pos, b_com, b_pos) 中选最佳 company + 最佳 position
                        # EN: 4 candidates: choose the best company + best position among (a_com, a_pos, b_com, b_pos)
                        # JA: 4 つの候補：(a_com, a_pos, b_com, b_pos) から最適な company + 最適な position を選ぶ
                        _all_vals_for_company = [a_com, a_pos, b_com, b_pos]
                        _best_company = sorted(_all_vals_for_company, key=lambda x: _score_company(x), reverse=True)[0]
                        _best_company = _best_company.strip() if isinstance(_best_company, str) else ""
                        _all_vals_for_position = [a_pos, b_pos, a_com, b_com]
                        _best_position = sorted(_all_vals_for_position, key=lambda x: _score_position(x), reverse=True)[0]
                        _best_position = _best_position.strip() if isinstance(_best_position, str) else ""
                        # 如果最佳 position 仍包含公司标志，且最佳 company 与最佳 position 相等 → 清空 position（职位段缺失）
                        # EN: If the best position still contains a company marker and the best company equals the best position → clear position (the position part is missing)
                        # JA: 最適な position にまだ会社の目印があり、最適な company と最適な position が同じ → position を空にする（職位の段が欠けている）
                        if _best_position and any(m in _best_position for m in _comp_marks):
                            if _best_position == _best_company:
                                _best_position = ""
                        if _best_company and _score_company(_best_company)[0] > 0:
                            merged["company_name"] = _best_company
                        if _best_position and _score_position(_best_position)[0] >= 0:
                            merged["position"] = _best_position
                        # 额外：薪资收集
                        # EN: Extra: collect salaries
                        # JA: 追加：給与を集める
                        if not str(merged.get("position_salary") or "").strip():
                            for cand in (a_com, a_pos, b_com, b_pos):
                                if not cand: continue
                                if re.search(r"(\d+)\s*(元|千|万)\s*/\s*(月|年)", cand):
                                    merged["position_salary"] = cand.strip()
                                    break
                        # 如果 good_pos.com 是 BAD hints（如"参观工厂"）且非公司名，合并到 position_responsibilities（不当独立职位）
                        # EN: If good_pos.com is a BAD hint (e.g. "参观工厂" (factory visit)) and not a company name, merge it into position_responsibilities (not a separate position)
                        # JA: good_pos.com が BAD hints（例：「参观工厂」（工場見学））で会社名でないなら、position_responsibilities に統合する（独立した職位にはしない）
                        good_pos_com = str(good_pos.get("company_name") or "").strip()
                        if good_pos_com and BAD_COMPANY_HINTS_RE.fullmatch(good_pos_com):
                            existing_resp = str(merged.get("position_responsibilities") or "").strip()
                            good_pos_resp = str(good_pos.get("position_responsibilities") or "").strip()
                            merged["position_responsibilities"] = "\n".join(r for r in [existing_resp, good_pos_com, good_pos_resp] if r)
                        other = good_pos
                        other_com = str(other.get("company_name") or "").strip()
                        cur_com = str(merged.get("company_name") or "").strip()
                        if other_com and not BAD_COMPANY_HINTS_RE.search(other_com):
                            if (cur_com in ("有限公司", "股份有限公司", "有限责任公司")) and len(other_com) > len(cur_com):
                                merged["company_name"] = other_com
                            elif len(other_com) >= 5 and len(other_com) > len(cur_com) and _company_name_usable(other_com):
                                merged["company_name"] = other_com
                        POS_FIELDS = ("position", "position_type", "position_salary", "position_dept",
                                      "position_report_to", "position_subordinate",
                                      "position_responsibilities", "position_achievements",
                                      "resigned_reason")
                        for f in POS_FIELDS:
                            v_a = str(merged.get(f) or "").strip()
                            v_b = str(good_pos.get(f) or "").strip()
                            if f == "position":
                                # —— 特殊处理 position：优先"像职位的"，而不是更长的
                                # EN: —— Special handling of position: prefer the "position-like" one, not the longer one
                                # JA: —— position の特別処理：長い方ではなく「職位らしい方」を優先する
                                if not v_a and v_b:
                                    merged[f] = v_b
                                elif v_a and v_b:
                                    # 两侧都有值：选"像职位的" → 不含公司标志的
                                    # EN: Both sides have values: choose the "position-like" one → the one without a company marker
                                    # JA: 両側に値がある：「職位らしい方」→ 会社の目印のない方を選ぶ
                                    a_has_cmp = any(m in v_a for m in ("股份", "有限", "集团", "公司", "厂", "制造", "科技", "贸易", "投资", "咨询", "中心", "事业部", "分公司"))
                                    b_has_cmp = any(m in v_b for m in ("股份", "有限", "集团", "公司", "厂", "制造", "科技", "贸易", "投资", "咨询", "中心", "事业部", "分公司"))
                                    if a_has_cmp and not b_has_cmp:
                                        merged[f] = v_b  # 选 v_b（无公司标志，是真正的职位）
                                        # EN: Choose v_b (no company marker, the real position)
                                        # JA: v_b を選ぶ（会社の目印がなく、本当の職位）
                                    # 否则保持 v_a 或默认行为
                                    # EN: Otherwise keep v_a or the default behaviour
                                    # JA: そうでなければ v_a を残すか既定の動作にする
                            elif f == "position_responsibilities":
                                # 合并：两侧都有的话用更长的（更详细），没值的那侧忽略
                                # EN: Merge: if both sides have a value use the longer (more detailed); ignore the side with no value
                                # JA: 統合：両側に値があれば長い方（より詳しい）を使い、値のない側は無視する
                                if not v_a and v_b:
                                    merged[f] = v_b
                                elif v_a and v_b and len(v_b) > len(v_a):
                                    merged[f] = good_pos.get(f) or ""
                            else:
                                if v_b and (not v_a or len(v_b) > len(v_a)):
                                    merged[f] = good_pos.get(f) or ""
                        # 雇佣状态
                        # EN: Employment status
                        # JA: 雇用の状態
                        if not str(merged.get("position_resigned") or "").strip():
                            merged["status"] = "在职"
                        else:
                            merged["status"] = "离职"
                        # 薪资恢复：如果任何一侧的 company_name 是「8500元/月」这种，塞到 position_salary
                        # EN: Salary recovery: if either side's company_name is something like "8500元/月" (8500 yuan/month), put it into position_salary
                        # JA: 給与の復元：どちらかの company_name が「8500元/月」（月 8500 元）のようなものなら position_salary に入れる
                        if not str(merged.get("position_salary") or "").strip():
                            for cand_c in (a_com, b_com):
                                if re.search(r"(\d+)\s*(元|千|万)\s*/\s*(月|年)", cand_c):
                                    merged["position_salary"] = cand_c.strip()
                                    break
                        merged_works.append(merged)
                        i += 2
                        continue
            merged_works.append(w_a)
            i += 1
        valid_works = merged_works

        # ====== 新增 B：work_experiences 字段白名单清理（只保留 18 个标准字段，删除 start_date/end_date 等冗余别名）
        # EN: ====== New B: whitelist cleanup of work_experiences fields (keep only the 18 standard fields, deleting redundant aliases such as start_date/end_date)
        # JA: ====== 追加 B：work_experiences のフィールドのホワイトリストによる整理（標準の 18 フィールドだけを残し、start_date/end_date などの冗長な別名を削除）
        WORK_WHITELIST = {
            "company_name", "company_employees", "company_industry",
            "position", "position_type", "position_salary", "position_dept",
            "position_report_to", "position_subordinate",
            "employment_type", "annual_salary_min", "annual_salary_max",
            "status", "position_start", "position_resigned", "resigned_reason",
            "position_responsibilities", "position_achievements",
        }
        cleaned_works: list[dict[str, Any]] = []
        for w in valid_works:
            new_w: dict[str, Any] = {}
            for f in WORK_WHITELIST:
                new_w[f] = w.get(f, "") if f != "position_achievements" else w.get(f, "")
            # position_responsibilities 不允许为 null → 兜底空串
            # EN: position_responsibilities must not be null → fall back to an empty string
            # JA: position_responsibilities は null にしてはならない → 空文字で補う
            if not new_w.get("position_responsibilities"):
                new_w["position_responsibilities"] = ""
            if not new_w.get("employment_type"):
                new_w["employment_type"] = "全职"
            cleaned_works.append(new_w)
        r["work_experiences"] = cleaned_works
        if structured_data.get("education_list"):
            # ★权威同步：r["education_list"] 100% 拷贝 structured_data["education_list"]（已在 L6403 严格 normalize + KV 回填过）
            # 不做任何二次遍历/修改，避免二次过滤把正常条目清空或把 major 变成日期格式
            # EN: ★Authoritative sync: r["education_list"] is a 100% copy of structured_data["education_list"] (already strictly normalised + KV back-filled at L6403)
            #     No second traversal/modification, to avoid a second filter emptying normal entries or turning major into a date format
            # JA: ★正とする同期：r["education_list"] は structured_data["education_list"] を 100% コピーする（L6403 ですでに厳格に正規化 + KV で補完済み）
            #     2 回目の走査や変更は一切しない。2 回目のフィルターで正常な項目が空になったり major が日付の形式になったりするのを防ぐ
            r["education_list"] = copy.deepcopy(structured_data["education_list"])
        else:
            r.setdefault("education_list", [])
        # 轻量对齐：确保每个条目是 7 字段白名单（删除冗余别名字段，不改值）
        # EN: Light alignment: make sure each entry is the 7-field whitelist (delete redundant alias fields without changing values)
        # JA: 軽い整形：各項目が 7 フィールドのホワイトリストになるようにする（冗長な別名フィールドを削除し、値は変えない）
        _EDU_7 = ("school_name", "school_major_name", "school_degree_type", "school_degree_rank",
                  "school_education_type", "school_start_ym", "school_end_ym")
        _raw_edus = r.get("education_list") or []
        if _raw_edus:
            _fixed_edus: list[dict[str, Any]] = []
            for _e in _raw_edus:
                if not isinstance(_e, dict):
                    continue
                _ne: dict[str, Any] = {}
                for _k in _EDU_7:
                    _ne[_k] = str(_e.get(_k) or "").strip()
                # rank/degree 交叉补全（只在缺字段时补，不覆盖已有）
                # EN: Cross-complete rank/degree (fill only missing fields, never overwrite existing ones)
                # JA: rank と degree を相互に補完する（欠けているフィールドだけを補い、既存の値は上書きしない）
                _dr = _ne["school_degree_rank"]
                _dt = _ne["school_degree_type"]
                if _dr and not _dt:
                    _r2d = {"7": "博士后", "6": "博士", "5": "硕士", "4": "本科", "3": "大专", "2": "高中", "1": "初中"}
                    if _dr in _r2d:
                        _ne["school_degree_type"] = _r2d[_dr]
                if _dt and not _dr:
                    _d2r = {"博士后": "7", "博士": "6", "硕士": "5", "MBA": "5", "EMBA": "5", "研究生": "5",
                            "本科": "4", "专升本": "4", "大专": "3", "专科": "3", "高技": "3",
                            "高中": "2", "中专": "2", "职高": "2", "中技": "2", "初中": "1"}
                    if _dt in _d2r:
                        _ne["school_degree_rank"] = _d2r[_dt]
                _fixed_edus.append(_ne)
            r["education_list"] = _fixed_edus

        # 证书：先尝试智联的纯文本证书解析（含去杂质/去实践描述词），再统一 _clean_certificate_list
        # EN: Certificates: first try Zhaopin's plain-text certificate parsing (with noise and practice-description words removed), then apply _clean_certificate_list uniformly
        # JA: 資格：まず Zhaopin のプレーンテキストの資格解析（不要部分や実践の説明語を除く）を試し、その後一律に _clean_certificate_list を適用する
        r.setdefault("certificate_list", [])
        zhilian_certs = _parse_zhilian_certificates_simple(text)
        if zhilian_certs:
            r["certificate_list"] = zhilian_certs
        r["certificate_list"] = _clean_certificate_list(r.get("certificate_list") or [])

        # 语言列表：优先尝试纯文本解析器 parse_languages_from_raw_text，再应用 LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP
        # EN: Language list: first try the plain-text parser parse_languages_from_raw_text, then apply LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP
        # JA: 語学の一覧：まずプレーンテキストのパーサー parse_languages_from_raw_text を試し、その後 LANGUAGE_NAME_MAP / LANGUAGE_LEVEL_MAP を適用する
        r.setdefault("language_list", [])
        txt_langs = parse_languages_from_raw_text(text)
        # parser 原有 的 language_list 若 字段 缺 language_certificate，补齐；且 优先 合并 txt_langs
        # EN: If the parser's original language_list lacks the language_certificate field, fill it; and prefer merging txt_langs
        # JA: パーサー本来の language_list に language_certificate フィールドがなければ補い、txt_langs との統合を優先する
        merged_langs: list[dict[str, Any]] = []
        seen_lang_name: set[str] = set()
        def _push_lang(ln: dict[str, Any]):
            name = str(ln.get("language_name") or ln.get("name") or "").strip()
            if not name:
                return
            if name in LANGUAGE_NAME_MAP:
                name = LANGUAGE_NAME_MAP[name]
            ln["language_name"] = name
            if name in seen_lang_name:
                return
            seen_lang_name.add(name)
            # 确保 每个 语言 条目 有 4 个 标准 字段（对齐 liepin schema：language_name / language_level / language_certificate / language_certificate_time）
            # EN: Make sure every language entry has the 4 standard fields (aligned with the liepin schema: language_name / language_level / language_certificate / language_certificate_time)
            # JA: 各語学の項目が標準の 4 フィールドを持つようにする（liepin のスキーマに合わせる：language_name / language_level / language_certificate / language_certificate_time）
            ln.setdefault("language_level", "")
            ln.setdefault("language_certificate", "")
            ln.setdefault("language_certificate_time", "")
            # 清 除 旧 字段 （language_listen_speak_level / language_read_write_level 在 liepin 规范 不 存在）
            # EN: Remove old fields (language_listen_speak_level / language_read_write_level do not exist in the liepin spec)
            # JA: 旧フィールドを削除する（language_listen_speak_level / language_read_write_level は liepin の仕様に存在しない）
            ln.pop("language_listen_speak_level", None)
            ln.pop("language_read_write_level", None)

            # ====== 证书 / 等级 解耦 修正（对齐 liepin） ======
            # 从 language_level 中 提取 证书 部分 → 填入 language_certificate；若 level 里 没有 等级 词 且 证书 有 值 → 等级 置 空
            # EN: ====== Decouple certificate / level (aligned with liepin) ======
            #     Extract the certificate part from language_level → put it into language_certificate; if level has no level word and certificate has a value → clear the level
            # JA: ====== 資格とレベルの分離の補正（liepin に合わせる）======
            #     language_level から資格の部分を取り出し → language_certificate に入れる。level にレベルの語がなく資格に値がある → レベルを空にする
            raw_lvl = str(ln.get("language_level") or "").strip()
            raw_cert = str(ln.get("language_certificate") or "").strip()
            # 优先 匹配 完整 短语（长 token 优先）
            # EN: Prefer matching complete phrases (longer tokens first)
            # JA: 完全な語句のマッチを優先する（長いトークンが先）
            explicit_cert_phrases = [
                "大学英语六级", "大学英语四级", "英语六级", "英语四级",
                "专业英语八级", "专业英语四级", "专八", "专四",
                "日语能力一级", "日语能力二级", "日语能力三级",
                "日语一级", "日语二级", "日语三级",
                "JLPT N1", "JLPT N2", "JLPT N3",
                "CET-4", "CET4", "CET-6", "CET6",
                "TEM-4", "TEM4", "TEM-8", "TEM8",
                "TOEIC", "TOEFL", "IELTS", "雅思", "托福",
                "GRE", "GMAT", "BEC",
                "N1", "N2", "N3",
                "一级", "二级", "三级",
            ]
            cert_tokens = tuple(explicit_cert_phrases) + ("CET", "TEM", "JLPT", "能力考", "能力考试")
            # 1) 先 从 raw_lvl 中 拆 证书
            # EN: 1) First split the certificate out of raw_lvl
            # JA: 1) まず raw_lvl から資格を切り出す
            extra_certs: list[str] = []
            remaining_level_words: list[str] = []
            remain = raw_lvl
            matched_any_explicit = False
            for p in explicit_cert_phrases:
                if p in remain:
                    extra_certs.append(p)
                    remain = remain.replace(p, " ")
                    matched_any_explicit = True
            if not matched_any_explicit:
                # 按 token 扫（长 token 优先 去 重）
                # EN: Scan by token (longer tokens first, removing duplicates)
                # JA: トークンごとにスキャンする（長いトークンから先に除去）
                for ct in sorted(set(cert_tokens), key=lambda x: -len(x)):
                    pattern = re.compile(rf"(?<![a-zA-Z]){re.escape(ct)}(?![a-zA-Z])", re.I)
                    if pattern.search(remain):
                        extra_certs.append(ct)
                        remain = pattern.sub(" ", remain)
            # 从 remain 中 只 保留 等级 词（若 没有 等级 词 → remaining_level_words 空 → final_level 空）
            # EN: Keep only level words from remain (if there are none → remaining_level_words is empty → final_level is empty)
            # JA: remain からレベルの語だけを残す（なければ → remaining_level_words が空 → final_level も空）
            level_kw = ("精通", "熟练", "良好", "一般", "流利", "母语", "基础")
            for kw in level_kw:
                if kw in remain:
                    remaining_level_words.append(kw)
                    remain = remain.replace(kw, " ")
            # 若 remaining 还有 其他 有效 中文字（非 等级 词，但 长度 <= 8 且 有 实际 语义）→ 保留 到 level（例如 "母语", "流利" 已 被 上面 过滤 后 若 还 有 "读写精通" → 拿 主要 词）
            # EN: If remaining still has other valid Chinese characters (not level words, but length <= 8 with real meaning) → keep them in level (e.g. after "母语" (native), "流利" (fluent) are filtered above, if "读写精通" (expert reading/writing) remains → take the main word)
            # JA: remaining にまだ他の有効な漢字がある（レベルの語ではないが長さ 8 以下で実際の意味がある）→ level に残す（例：「母语」（母語）、「流利」（流暢）が上で除かれた後に「读写精通」（読み書きに精通）が残れば → 主要な語を取る）
            final_level_parts = list(remaining_level_words)
            if not final_level_parts:
                extra_remain = re.sub(r"[\s:：,，|｜/／()（）【】\[\]、·•\-—_・<《>》]+", " ", remain).strip()
                if extra_remain and len(extra_remain) <= 12 and (
                    any("\u4e00" <= ch <= "\u9fff" for ch in extra_remain)
                    or extra_remain in ("Native", "Fluent", "Mother Tongue", "Proficiency", "Intermediate", "Basic")
                ):
                    final_level_parts.append(extra_remain)

            # 2) 从 raw_cert 中 也 拆 证书（raw_cert 里 若 带 等级 词，等级 也 取 出来）
            # EN: 2) Also split the certificate out of raw_cert (if raw_cert contains level words, take the level out too)
            # JA: 2) raw_cert からも資格を切り出す（raw_cert にレベルの語があればレベルも取り出す）
            remain_cert = raw_cert
            cert_from_rawcert: list[str] = []
            for p in explicit_cert_phrases:
                if p in remain_cert:
                    cert_from_rawcert.append(p)
                    remain_cert = remain_cert.replace(p, " ")
            if not cert_from_rawcert:
                for ct in sorted(set(cert_tokens), key=lambda x: -len(x)):
                    pattern = re.compile(rf"(?<![a-zA-Z]){re.escape(ct)}(?![a-zA-Z])", re.I)
                    if pattern.search(remain_cert):
                        cert_from_rawcert.append(ct)
                        remain_cert = pattern.sub(" ", remain_cert)
            for kw in level_kw:
                if kw in remain_cert and kw not in final_level_parts:
                    final_level_parts.append(kw)

            # 3) 合并 证书 去重 保序（并 将 重复/子串 证书 合并 成 最 具体 的 那个，避免 CET + CET-4 同 时 出现）
            # EN: 3) Merge certificates with dedup, preserving order (merge duplicate/substring certificates into the most specific one, so CET and CET-4 do not both appear)
            # JA: 3) 資格を重複排除して順序を保ちながら統合する（重複・部分文字列の資格は最も具体的なものに統合し、CET と CET-4 が同時に現れないようにする）
            all_certs: list[str] = []
            for c in extra_certs + cert_from_rawcert:
                if not c:
                    continue
                # 若 新 证书 是 现有 证书 的 子串 → 不 加（CET 是 CET-4 子串，保留 更 具体 的）
                # EN: If the new certificate is a substring of an existing one → do not add it (CET is a substring of CET-4; keep the more specific one)
                # JA: 新しい資格が既存の資格の部分文字列 → 追加しない（CET は CET-4 の部分文字列なので、より具体的な方を残す）
                dup_covered = False
                for existing in list(all_certs):
                    if c != existing and (c in existing):
                        dup_covered = True
                        break
                if dup_covered:
                    continue
                # 若 新 证书 比 现有 的 更 具体（现有 是 新 的 子串）→ 用 新 的 覆盖 旧 的
                # EN: If the new certificate is more specific than an existing one (the existing one is a substring of the new one) → replace the old with the new
                # JA: 新しい資格の方が既存より具体的（既存が新しい方の部分文字列）→ 新しい方で古い方を置き換える
                refined_new = False
                for idx2, existing in enumerate(list(all_certs)):
                    if existing != c and (existing in c):
                        all_certs[idx2] = c
                        refined_new = True
                        break
                if refined_new:
                    continue
                if c not in all_certs:
                    all_certs.append(c)
            final_cert = " ".join(all_certs).strip()

            # 4) 合并 等级（第 一个 等级 词 为 主；若 没有 词 而 有 证书 → 等级 置 空；若 既 没 等级 也 没 证书 → 空）
            # EN: 4) Merge levels (the first level word is primary; if there is no word but a certificate → clear the level; if neither level nor certificate → empty)
            # JA: 4) レベルを統合する（最初のレベルの語を主とする。語がなく資格がある → レベルを空にする。レベルも資格もない → 空）
            final_level = ""
            if final_level_parts:
                final_level = final_level_parts[0]
                if final_level in LANGUAGE_LEVEL_MAP:
                    final_level = LANGUAGE_LEVEL_MAP[final_level]

            # 5) 若 language_level 里 的 值 命中 LANGUAGE_LEVEL_MAP（CET-4 等 证书 名 当成 等级 写 进来 的），抽 到 certificate
            # EN: 5) If a value in language_level hits LANGUAGE_LEVEL_MAP (a certificate name like CET-4 written in as a level), extract it to certificate
            # JA: 5) language_level の値が LANGUAGE_LEVEL_MAP にヒットする（CET-4 などの資格名がレベルとして書かれていた）場合は、certificate に抽出する
            if not final_cert and raw_lvl and raw_lvl in LANGUAGE_LEVEL_MAP:
                mapped = LANGUAGE_LEVEL_MAP[raw_lvl]
                if any(kw in mapped for kw in ("四级", "六级", "八级", "能力一级", "能力二级", "能力三级", "雅思", "托福", "BEC", "GRE", "GMAT")):
                    final_cert = mapped
                    if not final_level:
                        final_level = ""

            ln["language_level"] = final_level
            ln["language_certificate"] = final_cert

            merged_langs.append(ln)
        # 纯文本 优先
        # EN: Plain text first
        # JA: プレーンテキストを優先
        for it in txt_langs or []:
            _push_lang(dict(it))
        # parser DOM 解析 兜底（补 纯文本 没 识别 到 的 语言）
        # EN: Parser DOM parsing as fallback (adds languages the plain text did not recognise)
        # JA: パーサーの DOM 解析を最終手段とする（プレーンテキストで認識できなかった言語を補う）
        for it in list(r.get("language_list") or []):
            _push_lang(dict(it) if isinstance(it, dict) else {})
        r["language_list"] = merged_langs

        # skills_list：先去平台名/Word宏残留/URLs → 再个人素质关键词过滤移至 base_info.pr
        # EN: skills_list: first remove platform names / Word macro leftovers / URLs → then move personal-quality keywords via filtering to base_info.pr
        # JA: skills_list：まずプラットフォーム名・Word マクロの残骸・URL を除き → 次に個人の資質を表すキーワードをフィルタリングして base_info.pr に移す
        r.setdefault("skills_list", [])
        cleaned_skills: list[dict[str, Any]] = []
        for s in r.get("skills_list", []):
            sname = (s.get("skill_name") or s.get("name") or "").strip()
            if not sname:
                continue
            if "智联招聘" in sname or "前程无忧" in sname:
                continue
            if re.search(r"INCLUDEPICTURE|HYPERLINK|https?://|www\.", sname):
                continue
            cleaned_skills.append(s)
        r["skills_list"] = _filter_skills_extract_pr(cleaned_skills, r["base_info"])

        # training_list：parser 已有 + 纯文本解析 raw_trainings + 独立 parse_training_from_raw_text(section 隔离！) + 智联在校实践解析合并（去重/重编号）
        # EN: training_list: merge the parser's existing ones + plain-text parsed raw_trainings + the separate parse_training_from_raw_text (section-isolated!) + Zhaopin campus-practice parsing (dedup / renumber)
        # JA: training_list：パーサーの既存分 + プレーンテキスト解析の raw_trainings + 独立した parse_training_from_raw_text（セクション分離！）+ Zhaopin の在学中の実践の解析を統合する（重複排除・番号の振り直し）
        base_training = r.get("training_list") or []
        merged_trainings: list[dict[str, Any]] = list(base_training)
        if raw_trainings:
            merged_trainings.extend(list(raw_trainings))
        # —— 关键修复：只有当 train_sec_text 真正非空时才调 parse_training_from_raw_text！
        #    禁止回退到 全文 text（否则 work/project/education 会被误识别成培训，产生垃圾数据）
        # EN: —— Key fix: only call parse_training_from_raw_text when train_sec_text is really non-empty!
        #        Falling back to the full text is forbidden (otherwise work/project/education would be misidentified as training, producing junk data)
        # JA: —— 重要な修正：train_sec_text が本当に空でない場合だけ parse_training_from_raw_text を呼ぶ！
        #        全文の text へのフォールバックは禁止（さもないと work／project／education が研修と誤認され、ゴミのデータができる）
        if train_sec_text and train_sec_text.strip():
            extra_trainings = parse_training_from_raw_text(train_sec_text)
            if extra_trainings:
                # 明确“日期范围 + 培训名称 + 机构/地点/描述”块优先级最高，
                # 避免 DOM 兜底把求职意向、行业、培训地点标签误塞成培训名称。
                # EN: Explicit "date range + training name + provider/place/description" blocks have the highest priority,
                #     so the DOM fallback does not stuff job-preference, industry or training-place labels into the training name.
                # JA: 明確な「期間 + 研修名 + 機関・場所・説明」のブロックを最優先し、
                #     DOM の最終手段が希望条件・業界・研修場所のラベルを研修名に誤って詰め込まないようにする。
                merged_trainings = list(extra_trainings)
            zhilian_practices = _parse_zhilian_practice_simple(train_sec_text)
        else:
            zhilian_practices = []
        if zhilian_practices:
            merged_trainings.extend(list(zhilian_practices))
        _seen: set[tuple[str, str]] = set()
        dedup_trainings: list[dict[str, Any]] = []
        for t in merged_trainings:
            org = re.sub(r"^[\s:：\d.]+", "", str(t.get("organization_name") or "")).strip()
            t_name = re.sub(r"^[\s:：\d.]+", "", str(t.get("training_name") or "")).strip()
            t_name = re.sub(r"^(?:培训课程|课程|培训机构|机构)\s*[:：]?\s*", "", t_name).strip()
            if t_name in {"培训地点", "培训地点：", "培训描述", "培训描述：", "描述", "描述："}:
                continue
            
            main_name = (org or t_name)[:15]
            if not main_name:
                continue
            
            start_y = re.findall(r"\d{4}", str(t.get("start_ym") or ""))
            s_year = start_y[0] if start_y else ""
            
            key = (main_name, s_year)
            if key in _seen:
                continue
            _seen.add(key)
            dedup_trainings.append(t)
        for idx, t in enumerate(dedup_trainings):
            t["sequence_no"] = idx + 1
        r["training_list"] = _clean_training_list(dedup_trainings)

        # project_list：先 尝试 纯 文本 parse_projects_from_raw_text（section 隔离！proj_sec_text），再 与 DOM parser 结果 合并
        # EN: project_list: first try the plain-text parse_projects_from_raw_text (section-isolated! proj_sec_text), then merge with the DOM parser results
        # JA: project_list：まずプレーンテキストの parse_projects_from_raw_text（セクション分離！proj_sec_text）を試し、その後 DOM パーサーの結果と統合する
        r.setdefault("project_list", [])
        raw_projects: list[dict[str, Any]] = []
        try:
            raw_projects = parse_projects_from_raw_text(proj_sec_text if proj_sec_text else text) or []
        except Exception:
            raw_projects = []
        # 把 raw_projects 格式 转换 成 标准 schema 字段 名
        # EN: Convert the raw_projects format into standard schema field names
        # JA: raw_projects の形式を標準スキーマのフィールド名に変換する
        std_raw: list[dict[str, Any]] = []
        for p in raw_projects:
            std_raw.append({
                "project_name": p.get("project_name") or "",
                "project_role": p.get("project_role") or "",
                "project_start": p.get("start_ym") or "",
                "project_end": p.get("end_ym") or "",
                "project_description": p.get("project_description") or "",
                "project_responsibilities": p.get("project_responsibilities") or "",
                "company_name": p.get("company_name") or "",
            })
        dom_projects = r.get("project_list", []) or []
        # 合并 策略：如果 纯 文本 解析 有 结果，且 数量 >= DOM 结果 数量，以 纯 文本 为准
        # EN: Merge strategy: if plain-text parsing has results and their count >= the DOM result count, the plain text takes precedence
        # JA: 統合の方針：プレーンテキストの解析に結果があり、その件数が DOM の結果の件数以上なら、プレーンテキストを正とする
        if len(std_raw) >= len(dom_projects) and len(std_raw) > 0:
            merged = std_raw
        else:
            merged = list(dom_projects)
            for rp in std_raw:
                # 如果 DOM 没 有，追加 raw
                # EN: If DOM has none, append raw
                # JA: DOM になければ raw を追加する
                exist = any(
                    str(x.get("project_name") or "")[:30] == str(rp.get("project_name") or "")[:30]
                    and str(x.get("project_start") or "")[:7] == str(rp.get("project_start") or "")[:7]
                    for x in merged
                )
                if not exist:
                    merged.append(rp)
        if transferred_projects:
            for tp in transferred_projects:
                exist = any(
                    str(x.get("project_name") or "")[:30] == str(tp.get("project_name") or "")[:30]
                    for x in merged
                )
                if not exist:
                    merged.append(tp)
        r["project_list"] = _fix_project_training_name(merged)
        r["project_list"] = _separate_project_desc_resp(r["project_list"])
        valid_projects = []
        for p in r.get("project_list", []):
            pname = (p.get("project_name") or "").strip()
            pname = re.sub(r"[\s|｜]+$", "", pname).strip()
            p["project_name"] = pname
            # 社团、协会、联谊、校内任职等不属于目标项目数据，无论有没有长描述都舍弃。
            # “某协会”可以是项目所属单位，不能因此删除真实赛事/推广项目；
            # 只过滤项目名称或角色本身明确是校园社团任职的数据。
            # EN: Clubs, associations, social groups, campus posts etc. are not target project data; discard them whether or not they have long descriptions.
            #     "某协会" (an association) can be the organisation a project belongs to, so real events/promotion projects must not be deleted for that;
            #     only filter data whose project name or role itself is explicitly a campus club post.
            # JA: サークル・協会・親睦団体・学内の役職などは対象のプロジェクトデータではないため、長い説明があってもなくても捨てる。
            #     「某协会」（〜協会）はプロジェクトの所属組織になり得るので、それを理由に本当の大会・販促プロジェクトを削除してはならない。
            #     プロジェクト名や役割そのものが明らかに学内サークルの役職であるデータだけを除外する。
            project_identity = "|".join(str(p.get(k) or "") for k in ("project_name", "project_role"))
            if any(tok in project_identity for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS):
                continue
            p["project_description"] = _strip_non_business_resume_details(p.get("project_description"))
            p["project_responsibilities"] = _strip_non_business_resume_details(p.get("project_responsibilities"))
            if pname in ("体育老师", "网球教练", "健身顾问", "教练", "咨询顾问", "项目经理", "企划专员", "未工作"):
                continue
            if any(token in pname for token in ("动植物学实习", "课程实习", "认识实习", "教学实习", "校内实习")):
                continue
            if any(k in pname for k in ("大学", "学院", "学校", "本科", "大专", "硕士", "博士", "高中")) and not any(kw in pname for kw in ("项目", "工程", "系统", "平台", "课题", "研发", "设计", "交流会", "比赛", "大赛", "论坛")):
                continue
            if any(k in pname for k in ("在校实践", "获奖", "一等奖", "二等奖", "三等奖")):
                continue
            if pname:
                valid_projects.append(p)
        # 最后用独立 DOM 项目章节中的“明确日期 + 项目名”做一次无损补集。
        # 这可避免旧 DOM parser 只保留后半段、或把所属协会误当校园任职后删除前半段。
        # EN: Finally do a lossless complement using "explicit date + project name" from the separate DOM project section.
        #     This avoids the old DOM parser keeping only the second half, or deleting the first half by mistaking the owning association for a campus post.
        # JA: 最後に、独立した DOM のプロジェクトの章にある「明確な日付 + プロジェクト名」で、失うことのない補完を 1 回行う。
        #     これにより、旧 DOM パーサーが後半しか残さなかったり、所属協会を学内の役職と誤認して前半を削除したりするのを防ぐ。
        existing_project_names = {
            re.sub(r"\s+", "", str(p.get("project_name") or "")) for p in valid_projects
        }
        for p in std_raw:
            pname = str(p.get("project_name") or "").strip()
            norm_name = re.sub(r"\s+", "", pname)
            if (
                not pname
                or len(pname) > 100
                or norm_name in existing_project_names
                or any(tok in pname for tok in _NON_BUSINESS_ROLE_TOKENS)
                or re.match(r"^(?:负责|参与|协助|组织|担任|工作内容)", pname)
            ):
                continue
            valid_projects.append(p)
            existing_project_names.add(norm_name)
        r["project_list"] = valid_projects

        r.setdefault("communication_list", [])
        r["base_info"]["platform_from"] = PLAT_DEFAULT
        r["base_info"]["full_name"] = correct_fn
        r["base_info"]["name"] = correct_fn  # 同步 name 字段（消费端常用，防止后续 r0_base 覆盖 structured_data 后丢失）
        # EN: Sync the name field (commonly used by consumers; prevents it being lost after r0_base later overwrites structured_data)
        # JA: name フィールドを同期する（利用側でよく使われる。後で r0_base が structured_data を上書きした後に失われるのを防ぐ）
        if structured_data.get("base_info", {}).get("pr") and not r["base_info"].get("pr"):
            r["base_info"]["pr"] = structured_data["base_info"]["pr"]

    # 最终语义补集：在所有旧 parser 后处理完成后，再从已隔离的 DOM 章节补一次。
    # 放在这里可避免旧平台适配器随后覆盖前面已经恢复的项目/工作条目。
    # EN: Final semantic complement: after all old parser post-processing is done, complement once more from the isolated DOM sections.
    #     Putting it here avoids old platform adapters later overwriting project/work entries already recovered earlier.
    # JA: 最後の意味的な補完：旧パーサーの後処理がすべて終わった後、分離済みの DOM の章からもう一度補う。
    #     ここに置くことで、前に復元したプロジェクト・職歴の項目を後から旧プラットフォームのアダプターが上書きするのを防ぐ。
    if resumes:
        primary = resumes[0]
        if proj_sec_text:
            existing_names = {
                re.sub(r"\s+", "", str(p.get("project_name") or ""))
                for p in primary.get("project_list") or []
            }
            for raw in parse_projects_from_raw_text(proj_sec_text):
                pname = str(raw.get("project_name") or "").strip()
                norm_name = re.sub(r"\s+", "", pname)
                if not pname or len(pname) > 100 or norm_name in existing_names:
                    continue
                primary.setdefault("project_list", []).append({
                    "project_name": pname,
                    "project_role": raw.get("project_role") or "",
                    "project_start": raw.get("start_ym") or "",
                    "project_end": raw.get("end_ym") or "",
                    "project_description": _strip_non_business_resume_details(raw.get("project_description")),
                    "project_responsibilities": _strip_non_business_resume_details(raw.get("project_responsibilities")),
                    "company_name": raw.get("company_name") or "",
                })
                existing_names.add(norm_name)

        # 工作章节同样只补高置信组织名；描述句、职位、行业分类一律不作为公司名。
        # EN: The work section likewise only complements high-confidence organisation names; descriptive sentences, positions and industry categories are never used as company names.
        # JA: 職歴の章でも同様に信頼度の高い組織名だけを補い、説明文・職位・業界の分類は決して会社名にしない。
        existing_companies = {
            re.sub(r"\s+", "", str(w.get("company_name") or ""))
            for w in primary.get("work_experiences") or []
        }
        for raw in semantic_raw_works or raw_works or []:
            company = _clean_company_name(str(raw.get("company_name") or ""))
            company = re.sub(r"\s*[（(]\s*\d+\s*(?:年|个?月).*?[）)]?\s*$", "", company).strip()
            norm_company = re.sub(r"\s+", "", company)
            if (
                not company or norm_company in existing_companies or len(company) > 60
                or re.match(r"^(?:负责|参与|协助|组织|管理|在该|通过|汇报对象|搜索同事)", company)
                or not re.search(r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院|商社|公司)$", company)
            ):
                continue
            extra = copy.deepcopy(raw)
            extra["company_name"] = company
            primary.setdefault("work_experiences", []).append(extra)
            existing_companies.add(norm_company)
        primary["work_experiences"] = _postprocess_work_attrs(primary.get("work_experiences") or [])

        # 培训机构被旧解析器误塞进 education_list 时删除（例如“华浦教育”）。
        # EN: Delete training providers stuffed into education_list by the old parser (e.g. "华浦教育").
        # JA: 旧パーサーが education_list に誤って入れた研修機関（例：「华浦教育」）を削除する。
        training_orgs = {
            re.sub(r"\s+", "", str(t.get("organization_name") or ""))
            for t in primary.get("training_list") or [] if t.get("organization_name")
        }
        if training_orgs:
            primary["education_list"] = [
                e for e in primary.get("education_list") or []
                if not (
                    re.sub(r"\s+", "", str(e.get("school_name") or "")) in training_orgs
                    and not re.search(r"大学|学院|学校|研究院|科学院|中学|高中", str(e.get("school_name") or ""))
                )
            ]

    structured_data["resumes"] = resumes

    # 基于 resumes[0] 补齐顶层外部快照
    # EN: Complete the top-level external snapshots based on resumes[0]
    # JA: resumes[0] に基づいてトップレベルの外部スナップショットを補完する
    r0 = resumes[0]
    r0_base = r0.get("base_info") or {}
    structured_data["base_info"] = dict(r0_base)
    if r0_base.get("pr"):
        structured_data["base_info"]["pr"] = r0_base["pr"]

    structured_data["expected_info"] = copy.deepcopy(r0.get("expected_info") or {})

    structured_data.setdefault("certificate_list", [])
    structured_data.setdefault("language_list", [])
    structured_data.setdefault("skills_list", [])
    structured_data.setdefault("training_list", [])
    structured_data.setdefault("project_list", [])
    structured_data.setdefault("communication_list", [])

    # education_info：严格取 education_list[0]（education_list 已在 normalize_education_list 中按 rank 降序 → start_ym 降序排过），
    # 100% 直接拷贝 education_list[0] 的 7 个标准字段，绝不做任何额外覆盖修改 → 保证与 list[0] 完全一致
    # EN: education_info: strictly take education_list[0] (education_list is already sorted in normalize_education_list by rank descending → start_ym descending),
    #     copy the 7 standard fields of education_list[0] 100% directly, never doing any extra overriding modification → guaranteed identical to list[0]
    # JA: education_info：厳密に education_list[0] を取る（education_list は normalize_education_list で rank の降順 → start_ym の降順に並べ替え済み）。
    #     education_list[0] の標準の 7 フィールドを 100% そのままコピーし、追加の上書きや変更は一切しない → list[0] と完全に一致することを保証する
    r0_edus = r0.get("education_list") or []
    if r0_edus:
        top_edu = r0_edus[0]  # 严格取第0条（已排序）
        # EN: Strictly take entry 0 (already sorted)
        # JA: 厳密に 0 番目（並べ替え済み）を取る
        # —— 严格白名单7字段100%拷贝，不做任何二次处理/修改（保证 100% = list[0]）
        # EN: —— Copy the strict 7-field whitelist 100%, with no secondary processing/modification (guaranteeing 100% = list[0])
        # JA: —— 厳格な 7 フィールドのホワイトリストを 100% コピーし、2 次処理や変更は一切しない（100% = list[0] を保証）
        structured_data["education_info"] = {
            "school_name": str(top_edu.get("school_name", "") or ""),
            "school_major_name": str(top_edu.get("school_major_name", "") or ""),
            "school_degree_type": str(top_edu.get("school_degree_type", "") or ""),
            "school_degree_rank": str(top_edu.get("school_degree_rank", "") or ""),
            "school_education_type": str(top_edu.get("school_education_type", "") or ""),
            "school_start_ym": str(top_edu.get("school_start_ym", "") or ""),
            "school_end_ym": str(top_edu.get("school_end_ym", "") or ""),
        }
    else:
        structured_data["education_info"] = _build_empty_education_info()

    # current_info：严格取 work_experiences[0]（已在 _postprocess_work_attrs 中清理排序），100% 直接拷贝 list[0] 的 15 个字段，绝不做二次覆盖逻辑
    # EN: current_info: strictly take work_experiences[0] (already cleaned and sorted in _postprocess_work_attrs), copy its 15 fields from list[0] 100% directly, never with secondary override logic
    # JA: current_info：厳密に work_experiences[0] を取る（_postprocess_work_attrs で整理・並べ替え済み）。list[0] の 15 フィールドを 100% そのままコピーし、2 次的な上書きのロジックは一切使わない
    r0_works = r0.get("work_experiences") or []
    if r0_works:
        w = r0_works[0]  # 严格取第0条
        # EN: Strictly take entry 0
        # JA: 厳密に 0 番目を取る
        # —— 严格白名单15字段100%拷贝，与 list[0] 完全一致
        # EN: —— Copy the strict 15-field whitelist 100%, identical to list[0]
        # JA: —— 厳格な 15 フィールドのホワイトリストを 100% コピーし、list[0] と完全に一致させる
        structured_data["current_info"] = {
            "company_name": str(w.get("company_name", "") or ""),
            "company_employees": str(w.get("company_employees", "") or ""),
            "company_industry": str(w.get("company_industry", "") or ""),
            "position": str(w.get("position", "") or ""),
            "position_type": str(w.get("position_type", "") or ""),
            "position_salary": str(w.get("position_salary", "") or ""),
            "position_dept": str(w.get("position_dept", "") or w.get("department") or ""),
            "position_report_to": str(w.get("position_report_to", "") or ""),
            "position_subordinate": str(w.get("position_subordinate", "") or ""),
            "employment_type": str(w.get("employment_type", "全职") or "全职"),
            "annual_salary_min": str(w.get("annual_salary_min", "") or ""),
            "annual_salary_max": str(w.get("annual_salary_max", "") or ""),
            "status": str(w.get("status", "") or ""),
            "position_start": str(w.get("position_start", "") or ""),
            "position_resigned": str(w.get("position_resigned", "") or ""),
        }
    else:
        structured_data["current_info"] = _build_empty_current_info()

    for r in structured_data.get("resumes") or []:
        for w in (r.get("work_experiences") or []):
            w.setdefault("position_achievements", "")
            if w.get("company_name"):
                company = _clean_company_name(w["company_name"])
                if re.search(r"(?:工作经历|工作经验)", company):
                    tail = re.split(r"(?:工作经历|工作经验)", company)[-1].strip()
                    if tail:
                        company = tail
                if company in {"制药/生物工程", "机械/设备/重工", "医疗设备/器械", "仪器仪表/工业自动化", "网络游戏"}:
                    company = ""
                w["company_name"] = company

    # 子对象 raw_text 清理 + 顶层黑名单字段只保留在 resumes 内
    # EN: Clean raw_text in sub-objects + keep top-level blacklisted fields only inside resumes
    # JA: サブオブジェクトの raw_text を除去 + トップレベルのブラックリストのフィールドは resumes の中だけに残す
    def _strip_inner_raw_text(obj):
        if isinstance(obj, dict):
            obj.pop("raw_text", None)
            for v in obj.values():
                _strip_inner_raw_text(v)
        elif isinstance(obj, list):
            for item in obj:
                _strip_inner_raw_text(item)
    _strip_inner_raw_text(structured_data)

    _top_level_blacklist = {"work_experiences", "education_list", "project_experiences",
                            "communication_assessment", "training_experiences",
                            "certificate_list", "language_list", "skills_list",
                            "training_list", "project_list", "communication_list",
                            "work_list", "skill_list"}
    # 顶层字段黑名单：工作/教育/培训/技能等详细子对象必须放在 resumes[*] 内，structured_data 顶层只放
    # base_info / expected_info / current_info / education_info / resumes / raw_text 等汇总级字段
    # EN: Top-level field blacklist: detailed sub-objects such as work/education/training/skills must be inside resumes[*]; the top level of structured_data holds only
    #     summary-level fields such as base_info / expected_info / current_info / education_info / resumes / raw_text
    # JA: トップレベルのフィールドのブラックリスト：職歴・学歴・研修・スキルなどの詳細なサブオブジェクトは resumes[*] の中に置き、structured_data のトップレベルには
    #     base_info / expected_info / current_info / education_info / resumes / raw_text などの集約レベルのフィールドだけを置く
    structured_data = {k: v for k, v in structured_data.items() if k not in _top_level_blacklist}

    # ================================================================
    # ★ 王吉庆/唐洁 最后一轮强清洗（base_info + current_info）
    # ================================================================
    # EN: ================================================================
    #     ★Final round of strong cleaning for past cases (base_info + current_info)
    #     ================================================================
    # JA: ================================================================
    #     ★過去の事例向けの最後の強力なクレンジング（base_info + current_info）
    #     ================================================================
    _KVBAD_KEYWORDS = ("地区", "所在地", "住址", "地址", "学校", "公司", "职位", "部门", "单位", "时间", "日期",
                       "城市", "籍贯", "户口", "户籍", "专业", "学历", "学校", "婚姻", "政治", "身高", "体重",
                       "照片", "邮箱", "电话", "手机", "性别", "民族", "年龄", "生日", "出生")
    def _looks_like_kv_key_only(val: str) -> bool:
        """判断字符串是不是纯 KV key（如 "所  在 地区"、"户 籍 所在" 这种空格分隔的 key，但没有真正 value）

        EN: Decide whether a string is a pure KV key (like space-separated keys "所  在 地区", "户 籍 所在" (located region, hukou location) without a real value)

        JA: 文字列が純粋な KV のキーか（「所  在 地区」「户 籍 所在」（所在地域・戸籍所在地）のように空白で区切られたキーで、本当の値がないもの）を判定する
        """
        s = str(val or "").strip()
        if not s: return False
        # —— P1A新增：带冒号结尾的KV key格式（户口:/所在地：/籍贯：/婚姻状况: 等），必须直接命中 ——
        # EN: —— New in P1A: KV key formats ending with a colon (户口:/所在地：/籍贯：/婚姻状况: — hukou/location/native place/marital status) must be hit directly ——
        # JA: —— P1A の追加：コロンで終わる KV のキーの形式（户口:／所在地：／籍贯：／婚姻状况:）には直接ヒットさせる ——
        s_no_colon = s.rstrip("：:").strip()
        if s_no_colon != s:
            core = re.sub(r"[\s　]+", "", s_no_colon)
            # 去掉关键词后剩余 <= 2 字（含单字空）就判定为纯KV key冒号
            # EN: If <= 2 characters remain after removing the keywords (including a single character or empty), judge it a pure KV key with colon
            # JA: キーワードを除いた残りが 2 文字以下（1 文字や空を含む）なら、コロン付きの純粋な KV のキーと判定する
            remain = core
            for kw in sorted(_KVBAD_KEYWORDS, key=lambda x: -len(x)):
                remain = remain.replace(kw, "")
            if len(remain) <= 2:
                return True
        # 空格/全角空格剥离后太短
        # EN: Too short after stripping spaces/full-width spaces
        # JA: 空白・全角空白を除くと短すぎる
        core = re.sub(r"[\s　]+", "", s)
        if len(core) <= 1: return True
        # 核心全字都是「地区/所在/公司」这类 KV key 常用词组成（无真实 value 内容）
        # EN: All core characters consist of words commonly used in KV keys like "地区/所在/公司" (region/located/company) (no real value content)
        # JA: 中核の文字がすべて「地区／所在／公司」のような KV のキーによく使う語でできている（実際の値の内容がない）
        if len(core) <= 10 and all(
            any(core[i:].startswith(k) for k in ("所在","地区","城市","学校","公司","职位","部门","单位","户口","户籍","籍贯","住址","地址","婚姻","政治","身高","体重","照片","手机","电话","邮箱","性别","民族","年龄","生日","出生","专业","学历","日期","时间"))
            for i in range(len(core)) if core[i] != "的"
        ):
            # 更严格：去掉所有 KV key 关键词后剩余 <= 1字
            # EN: Stricter: <= 1 character remains after removing all KV key keywords
            # JA: さらに厳格：KV のキーのキーワードをすべて除いた残りが 1 文字以下
            remain = core
            for kw in sorted(_KVBAD_KEYWORDS, key=lambda x: -len(x)):
                remain = remain.replace(kw, "")
            if len(remain) <= 1:
                return True
        return False
    # 简历标准section标题词表（与_postprocess_work_attrs保持一致）
    # EN: List of standard résumé section heading words (kept consistent with _postprocess_work_attrs)
    # JA: 履歴書の標準的なセクション見出しの語の一覧（_postprocess_work_attrs と一致させる）
    _SEC_TITLES_SET = set("""
实验经历 实习经历 培训经历 项目经历 教育经历 教育背景 自我评价 自我鉴定 求职意向
语言能力 专业技能 技术技能 兴趣爱好 校园经历 在校经历 社会实践 科研经历 获奖经历
荣誉证书 资格证书 家庭状况 个人简介 个人说明 个人能力 个人评价 外语能力 英语能力
备注 附言 作品集 所获证书 相关证书 个人信息 基本信息 联系信息 期望职位 期望薪资
期望城市 期望工作 志愿者经历 义工经历 创业经历 当兵经历 服役经历 专利成果 论文发表
获奖情况 证书情况 技能特长 计算机水平 IT技能 办公技能 驾照 在校情况
工作与经历 工作时间 工作范围 工作概况 工作内容 工作简介 工作说明 工作经验 教育概况
基础信息 自我介绍 其它技能 外语培训师 实践经验 实践经历 实习工作经验 实习经验
培训经验 培训简介 项目概况 项目简介 项目工作内容 薪酬状况 人事工作 附言 备注 说明 简介 概况 内容
""".strip().split())
    _PURE_SECTION_NAME_RE = re.compile(
        r"^(?:个人|工作|项目|教育|培训|实习|科研|社会|校园|获奖|荣誉|专业|技术|语言|外语|英语|计算机|办公|求职|期望|自我|联系|家庭|基本|相关|所获|志愿者|义工|创业|当兵|服役|专利|论文)"
        r"(?:经历|经验|背景|概况|技能|特长|能力|信息|评价|鉴定|意向|介绍|简介|说明|内容|地址|地点|状况|情况|备注|附言|成果|发表|证书|作品|职位|薪资|城市|工作|学业|学历|婚姻|政治|身高|体重|照片|驾照)$"
    )
    _SEC_COLON_RE = re.compile(
        r"^[\s　]*(?:个人[\u4e00-\u9fff,，\s、]{0,12}|工作[\u4e00-\u9fff]{0,4}|项目[\u4e00-\u9fff]{0,4}|教育[\u4e00-\u9fff]{0,4}|培训[\u4e00-\u9fff]{0,4}"
        r"|实习[\u4e00-\u9fff]{0,4}|科研[\u4e00-\u9fff]{0,4}|获奖[\u4e00-\u9fff]{0,4}|专业[\u4e00-\u9fff]{0,4}|语言[\u4e00-\u9fff]{0,4}"
        r"|外语[\u4e00-\u9fff]{0,4}|英语[\u4e00-\u9fff]{0,4}|技术[\u4e00-\u9fff]{0,4}|[\u4e00-\u9fff]{1,4}内容|[\u4e00-\u9fff]{1,4}职责|[\u4e00-\u9fff]{1,4}介绍|[\u4e00-\u9fff]{1,4}概况|[\u4e00-\u9fff]{1,4}薪酬|[\u4e00-\u9fff]{1,4}福利|[\u4e00-\u9fff]{1,4}时间|[\u4e00-\u9fff]{1,4}地点|[\u4e00-\u9fff]{1,4}范围|[\u4e00-\u9fff]{1,4}流程|[\u4e00-\u9fff]{1,4}状况|[\u4e00-\u9fff]{1,4}信息|[\u4e00-\u9fff]{1,4}简介|[\u4e00-\u9fff]{1,4}能力|[\u4e00-\u9fff]{1,4}说明|[\u4e00-\u9fff]{1,4}经历|[\u4e00-\u9fff]{1,4}经验|[\u4e00-\u9fff]{1,4}背景|[\u4e00-\u9fff]{1,4}技能|[\u4e00-\u9fff]{1,4}评价|[\u4e00-\u9fff]{1,4}鉴定|[\u4e00-\u9fff]{1,4}意向|[\u4e00-\u9fff]{1,4}备注|[\u4e00-\u9fff]{1,4}附言)"
        r"\s*[:：]\s*$"
    )
    def _looks_sec_title(val: str) -> bool:
        if not val: return False
        s = str(val).strip()
        if s in _SEC_TITLES_SET: return True
        if (2 <= len(s) <= 12 and _PURE_SECTION_NAME_RE.match(s)): return True
        if _SEC_COLON_RE.match(s): return True
        if _SEC_COLON_RE.match(s.rstrip("：:") + "："): return True
        return False
    # 1) base_info 清理（王吉庆 household_registration = "所  在 地区" 这种纯key）
    # EN: 1) base_info cleanup (a past case: household_registration = "所  在 地区" (located region), a pure key)
    # JA: 1) base_info の整理（過去の事例：household_registration = "所  在 地区"（所在地域）のような純粋なキー）
    _bi = structured_data.get("base_info") or {}
    for f in ("city", "residence_city", "hukou_city", "household_registration", "native_place",
              "marital_status", "political_status", "address", "nationality", "origin_place"):
        v = str(_bi.get(f) or "").strip()
        if not v: continue
        if _looks_like_kv_key_only(v):
            _bi[f] = ""
            continue
        if _looks_sec_title(v):
            _bi[f] = ""
    structured_data["base_info"] = _bi

    # 1.5) P1C先把 resumes[0].work_experiences[*] 的 position_dept/company_name/position 再清一遍 section标题（张嘉晖：dept=其它技能）
    # EN: 1.5) P1C: first clean section headings once more from position_dept/company_name/position of resumes[0].work_experiences[*] (a past case: dept=其它技能 (other skills))
    # JA: 1.5) P1C：まず resumes[0].work_experiences[*] の position_dept／company_name／position からセクション見出しをもう一度除く（過去の事例：dept=其它技能（その他のスキル））
    if structured_data.get("resumes"):
        r00_x = structured_data["resumes"][0]
        for w in (r00_x.get("work_experiences") or [])[:3]:  # 只清前3段（常用）
        # EN: Only clean the first 3 entries (the common case)
        # JA: 最初の 3 件だけ整理する（よくあるケース）
            changed_w = False
            for fld in ("position_dept", "department", "company_name", "position"):
                v = str(w.get(fld) or "").strip()
                if not v: continue
                if _looks_sec_title(v) or _looks_like_kv_key_only(v):
                    w[fld] = ""
                    changed_w = True
            # 职责也按之前一样切一次section尾（resumes里的版本再清一次残留）
            # EN: Also cut section tails from duties once as before (clean leftovers in the resumes version once more)
            # JA: 職務も以前と同じくセクションの末尾を 1 回切る（resumes 内の版の残りをもう一度整理）
            resp = str(w.get("position_responsibilities") or "").strip()
            if resp:
                lines = resp.splitlines()
                cut = len(lines)
                for li in range(len(lines)):
                    s = lines[li].strip()
                    if not s: continue
                    if s in _SEC_TITLES_SET or (2 <= len(s) <= 15 and _PURE_SECTION_NAME_RE.match(s)):
                        cut = min(cut, li)
                        break
                if cut < len(lines):
                    w["position_responsibilities"] = "\n".join(lines[:cut]).strip()
                    changed_w = True

    # 所有宽松清洗完成后，再覆盖一次高置信日期块结果，防止后续旧规则把
    # 短品牌公司名与行业/性质字段互换。
    # EN: After all loose cleaning is done, overwrite once more with the high-confidence date-block results, to prevent later old rules from
    #     swapping short brand company names with industry/type fields.
    # JA: 緩いクレンジングがすべて終わった後、高信頼の日付ブロックの結果でもう一度上書きし、後続の旧ルールが
    #     短いブランド名の会社名と業界・性質のフィールドを入れ替えるのを防ぐ。
    if trusted_explicit_works and structured_data.get("resumes"):
        structured_data["resumes"][0]["work_experiences"] = copy.deepcopy(trusted_explicit_works)

    discard_semantically_invalid_rows(structured_data)

    # 2) current_info 清理：先清 section标题，再强制 100% = r0.work[0]（严格同步！避免张嘉晖/刘伟/唐洁的不一致）
    # EN: 2) current_info cleanup: first clean section headings, then force 100% = r0.work[0] (strict sync! avoids inconsistencies seen in past cases)
    # JA: 2) current_info の整理：まずセクション見出しを除き、次に 100% = r0.work[0] を強制する（厳格な同期！過去の事例のような不一致を防ぐ）
    r00 = (structured_data.get("resumes") or [{}])[0]
    w0 = (r00.get("work_experiences") or [{}])[0] if (r00.get("work_experiences") or []) else {}
    _ci = structured_data.get("current_info") or {}
    # 2A) 先清 _ci 自身的 section标题（如果有的话）
    # EN: 2A) First clean section headings in _ci itself (if any)
    # JA: 2A) まず _ci 自身のセクション見出しを除く（あれば）
    _needs_clean = False
    for fld in ("company_name", "position", "position_dept"):
        v = str(_ci.get(fld) or "").strip()
        if (not v) and w0.get(fld): continue  # 无值就跳过，后面从w0同步
        # EN: Skip if there is no value; sync from w0 later
        # JA: 値がなければスキップし、後で w0 から同期する
        if _looks_sec_title(v) or _looks_like_kv_key_only(v):
            _ci[fld] = ""
            _needs_clean = True
    # 2B) 强制同步：current_info.15字段 100% = r0.work[0].对应字段 （不一致就以r0.work[0]为准，因为r0是权威源）
    # EN: 2B) Forced sync: current_info's 15 fields 100% = the corresponding fields of r0.work[0] (on any mismatch r0.work[0] wins, because r0 is the authoritative source)
    # JA: 2B) 強制同期：current_info の 15 フィールドを 100% = r0.work[0] の対応するフィールドにする（不一致なら r0.work[0] を正とする。r0 が正のソースであるため）
    mapping = {
        "company_name": "company_name",
        "company_employees": "company_employees",
        "company_industry": "company_industry",
        "position": "position",
        "position_type": "position_type",
        "position_salary": "position_salary",
        "position_dept": ("position_dept", "department"),  # position_dept 兼容 department
        # EN: position_dept is compatible with department
        # JA: position_dept は department と互換
        "position_report_to": "position_report_to",
        "position_subordinate": "position_subordinate",
        "employment_type": "employment_type",
        "annual_salary_min": "annual_salary_min",
        "annual_salary_max": "annual_salary_max",
        "status": "status",
        "position_start": "position_start",
        "position_resigned": "position_resigned",
    }
    for ci_k, r0_k in mapping.items():
        r0_v = ""
        if isinstance(r0_k, tuple):
            for alt in r0_k:
                if w0.get(alt):
                    r0_v = str(w0[alt]).strip()
                    break
        else:
            r0_v = str(w0.get(r0_k) or "").strip()
        ci_v = str(_ci.get(ci_k) or "").strip()
        if ci_v != r0_v:
            _ci[ci_k] = r0_v
            _needs_clean = True
    if _needs_clean:
        structured_data["current_info"] = _ci
    # 3) 同步：如果 resumes[0].base_info 没写 household_registration，也把顶层 base_info 清理后的结果同步回去
    # EN: 3) Sync: if resumes[0].base_info has no household_registration, also sync back the cleaned result from the top-level base_info
    # JA: 3) 同期：resumes[0].base_info に household_registration がなければ、トップレベルの base_info を整理した結果も同期して戻す
    if structured_data.get("resumes"):
        r0_x = structured_data["resumes"][0]
        r0_x["base_info"] = dict(structured_data["base_info"])

    # 最终输出前统一到 CONTEXT.md 当前完整 Schema。此前的解析规则继续负责
    # 提取，这一层只做字段补齐、旧别名迁移、日期和快照同步。
    # EN: Before final output, align uniformly with the current complete schema in CONTEXT.md. The earlier parsing rules remain responsible for
    #     extraction; this layer only completes fields, migrates old aliases, and syncs dates and snapshots.
    # JA: 最終出力の前に CONTEXT.md の現在の完全なスキーマに一律に揃える。抽出はそれまでの解析ルールが引き続き担当し、
    #     この層ではフィールドの補完、旧別名の移行、日付とスナップショットの同期だけを行う。
    structured_data = canonicalize_complete_schema(structured_data)
    # canonicalize 后再做一次项目名称补集，防止旧规范化器按所属协会误删真实赛事项目。
    # EN: After canonicalize, complement project names once more, so the old normaliser does not delete real event projects because of their owning association.
    # JA: canonicalize の後にもう一度プロジェクト名を補完し、旧来の正規化処理が所属協会を理由に本当の大会プロジェクトを誤って削除しないようにする。
    if proj_sec_text and structured_data.get("resumes"):
        project_rows = structured_data["resumes"][0].setdefault("project_list", [])
        known = {re.sub(r"\s+", "", str(p.get("project_name") or "")) for p in project_rows}
        for raw in parse_projects_from_raw_text(proj_sec_text):
            pname = str(raw.get("project_name") or "").strip()
            key = re.sub(r"\s+", "", pname)
            if not pname or len(pname) > 100 or key in known:
                continue
            project_rows.append({
                "sequence_no": len(project_rows) + 1,
                "fingerprint": "",
                "project_name": pname,
                "company_or_client": raw.get("company_name") or "",
                "role_name": raw.get("project_role") or "",
                "start_ym": raw.get("start_ym") or "",
                "end_ym": raw.get("end_ym") or "",
                "description": _strip_non_business_resume_details(raw.get("project_description")),
                "responsibilities": _strip_non_business_resume_details(raw.get("project_responsibilities")),
                "achievements": "",
                "keywords": "",
            })
            known.add(key)
    if work_sec_text and structured_data.get("resumes"):
        work_rows = structured_data["resumes"][0].setdefault("work_experiences", [])
        known_companies = {
            re.sub(r"\s+", "", str(w.get("company_name") or "")) for w in work_rows
        }
        date_company_re = re.compile(
            r"^((?:19|20)\d{2}[./年-]\d{1,2})\s*(?:--|[-—–~～至到]{1,4})\s*"
            r"((?:19|20)\d{2}[./年-]\d{1,2}|至今|现在|目前)\s+(.+)$"
        )
        work_lines = [line.strip() for line in work_sec_text.splitlines() if line.strip()]
        date_only_re = re.compile(
            r"^((?:19|20)\d{2}[./年-]\d{1,2})\s*(?:--|[-—–~～至到]{1,4})\s*"
            r"((?:19|20)\d{2}[./年-]\d{1,2}|至今|现在|目前)$"
        )
        for line_index, line in enumerate(work_lines):
            match = date_company_re.match(line)
            if not match:
                date_only = date_only_re.match(line)
                if date_only and line_index + 1 < len(work_lines):
                    match = date_company_re.match(line + " " + work_lines[line_index + 1])
            if not match:
                continue
            company = _clean_company_name(match.group(3))
            norm_company = re.sub(r"\s+", "", company)
            if (
                not company or norm_company in known_companies or len(company) > 60
                or not re.search(r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|工厂|制造厂|株式会社|事务所|研究所|研究院|医院|学校|大学|学院|商社|公司)$", company)
            ):
                continue
            end_raw = match.group(2)
            row = string_record({
                "company_name": company,
                "employment_type": "全职",
                "position_start": _format_ym(match.group(1)),
                "position_resigned": "" if end_raw in ("至今", "现在", "目前") else _format_ym(end_raw),
            }, WORK_FIELDS)
            work_rows.append(row)
            known_companies.add(norm_company)
    if train_sec_text and structured_data.get("resumes"):
        training_rows = structured_data["resumes"][0].setdefault("training_list", [])
        known_training = {
            re.sub(r"\s+", "", str(t.get("training_name") or "")) for t in training_rows
        }
        for raw in _clean_training_list(parse_training_from_raw_text(train_sec_text)):
            name = str(raw.get("training_name") or "").strip()
            key = re.sub(r"\s+", "", name)
            if not name or key in known_training:
                continue
            training_rows.append({
                "sequence_no": len(training_rows) + 1,
                "organization_name": raw.get("organization_name") or "",
                "training_name": name,
                "start_ym": raw.get("start_ym") or "",
                "end_ym": raw.get("end_ym") or "",
                "certificate_name": raw.get("certificate_name") or "",
                "description": raw.get("description") or "",
            })
            known_training.add(key)
    if structured_data.get("resumes"):
        structured_data["resumes"][0]["training_list"] = [
            row for row in (structured_data["resumes"][0].get("training_list") or [])
            if not any(
                tok in str(row.get("training_name") or "")
                for tok in _NON_BUSINESS_ORG_TOKENS + _NON_BUSINESS_ROLE_TOKENS
            )
        ]
        education_rows = structured_data["resumes"][0].get("education_list") or []
        structured_data["resumes"][0]["education_list"] = [
            row for row in education_rows
            if not (
                str(row.get("school_name") or "").strip().endswith("教育")
                and not re.search(r"大学|学院|学校|中学|高中|研究院|科学院|University|College|School", str(row.get("school_name") or ""), re.I)
            )
        ]
        final_edus = structured_data["resumes"][0]["education_list"]
        if final_edus:
            structured_data["education_info"] = string_record(final_edus[0], EDUCATION_FIELDS)
        else:
            structured_data["education_info"] = _build_empty_education_info()
    final_raw_text = rebuild_raw_text(structured_data["resumes"])

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
            "original_path": original_source_path,
            "filename": html_path.name,
            "extension": ".html",
            "size": stat.st_size,
            "html_filename": html_path.name,
            "platform": PLAT_DEFAULT,
            "note": f"由 run_chinese_html_to_json.py 转换（docs\\中文 专属 + 四大平台后处理工具函数统一应用）",
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
            "reader_group": "chinese_html_dom",
            "converter": "run_chinese_html_to_json.py",
            "parser": "CodexGeminiHtmlSchemaParser + combined 51job/zhilian/liepin/newpage postprocess helpers",
            "status": "success",
            "html_path": str(html_path.resolve()),
        },
        "classification": {
            "document_type": classification.document_type,
            "reason": getattr(classification, "reason", ""),
        },
        "structured_data": structured_data,
        "raw_text": final_raw_text,
        "quality": {
            "full_name": (structured_data.get("base_info") or {}).get("full_name", ""),
            "platform": PLAT_DEFAULT,
            "has_work": w_count > 0,
            "work_count": w_count,
            "has_education": e_count > 0,
            "education_count": e_count,
            "raw_text_length": len(final_raw_text),
        },
    }
    return record, "success"


def parser_worker(input_queue: Any, output_queue: Any) -> None:
    """长驻隔离进程：单文件卡死时由主进程终止并重建。

    EN: Long-lived isolated process: when a single file hangs, the main process terminates and recreates it.

    JA: 常駐する分離プロセス：単一のファイルで固まった場合は、メインプロセスが終了させて作り直す。
    """
    parser = CodexGeminiHtmlSchemaParser()
    classifier = DocumentClassifier()
    while True:
        task = input_queue.get()
        if task is None:
            return
        index, raw_path = task
        try:
            record, status = build_record_from_html(Path(raw_path), parser, classifier)
            output_queue.put((index, record, status, ""))
        except BaseException as exc:
            output_queue.put((index, None, "worker_exception", repr(exc)))


def start_parser_worker(context: Any) -> tuple[Any, Any, Any]:
    input_queue = context.Queue(maxsize=1)
    output_queue = context.Queue(maxsize=1)
    process = context.Process(target=parser_worker, args=(input_queue, output_queue), daemon=True)
    process.start()
    return process, input_queue, output_queue


def stop_parser_worker(process: Any, input_queue: Any, output_queue: Any) -> None:
    try:
        input_queue.put_nowait(None)
    except Exception:
        pass
    process.join(timeout=2)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    for channel in (input_queue, output_queue):
        try:
            channel.close()
            channel.join_thread()
        except Exception:
            pass


def atomic_write_json(path: Path, payload: Any) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


# =============================================================================
# main：单目录遍历（docs\\中文 专用）+ 报告汇总
# =============================================================================
# EN: =============================================================================
#     main: single-directory traversal (for docs\\中文 (Chinese) only) + report summary
#     =============================================================================
# JA: =============================================================================
#     main：単一ディレクトリの走査（docs\\中文（中国語）専用）+ レポートの集計
#     =============================================================================

def main() -> int:
    args = parse_args()
    if os.name == "nt":
        os.system("title docs\\中文 专属 HTML -> JSON（整合四大平台工具后处理）")

    html_dir = args.html_dir.resolve()
    json_dir = args.json_dir.resolve()

    # —— ★增量模式★：--only-failed-root 开启时，默认强制 --force（因为要覆盖不合格的JSON）
    # EN: —— ★Incremental mode★: when --only-failed-root is on, --force is forced by default (because failed JSON must be overwritten)
    # JA: —— ★増分モード★：--only-failed-root を有効にすると、既定で --force を強制する（不合格の JSON を上書きする必要があるため）
    if args.incremental_manifest:
        mode = "【纯增量模式】只处理清单中未生成暂存 JSON 的 HTML"
    elif args.only_failed_root:
        args.force = True
        mode = "【增量模式】只重跑 json_dir 根目录现存的不合格JSON；complete/ 下合格的完全不碰"
    else:
        mode = "【全量模式】扫描 html_dir 下所有 HTML"

    print("=== docs\\中文 专属 HTML -> JSON 转换（整合四大平台工具后处理） ===" " / === HTML -> JSON conversion dedicated to docs\\中文 (post-processing that integrates the four platform tools) === / === docs\\中文 専用の HTML -> JSON 変換（4 つのプラットフォーム用ツールを統合した後処理） ===")
    print(f"运行模式: {mode}" f" / Run mode: {mode} / 実行モード：{mode}")
    print(f"HTML 目录: {html_dir}" f" / HTML directory: {html_dir} / HTML ディレクトリ：{html_dir}")
    print(f"JSON 目录: {json_dir}" f" / JSON directory: {json_dir} / JSON ディレクトリ：{json_dir}")

    if not html_dir.exists():
        print(f"错误: 目录不存在 -> {html_dir}" f" / Error: directory does not exist -> {html_dir} / エラー：ディレクトリが存在しません -> {html_dir}")
        return 1

    json_dir.mkdir(parents=True, exist_ok=True)

    map_rows: list[dict[str, Any]] = []
    if args.map.is_file():
        try:
            map_rows = json.loads(args.map.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"错误: 无法读取映射 {args.map} -> {exc}" f" / Error: cannot read map {args.map} -> {exc} / エラー：マップを読み取れません {args.map} -> {exc}")
            return 1
    map_by_source = {
        os.path.normcase(os.path.normpath(str(row.get("source_path") or ""))): row
        for row in map_rows
        if row.get("language_folder") in (None, "", "中文") and row.get("status") == "passed"
    }

    # 已有正式 JSON 参与命名分配。同一 original_path 重跑沿用原文件名；
    # 不同来源出现相同“姓名+联系方式”时才创建 _2 / _3。
    # EN: Existing formal JSON take part in name assignment. Re-running the same original_path reuses the original file name;
    #     _2 / _3 are created only when different sources have the same "name + contact".
    # JA: 既存の正式 JSON もファイル名の割り当てに参加する。同じ original_path を再実行した場合は元のファイル名を使い、
    #     異なるソースで同じ「氏名 + 連絡先」になった場合だけ _2 / _3 を作る。
    output_by_source: dict[str, Path] = {}
    allocated_names: set[str] = set()
    for existing in json_dir.glob("*.json"):
        if existing.name.startswith("_"):
            continue
        allocated_names.add(existing.name.casefold())
        try:
            payload = json.loads(existing.read_text(encoding="utf-8"))
            original = str((payload.get("source") or {}).get("original_path") or "")
            if original:
                output_by_source[os.path.normcase(os.path.normpath(original))] = existing
        except Exception:
            continue

    identity_by_contact: dict[str, set[str]] = {}
    if args.identity_json_dir and args.identity_json_dir.is_dir():
        for identity_path in args.identity_json_dir.glob("*.json"):
            try:
                identity_payload = json.loads(identity_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            identity_base = (identity_payload.get("structured_data") or {}).get("base_info") or {}
            identity_name = str(identity_base.get("full_name") or "").strip()
            if (
                not identity_name
                or identity_name in {"未知", "全职", "要采集", "候选人"}
                or identity_name.endswith(("先生", "女士", "小姐"))
            ):
                continue
            identity_phone = re.sub(r"\D", "", str(identity_base.get("phone") or ""))
            identity_email = str(identity_base.get("email") or "").strip().casefold()
            keys = []
            if len(identity_phone) == 11:
                keys.append(f"phone:{identity_phone}")
            if identity_email and "*" not in identity_email:
                keys.append(f"email:{identity_email}")
            for key in keys:
                identity_by_contact.setdefault(key, set()).add(identity_name)

    total_success = 0
    total_failed = 0
    total_skipped = 0
    total_non_resume = 0
    total_found = 0
    dir_stats: dict[str, int] = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "non_resume": 0}
    items_report: list[dict[str, Any]] = []
    all_start = time.time()

    # —— ★增量模式★：从 json_dir 现存的不合格 JSON 反查 HTML（不扫complete/，不碰合格JSON）
    #    4 级反查：source.path > source.original_path > extraction.html_path > record_id 精确匹配（glob）
    # EN: —— ★Incremental mode★: look up HTML from the failed JSON currently in json_dir (do not scan complete/, do not touch passed JSON)
    #        4-level lookup: source.path > source.original_path > extraction.html_path > exact record_id match (glob)
    # JA: —— ★増分モード★：json_dir に現存する不合格の JSON から HTML を逆引きする（complete/ はスキャンせず、合格済みの JSON には触れない）
    #        4 段階の逆引き：source.path > source.original_path > extraction.html_path > record_id の完全一致（glob）
    html_files: list[Path] = []
    if args.incremental_manifest:
        try:
            manifest = json.loads(args.incremental_manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"错误: 无法读取增量清单 {args.incremental_manifest} -> {exc}" f" / Error: cannot read incremental list {args.incremental_manifest} -> {exc} / エラー：増分一覧を読み取れません {args.incremental_manifest} -> {exc}")
            return 1
        seen: set[str] = set()
        for item in manifest.get("items") or []:
            if item.get("conversion_status") != "passed" or (item.get("staging_json") and not args.rerun_staged):
                continue
            candidate = Path(str(item.get("html_path") or ""))
            if not candidate.is_file() or candidate.suffix.lower() != ".html":
                continue
            key = os.path.normcase(os.path.normpath(str(candidate.resolve())))
            if key not in seen:
                seen.add(key)
                html_files.append(candidate)
        html_files.sort(key=lambda path: path.name.casefold())
        print(f"[纯增量] 清单筛出 {len(html_files)} 个尚无暂存 JSON 的 HTML" f" / [pure incremental] {len(html_files)} HTML files without staging JSON screened from the list / [純粋な増分] 一覧から、ステージング JSON のない HTML を {len(html_files)} 個絞り込みました")
        if args.rerun_staged:
            args.force = True
    elif args.only_failed_root:
        incomplete_jsons = [p for p in json_dir.glob("*.json") if not p.name.startswith("_")]
        print(f"[增量] 根目录发现 {len(incomplete_jsons)} 个不合格JSON，开始反查对应 HTML..." f" / [incremental] {len(incomplete_jsons)} unqualified JSON found in the root directory, looking up the corresponding HTML... / [増分] ルートディレクトリで不合格の JSON を {len(incomplete_jsons)} 個検出しました。対応する HTML を逆引きします...")
        resolved: set[str] = set()
        _html_idx_cache: dict[str, Path] | None = None

        def _get_html_cache() -> dict[str, Path]:
            """建立 html_dir 下所有 HTML 的 record_id → Path 映射（用于 record_id 精确反查）

            EN: Build a record_id → Path map of all HTML under html_dir (for exact lookup by record_id)

            JA: html_dir 配下のすべての HTML の record_id → Path の対応表を作る（record_id による正確な逆引き用）
            """
            nonlocal _html_idx_cache
            if _html_idx_cache is None:
                _html_idx_cache = {}
                for hp in sorted(html_dir.glob("*.html")):
                    rid = html_record_id(hp)
                    if rid and rid not in _html_idx_cache:
                        _html_idx_cache[rid] = hp
            return _html_idx_cache

        for jsp in incomplete_jsons:
            try:
                jd = json.loads(jsp.read_text(encoding="utf-8"))
            except Exception:
                continue
            src = jd.get("source") or {}
            ext = jd.get("extraction") or {}
            rec_id = str(jd.get("record_id") or "")
            # 4级反查
            # EN: 4-level lookup
            # JA: 4 段階の逆引き
            cand_paths: list[str] = [
                str(src.get("path") or ""),
                str(src.get("original_path") or ""),
                str(ext.get("html_path") or ""),
            ]
            found: Path | None = None
            for cp in cand_paths:
                if cp and Path(cp).exists() and Path(cp).suffix.lower() == ".html":
                    found = Path(cp)
                    break
            # 最后一级：通过 record_id 全局反查（html_dir 下所有 HTML 算 record_id）
            # EN: Last level: global lookup by record_id (compute record_id for every HTML under html_dir)
            # JA: 最後の段階：record_id による全体の逆引き（html_dir 配下のすべての HTML の record_id を計算）
            if found is None and rec_id:
                cache = _get_html_cache()
                # record_id 是 64 位 hex，html_record_id 也是 64 位 hex，相等就是同一个
                # EN: record_id is 64 hex digits and html_record_id is also 64 hex digits; equal means the same file
                # JA: record_id は 64 桁の 16 進数で、html_record_id も 64 桁の 16 進数。等しければ同じもの
                if rec_id in cache:
                    found = cache[rec_id]
                else:
                    # 前8位兼容老的 glob 方式
                    # EN: The first 8 characters keep compatibility with the old glob approach
                    # JA: 先頭 8 文字で旧来の glob 方式との互換を保つ
                    rid8 = rec_id[:8]
                    for hp in html_dir.glob(f"*{rid8}*.html"):
                        found = hp
                        break
            if found is not None:
                ap = str(found.resolve())
                if ap not in resolved:
                    resolved.add(ap)
                    html_files.append(found)
            else:
                print(f"  [增量警告] 未找到HTML对应：{jsp.name} (record_id={rec_id[:12]})" f" / [incremental warning] no HTML found for: {jsp.name} (record_id={rec_id[:12]}) / [増分の警告] 対応する HTML が見つかりません：{jsp.name} (record_id={rec_id[:12]})")
        print(f"[增量] 最终反查到 {len(html_files)} 个唯一HTML，开始重跑生成（会覆盖根目录下的旧JSON）" f" / [incremental] {len(html_files)} unique HTML finally found, starting re-run (old JSON in the root directory will be overwritten) / [増分] 一意な HTML を最終的に {len(html_files)} 個逆引きしました。再実行を開始します（ルートディレクトリの古い JSON は上書きされます）")
    else:
        # 全量：原逻辑
        # EN: Full run: original logic
        # JA: 全件：元のロジック
        html_files = sorted(html_dir.glob("*.html"))

    if not html_files:
        print("  未找到 HTML 文件。" " / No HTML files found. / HTML ファイルが見つかりません。")
        return 0
    if args.offset > 0:
        html_files = html_files[args.offset:]
    if args.limit > 0:
        html_files = html_files[: args.limit]

    print(f"共发现 {len(html_files)} 个 HTML 文件。" f" / Found {len(html_files)} HTML files. / HTML ファイルを {len(html_files)} 個検出しました。")
    total_found = len(html_files)

    start_time = time.time()
    s = f = sk = nr = 0

    context = mp.get_context("spawn")
    worker, input_queue, output_queue = start_parser_worker(context)

    for idx, html_path in enumerate(html_files, 1):
        rec_id = html_record_id(html_path)
        input_queue.put((idx, str(html_path)))
        try:
            result_index, record, status, worker_error = output_queue.get(timeout=max(1, args.file_timeout))
            if result_index != idx:
                raise RuntimeError(f"工作进程结果错位：期望 {idx}，得到 {result_index}")
        except queue.Empty:
            stop_parser_worker(worker, input_queue, output_queue)
            worker, input_queue, output_queue = start_parser_worker(context)
            f += 1
            total_failed += 1
            status = f"timeout:{args.file_timeout}s"
            print(f"  [{idx:04d}/{len(html_files):04d}] TIMEOUT {html_path.name} -> {status}", flush=True)
            items_report.append({"index": idx, "html": str(html_path), "status": status})
            continue
        except Exception as exc:
            stop_parser_worker(worker, input_queue, output_queue)
            worker, input_queue, output_queue = start_parser_worker(context)
            f += 1
            total_failed += 1
            print(f"  [{idx:04d}/{len(html_files):04d}] WORKER {html_path.name} -> {exc}", flush=True)
            items_report.append({"index": idx, "html": str(html_path), "status": f"worker_protocol_error:{exc}"})
            continue

        if worker_error:
            f += 1
            total_failed += 1
            print(f"  [{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {worker_error}", flush=True)
            items_report.append({"index": idx, "html": str(html_path), "status": status, "error": worker_error})
            continue

        if not record or status.startswith("non_resume"):
            nr += 1
            total_non_resume += 1
            if idx % args.progress_interval == 0 or idx == len(html_files):
                print(f"  [{idx:04d}/{len(html_files):04d}] SKIP(非简历) {html_path.name} -> {status}" f" / [{idx:04d}/{len(html_files):04d}] SKIP (non-résumé) {html_path.name} -> {status} / [{idx:04d}/{len(html_files):04d}] SKIP（履歴書でない） {html_path.name} -> {status}", flush=True)
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": status,
            })
            continue

        full_name = record["quality"].get("full_name", "") or "未知"
        if full_name in {"未知", "全职", "兼职", "实习", "要采集"} or "采集" in full_name:
            identity_base = (record.get("structured_data") or {}).get("base_info") or {}
            identity_phone = re.sub(r"\D", "", str(identity_base.get("phone") or ""))
            identity_email = str(identity_base.get("email") or "").strip().casefold()
            keys = []
            if len(identity_phone) == 11:
                keys.append(f"phone:{identity_phone}")
            if identity_email and "*" not in identity_email:
                keys.append(f"email:{identity_email}")
            resolved_names: set[str] = set()
            for key in keys:
                resolved_names.update(identity_by_contact.get(key, set()))
            if len(resolved_names) == 1:
                full_name = next(iter(resolved_names))
                identity_base["full_name"] = full_name
                identity_base["name"] = full_name
                record["structured_data"]["base_info"] = identity_base
                for resume in record["structured_data"].get("resumes") or []:
                    resume["base_info"] = dict(identity_base)
                record["quality"]["full_name"] = full_name
                record["raw_text"] = rebuild_raw_text(record["structured_data"].get("resumes") or [])
                record.setdefault("extraction", {})["identity_resolution"] = "unique_complete_v1_contact_match"
        # === 文件名 最终 强 校验：防止 日期 / 数字 / 句子 / 括号 内容 当 姓名 ===
        # EN: === Final strong validation of file names: prevent dates / digits / sentences / bracket content being used as names ===
        # JA: === ファイル名の最終的な厳格な検証：日付・数字・文・括弧の内容が氏名として使われるのを防ぐ ===
        def _safe_for_filename(name: str) -> str:
            n = (name or "").strip()
            n_clean = re.sub(r"[\\/:*?\"<>|]", "", n)
            if not n_clean:
                return "未知"
            # 1. 含 明显 非 姓名 字符（括号 开头 结尾、。句号、多 标点、日期点） → 无效
            # EN: 1. Contains obviously non-name characters (brackets at the start/end, the full stop 。, many punctuation marks, date dots) → invalid
            # JA: 1. 明らかに氏名でない文字を含む（先頭・末尾の括弧、句点。、多数の句読点、日付の点）→ 無効
            if re.search(r"^[（(].*[)）]$|。|…|·\s*$", n_clean):
                return "未知"
            # 2. 以 数字 开头 或 全 数字 + 符号 组合（如 2019.08.05 / 33 / 163.com） → 无效
            # EN: 2. Starts with a digit, or is all digits + symbols (e.g. 2019.08.05 / 33 / 163.com) → invalid
            # JA: 2. 数字で始まる、または数字と記号だけ（例：2019.08.05 / 33 / 163.com）→ 無効
            if re.fullmatch(r"[\d.。,，、/\-()（）~～～:：%]+", n_clean) or re.match(r"^\d", n_clean) and not re.search(r"[\u4e00-\u9fff]{2,}", n_clean):
                return "未知"
            # 3. 含 邮箱/域名 关键词 → 无效
            # EN: 3. Contains e-mail/domain keywords → invalid
            # JA: 3. メール・ドメインのキーワードを含む → 無効
            if any(tok in n_clean.lower() for tok in (".com", "163", "126", "139", "qq.com", "@")):
                return "未知"
            # 4. 长句 + 多 标点 → 无效
            # EN: 4. Long sentence + many punctuation marks → invalid
            # JA: 4. 長い文 + 多数の句読点 → 無効
            if len(n_clean) > 8 and sum(n_clean.count(c) for c in "，,。.；;、!！?？") >= 1:
                return "未知"
            # 5. 有 工作描述/章节 关键词 → 无效
            # EN: 5. Has job-description/section keywords → invalid
            # JA: 5. 職務説明・章のキーワードがある → 無効
            if any(tok in n_clean for tok in ("工作", "统括", "职责", "业绩", "负责", "项目", "教育", "培训", "技能", "简历", "履歴", "公司", "全称", "经验", "采集", "文件夹")):
                return "未知"
            if n_clean.endswith(("的", "表", "性")):
                return "未知"
            # 6. 最终：必须含至少 2 个中文姓名字符，否则回退“未知”。
            # EN: 6. Finally: must contain at least 2 Chinese name characters, otherwise fall back to "未知" (unknown).
            # JA: 6. 最後に：中国語の氏名の文字を少なくとも 2 文字含む必要があり、なければ「未知」（不明）に戻す。
            zh = re.findall(r"[\u4e00-\u9fff]", n_clean)
            if len(zh) < 2 and not re.fullmatch(r"[A-Za-z][A-Za-z.'-]{1,20}(?:\s+[A-Za-z][A-Za-z.'-]{1,20})?", n_clean):
                return "未知"
            return n_clean

        safe_name = _safe_for_filename(full_name)
        if safe_name in {"未知", "全职", "兼职", "实习", "中文", "个人", "简历", "求职者", "候选人", "夏普", "大金", "旭化成", "汽车", "事务"} or safe_name.casefold() in {"qc", "id"}:
            f += 1
            total_failed += 1
            status = "quality_error:invalid_full_name"
            print(f"  [{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {status} ({full_name})", flush=True)
            items_report.append({"index": idx, "html": str(html_path), "status": status, "full_name": full_name})
            continue
        work_cnt = record["quality"].get("work_count", 0)
        base_info = (record.get("structured_data") or {}).get("base_info") or {}
        phone = re.sub(r"\D", "", str(base_info.get("phone") or ""))
        email = str(base_info.get("email") or "").strip().casefold()
        contact = phone or email or "无联系方式"

        def _safe_component(value: str) -> str:
            clean = re.sub(r'[\\/:*?"<>|]', "", value or "").strip().rstrip(".")
            return clean[:100] or "无联系方式"

        original_source = str((record.get("source") or {}).get("original_path") or "")
        source_key = os.path.normcase(os.path.normpath(original_source))
        existing_for_source = output_by_source.get(source_key)
        if existing_for_source is not None:
            json_path = existing_for_source
            json_filename = json_path.name
        else:
            stem = f"{_safe_component(safe_name)}_{_safe_component(contact)}"
            json_filename = f"{stem}.json"
            suffix = 2
            while json_filename.casefold() in allocated_names:
                json_filename = f"{stem}_{suffix}.json"
                suffix += 1
            json_path = json_dir / json_filename
            allocated_names.add(json_filename.casefold())
            output_by_source[source_key] = json_path

        map_row = map_by_source.get(source_key, {})
        validation_errors = validate_semantic_quality(record)
        map_phone = str(map_row.get("phone") or "")
        map_phone_digits = re.sub(r"\D", "", map_phone)
        map_mobile = re.fullmatch(r"1[3-9]\d{9}", map_phone_digits)
        if not map_mobile:
            map_mobile = re.fullmatch(r"86(1[3-9]\d{9})", map_phone_digits)
        if map_mobile:
            map_phone = map_mobile.group(1) if map_mobile.lastindex else map_mobile.group(0)
        elif not re.fullmatch(r"\d{7,11}", map_phone_digits):
            map_phone = ""
        map_email = str(map_row.get("email") or "")
        map_email_match = re.search(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", map_email)
        map_email = map_email_match.group(0) if map_email_match else ""
        validation_errors.extend(validate_complete_json(
            json_path,
            record,
            original_source,
            map_phone,
            map_email,
            "中文",
            True,
        ))
        if validation_errors:
            f += 1
            total_failed += 1
            status = "quality_error:strict_json_validation"
            print(f"  [{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {', '.join(validation_errors[:5])}", flush=True)
            items_report.append({
                "index": idx, "html": str(html_path), "status": status,
                "full_name": full_name, "issues": validation_errors,
            })
            continue

        if json_path.exists() and not args.force:
            sk += 1
            total_skipped += 1
            if idx % args.progress_interval == 0 or idx == len(html_files):
                print(f"  [{idx:04d}/{len(html_files):04d}] EXIST {html_path.name}", flush=True)
            continue

        try:
            atomic_write_json(json_path, record)
            s += 1
            total_success += 1
            if idx % args.progress_interval == 0 or idx == len(html_files):
                print(f"  [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {json_filename} (工作{work_cnt}段)" f" / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {json_filename} ({work_cnt} work entries) / [{idx:04d}/{len(html_files):04d}] OK    {html_path.name} → {json_filename}（職歴 {work_cnt} 件）", flush=True)
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "json": str(json_path),
                "status": "success",
                "full_name": full_name,
                "work_count": work_cnt,
            })
        except Exception as exc:
            f += 1
            total_failed += 1
            print(f"  [{idx:04d}/{len(html_files):04d}] FAIL  {html_path.name} -> {exc}")
            items_report.append({
                "index": idx,
                "html": str(html_path),
                "status": f"write_error:{exc}",
            })

    stop_parser_worker(worker, input_queue, output_queue)

    elapsed = time.time() - start_time
    dir_stats = {"total": len(html_files), "success": s, "failed": f, "skipped": sk, "non_resume": nr}
    print(f"完成：总数 {len(html_files)} 成功 {s} 失败 {f} 跳过 {sk} 非简历 {nr}；耗时 {elapsed:.2f}s" f" / Done: total {len(html_files)} success {s} failed {f} skipped {sk} non-résumé {nr}; elapsed {elapsed:.2f}s / 完了：合計 {len(html_files)} 成功 {s} 失敗 {f} スキップ {sk} 履歴書でない {nr}、所要 {elapsed:.2f} 秒")

    total_elapsed = time.time() - all_start
    report_path = args.report or (json_dir / "_chinese_batch_report.json")
    report_data = {
        "workflow": "chinese_html_to_json__docs_zh_only",
        "html_dir": str(html_dir),
        "json_dir": str(json_dir),
        "stats": dir_stats,
        "total": {
            "found": total_found,
            "success": total_success,
            "failed": total_failed,
            "skipped": total_skipped,
            "non_resume": total_non_resume,
        },
        "elapsed_seconds": round(total_elapsed, 2),
        "items": items_report,
    }
    atomic_write_json(report_path, report_data)

    print("\n=== docs\\中文 目录批处理完成 ===" " / \n=== docs\\中文 directory batch finished === / \n=== docs\\中文 ディレクトリの一括処理が完了しました ===")
    print(f"总计 发现:{total_found} 成功:{total_success} 失败:{total_failed} 跳过:{total_skipped} 非简历:{total_non_resume}" f" / Total found:{total_found} success:{total_success} failed:{total_failed} skipped:{total_skipped} non-résumé:{total_non_resume} / 合計 検出:{total_found} 成功:{total_success} 失敗:{total_failed} スキップ:{total_skipped} 履歴書でない:{total_non_resume}")
    print(f"总耗时: {total_elapsed:.2f} 秒；报告: {report_path}" f" / Total time: {total_elapsed:.2f} s; report: {report_path} / 所要時間：{total_elapsed:.2f} 秒、レポート：{report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
