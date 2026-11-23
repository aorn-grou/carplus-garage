"""Prépare le logiciel : rôles et paramètres. Le compte du patron est créé dans le navigateur, au premier lancement."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from garage.models import Parametres
from garage.roles import ROLES


class Command(BaseCommand):
    help = "Prépare les rôles (à lancer à l'installation)."

    def handle(self, *a, **kw):
        for r in ROLES:
            Group.objects.get_or_create(name=r)
        Parametres.get()
        self.stdout.write("Préparation terminée. Le compte du patron sera créé à la première ouverture du logiciel.")
