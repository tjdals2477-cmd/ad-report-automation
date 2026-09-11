@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "AD_REPORT_PYTHON=C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%AD_REPORT_PYTHON%" goto python_found

where python >nul 2>nul
if not errorlevel 1 (
  set "AD_REPORT_PYTHON=python"
  goto python_found
)

echo Python을 찾을 수 없습니다. Python 3.11 이상을 설치해주세요.
pause
exit /b 1

:python_found

"%AD_REPORT_PYTHON%" -c "import openpyxl" >nul 2>nul
if errorlevel 1 (
  echo 필요한 패키지 openpyxl이 없습니다.
  echo 명령 프롬프트에서 pip install openpyxl 을 실행한 뒤 다시 시도해주세요.
  pause
  exit /b 1
)

"%AD_REPORT_PYTHON%" server.py
if errorlevel 1 pause
