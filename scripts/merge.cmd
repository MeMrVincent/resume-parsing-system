@echo off
rem 合并 V2/V1 -> 一人一份 JSON：解压修复副本 -> 合并 -> 见证合并 -> 审计。读取项目根目录的 config.json。
rem EN: Merge V2/V1 -> one JSON per person: extract repair copies -> merge -> witness merge -> audit. Reads config.json in the project root.
rem JA: V2/V1 を統合 -> 1 人 1 ファイルの JSON：修復コピーを展開 -> 統合 -> 検証用統合 -> 監査。プロジェクトルートの config.json を読む。
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d %~dp0..
if not defined PY set PY=python
for /f "delims=" %%i in ('%PY% -c "import sys;sys.path.insert(0,'python/common');import rc_config as r;print(r.latest_repair_dir() or '')"') do set REP=%%i
for /f "delims=" %%i in ('%PY% -c "import sys;sys.path.insert(0,'python/common');import rc_config as r;print(r.path('merge_out_dir'))"') do set OUT=%%i
if "%REP%"=="" (echo 未找到修复副本目录（config.json 的 repair_dir），将不使用修复副本。) else (echo 使用修复副本目录：%REP%)
if not "%REP%"=="" %PY% -c "import zipfile,glob;[zipfile.ZipFile(z).extractall(r'%REP%') for z in sorted(glob.glob(r'%REP%\repair_json*.zip'))]"
%PY% python\common\check_inputs.py
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
if not exist "%OUT%" mkdir "%OUT%"
for /f %%i in ('%PY% -c "import datetime;print(datetime.datetime.now().strftime('%%Y%%m%%d-%%H%%M'))"') do set TS=%%i
set RUNID=%TS%-v3
set LOG=%OUT%\%RUNID%.log
set RARG=
if not "%REP%"=="" set RARG=--repair-dir "%REP%"
echo [1/3] 合并（约几分钟）...
%PY% python\v3\claude_merge.v3.py --run-id %RUNID% %RARG% > "%LOG%" 2>&1
if errorlevel 1 goto FAIL
echo [2/3] 见证合并（核对两次结果一致）...
%PY% python\v3\claude_merge.v3.py --run-id %RUNID%-witness %RARG% >> "%LOG%" 2>&1
if errorlevel 1 goto FAIL
echo [3/3] 审计...
%PY% python\v3\claude_merge_audit.v3.py --run-dir "%OUT%\%RUNID%" --compare-dir "%OUT%\%RUNID%-witness" >> "%LOG%" 2>&1
set AUDIT_RC=%ERRORLEVEL%
type "%LOG%"
echo.
if not "%AUDIT_RC%"=="0" (echo [审计未通过] 不要导入：%OUT%\%RUNID%\reports\audit.json & pause & exit /b 1)
echo Done. 输出：%OUT%\%RUNID%
pause
exit /b 0
:FAIL
echo [合并失败] 见日志：%LOG%
type "%LOG%"
pause
exit /b 1
