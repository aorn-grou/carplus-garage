import io
import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Client, Depense, Journal, LigneOrdre, OrdreReparation, Paiement, PhotoDegat, Rappel, Vehicule
from .roles import ROLES

MEDIA = tempfile.mkdtemp()


def grosse_photo(l=4000, h=3000):
    buf = io.BytesIO()
    import random
    img = Image.effect_noise((l, h), 80).convert("RGB")
    img.save(buf, "JPEG", quality=98)
    return SimpleUploadedFile("facture.jpg", buf.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        for r in ROLES:
            Group.objects.get_or_create(name=r)
        self.patron = User.objects.create_superuser("patron", "", "secret123")
        self.meca = User.objects.create_user("meca", password="secret123")
        self.meca.groups.add(Group.objects.get(name="Mécanicien"))
        self.caisse = User.objects.create_user("caisse", password="secret123")
        self.caisse.groups.add(Group.objects.get(name="Caisse"))
        self.cli = Client.objects.create(nom="Rakoto", telephone="0341234567")
        self.soc = Client.objects.create(nom="Société ABC", type="societe")
        self.v = Vehicule.objects.create(proprietaire=self.cli, immatriculation="1234 tba", marque="Toyota", modele="Hilux")
        self.client.login(username="patron", password="secret123")


class PhotosTests(Base):
    def test_photo_facture_compressee(self):
        brute = grosse_photo()
        taille_avant = brute.size
        d = Depense.objects.create(montant=10000, motif="Plaquettes", photo=brute)
        d.photo.open()
        img = Image.open(d.photo)
        self.assertLessEqual(max(img.size), 1600)
        self.assertLess(d.photo.size, taille_avant / 3)
        self.assertTrue(d.photo.name.endswith(".jpg"))

    def test_photo_degat_compressee(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Choc")
        p = PhotoDegat.objects.create(ordre=o, image=grosse_photo(3000, 4000))
        self.assertLessEqual(max(Image.open(p.image).size), 1600)

    def test_depense_avec_facture_exige_photo(self):
        r = self.client.post("/depenses/nouvelle/", {"avec_facture": "on", "montant": 5000, "categorie": "divers",
                                                     "motif": "Test", "mode": "especes"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Depense.objects.count(), 0)

    def test_depense_sans_facture_bon_interne(self):
        self.client.post("/depenses/nouvelle/", {"montant": 5000, "categorie": "divers", "motif": "Taxi", "mode": "especes"})
        d = Depense.objects.get()
        self.assertFalse(d.avec_facture)
        self.assertTrue(d.numero_bon.startswith("BI"))


class CalculsTests(Base):
    def test_totaux_ordre(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Freins", remise=5000)
        LigneOrdre.objects.create(ordre=o, designation="Plaquettes", quantite=2, prix_unitaire=45000)
        LigneOrdre.objects.create(ordre=o, type="mo", designation="Pose", quantite=1.5, prix_unitaire=20000)
        Paiement.objects.create(ordre=o, montant=50000, libelle="Acompte")
        Depense.objects.create(ordre=o, montant=60000, motif="Achat plaquettes", avec_facture=False)
        self.assertEqual(o.total_pieces, 90000)
        self.assertEqual(o.total_main_oeuvre, 30000)
        self.assertEqual(o.total, 115000)
        self.assertEqual(o.reste, 65000)
        self.assertEqual(o.marge, 55000)

    def test_numerotation(self):
        o1 = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="a")
        o2 = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="b")
        self.assertNotEqual(o1.numero, o2.numero)

    def test_caisse_periodes(self):
        Paiement.objects.create(montant=100000, libelle="x")
        Depense.objects.create(montant=30000, motif="y", avec_facture=False)
        for p in ("jour", "semaine", "mois", "annee"):
            r = self.client.get(f"/caisse/?periode={p}")
            self.assertEqual(r.context["total_e"], 100000, p)
            self.assertEqual(r.context["solde"], 70000, p)

    def test_caisse_rapide(self):
        self.client.post("/caisse/", {"sens": "sortie", "montant": 2000, "libelle": "Pain", "mode": "especes"})
        self.assertEqual(Depense.objects.get().numero_bon[:2], "BI")


class VehiculesTests(Base):
    def test_immatriculation_normalisee(self):
        self.assertEqual(self.v.immatriculation, "1234TBA")

    def test_changement_proprietaire_garde_historique(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Vidange")
        self.v.changer_proprietaire(self.soc, self.patron)
        self.v.refresh_from_db()
        self.assertEqual(self.v.proprietaire, self.soc)
        self.assertIn(o, self.v.ordres.all())
        self.assertEqual(self.v.changements.count(), 1)

    def test_livraison_cree_rappel(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Vidange")
        retour = timezone.localdate() + dt.timedelta(days=90)
        self.client.post(f"/atelier/{o.pk}/statut/", {"statut": "livre", "date_retour": retour.isoformat(), "motif_retour": "Vidange"})
        r = Rappel.objects.get()
        self.assertEqual((r.vehicule, r.date_prevue, r.motif), (self.v, retour, "Vidange"))

    def test_livraison_sans_date_aucun_rappel(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Vidange")
        LigneOrdre.objects.create(ordre=o, designation="Pièce", prix_unitaire=100000)
        self.client.post(f"/atelier/{o.pk}/statut/", {"statut": "livre"})
        self.assertFalse(Rappel.objects.exists())   # le logiciel ne choisit aucune date tout seul

    def test_rappel_groupe_societe(self):
        Vehicule.objects.create(proprietaire=self.soc, immatriculation="1", marque="A", modele="B")
        Vehicule.objects.create(proprietaire=self.soc, immatriculation="2", marque="A", modele="B")
        self.client.post(f"/clients/{self.soc.pk}/alertes/", {"motif": "Révision flotte"})
        self.assertEqual(Rappel.objects.filter(client=self.soc).count(), 2)


class EditionTests(Base):
    def test_edition_directe_et_journal(self):
        r = self.client.post(f"/modifier/client/{self.cli.pk}/telephone/", {"valeur": "0330000000"})
        self.assertEqual(r.status_code, 200)
        self.cli.refresh_from_db()
        self.assertEqual(self.cli.telephone, "0330000000")
        j = Journal.objects.get()
        self.assertEqual((j.ancienne, j.nouvelle), ("0341234567", "0330000000"))

    def test_edition_valeur_invalide(self):
        r = self.client.post(f"/modifier/vehicule/{self.v.pk}/kilometrage/", {"valeur": "abc"})
        self.assertContains(r, "erreur")
        self.v.refresh_from_db()
        self.assertEqual(self.v.kilometrage, 0)

    def test_champ_non_autorise(self):
        r = self.client.post(f"/modifier/client/{self.cli.pk}/type/", {"valeur": "societe"})
        self.assertEqual(r.status_code, 403)


class RolesTests(Base):
    def test_mecanicien_sans_argent(self):
        self.client.login(username="meca", password="secret123")
        self.assertEqual(self.client.get("/caisse/").status_code, 403)
        self.assertEqual(self.client.get("/depenses/").status_code, 403)
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x", mecanicien=self.meca)
        LigneOrdre.objects.create(ordre=o, designation="Cardan", prix_unitaire=450000)
        r = self.client.get(f"/atelier/{o.pk}/")
        self.assertNotContains(r, "450")
        o2 = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x")
        r = self.client.post(f"/modifier/ligne/{o2.pk}/prix_unitaire/", {"valeur": "1"})
        self.assertEqual(r.status_code, 403)

    def test_caisse_voit_argent(self):
        self.client.login(username="caisse", password="secret123")
        self.assertEqual(self.client.get("/caisse/").status_code, 200)
        self.assertEqual(self.client.get("/historique/").status_code, 403)

    def test_connexion_obligatoire(self):
        self.client.logout()
        self.assertEqual(self.client.get("/caisse/").status_code, 302)


class RechercheTests(Base):
    def test_recherche_globale(self):
        r = self.client.get("/recherche/?q=hilux", HTTP_HX_REQUEST="true")
        self.assertContains(r, "1234TBA")
        r = self.client.get("/recherche/?q=caisse", HTTP_HX_REQUEST="true")
        self.assertContains(r, "/caisse/")
        r = self.client.get("/recherche/?q=0341", HTTP_HX_REQUEST="true")
        self.assertContains(r, "Rakoto")


import datetime as dt  # noqa: E402

from django.utils import timezone  # noqa: E402

from .models import Entretien, Systeme  # noqa: E402
from .services import generer_alertes_entretien  # noqa: E402


class CarnetTests(Base):
    def _ordre(self, jours, km, systeme=None, **kw):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme=kw.pop("probleme", "x"),
                                           kilometrage=km, date_reception=timezone.now() - dt.timedelta(days=jours), **kw)
        if systeme:
            o.systemes.add(Systeme.objects.get(nom=systeme))
        return o

    def test_km_estime(self):
        self._ordre(400, 100000)
        self._ordre(100, 115000)          # 15 000 km en 300 jours = 50 km/jour
        self.assertAlmostEqual(self.v.km_par_jour(), 50, delta=0.1)
        self.assertAlmostEqual(self.v.km_estime(), 120000, delta=100)

    def test_alerte_entretien_par_km(self):
        self._ordre(400, 100000)
        o = self._ordre(100, 115000)
        Entretien.objects.create(vehicule=self.v, designation="Vidange", ordre=o, fait_le=o.date_reception.date(),
                                 fait_km=115000, prochain_km=120500)   # estimé ≈ 120 000 → « bientôt »
        self.assertEqual(generer_alertes_entretien(), 1)
        self.assertEqual(generer_alertes_entretien(), 0)               # pas de doublon
        r = Rappel.objects.get()
        self.assertIn("Vidange", r.motif)

    def test_alerte_entretien_par_date(self):
        Entretien.objects.create(vehicule=self.v, designation="Liquide de frein", fait_le=timezone.localdate() - dt.timedelta(days=700),
                                 prochaine_date=timezone.localdate() - dt.timedelta(days=5))
        self.assertEqual(generer_alertes_entretien(), 1)

    def test_entretien_remplace_ancien_et_ferme_alerte(self):
        e1 = Entretien.objects.create(vehicule=self.v, designation="Vidange", fait_le=timezone.localdate() - dt.timedelta(days=400),
                                      prochaine_date=timezone.localdate() - dt.timedelta(days=1))
        generer_alertes_entretien()
        Entretien.objects.create(vehicule=self.v, designation="vidange", fait_le=timezone.localdate(),
                                 prochaine_date=timezone.localdate() + dt.timedelta(days=180))
        e1.refresh_from_db()
        self.assertFalse(e1.actif)
        self.assertEqual(Rappel.objects.get().statut, "annule")

    def test_formulaire_entretien_depuis_reparation(self):
        o = self._ordre(0, 80000)
        self.client.post(f"/vehicules/{self.v.pk}/entretien/", {"ordre": o.pk, "autre": "Vidange huile moteur",
                                                              "fait_le": timezone.localdate().isoformat(), "fait_km": 80000,
                                                              "prochain_km": 85000,
                                                              "prochaine_date": "2027-05-20"})
        e = Entretien.objects.get()
        self.assertEqual((e.prochain_km, e.ordre, str(e.prochaine_date)), (85000, o, "2027-05-20"))


class RecidiveTests(Base):
    def test_meme_partie_et_piece_deja_changee(self):
        a = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Claquement", kilometrage=100000,
                                           date_reception=timezone.now() - dt.timedelta(days=60))
        a.systemes.add(Systeme.objects.get(nom="Train avant"))
        LigneOrdre.objects.create(ordre=a, designation="Rotule de direction gauche", prix_unitaire=1)
        b = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Claquement encore", kilometrage=103000)
        b.systemes.add(Systeme.objects.get(nom="Train avant"))
        LigneOrdre.objects.create(ordre=b, designation="rotule de direction gauche", prix_unitaire=1)
        ant = b.antecedents()
        self.assertEqual(ant["meme_partie"][0]["km"], 3000)
        self.assertEqual(len(ant["pieces"]), 1)
        self.assertEqual(self.v.problemes_recurrents()[0][0].nom, "Train avant")
        r = self.client.get(f"/atelier/{b.pk}/")
        self.assertContains(r, "Même partie déjà réparée")
        self.assertContains(r, "Pièce déjà changée")

    def test_travaux_refuses_rappeles(self):
        a = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Vidange",
                                           travaux_refuses="Amortisseurs avant usés", risque="Usure des pneus",
                                           date_reception=timezone.now() - dt.timedelta(days=30))
        self.client.post(f"/atelier/{a.pk}/statut/", {"statut": "livre", "date_relance_refus": "2027-01-15"})
        self.assertEqual(str(Rappel.objects.get(motif__contains="Amortisseurs").date_prevue), "2027-01-15")
        b = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Bruit")
        self.assertContains(self.client.get(f"/atelier/{b.pk}/"), "Amortisseurs avant usés")

    def test_lien_avec_reparation_precedente(self):
        a = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Fuite radiateur non réparée",
                                           date_reception=timezone.now() - dt.timedelta(days=30))
        b = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Surchauffe moteur")
        self.client.post(f"/atelier/{b.pk}/lien/", {"lie_a": a.pk, "nature_lien": "non_repare"})
        b.refresh_from_db()
        self.assertEqual((b.lie_a, b.nature_lien), (a, "non_repare"))
        self.assertContains(self.client.get(f"/atelier/{a.pk}/"), "Une réparation suivante est liée")


class ReceptionTests(Base):
    def test_reception_nouveau_vehicule_et_client_en_un_ecran(self):
        r = self.client.post("/atelier/reception/", {
            "immatriculation": "9999 tbb", "marque": "Nissan", "modele": "Navara", "categorie": "voiture",
            "client_nom": "Randria", "client_type": "particulier", "client_telephone": "0340000000",
            "kilometrage": 50000, "probleme": "Freins", "systemes": [Systeme.objects.get(nom="Freins").pk]})
        o = OrdreReparation.objects.get()
        self.assertRedirects(r, o.get_absolute_url())
        self.assertEqual((o.vehicule.immatriculation, o.client.nom, o.kilometrage), ("9999TBB", "Randria", 50000))
        self.assertEqual(o.systemes.get().nom, "Freins")

    def test_reception_vehicule_connu_affiche_historique(self):
        OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Vidange ancienne")
        r = self.client.get("/atelier/reception/vehicule/?immatriculation=1234 TBA")
        self.assertContains(r, "Véhicule connu")
        self.assertContains(r, "Vidange ancienne")

    def test_impaye_cree_rappel(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x")
        LigneOrdre.objects.create(ordre=o, designation="Pièce", prix_unitaire=100000)
        self.client.post(f"/atelier/{o.pk}/statut/", {"statut": "livre", "date_relance_paiement": "2027-01-05"})
        self.assertEqual(str(Rappel.objects.get(motif__startswith="Facture impayée").date_prevue), "2027-01-05")

    def test_chrono(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x")
        self.client.post(f"/atelier/{o.pk}/chrono/")
        self.assertEqual(o.pointages.filter(fin__isnull=True).count(), 1)
        self.client.post(f"/atelier/{o.pk}/chrono/")
        self.assertEqual(o.pointages.filter(fin__isnull=True).count(), 0)

    def test_campagne_et_inactifs(self):
        self.v.annee = 2010
        self.v.save()
        self.client.post("/vehicules/?age=5", {"motif": "Offre courroie"})
        self.assertEqual(Rappel.objects.filter(motif="Offre courroie").count(), 1)
        r = self.client.get("/alertes/?vue=inactifs")
        self.assertContains(r, "Rakoto")


class DatesChoisiesTests(Base):
    def test_reporter_a_une_date_choisie(self):
        r = Rappel.objects.create(client=self.cli, motif="Vidange", date_prevue=timezone.localdate())
        self.client.post(f"/alertes/{r.pk}/", {"action": "reporter", "date": "2027-03-01"})
        r.refresh_from_db()
        self.assertEqual(str(r.date_prevue), "2027-03-01")

    def test_modifier_date_de_retour_entretien(self):
        e = Entretien.objects.create(vehicule=self.v, designation="Vidange", fait_le=timezone.localdate(),
                                     prochaine_date=timezone.localdate() + dt.timedelta(days=100))
        self.client.post(f"/modifier/entretien/{e.pk}/prochaine_date/", {"valeur": "2027-06-30"})
        e.refresh_from_db()
        self.assertEqual(str(e.prochaine_date), "2027-06-30")


class ContactsTests(Base):
    def setUp(self):
        super().setUp()
        self.cli.facebook = "rakoto.jean"
        self.cli.email = "rakoto@example.com"
        self.cli.canal_prefere = "facebook"
        self.cli.save()
        self.r = Rappel.objects.create(client=self.cli, motif="Vidange", date_prevue=timezone.localdate())

    def test_boutons_de_contact(self):
        r = self.client.get("/alertes/")
        for attendu in ["tel:0341234567", "sms:0341234567", "wa.me/261341234567", "m.me/rakoto.jean", "mailto:rakoto@example.com",
                        "Copier le message"]:
            self.assertContains(r, attendu)

    def test_contact_joint_ferme_alerte(self):
        from .models import ContactClient
        self.client.post(f"/alertes/{self.r.pk}/contact/", {"canal": "appel", "resultat": "joint", "note": "Vient lundi"})
        self.r.refresh_from_db()
        self.assertEqual(self.r.statut, "contacte")
        self.assertEqual(ContactClient.objects.get().note, "Vient lundi")
        self.assertContains(self.client.get(f"/clients/{self.cli.pk}/"), "Vient lundi")

    def test_pas_de_reponse_garde_alerte_a_nouvelle_date(self):
        self.client.post(f"/alertes/{self.r.pk}/contact/", {"canal": "sms", "resultat": "pas_repondu", "date": "2027-02-02"})
        self.r.refresh_from_db()
        self.assertEqual((self.r.statut, str(self.r.date_prevue)), ("a_faire", "2027-02-02"))



class PremierDemarrageTests(TestCase):
    def test_le_client_cree_son_compte(self):
        User.objects.create_user("mecano", password="x12345678")   # ex. données d'exemple chargées avant
        self.assertRedirects(self.client.get("/"), "/premier-demarrage/", fetch_redirect_response=False)
        r = self.client.post("/premier-demarrage/", {"g-nom": "CAR SERVICE PLUS", "g-telephone": "034 00 000 00", "g-nif": "123", "g-prochain_numero_facture": 18,
                                                     "u-username": "patron", "u-password1": "Garage-2026!x", "u-password2": "Garage-2026!x"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        u = User.objects.get(username="patron")
        self.assertTrue(u.is_superuser)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.client.logout()
        self.assertRedirects(self.client.get("/premier-demarrage/"), "/connexion/", fetch_redirect_response=False)



class FactureGarageTests(Base):
    def test_montant_en_lettres(self):
        from .lettres import montant_en_lettres
        self.assertEqual(montant_en_lettres(2050000), "Deux millions cinquante mille ariary")
        self.assertEqual(montant_en_lettres(11672640), "Onze millions six cent soixante-douze mille six cent quarante ariary")
        self.assertEqual(montant_en_lettres(80), "Quatre-vingts ariary")
        self.assertEqual(montant_en_lettres(71), "Soixante et onze ariary")

    def test_forfait_lignes_incluses_et_numero(self):
        from .models import Parametres
        p = Parametres.get()
        p.prochain_numero_facture = 18
        p.save()
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="Restauration", forfait=2050000)
        LigneOrdre.objects.create(ordre=o, designation="Réparation et restauration complet", prix_unitaire=0)
        LigneOrdre.objects.create(ordre=o, designation="Transport", prix_unitaire=0)
        self.assertEqual(o.total, 2050000)
        r = self.client.get(f"/atelier/{o.pk}/imprimer/?doc=facture")
        self.assertContains(r, "FAC-000018")          # page « Établir la facture »
        self.client.post(f"/atelier/{o.pk}/facture/")
        o.refresh_from_db()
        self.assertEqual(o.numero_facture, "FAC-000018")
        self.client.post(f"/atelier/{o.pk}/facture/")  # deuxième clic : le numéro ne change pas
        o.refresh_from_db()
        self.assertEqual(o.numero_facture, "FAC-000018")
        self.assertEqual(Parametres.get().prochain_numero_facture, 19)
        r = self.client.get(f"/atelier/{o.pk}/imprimer/?doc=facture")
        self.assertContains(r, "inclus")
        self.assertContains(r, "Deux millions cinquante mille ariary")
        self.assertContains(r, self.cli.code)

    def test_tva_si_reglee(self):
        from .models import Parametres
        p = Parametres.get()
        p.taux_tva = 20
        p.save()
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x")
        LigneOrdre.objects.create(ordre=o, designation="Couple conique", prix_unitaire=9727200)
        self.assertEqual((o.montant_tva, o.total), (1945440, 11672640))

    def test_etat_de_depense(self):
        o = OrdreReparation.objects.create(vehicule=self.v, client=self.cli, probleme="x")
        Depense.objects.create(ordre=o, montant=80000, motif="Achat batterie moto", avec_facture=False)
        Depense.objects.create(ordre=o, montant=150000, motif="Transport", avec_facture=False)
        r = self.client.get(f"/atelier/{o.pk}/imprimer/?doc=depenses")
        self.assertContains(r, "ÉTAT DE DÉPENSE")
        self.assertContains(r, "Deux cent trente mille ariary")


class NomUtilisateurTests(TestCase):
    def test_espace_message_clair(self):
        r = self.client.post("/premier-demarrage/", {"g-nom": "CAR SERVICE PLUS", "g-prochain_numero_facture": 18,
                                                     "u-username": "Mr-Tahirsoa Admin1.8", "u-password1": "Garage-2026!x",
                                                     "u-password2": "Garage-2026!x"})
        self.assertContains(r, "Pas d&#x27;espace dans le nom d&#x27;utilisateur")
        self.assertFalse(User.objects.exists())
