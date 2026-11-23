@echo off
chcp 65001 >nul
cd /d "%~dp0"
set RUN=venv\Scripts\python
if exist python\python.exe set RUN=python\python.exe
title CAR PLUS - Sauvegarde
%RUN% manage.py sauvegarder
echo.
echo  Les sauvegardes sont dans le dossier "sauvegardes".
echo  Copiez le dernier fichier .zip sur une cle USB ou un disque externe.
explorer sauvegardes
pause
