@echo off
rem 静态检查全部 python 代码（语法、import、文件名引用），不运行任何脚本。
rem EN: Statically check all Python code (syntax, imports, file-name references) without running any script.
rem JA: すべての Python コードを静的にチェックする（構文、import、ファイル名の参照）。スクリプトは一切実行しない。
chcp 65001 >nul
cd /d %~dp0..
if not defined PY set PY=python
%PY% python\common\check_code.py
pause
