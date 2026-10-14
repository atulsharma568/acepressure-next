@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
 echo Install Node.js 20 or newer from https://nodejs.org/, then rerun this file.
 pause
 exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
 echo npm was not found. Reinstall Node.js with npm enabled, then rerun this file.
 pause
 exit /b 1
)
if not exist "web\package.json" (
 echo web\package.json was not found. This is not a complete AcePressure package.
 pause
 exit /b 1
)
if not exist "web\package-lock.json" (
 echo web\package-lock.json was not found. Refusing to install an unpinned dependency tree.
 pause
 exit /b 1
)

pushd web
npm ci
if errorlevel 1 goto fail
if not exist ".env.local" copy /y "env.example" ".env.local" >nul
popd
echo Next frontend installation complete.
echo Start AcePressure first, then run Start_Web.bat.
pause
exit /b 0

:fail
popd
echo Web installation failed. Review the npm error above; no application data was changed.
pause
exit /b 1
