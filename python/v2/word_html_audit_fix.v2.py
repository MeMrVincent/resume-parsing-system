import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）
import os
import sys
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = _rc.project_root()
PYTHON_ROOT = _rc.PYTHON_DIR / "v2"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from process_word_to_html import (
    convert_single_word,
    clean_html_styles,
    strip_tags,
    extract_contacts,
    read_file_text_safe,
    source_path_hash,
    safe_stem
)

# 质检规则模式
# EN: Quality-check rule patterns
# JA: 品質チェックのルールのパターン
QMARK_RUN_RE = re.compile(r"\?{3,}")
PUA_CHAR_RE = re.compile(r"[\ue000-\uf8ff]")
ENTITY_RE = re.compile(r"&#\d{3,5};")
HEX_URL_RE = re.compile(r"\b(?:[0-9A-F]{2}\s+){3,}[0-9A-F]{2}\b", re.IGNORECASE)
GARBAGE_CJK_RE = re.compile(r"[捨鐽伀圂坄態捸坸锵渀强渀椽鬧鲋犀鱤骥醳玅鮩邩疄婣蒐兣捅桄禋奧c敁僙觿局閫沠光尦骺恾驄尀脈瀁瀭唀摧帞粇并圁遄怆躧蹳坳钯癨攷誥漯鯝婹铜韝坶绝屼禛祙銯犯劯詨罠愀承黟翟羟罝]{2,}")

def needs_repair(content: str) -> bool:
    if QMARK_RUN_RE.search(content):
        return True
    if PUA_CHAR_RE.search(content):
        return True
    if ENTITY_RE.search(content):
        return True
    if HEX_URL_RE.search(content):
        return True
    if GARBAGE_CJK_RE.search(content):
        return True
    return False

def audit_and_fix_all(base_docs_dir: str):
    docs_p = Path(base_docs_dir)
    passed_dir = docs_p / "passed"
    review_dir = docs_p / "review"

    all_html_files = []
    if passed_dir.exists():
        all_html_files.extend(list(passed_dir.glob("*.html")))
    if review_dir.exists():
        all_html_files.extend(list(review_dir.glob("*.html")))

    # 过滤出文件大小超过 10KB (10240 字节) 的文件
    # EN: Filter files larger than 10KB (10240 bytes)
    # JA: 10KB（10240 バイト）を超えるファイルを絞り込む
    gt10k_files = [f for f in all_html_files if f.stat().st_size > 10240]
    total_count = len(gt10k_files)
    print(f"正在开始针对大于 10KB 的 HTML 文件进行全量质检与重新修复，共 {total_count} 个文件..." f" / Start full quality check and re-repair of HTML files larger than 10KB, {total_count} files... / 10KB を超える HTML ファイルについて、全件の品質確認と再修復を開始します。全 {total_count} ファイル...")

    fixed_count = 0
    upgraded_to_passed_count = 0
    clean_count = 0
    start_time = time.time()

    for idx, html_file in enumerate(gt10k_files, 1):
        try:
            content = html_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if needs_repair(content):
            fixed_count += 1
            
            # 提取源文件路径
            # EN: Extract the source file path
            # JA: ソースファイルのパスを抽出する
            src_path_match = re.search(r"<b>源文件路径：</b>([^<]+)", content)
            date_match = re.search(r"<b>简历落地时间：</b>([^<]+)", content)
            
            src_path_str = src_path_match.group(1).strip() if src_path_match else ""
            download_date = date_match.group(1).strip() if date_match else ""
            
            if src_path_str and Path(src_path_str).exists():
                # 调用无损转换引擎重写，传入真实源文件名以实现严格同名覆盖
                # EN: Rewrite with the lossless conversion engine, passing the real source file name to overwrite strictly under the same name
                # JA: 無損失の変換エンジンで書き直し、本当のソースファイル名を渡して同じ名前で厳密に上書きする
                original_src_p = Path(src_path_str)
                real_filename = original_src_p.name
                
                ok, status, phone, email, out_path_str = convert_single_word(
                    src_path_str, passed_dir, review_dir, real_filename, download_date
                )
                
                # 如果该文件原本在 review/ 下，但修补后成功提纯出了手机号/邮箱，原旧文件若在 review，删除之
                # EN: If the file was originally under review/ but a phone/e-mail was successfully extracted after patching, delete the old file in review
                # JA: そのファイルが元は review/ にあったが、修正後に電話番号・メールを抽出できた場合は、review にある古いファイルを削除する
                if status == "passed" and html_file.parent == review_dir:
                    upgraded_to_passed_count += 1
                    try:
                        html_file.unlink()
                    except Exception:
                        pass
            else:
                # 若源文件无法定位，直接在现有 HTML 内容上强行执行样式与杂质二次蒸馏清洗
                # EN: If the source file cannot be located, force a second distillation cleaning of styles and noise on the existing HTML content
                # JA: 元のファイルの場所がわからない場合は、既存の HTML の内容にスタイルと不要部分の 2 回目の抽出・クレンジングを強制する
                cleaned_body = clean_html_styles(content)
                html_file.write_text(cleaned_body, encoding="utf-8")
        else:
            clean_count += 1

        if idx % 50 == 0 or idx == total_count:
            elapsed = time.time() - start_time
            speed = idx / elapsed if elapsed > 0 else 0
            print(f"质检进度 [{idx}/{total_count}] | 已修复: {fixed_count} | 重抽取联系方式升格为passed: {upgraded_to_passed_count} | 原本合格: {clean_count} | 速度: {speed:.1f} 文件/秒" f" / Check progress [{idx}/{total_count}] | repaired: {fixed_count} | contacts re-extracted and promoted to passed: {upgraded_to_passed_count} | originally qualified: {clean_count} | speed: {speed:.1f} files/s / 確認の進捗 [{idx}/{total_count}] | 修復済み：{fixed_count} | 連絡先を再抽出して passed に昇格：{upgraded_to_passed_count} | もともと合格：{clean_count} | 速度：{speed:.1f} ファイル/秒", flush=True)

    print("\n================== 10KB+ HTML 全量质检修补完成汇总 ==================" " / \n================== Full quality check and repair of 10KB+ HTML: summary ================== / \n================== 10KB 超の HTML の全件品質確認・修復の完了サマリー ==================")
    print(f"总抽检文件 (>10KB): {total_count}" f" / Files sampled (>10KB): {total_count} / 抽出検査したファイルの総数（10KB 超）：{total_count}")
    print(f"成功质检修复不合格文件: {fixed_count}" f" / Unqualified files checked and repaired successfully: {fixed_count} / 品質確認で不合格を修復できたファイル：{fixed_count}")
    print(f"重新提纯手机号/邮箱并升级至 passed 目录: {upgraded_to_passed_count}" f" / Mobile/e-mail re-purified and promoted to the passed directory: {upgraded_to_passed_count} / 携帯番号／メールを再精製して passed ディレクトリへ昇格したもの：{upgraded_to_passed_count}")
    print(f"原本质量合格文件: {clean_count}" f" / Files that were qualified originally: {clean_count} / もともと品質が合格していたファイル：{clean_count}")
    print("====================================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="对 >10KB 的 HTML 文件进行全量质检与二次重新修复" " / Full quality check and second repair of HTML files larger than 10KB / 10KB を超える HTML ファイルの全件品質確認と 2 回目の再修復")
    parser.add_argument("--docs-dir", default=str(_rc.project_root() / _rc.dirname("complete-transfered-htmls") / "docs"), help="HTML 根目录" " / HTML root directory / HTML のルートディレクトリ")
    args = parser.parse_args()
    
    audit_and_fix_all(args.docs_dir)
