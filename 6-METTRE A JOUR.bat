@echo off
title CAR PLUS - Mise a jour
chcp 65001 >nul
cd /d "%~dp0"
set RUN=venv\Scripts\python
if exist python\python.exe set RUN=python\python.exe
echo.
echo  =============================================
echo     CAR PLUS - Mise a jour (donnees conservees)
echo  =============================================
%RUN% outils\mettre_a_jour.py %1
pause
