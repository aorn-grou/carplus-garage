"""Rôles : Patron (tout), Caisse (argent + clients), Mécanicien (atelier, sans prix)."""
from functools import wraps

from django.core.exceptions import PermissionDenied

PATRON, CAISSE, MECANICIEN = "Patron", "Caisse", "Mécanicien"
ROLES = [PATRON, CAISSE, MECANICIEN]


def role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return PATRON
    noms = set(user.groups.values_list("name", flat=True))
    for r in ROLES:
        if r in noms:
            return r
    return MECANICIEN


def voit_argent(user):
    return role(user) in (PATRON, CAISSE)


def est_patron(user):
    return role(user) == PATRON


def exige(*roles_autorises):
    def deco(vue):
        @wraps(vue)
        def inner(request, *a, **kw):
            if role(request.user) not in roles_autorises:
                raise PermissionDenied("Accès réservé.")
            return vue(request, *a, **kw)
        return inner
    return deco
