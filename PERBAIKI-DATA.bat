@echo off
cd /d "%~dp0"
echo MMS Drilling - pemulihan database
echo Pastikan terminal aplikasi lama sudah ditutup.
python tools\restore_database.py
if errorlevel 1 goto gagal
echo.
echo Membuka aplikasi dengan database hasil pemulihan...
python app.py
pause
exit /b
:gagal
echo.
echo Baca pesan di atas. Jangan hapus database atau file WAL secara manual.
pause
exit /b 1
