@echo off
setlocal
cd /d "%~dp0"
if not exist "web\node_modules\.bin\next.cmd" (
 echo Run Install_Web.bat first.
 pause
 exit /b 1
)
pushd web
npm run dev
popd
if errorlevel 1 pause
