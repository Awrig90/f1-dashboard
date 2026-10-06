@echo off
setlocal
cd /d "%~dp0"

if exist .venv\Scripts\python.exe goto install

echo First run: creating isolated Python environment...

rem Prefer the standard Windows Python launcher when available.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
  if not errorlevel 1 goto checkvenv
)

rem Fall back to python on PATH.
where python >nul 2>&1
if not errorlevel 1 (
  python -m venv .venv
  if not errorlevel 1 goto checkvenv
)

rem Common Anaconda/Miniconda locations for machines where Python is not on PATH.
if exist "%USERPROFILE%\anaconda3\python.exe" (
  "%USERPROFILE%\anaconda3\python.exe" -m venv .venv
  if not errorlevel 1 goto checkvenv
)
if exist "%USERPROFILE%\miniconda3\python.exe" (
  "%USERPROFILE%\miniconda3\python.exe" -m venv .venv
  if not errorlevel 1 goto checkvenv
)

echo Python could not be found automatically.
echo Install Python 3 or Anaconda, or run the app from an environment where python is available.
goto fail

:checkvenv
if not exist .venv\Scripts\python.exe goto fail

:install
if not exist .venv\dashboard-installed (
  echo Installing dashboard requirements into .venv...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  echo installed>.venv\dashboard-installed
)

echo Starting F1 Session Lab...
.venv\Scripts\python.exe -m streamlit run app.py
if errorlevel 1 goto fail
exit /b 0

:fail
echo Setup or startup failed. See the message above and README.md.
pause
exit /b 1
