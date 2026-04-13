@echo off
setlocal
cd /d "%~dp0..\trade-mcp"
echo [test-trade-mcp-all-tools] Running AllMcpToolsSmokeTest...
call mvn -q test -Dtest=AllMcpToolsSmokeTest
if errorlevel 1 exit /b 1
echo [test-trade-mcp-all-tools] OK.
