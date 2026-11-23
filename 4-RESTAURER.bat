@echo off
chcp 65001 >nul
cd /d "%~dp0"
set RUN=venv\Scripts\python
if exist python\python.exe set RUN=python\python.exe
title CAR PLUS - Restauration
echo.
echo  ATTENTION : la restauration remplace les donnees actuelles
echo  (une copie de securite est faite automatiquement avant).
echo  Fermez d'abord la fenetre "CAR PLUS" si elle est ouverte.
echo.
set /p FICHIER=Glissez ici le fichier .zip de sauvegarde puis appuyez sur Entree : 
%RUN% manage.py restaurer %FICHIER%
pause
