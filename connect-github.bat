@echo off
REM ============================================================
REM  Connect this folder to a GitHub repository (set 'origin').
REM  Use this ONCE to link / re-link / FIX the remote.
REM  It does NOT commit or push - run push.bat for that.
REM
REM  Usage:
REM    connect-github.bat                    ask for the repo
REM    connect-github.bat owner/repo         connect to that repo
REM    connect-github.bat https://github.com/owner/repo
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ===========================================
echo   Connect folder to GitHub
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

REM --- make this folder a git repo if it isn't one ---
if not exist ".git" (
  echo Initialising git repository...
  git init
  git branch -M main
)

REM --- show what is currently connected ---
set "CURRENT="
for /f "delims=" %%u in ('git remote get-url origin 2^>nul') do set "CURRENT=%%u"
if defined CURRENT (
  echo Currently connected to: !CURRENT!
) else (
  echo Not connected to any repository yet.
)
echo.

REM --- repo from argument, else ask ---
set "INPUT=%~1"
if not defined INPUT (
  echo Enter the GitHub repository to connect to.
  echo   - Full URL  e.g.  https://github.com/your-name/your-repo
  echo   - Or short  e.g.  your-name/your-repo
  echo.
  set /p "INPUT=Repository: "
)
if not defined INPUT (
  echo [ERROR] No repository entered. Aborting.
  echo.
  pause
  exit /b 1
)

REM --- normalise: shorthand -> full URL ---
set "REPO=!INPUT!"
echo !REPO! | findstr /b /i "http git@" >nul
if errorlevel 1 set "REPO=https://github.com/!REPO!"

REM --- collapse any repeated .git suffix to exactly one ---
:fixgit
echo !REPO! | findstr /e /i ".git.git" >nul
if not errorlevel 1 (
  set "REPO=!REPO:~0,-4!"
  goto :fixgit
)
echo !REPO! | findstr /e /i ".git" >nul
if errorlevel 1 set "REPO=!REPO!.git"

echo.
echo Connecting to: !REPO!

REM --- set or add origin ---
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "!REPO!"
) else (
  git remote set-url origin "!REPO!"
)

REM --- verify the repo actually exists / is reachable ---
echo.
echo Checking the repository is reachable...
git ls-remote "!REPO!" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [WARNING] Could not reach !REPO!
  echo   - Check the owner/name spelling.
  echo   - Create the repo on github.com if it does not exist.
  echo   - You may be prompted to sign in / use a Personal Access Token.
  echo The remote was still saved; fix the above and run push.bat.
) else (
  echo OK - repository found and connected.
)

echo.
echo Current remotes:
git remote -v
echo.
echo Done. Now run push.bat to upload your code.
echo.
pause
endlocal
