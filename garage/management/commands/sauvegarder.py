"""Sauvegarde complète (base + photos) dans un fichier .zip daté."""
from django.conf import settings
from django.core.management.base import BaseCommand

from garage.donnees import creer_sauvegarde


class Command(BaseCommand):
    help = "Sauvegarde la base de données et les photos."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", default=str(settings.BASE_DIR / "sauvegardes"))
        parser.add_argument("--garder", type=int, default=30, help="Nombre de sauvegardes à conserver")

    def handle(self, *a, dossier, garder, **kw):
        nom = creer_sauvegarde(dossier, garder)
        if not nom:
            self.stdout.write("Aucune donnée à sauvegarder pour l'instant.")
            return
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde créée : {nom}"))
