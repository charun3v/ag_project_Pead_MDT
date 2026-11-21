@echo off
title Pead MDT Clinical System Server
echo ========================================================
echo   Starting Paediatric Oncology MDT System (Django)
echo   Local Address: http://127.0.0.1:8000/
echo   Default Logins: admin (pass: admin123) or n3v (pass: admin123)
echo ========================================================
echo.
python manage.py runserver 127.0.0.1:8000
pause
