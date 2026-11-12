@echo off
REM Builds "TikTok Downloader.exe" and its SHA-256 fingerprint in the dist folder.
REM Attach BOTH files to the GitHub release: the app refuses updates without the fingerprint.
cd /d "%~dp0"
echo Building TikTok Downloader... (1-3 minutes, keep this window open)
echo.

echo [1/3] Installing build tools...
python -m pip install -U -r requirements.txt pyinstaller > build.log 2>&1 || goto :fail

echo [2/3] Packing the app...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "TikTok Downloader" ^
  --collect-data customtkinter --collect-submodules yt_dlp main.py >> build.log 2>&1 || goto :fail
if not exist "dist\TikTok Downloader.exe" goto :missing

echo [3/3] Creating the safety fingerprint...
powershell -NoProfile -Command "(Get-FileHash 'dist\TikTok Downloader.exe' -Algorithm SHA256).Hash.ToLower() + '  TikTok Downloader.exe' | Set-Content -Encoding ascii 'dist\TikTok Downloader.exe.sha256'" || goto :fail

echo.
echo DONE. Upload BOTH files from the dist folder to your GitHub release:
echo   - TikTok Downloader.exe
echo   - TikTok Downloader.exe.sha256
explorer dist
pause
exit /b 0

:missing
echo.
echo The build finished but the .exe is missing.
echo Your antivirus probably removed it. Allow it in Windows Security ^> Protection history,
echo or add this folder as an exclusion, then run build.bat again.
pause
exit /b 1

:fail
echo.
echo Build failed. The details are in build.log (send it to Claude).
pause
exit /b 1
