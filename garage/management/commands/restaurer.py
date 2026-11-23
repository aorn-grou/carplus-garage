"""Restaure une sauvegarde .zip (remplace les données actuelles)."""
import shutil
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restaure une sauvegarde : python manage.py restaurer chemin\\vers\\fichier.zip"

    def add_arguments(self, parser):
        parser.add_argument("fichier")

    def handle(self, *a, fichier, **kw):
        f = Path(fichier)
        if not f.exists():
            raise CommandError(f"Fichier introuvable : {f}")
        # Sécurité : on sauvegarde d'abord l'état actuel
        call_command("sauvegarder", dossier=str(settings.BASE_DIR / "sauvegardes" / "avant_restauration"))
        base = Path(settings.DATABASES["default"]["NAME"])
        photos = Path(settings.MEDIA_ROOT)
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    raise CommandError("Sauvegarde invalide.")
            if photos.exists():
                shutil.rmtree(photos)
            for n in z.namelist():
                if n == "carplus.sqlite3":
                    with z.open(n) as s, open(base, "wb") as d:
                        shutil.copyfileobj(s, d)
                elif n.startswith("photos/") and not n.endswith("/"):
                    cible = photos / Path(n).relative_to("photos")
                    cible.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as s, open(cible, "wb") as d:
                        shutil.copyfileobj(s, d)
        self.stdout.write(self.style.SUCCESS("Restauration terminée."))
