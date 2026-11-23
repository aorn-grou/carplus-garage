from django.contrib import admin

from .models import (Client, Depense, Entretien, Journal, OrdreReparation, Paiement, Parametres, Rappel, Systeme, ContactClient,
                     TypeEntretien, Vehicule)

admin.site.register([Client, Vehicule, OrdreReparation, Paiement, Depense, Rappel, Parametres, Systeme, Entretien, ContactClient])


@admin.register(TypeEntretien)
class TypeEntretienAdmin(admin.ModelAdmin):
    list_display = ["nom"]
    fields = ["nom"]


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ["date", "utilisateur", "objet", "objet_id", "champ", "ancienne", "nouvelle"]

    def has_change_permission(self, *a):
        return False

    def has_delete_permission(self, *a):
        return False
