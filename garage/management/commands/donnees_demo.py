"""Données d'essai (pour la démonstration seulement)."""
import datetime as dt
import random

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from garage.models import Client, Depense, Entretien, LigneOrdre, OrdreReparation, Paiement, Rappel, Systeme, Vehicule


class Command(BaseCommand):
    help = "Ajoute des données d'exemple."

    def handle(self, *a, **kw):
        meca, _ = User.objects.get_or_create(username="rivo", defaults={"first_name": "Rivo"})
        meca.set_password("garage123"); meca.save(); meca.groups.add(Group.objects.get(name="Mécanicien"))
        caisse, _ = User.objects.get_or_create(username="caisse", defaults={"first_name": "Fara"})
        caisse.set_password("garage123"); caisse.save(); caisse.groups.add(Group.objects.get(name="Caisse"))
        r = Client.objects.create(nom="Rakoto Jean", telephone="0341234567", whatsapp="0341234567",
                                  facebook="facebook.com/rakoto.jean.exemple", canal_prefere="whatsapp")
        h = Client.objects.create(nom="Rasoa Hanta", telephone="0329876543", langue="mg", canal_prefere="appel")
        s = Client.objects.create(type="societe", nom="Trans Iarivo SARL", telephone="0202212345", nif="1234567890",
                                  stat="49290 11 2015 0 01234", contact="M. Andry (flotte)",
                                  email="flotte@trans-iarivo.exemple", canal_prefere="email")
        v1 = Vehicule.objects.create(proprietaire=r, immatriculation="1234 TBA", marque="Toyota", modele="Hilux", annee=2018,
                                     carburant="diesel", kilometrage=142000)
        v2 = Vehicule.objects.create(proprietaire=h, immatriculation="5678 TAB", marque="Yamaha", modele="Crypton", annee=2021,
                                     categorie="moto", kilometrage=23000)
        v3 = Vehicule.objects.create(proprietaire=s, immatriculation="4321 TBE", marque="Great Wall", modele="Wingle 5",
                                     annee=2019, carburant="diesel", kilometrage=98000)
        v4 = Vehicule.objects.create(proprietaire=s, immatriculation="8765 TBE", marque="Toyota", modele="Hiace", annee=2016,
                                     carburant="diesel", kilometrage=210000)
        now = timezone.now()
        ta = Systeme.objects.get(nom="Train avant")
        a1 = OrdreReparation.objects.create(vehicule=v1, client=r, kilometrage=118000, probleme="Vidange",
                                            date_reception=now - dt.timedelta(days=420), statut="livre",
                                            travaux="Vidange moteur + filtre", recommandations="Surveiller les amortisseurs avant",
                                            travaux_refuses="Remplacement des amortisseurs avant (client a reporté)",
                                            risque="Usure irrégulière des pneus et fatigue du train avant")
        Entretien.objects.create(vehicule=v1, designation="Vidange huile moteur + filtre à huile", ordre=a1,
                                 fait_le=a1.date_reception.date(), fait_km=118000, prochain_km=128000,
                                 prochaine_date=a1.date_reception.date() + dt.timedelta(days=365))
        a2 = OrdreReparation.objects.create(vehicule=v1, client=r, kilometrage=131000, probleme="Claquement à l'avant gauche",
                                            date_reception=now - dt.timedelta(days=95), statut="livre",
                                            cause="Cardan avant gauche usé (soufflet déchiré)", travaux="Remplacement du cardan avant gauche")
        a2.systemes.add(ta)
        LigneOrdre.objects.create(ordre=a2, designation="Cardan avant gauche", prix_unitaire=0)
        o1 = OrdreReparation.objects.create(vehicule=v1, client=r, kilometrage=142000, probleme="Claquement à l'avant gauche en virage",
                                            statut="reparation", mecanicien=meca, date_reception=now - dt.timedelta(days=1))
        o1.systemes.add(ta)
        o1.lie_a, o1.nature_lien = a2, "meme"
        o1.save()
        LigneOrdre.objects.create(ordre=o1, designation="Cardan avant gauche", prix_unitaire=450000)
        LigneOrdre.objects.create(ordre=o1, type="mo", designation="Dépose / pose cardan", quantite=2, prix_unitaire=40000)
        Depense.objects.create(montant=380000, categorie="pieces", motif="Cardan avant gauche Hilux", fournisseur="Pièces Auto Analakely",
                               avec_facture=False, ordre=o1)
        o2 = OrdreReparation.objects.create(vehicule=v3, client=s, kilometrage=98000, probleme="Vidange + filtres",
                                            statut="livre", date_reception=now - dt.timedelta(days=12), date_livraison=now - dt.timedelta(days=11))
        LigneOrdre.objects.create(ordre=o2, designation="Huile moteur 15W40", quantite=7, prix_unitaire=28000)
        LigneOrdre.objects.create(ordre=o2, designation="Filtre à huile", prix_unitaire=35000)
        LigneOrdre.objects.create(ordre=o2, type="mo", designation="Vidange", prix_unitaire=30000)
        Paiement.objects.create(ordre=o2, client=s, montant=150000, libelle="Acompte OR " + o2.numero, date=now - dt.timedelta(days=11))
        OrdreReparation.objects.create(vehicule=v2, client=h, kilometrage=23000, probleme="Frein arrière faible", statut="attente_pieces")
        for i in range(25):
            d = now - dt.timedelta(days=random.randint(0, 120), hours=random.randint(0, 8))
            Paiement.objects.create(montant=random.choice([50000, 120000, 250000, 480000]), libelle="Réparation (exemple)", date=d)
            Depense.objects.create(montant=random.choice([10000, 25000, 60000, 150000]), motif="Dépense (exemple)",
                                   categorie=random.choice(["carburant", "consommables", "transport", "divers"]),
                                   avec_facture=False, date=d)
        Rappel.objects.create(client=r, vehicule=v1, motif="Votre prochain entretien est à prévoir", date_prevue=timezone.localdate())
        Rappel.objects.create(client=s, vehicule=v4, motif="Contrôle des freins recommandé", date_prevue=timezone.localdate() - dt.timedelta(days=3))
        self.stdout.write(self.style.SUCCESS("Données d'exemple ajoutées (utilisateurs : rivo / caisse, mot de passe garage123)."))
