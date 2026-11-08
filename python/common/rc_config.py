# -*- coding: utf-8 -*-
"""
rc_config.py —— 项目统一配置读取（common）。

所有脚本通过它得到“简历源文件夹 / V1 / V2 / V3 目录 / 输出目录”等路径，不再写死盘符。
别人拿到项目，只需复制 config.example.json 为 config.json，改几个路径即可。

查找顺序（找到第一个存在的）：
  1. 环境变量 RESUME_CONFIG 指向的文件
  2. <项目根>/config.json
  3. <项目根>/python/config.json
都没有则使用内置默认值（目录名与本项目原始布局一致）。

路径解析规则：config 里的相对路径相对“项目根”；绝对路径原样使用。
项目根：环境变量 RESUME_ROOT > config 里的 project_root > 本文件上两级目录（python/common 的上上级）。

优先级（高→低）：命令行参数 > 环境变量 > config.json > 内置默认。

EN: rc_config.py -- the project's unified configuration loader (common).

Every script gets paths such as "résumé source folder / V1 / V2 / V3 directories / output directory" from it; drive letters are no longer hard-coded.
Anyone who receives the project only needs to copy config.example.json to config.json and change a few paths.

Lookup order (the first one that exists wins):
  1. The file pointed to by the RESUME_CONFIG environment variable
  2. <project root>/config.json
  3. <project root>/python/config.json
If none exists, built-in defaults are used (directory names match the project's original layout).

Path resolution: relative paths in config are relative to the "project root"; absolute paths are used as-is.
Project root: RESUME_ROOT environment variable > project_root in config > two levels above this file (the grandparent of python/common).

Precedence (high -> low): command-line arguments > environment variables > config.json > built-in defaults.

JA: rc_config.py —— プロジェクト共通の設定読み込み（common）。

すべてのスクリプトはここから「履歴書ソースフォルダ / V1 / V2 / V3 ディレクトリ / 出力ディレクトリ」などのパスを取得し、ドライブ名はもうハードコードしない。
プロジェクトを受け取った人は config.example.json を config.json にコピーし、いくつかのパスを変えるだけでよい。

検索順序（最初に存在したものを採用）：
  1. 環境変数 RESUME_CONFIG が指すファイル
  2. <プロジェクトルート>/config.json
  3. <プロジェクトルート>/python/config.json
どれもなければ組み込みの既定値を使う（ディレクトリ名は本プロジェクト本来の構成と同じ）。

パス解決ルール：config 内の相対パスは「プロジェクトルート」基準、絶対パスはそのまま使う。
プロジェクトルート：環境変数 RESUME_ROOT > config の project_root > このファイルの 2 階層上（python/common の親の親）。

優先順位（高 → 低）：コマンドライン引数 > 環境変数 > config.json > 組み込み既定値。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve()
PYTHON_DIR = _HERE.parents[1]
DEFAULT_ROOT = _HERE.parents[2]

DEFAULTS = {
    "project_root": "",                       # 留空 = 自动（python 目录的上一级）
    # EN: Leave empty = automatic (the parent of the python directory)
    # JA: 空欄 = 自動（python ディレクトリの 1 つ上）
    "source_dir": "需要采集的简历文件夹",        # 原始简历文件（只读）
    # EN: Original résumé files (read-only)
    # JA: 元の履歴書ファイル（読み取り専用）
    "html_dir": "complete-transfered-htmls",     # V2 中间 HTML
    # EN: V2 intermediate HTML
    # JA: V2 の中間 HTML
    "v1_dir": "complete-v1",                  # V1 JSON（合并的辅助来源）
    # EN: V1 JSON (secondary source for merging)
    # JA: V1 JSON（統合の副ソース）
    "v2_dir": "complete-transfered-jsons",             # V2 JSON（合并的主来源）
    # EN: V2 JSON (primary source for merging)
    # JA: V2 JSON（統合の主ソース）
    "v3_dir": "complete-v3",                  # V3 最终成品（一人一份）
    # EN: V3 final output (one file per person)
    # JA: V3 最終成果物（1 人 1 ファイル）
    "output_dir": "output",                   # 运行输出根目录
    # EN: Root directory of run output
    # JA: 実行出力のルートディレクトリ
    "merge_out_dir": "output/merge-v3",       # 合并运行输出
    # EN: Merge run output
    # JA: 統合実行の出力
    "repair_dir": "output/source-repair-v3",  # 修复副本根目录（取其中名字最新的子目录）
    # EN: Root directory of repair copies (the subdirectory with the latest name is used)
    # JA: 修復コピーのルートディレクトリ（名前が最も新しいサブディレクトリを使用）
    "align_dir": "claude-align",              # 多语言对齐工作目录
    # EN: Multilingual alignment working directory
    # JA: 多言語対応付けの作業ディレクトリ
    "python_exe": "python",                   # .cmd 入口使用的解释器
    # EN: Interpreter used by the .cmd entry points
    # JA: .cmd 起動スクリプトが使うインタープリター
    "path_map": {},                           # 旧来源路径前缀 -> 新位置，如 {"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}
    # EN: Old source-path prefix -> new location, e.g. {"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}
    # JA: 旧ソースパスの接頭辞 -> 新しい場所。例：{"E:\\resume-system\\codex-transfered-htmls": "{root}/complete-transfered-htmls"}
    "dir_names": {},                          # 额外的“目录名改名”映射，如 {"complete-transfered-jsons": "my-json"}
    # EN: Extra "directory rename" map, e.g. {"complete-transfered-jsons": "my-json"}
    # JA: 追加の「ディレクトリ名変更」マッピング。例：{"complete-transfered-jsons": "my-json"}
}

# 代码里出现的“默认目录名” -> 对应的配置键
# EN: "Default directory name" appearing in code -> corresponding config key
# JA: コード中に現れる「既定のディレクトリ名」 -> 対応する設定キー
_NAME_TO_KEY = {
    DEFAULTS["source_dir"]: "source_dir",
    DEFAULTS["html_dir"]: "html_dir",
    DEFAULTS["v1_dir"]: "v1_dir",
    DEFAULTS["v2_dir"]: "v2_dir",
    DEFAULTS["v3_dir"]: "v3_dir",
    DEFAULTS["output_dir"]: "output_dir",
}

_cache: dict | None = None


def _find_config() -> Path | None:
    env = os.environ.get("RESUME_CONFIG")
    if env and Path(env).is_file():
        return Path(env)
    root = Path(os.environ.get("RESUME_ROOT") or DEFAULT_ROOT)
    for p in (root / "config.json", PYTHON_DIR / "config.json"):
        if p.is_file():
            return p
    return None


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    cfg = dict(DEFAULTS)
    p = _find_config()
    if p:
        with open(p, "r", encoding="utf-8-sig") as f:
            user = json.load(f)
        for k, v in user.items():
            if k.startswith("_"):
                continue
            cfg[k] = v
    _cache = cfg
    return cfg


def project_root() -> Path:
    env = os.environ.get("RESUME_ROOT")
    if env:
        return Path(env)
    cfg = load()
    if cfg.get("project_root"):
        return Path(cfg["project_root"])
    return DEFAULT_ROOT


def get(key: str):
    return load()[key]


def path(key: str) -> Path:
    """配置里的目录键 -> 绝对路径（相对路径相对项目根）。

    EN: Directory key in config -> absolute path (relative paths are relative to the project root).

    JA: 設定のディレクトリキー -> 絶対パス（相対パスはプロジェクトルート基準）。
    """
    v = Path(str(load()[key]))
    return v if v.is_absolute() else project_root() / v


def dirname(default_name: str) -> str:
    """代码里写死的目录名 -> 配置里实际使用的目录名（未配置则原样返回）。

    V2 脚本里大量出现 "complete-transfered-htmls" 之类的目录名，统一经过这里换算。

    EN: Directory name hard-coded in code -> directory name actually used in config (returned unchanged if not configured).

    V2 scripts contain many directory names like "complete-transfered-htmls"; all of them are converted here.

    JA: コードにハードコードされたディレクトリ名 -> 設定で実際に使うディレクトリ名（未設定ならそのまま返す）。

    V2 スクリプトには "complete-transfered-htmls" のようなディレクトリ名が大量にあり、すべてここで変換する。
    """
    cfg = load()
    extra = cfg.get("dir_names") or {}
    if default_name in extra:
        return str(extra[default_name])
    key = _NAME_TO_KEY.get(default_name)
    if key:
        return str(cfg[key])
    return default_name


def latest_repair_dir() -> Path | None:
    """repair_dir 下按名字排序的最后一个子目录（修复副本）。

    EN: The last subdirectory (by name) under repair_dir (repair copies).

    JA: repair_dir 配下で名前順の最後のサブディレクトリ（修復コピー）。
    """
    r = path("repair_dir")
    if not r.is_dir():
        return None
    subs = sorted(d for d in r.iterdir() if d.is_dir())
    return subs[-1] if subs else None


def _norm_prefix(p: str) -> str:
    return str(p).replace("\\", "/").rstrip("/").lower()


def resolve_path(p) -> str:
    """JSON 里记录的“来源路径”(original_path / html_path) -> 当前机器上的实际位置。

    搬动过目录、换了机器之后，成品 JSON 里的旧路径会失效。config.json 的 path_map 给出
    “旧前缀 -> 新前缀”，新前缀里的 {root} 代表项目根，相对路径也相对项目根。
    规则：路径现在就存在则原样返回；否则按最长前缀匹配替换；都不命中则原样返回。
    只用于“找文件/检查文件是否存在”，不会改写 JSON 里记录的原始路径。

    EN: Map a "source path" recorded in the JSON (original_path / html_path) to its real location on this machine.
    After directories are moved or the machine changes, old paths in the final JSON become invalid. path_map in
    config.json maps "old prefix -> new prefix"; {root} in the new prefix means the project root, and relative
    paths are relative to the project root. Rule: return the path unchanged if it exists now; otherwise replace by
    the longest matching prefix; return it unchanged if nothing matches. Used only to find files / check existence;
    it never rewrites the paths recorded in the JSON.

    JA: JSON に記録された「ソースパス」(original_path / html_path) を、このマシン上の実際の場所に変換する。
    ディレクトリを移動したりマシンが変わると、成果物 JSON の古いパスは無効になる。config.json の path_map は
    「旧接頭辞 -> 新接頭辞」を与え、新接頭辞の {root} はプロジェクトルート、相対パスもルート基準。
    規則：今そのパスが存在すればそのまま返す。なければ最長一致の接頭辞で置換し、どれにも一致しなければそのまま返す。
    ファイルを探す／存在を確認するためだけに使い、JSON に記録された元のパスは書き換えない。
    """
    import os
    p = str(p or "")
    if not p or os.path.exists(p):
        return p
    pm = load().get("path_map") or {}
    low = p.replace("\\", "/").lower()
    for old in sorted(pm, key=lambda k: -len(_norm_prefix(k))):
        o = _norm_prefix(old)
        if low == o or low.startswith(o + "/"):
            rest = p.replace("\\", "/")[len(o):].lstrip("/")
            new = str(pm[old]).replace("{root}", str(project_root()).replace("\\", "/"))
            base = Path(new)
            if not base.is_absolute():
                base = project_root() / new
            cand = base / rest if rest else base
            return str(cand)
    return p
