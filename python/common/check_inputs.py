"""合并前检查输入目录：V2 / V1 目录必须存在且里面有 .json，否则报错退出（退出码 1）。
EN: Pre-merge input check: the V2 / V1 directories must exist and contain .json files, otherwise exit with code 1.
JA: 統合前の入力チェック：V2 / V1 ディレクトリが存在し .json を含んでいなければ、終了コード 1 で中止する。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc_config as rc  # noqa: E402


def count_json(d: Path) -> int:
    if not d.is_dir():
        return -1
    return sum(1 for p in d.iterdir() if p.suffix.lower() == ".json" and not p.name.startswith("_"))


def main() -> int:
    bad = False
    for key, label in (("v2_dir", "V2（主来源）"), ("v1_dir", "V1（辅助来源）")):
        d = Path(rc.path(key))
        n = count_json(d)
        if n < 0:
            print(f"[错误] {label} 目录不存在：{d}")
            bad = True
        elif n == 0:
            print(f"[错误] {label} 目录里没有 .json 文件：{d}")
            bad = True
        else:
            print(f"[OK] {label}：{n} 个 JSON  {d}")
    if bad:
        print("输入不完整，已中止。合并结果会缺人，不要继续。请先把 V2/V1 文件放回上面的目录。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
