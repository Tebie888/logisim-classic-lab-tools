@echo off
rem ==============================================================
rem  launch-logisim.cmd  -  start classic Logisim (GUI)
rem
rem  Usage:
rem    launch-logisim.cmd                     open empty project
rem    launch-logisim.cmd D:\path\lab.circ    open a circuit
rem    launch-logisim.cmd -version            print version only
rem
rem  NOTE: this file is intentionally ASCII-only. cmd.exe parses .cmd
rem  files with the OEM code page, so non-ASCII paths inside the script
rem  corrupt the batch parser. Override the location with the
rem  LOGISIM_HUST_EXE environment variable when needed.
rem ==============================================================
setlocal enabledelayedexpansion

if not defined LOGISIM_HUST_EXE (
  echo [ERROR] Set LOGISIM_HUST_EXE to the Logisim executable path
  echo         Set LOGISIM_HUST_EXE to its full path and retry.
  pause
  exit /b 1
)

if "%~1"=="" (
  start "" "%LOGISIM_HUST_EXE%"
  exit /b 0
)

rem Options (-version / -help / -tty ...) run in this console; files open detached.
echo %~1 | findstr /b /c:"-" >nul 2>nul
if not errorlevel 1 (
  "%LOGISIM_HUST_EXE%" %*
  exit /b %ERRORLEVEL%
)

start "" "%LOGISIM_HUST_EXE%" %*
exit /b 0
