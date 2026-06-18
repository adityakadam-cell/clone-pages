@echo off
REM ============================================================
REM  API-Agent  -  one-click push to GitHub
REM  Double-click this file to upload all changes.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ===========================================
echo   API-Agent : pushing to GitHub
echo ===========================================
echo.

REM --- make sure git is installed ---
where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not on PATH.
  echo Install it from https://git-scm.com/download/win then run this again.
  echo.
  pause
  exit /b 1
)

REM --- first time: initialise the repo ---
if not exist ".git" (
  echo Initialising git repository...
  git init
  git branch -M main
)

REM --- show the repo currently configured (if any) ---
set "CURRENT="
for /f "delims=" %%u in ('git remote get-url origin 2^>nul') do set "CURRENT=%%u"
if defined CURRENT (
  echo Current repository: !CURRENT!
) else (
  echo No repository is set yet.
)
echo.

REM --- ask which repository to push to ---
echo Enter the GitHub repository to push to.
echo   - Full URL  e.g.  https://github.com/your-name/your-repo.git
echo   - Or short  e.g.  your-name/your-repo
if defined CURRENT echo   - Or just press Enter to keep the current one.
echo.
set "INPUT="
set /p "INPUT=Repository: "

REM --- decide the final repo URL ---
set "REPO="
if "%INPUT%"=="" (
  if defined CURRENT (
    set "REPO=!CURRENT!"
  ) else (
    echo [ERROR] No repository entered and none is set. Aborting.
    echo.
    pause
    exit /b 1
  )
) else (
  set "REPO=%INPUT%"
  REM if it doesn't start with http, treat it as owner/repo shorthand
  echo !REPO! | findstr /b /i "http" >nul
  if errorlevel 1 set "REPO=https://github.com/!REPO!"
  REM append .git if missing
  echo !REPO! | findstr /e /i ".git" >nul
  if errorlevel 1 set "REPO=!REPO!.git"
)

echo.
echo Using repository: !REPO!
echo.

REM --- point 'origin' at the chosen repo (add if missing, else update) ---
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "!REPO!"
) else (
  git remote set-url origin "!REPO!"
)

REM --- ask for a commit message (Enter = automatic timestamp) ---
set "MSG="
set /p "MSG=Enter a short message describing your change (or press Enter): "
if "%MSG%"=="" set "MSG=Update %date% %time%"

echo.
echo Staging all files...
git add -A

echo Committing...
git commit -m "%MSG%"
if errorlevel 1 echo (Nothing new to commit - will still push.)

echo.
echo Pushing to GitHub...
git push -u origin main
if errorlevel 1 (
  echo.
  echo [ERROR] Push failed. Common causes:
  echo   - You are signed in as the wrong GitHub account.
  echo   - The repo !REPO! does not exist yet.
  echo   - The remote has commits you don't have locally
  echo       ^(fix once with:  git push -u origin main --force^).
  echo   - You need a Personal Access Token instead of a password.
  echo.
  pause
  exit /b 1
)

echo.
echo ===========================================
echo   Done. Changes are on GitHub.
echo ===========================================
echo.
pause
endlocal
