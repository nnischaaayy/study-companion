@echo off
:: ============================================================
:: build.bat — One-click build for Study Companion
:: Run this from inside D:\projects\study_companion\
:: ============================================================

title Building Study Companion...
echo.
echo  =============================================
echo   Study Companion — Windows App Builder
echo  =============================================
echo.

:: Step 1: Install build tools
echo [1/5] Installing build dependencies...
pip install pyinstaller pillow --quiet
if errorlevel 1 ( echo ERROR: pip failed. Make sure Python is in PATH. & pause & exit /b 1 )

:: Step 2: Generate icon
echo [2/5] Generating app icon...
python create_icon.py
if errorlevel 1 ( echo WARNING: Icon generation failed, using default. )

:: Step 3: PyInstaller — bundle into .exe
echo [3/5] Bundling app into .exe (this takes 2-4 minutes)...
pyinstaller study_companion.spec --clean --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed. See errors above. & pause & exit /b 1 )

:: Step 4: Verify output
if not exist "dist\StudyCompanion.exe" (
    echo ERROR: dist\StudyCompanion.exe was not created.
    pause & exit /b 1
)
echo [4/5] .exe created successfully!

:: Step 5: Check for Inno Setup and build installer
echo [5/5] Looking for Inno Setup to build installer...

set INNO=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO="C:\Program Files\Inno Setup 6\ISCC.exe"

if %INNO%=="" (
    echo.
    echo  Inno Setup not found.
    echo  To build the installer:
    echo    1. Download from https://jrsoftware.org/isinfo.php
    echo    2. Install it
    echo    3. Run this script again, OR open study_companion_installer.iss manually
    echo.
    echo  For now, your .exe is ready at:
    echo    dist\StudyCompanion.exe
    echo  You can run it directly or create a shortcut manually.
) else (
    mkdir installer_output 2>nul
    %INNO% study_companion_installer.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup build failed.
    ) else (
        echo.
        echo  =============================================
        echo   SUCCESS! Installer created in:
        echo   installer_output\StudyCompanion_Setup_v1.0.0.exe
        echo  =============================================
        echo.
        echo  Run the installer to:
        echo    - Install to Program Files
        echo    - Add to Start Menu (searchable!)
        echo    - Pin to Taskbar
        echo    - Add uninstaller to Add/Remove Programs
    )
)

echo.
pause
