"""Sauvegarde complète (base + photos) dans un fichier .zip daté."""
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sauvegarde la base de données et les photos."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", default=str(settings.BASE_DIR / "sauvegardes"))
        parser.add_argument("--garder", type=int, default=30, help="Nombre de sauvegardes à conserver")

    def handle(self, *a, dossier, garder, **kw):
        dossier = Path(dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        base = Path(settings.DATABASES["default"]["NAME"])
        if not base.exists():
            self.stdout.write("Aucune donnée à sauvegarder pour l'instant.")
            return
        nom = dossier / f"carplus_{datetime.now():%Y-%m-%d_%Hh%M}.zip"
        with tempfile.TemporaryDirectory() as tmp:
            copie = Path(tmp) / "carplus.sqlite3"
            src, dst = sqlite3.connect(base), sqlite3.connect(copie)
            with dst:
                src.backup(dst)      # copie sûre même pendant l'utilisation
            src.close(); dst.close()
            with zipfile.ZipFile(nom, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(copie, "carplus.sqlite3")
                photos = Path(settings.MEDIA_ROOT)
                if photos.exists():
                    for f in photos.rglob("*"):
                        if f.is_file():
                            z.write(f, Path("photos") / f.relative_to(photos))
        anciens = sorted(dossier.glob("carplus_*.zip"))[:-garder]
        for f in anciens:
            f.unlink()
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde créée : {nom}"))
