@echo off
REM Fuel price robot: double-click to collect the latest prices and open the dashboard.
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
echo.
echo ===== Fuel price robot =====
echo.

REM ---- Find a real Python 3.9+ ----
set "PY="
call :try py -3
if not defined PY call :try python
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-3*") do if not defined PY call :tryfile "%%~D\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :tryfile "%%~D\python.exe"
if not defined PY for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PY call :tryfile "%%~D\python.exe"
if not defined PY goto nopython

REM ---- Project environment (built once, reused after that) ----
set "VPY=.venv\Scripts\python.exe"
set "RETRIED="
:makevenv
if exist "%VPY%" "%VPY%" -c "import sys" >nul 2>nul
if exist "%VPY%" if errorlevel 1 rmdir /s /q ".venv"
if exist ".venv" if not exist "%VPY%" rmdir /s /q ".venv"
if not exist "%VPY%" (
    echo Setting up a private Python environment ^(first time only^)...
    %PY% -m venv .venv
)
if not exist "%VPY%" goto nopython
if not exist ".venv\installed.flag" (
    echo Installing packages ^(first time only, about a minute^)...
    "%VPY%" -m pip install -q --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto pipfailed
    echo ok> ".venv\installed.flag"
)
:afterinstall

echo.
echo Asking GOV.UK for the latest prices...
"%VPY%" -m robot.run
echo.
REM Skip Streamlit's one-time "enter your email" question so it doesn't sit waiting
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)
echo Opening the dashboard in your browser.
echo Leave this window open while you use it. Close it to stop the dashboard.
echo.
"%VPY%" -m streamlit run dashboard.py --browser.gatherUsageStats false
pause
exit /b 0

:try
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:tryfile
if not exist "%~1" exit /b 0
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set PY="%~1"
exit /b 0

:pipfailed
REM Brand-new Python versions sometimes lack ready-made packages. Use uv to fetch Python 3.13 just for
REM this project (downloaded into your user folder, no admin rights or Microsoft Store needed).
if defined RETRIED goto fail
set "RETRIED=1"
echo.
echo Some packages don't support this brand-new Python yet.
echo Switching this project to Python 3.13 (downloaded automatically, about 2 minutes)...
if not exist ".tools\Scripts\python.exe" %PY% -m venv .tools
".tools\Scripts\python.exe" -m pip install -q --disable-pip-version-check uv
if errorlevel 1 goto fail
rmdir /s /q ".venv"
".tools\Scripts\uv.exe" venv .venv --python 3.13 --seed
if not exist "%VPY%" goto fail
echo Installing packages with Python 3.13...
"%VPY%" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail
echo ok> ".venv\installed.flag"
goto afterinstall

:nopython
echo Couldn't find Python 3.9 or newer. Install it from https://www.python.org/downloads/ and run this again.
pause
exit /b 1

:fail
echo.
echo Something went wrong installing packages. Check the error message above.
pause
exit /b 1
