@echo off
title CAR SERVICE PLUS - NE PAS FERMER CETTE FENETRE
chcp 65001 >nul
cd /d "%~dp0"
set RUN=venv\Scripts\python
if exist python\python.exe set RUN=python\python.exe
if not exist %RUN% (
  echo  Lancez d'abord "1-INSTALLER.bat".
  pause
  exit /b 1
)
%RUN% outils\lancer.py
pause
