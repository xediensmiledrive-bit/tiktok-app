@echo off
REM Doi giong hang loat tren may Windows.
REM Dat file nay canh thu muc scripts\ roi bam doi, hoac chay tu Command Prompt.
setlocal

REM --- Sua hai dong nay cho khop may anh ---
set INPUT=Y:\CLAUDE\Workflow Automation\Change-tone\Video dau vao
set OUTPUT=Y:\CLAUDE\Workflow Automation\Change-tone\Video da doi giong

REM Khoa API doc tu bien moi truong hoac tu file .env canh config.json
if "%ELEVENLABS_API_KEY%"=="" (
  if not exist "%~dp0.env" (
    echo [LOI] Chua co ELEVENLABS_API_KEY.
    echo       Tao file .env canh file nay voi mot dong:
    echo       ELEVENLABS_API_KEY=xi_...
    pause & exit /b 1
  )
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua co ffmpeg trong PATH.
  echo       Cai bang: winget install Gyan.FFmpeg
  echo       Roi MO LAI Command Prompt.
  pause & exit /b 1
)

python -c "import requests" 2>nul
if errorlevel 1 (
  echo Dang cai thu vien requests...
  python -m pip install requests || (echo [LOI] khong cai duoc & pause & exit /b 1)
)

if not exist "%OUTPUT%" mkdir "%OUTPUT%"

echo.
echo ============================================================
echo  PHA 1 — boc chu va chuyen tu vung Bac sang Nam
echo  Chua doc, chua ton nhieu credit.
echo ============================================================
python "%~dp0scripts\batch.py" --pha 1 --input "%INPUT%" --output "%OUTPUT%"
if errorlevel 1 (echo. & echo Pha 1 co loi, xem o tren. & pause & exit /b 1)

echo.
echo ============================================================
echo  Gio mo thu muc work\ doc cac file nam.txt
echo  Sua cau nao sai roi luu lai. Xong thi bam phim bat ky.
echo ============================================================
pause

echo.
echo ============================================================
echo  PHA 2 — doc lai bang giong mien Nam va ghep clip
echo ============================================================
python "%~dp0scripts\batch.py" --pha 2 --input "%INPUT%" --output "%OUTPUT%"

echo.
echo Xong. Clip ket qua nam trong: %OUTPUT%
pause
