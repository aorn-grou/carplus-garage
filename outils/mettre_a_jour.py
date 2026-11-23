"""Mise à jour de CAR PLUS en un double-clic, sans perdre les données.

Cherche le fichier de mise à jour le plus récent (CARPLUS_MAJ_x.y.zip) :
dans ce dossier, le dossier parent, Téléchargements, et les clés USB.
1. sauvegarde complète  2. remplace uniquement le programme  3. met la base à jour.
Les dossiers « donnees », « sauvegardes », « python » et « venv » ne sont jamais touchés.
"""
import os
import re
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REMPLACES = ["config", "garage", "outils", "manage.py", "requirements.txt", "VERSION", "MODE D'EMPLOI.txt", "paquets"]
MOTIF = re.compile(r"CARPLUS_MAJ_(\d+(?:\.\d+)*)\.zip$", re.I)


def version(txt):
    return tuple(int(x) for x in txt.strip().split("."))


def version_installee():
    try:
        return version((RACINE / "VERSION").read_text())
    except Exception:
        return (0,)


def dossiers_a_fouiller():
    home = Path.home()
    lieux = [RACINE, RACINE.parent, RACINE.parent.parent, home / "Downloads", home / "Téléchargements",
             home / "Desktop", home / "Bureau"]
    for lettre in string.ascii_uppercase[2:]:
        for sous in ("", "Telechargements", "Téléchargements", "Downloads"):
            lieux.append(Path(f"{lettre}:\\") / sous)
    return [p for p in lieux if p.exists()]


def trouver_maj():
    if len(sys.argv) > 1 and Path(sys.argv[1].strip('"')).exists():
        f = Path(sys.argv[1].strip('"'))
        m = MOTIF.search(f.name)
        return f, version(m.group(1)) if m else (999,)
    meilleur = None
    for d in dossiers_a_fouiller():
        try:
            for f in d.iterdir():
                m = MOTIF.search(f.name)
                if m and f.is_file():
                    v = version(m.group(1))
                    if not meilleur or v > meilleur[1]:
                        meilleur = (f, v)
        except OSError:
            pass
    return meilleur


def logiciel_ouvert():
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", 8000)) == 0
    finally:
        s.close()


def depot():
    try:
        return (RACINE / "outils" / "source.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def version_en_ligne(timeout=6):
    """Version publiée sur Internet, ou None (pas d'Internet, dépôt absent…)."""
    import urllib.request
    d = depot()
    if not d:
        return None
    try:
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{d}/main/VERSION", timeout=timeout) as r:
            return version(r.read().decode())
    except Exception:
        return None


def telecharger(timeout=60):
    import urllib.request
    dest = Path(tempfile.gettempdir()) / "carplus_maj_en_ligne.zip"
    with urllib.request.urlopen(f"https://codeload.github.com/{depot()}/zip/refs/heads/main", timeout=timeout) as r, \
            open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def maj_en_ligne(silencieux=False):
    """Vérifie Internet et installe la nouvelle version si elle existe. Renvoie True si mise à jour faite."""
    actuelle, enligne = version_installee(), version_en_ligne()
    if not enligne or enligne <= actuelle:
        if not silencieux:
            print("  En ligne : " + ("pas de connexion Internet." if not enligne else "le logiciel est déjà à jour."))
        return False
    print(f"  Nouvelle version disponible : {'.'.join(map(str, enligne))}. Téléchargement...")
    try:
        f = telecharger()
    except Exception as e:
        print(f"  Téléchargement impossible ({e}). On continue avec la version actuelle.")
        return False
    return appliquer(f, enligne) == 0


def main():
    actuelle = version_installee()
    print(f"\n  Version installée : {'.'.join(map(str, actuelle))}")
    if maj_en_ligne():
        return 0
    trouve = trouver_maj()
    if not trouve:
        print("  Aucun fichier de mise à jour trouvé (CARPLUS_MAJ_....zip).")
        print("  Téléchargez-le, ou mettez-le sur une clé USB, puis relancez.")
        return 1
    fichier, nouvelle = trouve
    print(f"  Mise à jour trouvée : {fichier}  (version {'.'.join(map(str, nouvelle))})")
    if nouvelle <= actuelle:
        print("  Le logiciel est déjà à jour. Rien à faire.")
        return 0
    return appliquer(fichier, nouvelle)


def appliquer(fichier, nouvelle):
    if logiciel_ouvert():
        print("\n  Fermez d'abord la fenêtre noire « CAR PLUS - NE PAS FERMER » puis relancez la mise à jour.")
        return 1
    py = sys.executable
    print("  [1/3] Sauvegarde complète des données...")
    if (RACINE / "donnees" / "carplus.sqlite3").exists():
        subprocess.run([py, str(RACINE / "manage.py"), "sauvegarder",
                        "--dossier", str(RACINE / "sauvegardes" / "avant_mise_a_jour")], check=True, cwd=RACINE)
    print("  [2/3] Remplacement du programme (les données ne sont pas touchées)...")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(fichier) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    print("  Fichier de mise à jour invalide.")
                    return 1
            z.extractall(tmp)
        src = Path(tmp)
        if (src / "CARPLUS").is_dir():
            src = src / "CARPLUS"
        else:   # archive GitHub : un seul dossier « depot-main »
            dossiers = [d for d in src.iterdir() if d.is_dir()]
            if len(dossiers) == 1 and (dossiers[0] / "manage.py").exists():
                src = dossiers[0]
        if not (src / "manage.py").exists() or not (src / "garage").is_dir():
            print("  Ce fichier n'est pas une mise à jour CAR PLUS.")
            return 1
        for nom in REMPLACES:
            s, d = src / nom, RACINE / nom
            if not s.exists():
                continue
            if d.is_dir():
                shutil.rmtree(d)
            elif d.exists():
                d.unlink()
            shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
        for bat in src.glob("*.bat"):     # les raccourcis (.bat), sauf ceux qui peuvent être en cours d'exécution
            if bat.name.startswith(("2-", "6-")):
                continue
            shutil.copy2(bat, RACINE / bat.name)
    print("  [3/3] Mise à jour de la base de données...")
    subprocess.run([py, "manage.py", "migrate", "-v", "0"], check=True, cwd=RACINE)
    subprocess.run([py, "manage.py", "collectstatic", "--noinput", "-v", "0"], check=True, cwd=RACINE)
    subprocess.run([py, "manage.py", "initialiser"], check=True, cwd=RACINE)
    print(f"\n  MISE A JOUR TERMINEE : version {'.'.join(map(str, nouvelle))}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError:
        print("\n  Erreur pendant la mise à jour. Les données ont été sauvegardées dans « sauvegardes\\avant_mise_a_jour ».")
        print("  Envoyez une photo de cet écran à votre développeur.")
        sys.exit(1)
