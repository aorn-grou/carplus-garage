@echo off
chcp 65001 >nul
title CAR PLUS - Preparer la version pour le client
cd /d "%~dp0"
echo.
echo  =====================================================================
echo   POUR LE CONCEPTEUR : prepare un dossier qui marche SANS installer
echo   Python chez le client. A faire une seule fois, sur VOTRE ordinateur,
echo   avec Internet. Ensuite copiez tout le dossier CARPLUS chez le client.
echo  =====================================================================
echo.
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if exist python\python.exe (
  echo  Le Python integre est deja present dans le dossier "python".
  goto fin
)
echo  [1/3] Telechargement de Python 3.13 integre (environ 11 Mo)...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip' -OutFile 'python-embed.zip'"
if errorlevel 1 goto erreur
echo  [2/3] Decompression...
powershell -NoProfile -Command "Expand-Archive -Path 'python-embed.zip' -DestinationPath 'python' -Force; $f = Get-ChildItem 'python\python*._pth' | Select-Object -First 1; (Get-Content $f.FullName) -replace '^#\s*import site','import site' | Set-Content $f.FullName; Add-Content $f.FullName '..'"
if errorlevel 1 goto erreur
del python-embed.zip
echo  [3/3] Installation des composants dans le Python integre...
%PY% -m pip install --no-index --find-links paquets --target python\Lib\site-packages --platform win_amd64 --python-version 3.13 --implementation cp --only-binary=:all: -r requirements.txt -q
if errorlevel 1 goto erreur
python\python.exe -c "import django, PIL, waitress, whitenoise; print('  Verification OK : Django', django.get_version())"
if errorlevel 1 goto erreur
:fin
echo.
echo  TERMINE. Pour livrer : copiez tout le dossier CARPLUS (avec le dossier "python")
echo  sur une cle USB, SANS les dossiers "donnees", "venv" et "sauvegardes" s'ils existent.
echo  Chez le client : double-clic sur "1-INSTALLER.bat" puis "2-LANCER CAR PLUS.bat".
pause
exit /b 0
:erreur
echo.
echo  Une erreur est survenue (Internet coupe ?). Envoyez une photo de cet ecran.
pause
exit /b 1
