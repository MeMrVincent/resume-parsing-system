import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）
import os
import sys
import re
import html
import time
from pathlib import Path

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from process_word_to_html import (
    clean_html_styles,
    convert_single_word
)

# 不合格问题规则检视器
# EN: Rule inspector for failing issues
# JA: 不合格の問題のルール検査器
QMARK_RE = re.compile(r"\?{3,}")
ENTITY_RE = re.compile(r"&#\d{3,5};")
PUA_RE = re.compile(r"[\ue000-\uf8ff]")
OP_RE = re.compile(r"</?o:p[^>]*>", re.IGNORECASE)
NS_RE = re.compile(r"</?[a-z0-9]+:[a-z0-9]+[^>]*>", re.IGNORECASE)
QP_RE = re.compile(r"=\s*[\r\n]+")
GARBAGE_CJK_RE = re.compile(r"[捨鐽伀圂坄態捸坸锵渀强渀椽鬧鲋犀鱤骥醳玅鮩邩疄婣蒐兣捅桄禋奧c敁僙觿局閫沠光尦骺恾驄尀脈瀁瀭唀摧帞粇并圁遄怆躧蹳坳钯癨攷誥漯鯝婹铜韝坶绝屼禛祙銯犯劯詨罠愀承黟翟羟罝]{2,}")

def check_issues(content: str) -> bool:
    if OP_RE.search(content):
        return True
    if ENTITY_RE.search(content):
        return True
    if PUA_RE.search(content):
        return True
    if QMARK_RE.search(content):
        return True
    if QP_RE.search(content):
        return True
    if GARBAGE_CJK_RE.search(content):
        return True
    return False

def clean_docs_root():
    docs_p = _rc.project_root() / _rc.dirname("complete-transfered-htmls") / "docs"
    if docs_p.exists():
        # 清理根目录散落 HTML
        # EN: Clean up HTML scattered in the root directory
        # JA: ルートディレクトリに散らばった HTML を片付ける
        for f in docs_p.glob("*.html"):
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass
        # 维护并创建 docs/temp 目录
        # EN: Maintain and create the docs/temp directory
        # JA: docs/temp ディレクトリを維持・作成する
        temp_p = docs_p / "temp"
        temp_p.mkdir(parents=True, exist_ok=True)

def main():
    clean_docs_root()
    
    docs_p = _rc.project_root() / _rc.dirname("complete-transfered-htmls") / "docs"
    passed_dir = docs_p / "passed"
    review_dir = docs_p / "review"
    
    passed_files = list(passed_dir.glob("*.html")) if passed_dir.exists() else []
    review_files = list(review_dir.glob("*.html")) if review_dir.exists() else []
    
    all_files = passed_files + review_files
    total = len(all_files)
    
    print(f"=================================================================")
    print(f"开始对 passed ({len(passed_files)}) 和 review ({len(review_files)}) 下全量 {total} 个 HTML 文件进行逐一全读质检与深度蒸馏重修！" f" / Start a full read-through quality check and deep repair of all {total} HTML files under passed ({len(passed_files)}) and review ({len(review_files)})! / passed（{len(passed_files)}）と review（{len(review_files)}）配下の全 {total} 件の HTML ファイルについて、1 件ずつ全文を読んで品質確認し、徹底的に修復を始めます！")
    print(f"=================================================================")
    
    repaired_count = 0
    clean_count = 0
    upgraded_count = 0
    start_t = time.time()
    
    for idx, f_path in enumerate(all_files, 1):
        try:
            content = f_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
            
        if check_issues(content):
            repaired_count += 1
            
            # 1. 从 Header 提取源 Word 文件路径
            # EN: 1. Extract the source Word file path from the header
            # JA: 1. ヘッダーから元の Word ファイルのパスを抽出する
            src_m = re.search(r"<b>源文件路径：</b>([^<]+)", content)
            date_m = re.search(r"<b>简历落地时间：</b>([^<]+)", content)
            
            src_str = src_m.group(1).strip() if src_m else ""
            date_str = date_m.group(1).strip() if date_m else ""
            
            if src_str and Path(src_str).exists():
                real_name = Path(src_str).name
                ok, status, phone, email, out_path = convert_single_word(
                    src_str, passed_dir, review_dir, real_name, date_str
                )
                if status == "passed" and f_path.parent == review_dir:
                    upgraded_count += 1
                    try:
                        f_path.unlink()
                    except Exception:
                        pass
            else:
                # 若源文件无法读取，直接在原 HTML 上执行纯 Python 蒸馏清洗并同名覆盖写回
                # EN: If the source file cannot be read, run pure-Python distillation cleaning directly on the original HTML and write it back under the same name
                # JA: 元のファイルが読めない場合は、元の HTML に純粋な Python による抽出・クレンジングを直接行い、同じ名前で書き戻す
                distilled = clean_html_styles(content)
                f_path.write_text(distilled, encoding="utf-8")
        else:
            clean_count += 1
            
        if idx % 100 == 0 or idx == total:
            elapsed = time.time() - start_t
            spd = idx / elapsed if elapsed > 0 else 0
            print(f"全读质检进度 [{idx}/{total}] | 已精纯重修: {repaired_count} | 升级移入passed: {upgraded_count} | 原本干净: {clean_count} | 速度: {spd:.1f} 文件/秒" f" / Read-through progress [{idx}/{total}] | refined and repaired: {repaired_count} | promoted to passed: {upgraded_count} | originally clean: {clean_count} | speed: {spd:.1f} files/s / 通読の進捗 [{idx}/{total}] | 精製・修復済み：{repaired_count} | passed に昇格：{upgraded_count} | もともと正常：{clean_count} | 速度：{spd:.1f} ファイル/秒", flush=True)

    clean_docs_root()
    print("\n================== 全量 HTML 逐一阅读质检重修完成报告 ==================" " / \n================== Full HTML read-through quality check and repair: report ================== / \n================== HTML 全件の通読による品質確認・修復の完了レポート ==================")
    print(f"扫描文件总数: {total}" f" / Total files scanned: {total} / 走査したファイルの総数：{total}")
    print(f"成功质检重修问题文件: {repaired_count}" f" / Problem files checked and repaired successfully: {repaired_count} / 品質確認で問題を修復できたファイル：{repaired_count}")
    print(f"提纯联系方式并升级移入 passed: {upgraded_count}" f" / Contacts purified and files promoted to passed: {upgraded_count} / 連絡先を精製して passed に昇格したもの：{upgraded_count}")
    print(f"原质无瑕合格文件: {clean_count}" f" / Originally flawless files: {clean_count} / もともと問題のなかったファイル：{clean_count}")
    print(f"docs 根目录杂文件清扫完成！" f" / Clean-up of stray files in the docs root finished! / docs ルートの雑多なファイルの整理が完了しました！")
    print("==========================================================================")

if __name__ == "__main__":
    main()
