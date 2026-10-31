@echo off
setlocal
set "SCRIPT=%~dp0clear-dsh-cookies.py"
set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED%" (
  "%BUNDLED%" "%SCRIPT%" %*
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python "%SCRIPT%" %*
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%SCRIPT%" %*
  goto done
)
echo [error] Python 3 not found. Reinstall DSH or install Python 3.
if "%~1"=="" pause
exit /b 1

:done
if errorlevel 1 if "%~1"=="" pause
exit /b %errorlevel%
