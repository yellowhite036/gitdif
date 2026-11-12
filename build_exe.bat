@echo off
chcp 65001 >nul
REM ============================================
REM   One-click build: gitdiff.py -> dist\gitdiff.exe
REM   Double-click this file. It will:
REM     1. install PyInstaller if missing
REM     2. build a single-file gitdiff.exe
REM     3. copy SKILL.md next to the exe (the exe reads it from there)
REM ============================================

setlocal
cd /d "%~dp0"

if not exist "gitdiff.py" (
    echo Error: gitdiff.py not found in %CD%
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo Error: python not found in PATH.
    pause
    exit /b 1
)

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found, installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Error: failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Building gitdiff.exe ...
echo.

REM --specpath build : keep the generated .spec inside build\ instead of the project root
python -m PyInstaller --noconfirm --clean --onefile --name gitdiff --specpath build gitdiff.py
if errorlevel 1 (
    echo.
    echo Build FAILED. See the messages above.
    pause
    exit /b 1
)

if exist "SKILL.md" (
    copy /Y "SKILL.md" "dist\SKILL.md" >nul
    echo Copied SKILL.md to dist\
) else (
    echo Warning: SKILL.md not found, the exe will run without it.
)

echo.
echo ============================================
echo Done!  dist\gitdiff.exe  +  dist\SKILL.md
echo ============================================
pause
