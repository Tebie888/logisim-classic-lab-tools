@echo off
rem ============================================================
rem  run-mcp.cmd  -  launch logisim-classic-lab-mcp (stdio MCP server)
rem
rem  Point your MCP client's "command" at the full path of this file.
rem
rem  NOTE: this file is intentionally ASCII-only. cmd.exe parses .cmd
rem  files using the OEM code page, so non-ASCII text inside a batch
rem  file corrupts the parser (including inside rem comments).
rem
rem  Env overrides:
rem    LOGISIM_HUST_EXE        full path to compatible Logisim executable
rem    LOGISIM_MCP_JAVA        full path to java.exe
rem    LOGISIM_MCP_WORKSPACE   fence: only files under this dir are touched
rem    LOGISIM_MCP_MAX_TIMEOUT simulation timeout cap in seconds (default 300)
rem ============================================================
setlocal
set "PYTHONIOENCODING=utf-8"
set "SCRIPT=%~dp0server.py"

set "PYEXE="
where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto run

where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto run

echo [ERROR] Python 3.8+ not found on PATH. Install it, or edit PYEXE in this script. 1>&2
exit /b 1

:run
%PYEXE% "%SCRIPT%" %*
exit /b %ERRORLEVEL%
