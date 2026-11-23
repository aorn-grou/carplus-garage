@echo off
chcp 65001 >nul
title CAR PLUS - Installation
cd /d "%~dp0"
echo.
echo  =============================================
echo     CAR PLUS - Installation (une seule fois)
echo  =============================================
echo.
if exist python\python.exe (
  set RUN=python\python.exe
  echo  Python integre trouve : rien a installer.
  goto base
)
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo  ERREUR : Python 3.10 ou plus recent est necessaire sur cet ordinateur,
  echo  ou bien utilisez la version preparee pour le client (dossier "python").
  pause
  exit /b 1
)
%PY% --version
echo  [1/3] Preparation de l'environnement...
if not exist venv %PY% -m venv venv
if errorlevel 1 goto erreur
echo  [2/3] Installation des composants...
venv\Scripts\python -m pip install --no-index --find-links paquets -r requirements.txt -q
if errorlevel 1 (
  echo  Telechargement des composants par Internet...
  venv\Scripts\python -m pip install --find-links paquets -r requirements.txt -q
  if errorlevel 1 goto erreur
)
set RUN=venv\Scripts\python
:base
echo  [3/3] Creation de la base de donnees...
%RUN% manage.py migrate -v 0
if errorlevel 1 goto erreur
%RUN% manage.py collectstatic --noinput -v 0
%RUN% manage.py initialiser
if errorlevel 1 goto erreur
echo.
echo  INSTALLATION TERMINEE.
echo  Double-cliquez maintenant sur "2-LANCER CAR PLUS.bat".
echo  A la premiere ouverture, le patron cree lui-meme son compte.
echo.
pause
exit /b 0
:erreur
echo.
echo  Une erreur est survenue. Envoyez une photo de cet ecran a votre developpeur.
pause
exit /b 1
