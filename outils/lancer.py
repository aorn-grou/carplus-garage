"""Démarrage de CAR SERVICE PLUS : mise à jour automatique (si Internet), base à jour, puis lancement.

Appelé par « 2-LANCER CAR PLUS.bat ». Les données ne sont jamais touchées par la mise à jour.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PY = sys.executable


def manage(*args):
    return subprocess.run([PY, str(RACINE / "manage.py"), *args], cwd=RACINE).returncode


def main():
    os.chdir(RACINE)
    if "--apres-maj" not in sys.argv:
        sys.path.insert(0, str(RACINE / "outils"))
        try:
            import mettre_a_jour
            print("  Recherche d'une mise à jour sur Internet...")
            if mettre_a_jour.maj_en_ligne(silencieux=True):
                # relancer avec le nouveau programme
                sys.exit(subprocess.run([PY, str(RACINE / "outils" / "lancer.py"), "--apres-maj"], cwd=RACINE).returncode)
            print("  Logiciel à jour.")
        except Exception as e:      # jamais bloquant : sans Internet, on démarre normalement
            print(f"  (Mise à jour automatique impossible : {e})")
    if manage("migrate", "-v", "0") != 0:
        print("  Erreur de base de données. Envoyez une photo de cet écran à votre développeur.")
        return 1
    manage("collectstatic", "--noinput", "-v", "0")
    manage("initialiser")
    threading.Thread(target=lambda: (time.sleep(3), webbrowser.open("http://localhost:8000")), daemon=True).start()
    return manage("demarrer", "--port", "8000")


if __name__ == "__main__":
    sys.exit(main())
