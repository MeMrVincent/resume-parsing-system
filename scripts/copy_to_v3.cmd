@echo off
rem 把最新一次合并运行里通过审计的 formal 简历复制到 v3_dir（默认 complete-v3）。复制，不删除源文件。
rem EN: Copy the audited formal résumés from the latest merge run to v3_dir (default complete-v3). Copies only; source files are not deleted.
rem JA: 最新の統合の実行で監査に合格した formal の履歴書を v3_dir（既定は complete-v3）にコピーする。コピーするだけで、元のファイルは削除しない。
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d %~dp0..
if not defined PY set PY=python
%PY% python\v3\copy_to_v3.py %*
pause
