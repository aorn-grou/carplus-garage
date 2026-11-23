"""Listes de départ modifiables par le garage.

Seulement des NOMS : aucun intervalle (km/mois) n'est inventé.
Le patron saisit ses intervalles dans Administration > Types d'entretien.
"""
from django.db import migrations

SYSTEMES = [
    "Moteur", "Injection / alimentation", "Refroidissement", "Distribution", "Embrayage", "Boîte de vitesses",
    "Transmission / cardans", "Pont / différentiel", "Train avant", "Train arrière", "Suspension / amortisseurs",
    "Direction", "Freins", "Pneus / roues", "Échappement", "Électricité / batterie", "Démarrage / charge",
    "Éclairage", "Climatisation", "Carrosserie", "Peinture", "Vitrage", "Intérieur", "Chaîne / kit transmission (moto)",
    "Carénage (moto)", "Autre",
]

ENTRETIENS = [
    "Vidange huile moteur + filtre à huile", "Filtre à air", "Filtre à carburant", "Filtre d'habitacle",
    "Bougies", "Courroie de distribution", "Courroie d'accessoires", "Plaquettes de frein avant",
    "Plaquettes de frein arrière", "Disques de frein", "Liquide de frein", "Liquide de refroidissement",
    "Huile de boîte de vitesses", "Huile de pont / différentiel", "Pneus", "Batterie", "Amortisseurs",
    "Recharge climatisation", "Kit chaîne (moto)", "Contrôle général",
]


def remplir(apps, schema_editor):
    Systeme = apps.get_model("garage", "Systeme")
    TypeEntretien = apps.get_model("garage", "TypeEntretien")
    for n in SYSTEMES:
        Systeme.objects.get_or_create(nom=n)
    for n in ENTRETIENS:
        TypeEntretien.objects.get_or_create(nom=n)


class Migration(migrations.Migration):
    dependencies = [("garage", "0002_carnet_entretien")]
    operations = [migrations.RunPython(remplir, migrations.RunPython.noop)]
