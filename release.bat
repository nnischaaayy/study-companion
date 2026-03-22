@echo off
:: ============================================================
:: release.bat — One command full release pipeline
:: Usage: .\release.bat 1.0.4
:: ============================================================

title Releasing Study Companion...

set VERSION=%1
if "%VERSION%"=="" (
    echo.
    echo  Usage: .\release.bat 1.0.4
    echo.
    goto :END
)

echo.
echo  =============================================
echo   Releasing Study Companion v%VERSION%
echo  =============================================
echo.

:: Step 1: Update version.py
echo [1/6] Updating version.py to %VERSION%...
python -c "import re; f=open('version.py', encoding='utf-8'); c=f.read(); f.close(); c=re.sub(r'__version__ = \".*?\"','__version__ = \"%VERSION%\"',c); f=open('version.py','w', encoding='utf-8'); f.write(c); f.close(); print('Done.')"
if errorlevel 1 ( echo ERROR: Could not update version.py & goto :END )

:: Step 2: Rebuild icon
echo [2/6] Regenerating icon...
python create_icon.py

:: Step 3: PyInstaller
echo [3/6] Building .exe (this takes 2-4 minutes, please wait)...
pyinstaller study_companion.spec --clean --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed. & goto :END )
if not exist "dist\StudyCompanion.exe" ( echo ERROR: .exe not found after build. & goto :END )

:: Step 4: Inno Setup
echo [4/6] Building installer...
set INNO=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO=C:\Program Files\Inno Setup 6\ISCC.exe
if not defined INNO ( echo ERROR: Inno Setup not found. Install from https://jrsoftware.org/isinfo.php & goto :END )

mkdir installer_output 2>nul
"%INNO%" /DAppVersion=%VERSION% study_companion_installer.iss
if errorlevel 1 ( echo ERROR: Installer build failed. & goto :END )

:: Step 5: Git commit + tag + push
echo [5/6] Committing and pushing to GitHub...
git add -A
git commit -m "Release v%VERSION%" 2>nul
git tag -a "v%VERSION%" -m "Release v%VERSION%"
git push origin main
git push origin "v%VERSION%"
if errorlevel 1 ( echo ERROR: Git push failed. Run: git remote -v to check your repo is connected. & goto :END )

:: Step 6: Publish GitHub Release
echo [6/6] Publishing GitHub Release...
gh release create "v%VERSION%" "installer_output\StudyCompanion_Setup_v%VERSION%.exe" --title "v%VERSION%" --generate-notes
if errorlevel 1 ( echo ERROR: gh release failed. Make sure GitHub CLI is installed and you ran: gh auth login & goto :END )

echo.
echo  =============================================
echo   SUCCESS! v%VERSION% is live on GitHub.
echo   Users will see the update banner next launch.
echo  =============================================
echo.

:END
echo  Done. You can close this window.