"""修复已由源文件明确确认的多语言 JSON 姓名并按姓名+联系方式重命名。

EN: Fix multilingual JSON names explicitly confirmed by the source file, and rename them by name + contact.

JA: ソースファイルで明確に確認された多言語 JSON の氏名を修正し、氏名 + 連絡先で名前を付け直す。
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import json
from pathlib import Path

def _load_repair_table(name, default):
    """一次性修复所需的“姓名/联系方式/名单”不随仓库发布：放在 <项目根>/repair_data/<name>.json。
    文件不存在则使用空表（脚本不会改动任何文件）。示例见 repair_data/ 下的 *.example.json。

    EN: The "name / contact / list" data needed for one-off repairs is not published with the repository: put it at <project root>/repair_data/<name>.json.
    If the file does not exist an empty table is used (the script will not change any file). See the *.example.json files under repair_data/ for samples.

    JA: 一回限りの修復に必要な「氏名・連絡先・名簿」のデータはリポジトリに含めない：<プロジェクトルート>/repair_data/<name>.json に置く。
    ファイルがなければ空の表を使う（スクリプトはどのファイルも変更しない）。例は repair_data/ 配下の *.example.json を参照。
    """
    p = _rc.project_root() / "repair_data" / (name + ".json")
    if p.is_file():
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return default


ROOT = _rc.project_root() / _rc.dirname("complete-transfered-jsons") / "docs"
_FIXES_RAW = _load_repair_table("known_names", [])  # [{"old": "中日文\\未知_13800000001.json", "name": "张三", "new": "张三_13800000001.json"}]
# EN: [{"old": "中日文\\未知_13800000001.json", "name": "张三", "new": "张三_13800000001.json"}] (old path in the Chinese-Japanese folder with an unknown name → new file named name_phone)
# JA: [{"old": "中日文\\未知_13800000001.json", "name": "张三", "new": "张三_13800000001.json"}]（中日フォルダ内の氏名不明の旧パス → 氏名_電話番号 の新しいファイル名）
FIXES = {ROOT / item["old"]: (item["name"], item["new"]) for item in _FIXES_RAW}


for old_path, (name, new_filename) in FIXES.items():
    payload = json.loads(old_path.read_text(encoding="utf-8"))
    structured = payload["structured_data"]
    structured["base_info"]["full_name"] = name
    for resume in structured.get("resumes") or []:
        resume.setdefault("base_info", {})["full_name"] = name
    values = []
    seen = set()
    for resume in structured.get("resumes") or []:
        for value in json.loads(json.dumps(resume, ensure_ascii=False)).values():
            if isinstance(value, str) and value.strip() and value.strip() not in seen:
                seen.add(value.strip())
                values.append(value.strip())
    # 保留原有 raw_text 的完整履历，只替换明确的占位姓名。
    # EN: Keep the complete history in the original raw_text and only replace explicit placeholder names.
    # JA: 元の raw_text にある完全な経歴は残し、明確なプレースホルダーの氏名だけを置き換える。
    raw = str(payload.get("raw_text") or "")
    payload["raw_text"] = raw.replace("待确认姓名", name).replace("未知", name)
    new_path = old_path.with_name(new_filename)
    if new_path.exists() and new_path != old_path:
        raise FileExistsError(new_path)
    new_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if new_path != old_path:
        old_path.unlink()
    print(f"{old_path.name} -> {new_path.name}: {name}")
