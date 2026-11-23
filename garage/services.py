"""Alertes automatiques : entretiens qui arrivent à échéance (date ou kilométrage)."""
from django.utils import timezone

from .models import Entretien, Rappel


def generer_alertes_entretien():
    """Crée une alerte « À contacter » pour chaque entretien échu ou bientôt échu.

    Une seule alerte ouverte par entretien : pas de répétition inutile.
    """
    aujourd_hui = timezone.localdate()
    cache_km = {}
    crees = 0
    deja = set(Rappel.objects.filter(entretien__isnull=False).values_list("entretien_id", flat=True))
    for e in Entretien.objects.filter(actif=True).exclude(pk__in=deja).select_related("vehicule__proprietaire"):
        if not (e.prochain_km or e.prochaine_date):
            continue
        v = e.vehicule
        if v.pk not in cache_km:
            cache_km[v.pk] = v.km_estime()
        km = cache_km[v.pk]
        etat = e.etat(km_actuel=km, aujourd_hui=aujourd_hui)
        if etat == "ok":
            continue
        echeance = []
        if e.prochain_km:
            echeance.append(f"{e.prochain_km:,} km".replace(",", " "))
        if e.prochaine_date:
            echeance.append(e.prochaine_date.strftime("%d/%m/%Y"))
        motif = f"{e.designation} à prévoir (échéance : {' ou '.join(echeance)})"
        Rappel.objects.create(client=v.proprietaire, vehicule=v, entretien=e, motif=motif,
                              note=f"Kilométrage estimé aujourd'hui : {km:,} km".replace(",", " "),
                              date_prevue=aujourd_hui)
        crees += 1
    return crees
