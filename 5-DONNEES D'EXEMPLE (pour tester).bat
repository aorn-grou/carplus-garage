@echo off
chcp 65001 >nul
cd /d "%~dp0"
set RUN=venv\Scripts\python
if exist python\python.exe set RUN=python\python.exe
title CAR PLUS - Donnees d'exemple
echo.
echo  Ajoute des clients, vehicules et reparations d'EXEMPLE pour tester.
echo  A utiliser seulement pour essayer, PAS sur l'installation reelle du garage.
echo.
set /p OK=Tapez OUI puis Entree pour continuer : 
if /i not "%OK%"=="OUI" exit /b 0
%RUN% manage.py donnees_demo
pause
