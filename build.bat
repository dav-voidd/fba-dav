@echo off
REM Builds a standalone "TikTok Downloader.exe" in the dist folder.
cd /d "%~dp0"
python -m pip install -U -r requirements.txt pyinstaller || goto :fail
python -m PyInstaller --noconfirm --onefile --windowed --name "TikTok Downloader" ^
  --collect-data customtkinter --collect-submodules yt_dlp --collect-all curl_cffi main.py || goto :fail
echo.
echo Done: dist\TikTok Downloader.exe
pause
exit /b 0
:fail
echo Build failed - see the messages above.
pause
exit /b 1
