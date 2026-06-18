@echo off
REM ============================================================
REM  API-Agent  -  one-click push to GitHub
REM  Double-click this file to upload all changes.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "REPO=https://github.com/adityakadam-cell/clone-pages.git"

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

REM --- point 'origin' at the repo (add if missing, else update) ---
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "%REPO%"
) else (
  git remote set-url origin "%REPO%"
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
  echo   - The repo %REPO% does not exist yet.
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
