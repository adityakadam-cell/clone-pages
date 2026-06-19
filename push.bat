@echo off
REM ============================================================
REM  Universal one-click GitHub push
REM  Drop this .bat in ANY project folder and double-click it.
REM
REM  Usage:
REM    push.bat                         push to the remembered repo
REM    push.bat owner/repo              push to that repo (shorthand)
REM    push.bat https://github.com/o/r  push to that repo (full URL)
REM    push.bat owner/repo "my message" repo + commit message
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ===========================================
echo   Pushing this folder to GitHub
echo   Folder: %CD%
echo ===========================================
echo.

REM --- git installed? ---
where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not on PATH.
  echo Install it from https://git-scm.com/download/win then run this again.
  echo.
  pause
  exit /b 1
)

REM --- first time in this folder: initialise the repo ---
if not exist ".git" (
  echo Initialising git repository...
  git init >nul
  git branch -M main
)

REM --- what repo is currently configured? ---
set "CURRENT="
for /f "delims=" %%u in ('git remote get-url origin 2^>nul') do set "CURRENT=%%u"

REM --- decide the repo: argument 1  >  remembered origin  >  ask ---
set "INPUT=%~1"
if not defined INPUT (
  if defined CURRENT (
    set "INPUT=!CURRENT!"
  ) else (
    echo This folder has no GitHub repo yet.
    echo   - Full URL  e.g.  https://github.com/your-name/your-repo
    echo   - Or short  e.g.  your-name/your-repo
    echo.
    set /p "INPUT=Repository: "
  )
)
if not defined INPUT (
  echo [ERROR] No repository given and none remembered. Aborting.
  echo.
  pause
  exit /b 1
)

REM --- normalise: shorthand -> https URL, add .git if missing ---
set "REPO=!INPUT!"
echo !REPO! | findstr /b /i "http git@" >nul
if errorlevel 1 set "REPO=https://github.com/!REPO!"
echo !REPO! | findstr /e /i ".git" >nul
if errorlevel 1 set "REPO=!REPO!.git"

echo Using repository: !REPO!
echo.

REM --- point origin at the chosen repo (add if missing, else update) ---
if defined CURRENT (
  git remote set-url origin "!REPO!"
) else (
  git remote add origin "!REPO!"
)

REM --- commit message: argument 2, else timestamp ---
set "MSG=%~2"
if not defined MSG set "MSG=Update %date% %time%"

echo Staging all files...
git add -A
echo Committing: !MSG!
git commit -m "!MSG!" >nul 2>&1
if errorlevel 1 echo (Nothing new to commit - will still push.)

echo.
echo Pushing to GitHub...
git push -u origin main
if not errorlevel 1 goto :pushed

echo.
echo Normal push was rejected. Syncing with the remote and retrying...
git fetch origin >nul 2>&1
git push -u origin main --force-with-lease
if not errorlevel 1 goto :pushed
echo Safe force could not verify the remote. Doing a plain force...
git push -u origin main --force
if not errorlevel 1 goto :pushed

echo.
echo [ERROR] Push still failed. Common causes:
echo   - Signed in as the wrong GitHub account.
echo   - The repo !REPO! does not exist yet (create it on github.com).
echo   - You need a Personal Access Token instead of a password.
echo.
pause
exit /b 1

:pushed
echo.
echo ===========================================
echo   Done. Changes are on GitHub.
echo   !REPO!
echo ===========================================
echo.
pause
endlocal
