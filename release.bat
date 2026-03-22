@echo off
:: ============================================================
:: release.bat — Build + tag + push a new GitHub release
::
:: Usage: .\release.bat 1.0.1
::   - Updates version.py
::   - Rebuilds the .exe
::   - Builds the installer
::   - Commits, tags, and pushes to GitHub
::   - GitHub Actions (or you manually) uploads the installer as a Release asset
::
:: Requirements:
::   - git installed and repo already connected to GitHub
::   - Inno Setup installed
::   - pyinstaller in PATH
:: ============================================================

title Releasing Study Companion...

:: Get version from argument
set VERSION=%1
if "%VERSION%"=="" (
    echo Usage: .\release.bat 1.0.1
    echo Example: .\release.bat 1.1.0
    pause & exit /b 1
)

echo.
echo  =============================================
echo   Releasing Study Companion v%VERSION%
echo  =============================================
echo.

:: Step 1: Update version.py
echo [1/6] Updating version.py to %VERSION%...
python -c "
content = open('version.py').read()
import re
new = re.sub(r'__version__ = \".*?\"', '__version__ = \"%VERSION%\"', content)
open('version.py', 'w').write(new)
print('version.py updated.')
"

:: Step 2: Rebuild icon
echo [2/6] Regenerating icon...
python create_icon.py

:: Step 3: PyInstaller
echo [3/6] Building .exe (2-4 minutes)...
pyinstaller study_companion.spec --clean --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed. & pause & exit /b 1 )

:: Step 4: Inno Setup — inject version number via /D flag
echo [4/6] Building installer...
set INNO=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO="C:\Program Files\Inno Setup 6\ISCC.exe"

if %INNO%=="" ( echo ERROR: Inno Setup not found. & pause & exit /b 1 )

mkdir installer_output 2>nul
%INNO% /DAppVersion=%VERSION% study_companion_installer.iss
if errorlevel 1 ( echo ERROR: Installer build failed. & pause & exit /b 1 )

:: Step 5: Git commit + tag
echo [5/6] Committing and tagging v%VERSION%...
git add -A
git commit -m "Release v%VERSION%"
git tag -a "v%VERSION%" -m "Release v%VERSION%"
git push origin main
git push origin "v%VERSION%"
if errorlevel 1 ( echo ERROR: Git push failed. Make sure your repo is set up. & pause & exit /b 1 )

:: Step 6: Instructions for uploading the release asset
echo [6/6] Almost done!
echo.
echo  =============================================
echo   v%VERSION% tagged and pushed to GitHub!
echo  =============================================
echo.
echo  Now upload the installer as a GitHub Release asset:
echo.
echo [6/6] Publishing GitHub Release...
gh release create v%VERSION% "installer_output\StudyCompanion_Setup_v%VERSION%.exe" --title "v%VERSION%" --generate-notes
if errorlevel 1 (
    echo ERROR: gh release failed. Is GitHub CLI installed?
    echo Install from: https://cli.github.com
) else (
    echo.
    echo  =============================================
    echo   DONE! v%VERSION% is live on GitHub.
    echo   Users will see the update banner automatically.
    echo  =============================================
)
pause
```

After that one edit, your entire release process for every future update forever is just:
```
.\release.bat 1.0.2
