"""Données du garage CAR PLUS. Montants en ariary (entiers)."""
from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from .photos import compresser_photo


def montant(**kw):
    return models.DecimalField(max_digits=14, decimal_places=0, default=0, **kw)


class Client(models.Model):
    PARTICULIER, SOCIETE = "particulier", "societe"
    TYPES = [(PARTICULIER, "Particulier"), (SOCIETE, "Société")]
    LANGUES = [("fr", "Français"), ("mg", "Malgache")]

    type = models.CharField(max_length=12, choices=TYPES, default=PARTICULIER)
    nom = models.CharField("Nom / raison sociale", max_length=150)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    telephone2 = models.CharField("Téléphone 2", max_length=30, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.CharField(max_length=250, blank=True)
    nif = models.CharField("NIF", max_length=40, blank=True)
    stat = models.CharField("STAT", max_length=40, blank=True)
    contact = models.CharField("Personne à contacter", max_length=150, blank=True)
    facebook = models.CharField("Facebook / Messenger", max_length=200, blank=True,
                                help_text="Lien du profil ou de la page (ex. : facebook.com/rakoto.jean) ou nom d'utilisateur")
    CANAUX = [("appel", "Appel téléphonique"), ("sms", "SMS"), ("whatsapp", "WhatsApp"), ("facebook", "Facebook / Messenger"),
              ("email", "E-mail"), ("visite", "En personne")]
    canal_prefere = models.CharField("Préfère être contacté par", max_length=10, choices=CANAUX, default="appel")
    langue = models.CharField(max_length=2, choices=LANGUES, default="fr")
    accepte_rappels = models.BooleanField("Accepte les rappels", default=True)
    notes = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def get_absolute_url(self):
        return reverse("client_detail", args=[self.pk])

    @property
    def code(self):
        return f"CLI-{self.pk:06d}"

    @property
    def lien_facebook(self):
        f = self.facebook.strip()
        if not f:
            return ""
        if f.startswith("http"):
            return f
        if "facebook.com" in f or "fb.com" in f or "m.me" in f:
            return "https://" + f.lstrip("/")
        return "https://m.me/" + f.lstrip("@")

    @property
    def numero_whatsapp(self):
        num = "".join(c for c in (self.whatsapp or self.telephone) if c.isdigit())
        if num.startswith("0") and len(num) == 10:  # 034... -> 26134...
            num = "261" + num[1:]
        return num


class Vehicule(models.Model):
    CATEGORIES = [("voiture", "Voiture"), ("moto", "Moto"), ("utilitaire", "Utilitaire"), ("camion", "Camion")]
    CARBURANTS = [("", "—"), ("essence", "Essence"), ("diesel", "Diesel"), ("hybride", "Hybride"), ("electrique", "Électrique")]

    categorie = models.CharField("Catégorie", max_length=12, choices=CATEGORIES, default="voiture")
    immatriculation = models.CharField(max_length=20, unique=True)
    marque = models.CharField(max_length=60)
    modele = models.CharField("Modèle", max_length=60)
    annee = models.PositiveIntegerField("Année", null=True, blank=True)
    vin = models.CharField("VIN / n° de cadre", max_length=40, blank=True)
    moteur = models.CharField("Moteur", max_length=60, blank=True)
    carburant = models.CharField(max_length=12, choices=CARBURANTS, blank=True)
    couleur = models.CharField(max_length=30, blank=True)
    kilometrage = models.PositiveIntegerField("Kilométrage", default=0)
    proprietaire = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="vehicules", verbose_name="Propriétaire")
    notes = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["immatriculation"]

    def __str__(self):
        return f"{self.immatriculation} — {self.marque} {self.modele}"

    def save(self, *a, **kw):
        self.immatriculation = self.immatriculation.upper().replace(" ", "")
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("vehicule_detail", args=[self.pk])

    def releves_km(self):
        """Relevés de kilométrage connus (date, km), du plus ancien au plus récent."""
        pts = [(o.date_reception.date(), o.kilometrage) for o in self.ordres.exclude(statut="annule")
               if o.kilometrage]
        pts += [(e.fait_le, e.fait_km) for e in self.entretiens.all() if e.fait_km]
        return sorted(set(pts))

    def km_par_jour(self):
        """Moyenne de km parcourus par jour, calculée sur l'historique du garage."""
        pts = self.releves_km()
        if len(pts) < 2:
            return None
        (d0, k0), (d1, k1) = pts[0], pts[-1]
        jours = (d1 - d0).days
        if jours < 30 or k1 <= k0:
            return None
        return (k1 - k0) / jours

    def km_estime(self):
        """Kilométrage estimé aujourd'hui (dernier relevé + moyenne × jours écoulés)."""
        pts = self.releves_km()
        dernier_km = max([self.kilometrage] + [k for _, k in pts])
        rythme = self.km_par_jour()
        if not rythme or not pts:
            return dernier_km
        jours = (timezone.localdate() - pts[-1][0]).days
        return int(max(dernier_km, pts[-1][1] + rythme * jours))

    def a_surveiller(self):
        """Travaux conseillés refusés/reportés et recommandations des visites passées."""
        return self.ordres.exclude(statut="annule").exclude(travaux_refuses="", recommandations="").order_by("-date_reception")

    def problemes_recurrents(self):
        """Systèmes touchés au moins 2 fois : [(systeme, [ordres...])]."""
        res = {}
        for o in self.ordres.exclude(statut="annule").prefetch_related("systemes").order_by("date_reception"):
            for s in o.systemes.all():
                res.setdefault(s, []).append(o)
        return [(s, ords) for s, ords in res.items() if len(ords) >= 2]

    @transaction.atomic
    def changer_proprietaire(self, nouveau, utilisateur, date=None):
        ChangementProprietaire.objects.create(
            vehicule=self, ancien=self.proprietaire, nouveau=nouveau,
            date=date or timezone.localdate(), par=utilisateur)
        self.proprietaire = nouveau
        self.save(update_fields=["proprietaire"])


class ChangementProprietaire(models.Model):
    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, related_name="changements")
    ancien = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="+")
    nouveau = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]


class Systeme(models.Model):
    """Partie du véhicule touchée (freins, train avant, moteur…), pour repérer les problèmes qui reviennent."""
    nom = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Système / organe"

    def __str__(self):
        return self.nom


class OrdreReparation(models.Model):
    NIVEAUX = [("", "—"), ("reserve", "Réserve"), ("1/4", "1/4"), ("1/2", "1/2"), ("3/4", "3/4"), ("plein", "Plein")]
    LIENS = [
        ("", "—"),
        ("meme", "Le même problème revient"),
        ("consequence", "Conséquence d'un problème précédent"),
        ("non_repare", "Dégât causé par un travail refusé ou reporté"),
        ("garantie", "Retour sous garantie (notre réparation)"),
    ]
    STATUTS = [
        ("recu", "Véhicule reçu"),
        ("diagnostic", "Diagnostic"),
        ("devis", "Devis à valider"),
        ("attente_pieces", "En attente de pièces"),
        ("reparation", "En réparation"),
        ("pret", "Prêt à livrer"),
        ("livre", "Livré"),
        ("annule", "Annulé"),
    ]
    STATUTS_ACTIFS = ["recu", "diagnostic", "devis", "attente_pieces", "reparation", "pret"]

    numero = models.CharField("N°", max_length=20, unique=True, editable=False)
    vehicule = models.ForeignKey(Vehicule, on_delete=models.PROTECT, related_name="ordres", verbose_name="Véhicule")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="ordres", verbose_name="Client (payeur)")
    date_reception = models.DateTimeField("Reçu le", default=timezone.now)
    kilometrage = models.PositiveIntegerField("Kilométrage", default=0)
    deposant = models.CharField("Déposé par", max_length=120, blank=True)
    niveau_carburant = models.CharField("Niveau de carburant", max_length=8, choices=NIVEAUX, blank=True)
    accessoires = models.CharField("Objets / accessoires dans le véhicule", max_length=250, blank=True)
    etat_carrosserie = models.TextField("État de la carrosserie à la réception", blank=True)
    probleme = models.TextField("Problème signalé")
    systemes = models.ManyToManyField(Systeme, blank=True, related_name="ordres", verbose_name="Parties touchées")
    diagnostic = models.TextField(blank=True)
    cause = models.TextField("Cause trouvée", blank=True)
    travaux = models.TextField("Travaux réalisés", blank=True)
    recommandations = models.TextField("Recommandations pour plus tard", blank=True)
    travaux_refuses = models.TextField("Travaux conseillés refusés ou reportés par le client", blank=True)
    risque = models.TextField("Risque si ces travaux ne sont pas faits", blank=True)
    lie_a = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="suites",
                              verbose_name="Lié à la réparation")
    nature_lien = models.CharField("Nature du lien", max_length=12, choices=LIENS, blank=True)
    mecanicien = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="ordres", verbose_name="Mécanicien")
    statut = models.CharField(max_length=20, choices=STATUTS, default="recu")
    remise = montant()
    forfait = montant(verbose_name="Prix global (forfait)",
                      help_text="Si rempli, c'est ce montant qui est facturé ; les lignes sans prix apparaissent « inclus ».")
    numero_facture = models.CharField("N° de facture", max_length=20, blank=True, editable=False)
    date_facture = models.DateField(null=True, blank=True, editable=False)
    date_livraison = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date_reception"]

    def __str__(self):
        return f"OR {self.numero}"

    def get_absolute_url(self):
        return reverse("ordre_detail", args=[self.pk])

    def save(self, *a, **kw):
        if not self.numero:
            annee = timezone.localdate().year
            dernier = OrdreReparation.objects.filter(numero__startswith=f"{annee}-").order_by("-numero").first()
            n = int(dernier.numero.split("-")[1]) + 1 if dernier else 1
            self.numero = f"{annee}-{n:05d}"
        super().save(*a, **kw)

    @property
    def total_pieces(self):
        return sum((l.total for l in self.lignes.all() if l.type == "piece"), 0)

    @property
    def total_main_oeuvre(self):
        return sum((l.total for l in self.lignes.all() if l.type == "mo"), 0)

    @property
    def sous_total(self):
        return self.forfait if self.forfait else self.total_pieces + self.total_main_oeuvre

    @property
    def total(self):
        """Total à payer (TTC si le garage applique une TVA)."""
        return self.total_ht + self.montant_tva

    @property
    def total_ht(self):
        return self.sous_total - self.remise

    @property
    def montant_tva(self):
        taux = Parametres.get().taux_tva
        return (self.total_ht * taux / 100).quantize(1) if taux else 0

    def etablir_facture(self):
        """Donne un numéro de facture définitif (FAC-000018…), une seule fois."""
        if self.numero_facture:
            return
        with transaction.atomic():
            p = Parametres.objects.select_for_update().get(pk=Parametres.get().pk)
            self.numero_facture = f"FAC-{p.prochain_numero_facture:06d}"
            self.date_facture = timezone.localdate()
            p.prochain_numero_facture += 1
            p.save(update_fields=["prochain_numero_facture"])
            self.save(update_fields=["numero_facture", "date_facture"])

    @property
    def paye(self):
        return self.paiements.aggregate(s=Sum("montant"))["s"] or 0

    @property
    def reste(self):
        return self.total - self.paye

    @property
    def cout_pieces(self):
        return self.depenses.aggregate(s=Sum("montant"))["s"] or 0

    @property
    def marge(self):
        return self.total - self.cout_pieces

    @property
    def jours_atelier(self):
        fin = self.date_livraison or timezone.now()
        return (fin - self.date_reception).days

    @property
    def minutes_travail(self):
        return sum(p.minutes for p in self.pointages.all())

    def antecedents(self):
        """Ce qui s'est déjà passé sur ce véhicule et qui concerne cette réparation."""
        avant = self.vehicule.ordres.exclude(pk=self.pk).exclude(statut="annule") \
            .filter(date_reception__lt=self.date_reception).prefetch_related("systemes", "lignes")
        mes_sys = set(self.systemes.all())
        mes_pieces = {_norm(l.designation) for l in self.lignes.all() if l.type == "piece"}
        meme_partie, pieces = [], []
        for o in avant:
            communs = mes_sys & set(o.systemes.all())
            if communs:
                meme_partie.append({"ordre": o, "systemes": sorted(s.nom for s in communs),
                                    "jours": (self.date_reception - o.date_reception).days,
                                    "km": (self.kilometrage - o.kilometrage) if self.kilometrage and o.kilometrage else None})
            for l in o.lignes.all():
                n = _norm(l.designation)
                if l.type == "piece" and n and any(n in m or m in n for m in mes_pieces):
                    pieces.append({"ordre": o, "piece": l.designation,
                                   "jours": (self.date_reception - o.date_reception).days,
                                   "km": (self.kilometrage - o.kilometrage) if self.kilometrage and o.kilometrage else None})
        surveiller = [o for o in avant if o.travaux_refuses or o.recommandations]
        return {"meme_partie": meme_partie, "pieces": pieces, "surveiller": surveiller,
                "vide": not (meme_partie or pieces or surveiller)}


def _norm(txt):
    return " ".join(txt.lower().replace("-", " ").split())


class NoteVisite(models.Model):
    """Notes prises pendant la visite (qui, quand, quoi)."""
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="notes")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    date = models.DateTimeField(auto_now_add=True)
    texte = models.TextField()

    class Meta:
        ordering = ["date"]


class Pointage(models.Model):
    """Temps de travail d'un mécanicien sur une réparation (démarrer / arrêter)."""
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="pointages")
    mecanicien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pointages")
    debut = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField(null=True, blank=True)

    @property
    def minutes(self):
        return int(((self.fin or timezone.now()) - self.debut).total_seconds() // 60)


class TypeEntretien(models.Model):
    """Liste des noms d'entretien. Les dates de retour sont choisies par le garage à chaque fois."""
    nom = models.CharField(max_length=100, unique=True)
    intervalle_km = models.PositiveIntegerField("Tous les … km", null=True, blank=True)
    intervalle_mois = models.PositiveIntegerField("Tous les … mois", null=True, blank=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Type d'entretien"

    def __str__(self):
        return self.nom


class Entretien(models.Model):
    """Carnet d'entretien : ce qui a été fait et quand le refaire (date et/ou kilométrage)."""
    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, related_name="entretiens")
    designation = models.CharField("Entretien", max_length=150)
    ordre = models.ForeignKey(OrdreReparation, null=True, blank=True, on_delete=models.SET_NULL, related_name="entretiens")
    fait_le = models.DateField("Fait le")
    fait_km = models.PositiveIntegerField("Fait à (km)", null=True, blank=True)
    prochain_km = models.PositiveIntegerField("Prochain à (km)", null=True, blank=True)
    prochaine_date = models.DateField("Prochain le", null=True, blank=True)
    actif = models.BooleanField(default=True, help_text="Remplacé par un entretien plus récent du même type → inactif")

    class Meta:
        ordering = ["-fait_le", "-id"]

    def save(self, *a, **kw):
        super().save(*a, **kw)
        if self.actif:   # le nouvel entretien remplace l'ancien du même type
            anciens = Entretien.objects.filter(vehicule=self.vehicule, actif=True, designation__iexact=self.designation) \
                .exclude(pk=self.pk).filter(fait_le__lte=self.fait_le)
            Rappel.objects.filter(entretien__in=anciens, statut="a_faire").update(statut="annule", note="Entretien fait")
            anciens.update(actif=False)

    def etat(self, km_actuel=None, aujourd_hui=None):
        """'depasse', 'bientot' ou 'ok'."""
        aujourd_hui = aujourd_hui or timezone.localdate()
        km_actuel = km_actuel if km_actuel is not None else self.vehicule.km_estime()
        p = Parametres.get()
        etats = []
        if self.prochaine_date:
            j = (self.prochaine_date - aujourd_hui).days
            etats.append("depasse" if j < 0 else "bientot" if j <= p.alerte_jours else "ok")
        if self.prochain_km:
            k = self.prochain_km - km_actuel
            etats.append("depasse" if k < 0 else "bientot" if k <= p.alerte_km else "ok")
        for e in ("depasse", "bientot"):
            if e in etats:
                return e
        return "ok"


class LigneOrdre(models.Model):
    TYPES = [("piece", "Pièce"), ("mo", "Main-d'œuvre")]
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="lignes")
    type = models.CharField(max_length=6, choices=TYPES, default="piece")
    designation = models.CharField("Désignation", max_length=200)
    quantite = models.DecimalField("Qté", max_digits=8, decimal_places=2, default=1)
    prix_unitaire = montant(verbose_name="Prix unitaire")

    @property
    def total(self):
        return (self.quantite * self.prix_unitaire).quantize(1)


def chemin_photo(instance, filename):
    dossier = "factures" if isinstance(instance, Depense) else "degats"
    return f"{dossier}/{timezone.localdate():%Y/%m}/{filename}"


class PhotoDegat(models.Model):
    ordre = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=chemin_photo)
    legende = models.CharField("Légende", max_length=120, blank=True)
    ajoute_le = models.DateTimeField(auto_now_add=True)

    def save(self, *a, **kw):
        if self.image and not self.pk:
            self.image = compresser_photo(self.image)
        super().save(*a, **kw)


MODES = [("especes", "Espèces"), ("mobile", "Mobile money"), ("banque", "Banque / chèque")]


class Paiement(models.Model):
    """Argent qui entre dans la caisse."""
    date = models.DateTimeField(default=timezone.now)
    montant = montant()
    mode = models.CharField(max_length=10, choices=MODES, default="especes")
    libelle = models.CharField("Libellé", max_length=200)
    ordre = models.ForeignKey(OrdreReparation, null=True, blank=True, on_delete=models.PROTECT, related_name="paiements")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.PROTECT, related_name="paiements")
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date"]


class Depense(models.Model):
    """Argent qui sort : avec facture (photo) ou sans facture (bon interne)."""
    CATEGORIES = [
        ("pieces", "Achat de pièces"), ("consommables", "Consommables / huile"), ("salaires", "Salaires"),
        ("transport", "Transport"), ("carburant", "Carburant"), ("electricite", "Électricité / eau"),
        ("internet", "Internet / téléphone"), ("loyer", "Loyer"), ("outillage", "Outillage"),
        ("entretien", "Entretien du garage"), ("frais", "Frais bancaires / mobile money"), ("divers", "Divers"),
    ]
    date = models.DateTimeField(default=timezone.now)
    montant = montant()
    categorie = models.CharField("Catégorie", max_length=15, choices=CATEGORIES, default="divers")
    avec_facture = models.BooleanField("Avec facture", default=True)
    fournisseur = models.CharField("Fournisseur / bénéficiaire", max_length=150, blank=True)
    numero_document = models.CharField("N° de facture", max_length=60, blank=True)
    motif = models.CharField(max_length=250)
    mode = models.CharField(max_length=10, choices=MODES, default="especes")
    photo = models.ImageField("Photo de la facture", upload_to=chemin_photo, blank=True)
    ordre = models.ForeignKey(OrdreReparation, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="depenses", verbose_name="Réparation liée")
    numero_bon = models.CharField("N° bon interne", max_length=20, blank=True, editable=False)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date"]

    def save(self, *a, **kw):
        if self.photo and not self.pk:
            self.photo = compresser_photo(self.photo)
        if not self.avec_facture and not self.numero_bon:
            annee = timezone.localdate().year
            n = Depense.objects.filter(numero_bon__startswith=f"BI{annee}-").count() + 1
            self.numero_bon = f"BI{annee}-{n:04d}"
        super().save(*a, **kw)


class Rappel(models.Model):
    """Client à contacter (entretien, véhicule prêt, devis, impayé…)."""
    STATUTS = [("a_faire", "À contacter"), ("contacte", "Contacté"), ("annule", "Annulé")]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="rappels")
    vehicule = models.ForeignKey(Vehicule, null=True, blank=True, on_delete=models.CASCADE, related_name="rappels")
    motif = models.CharField(max_length=200)
    date_prevue = models.DateField("À contacter le")
    statut = models.CharField(max_length=10, choices=STATUTS, default="a_faire")
    note = models.CharField(max_length=250, blank=True)
    contacte_le = models.DateTimeField(null=True, blank=True)
    entretien = models.ForeignKey("Entretien", null=True, blank=True, on_delete=models.CASCADE, related_name="rappels")
    ordre = models.ForeignKey(OrdreReparation, null=True, blank=True, on_delete=models.CASCADE, related_name="rappels")

    class Meta:
        ordering = ["date_prevue"]

    @property
    def en_retard(self):
        return self.statut == "a_faire" and self.date_prevue < timezone.localdate()

    def message(self):
        veh = f" ({self.vehicule.marque} {self.vehicule.modele} {self.vehicule.immatriculation})" if self.vehicule else ""
        if self.client.langue == "mg":
            return f"Manao ahoana {self.client.nom}, garage CAR PLUS ity. {self.motif}{veh}. Misaotra!"
        return f"Bonjour {self.client.nom}, ici le garage CAR PLUS. {self.motif}{veh}. Merci !"


class ContactClient(models.Model):
    """Chaque tentative de contact : par quel moyen, et le résultat."""
    RESULTATS = [("joint", "Joint, d'accord"), ("message", "Message envoyé"), ("pas_repondu", "Pas de réponse"),
                 ("rappeler", "À rappeler"), ("refuse", "Ne souhaite pas"), ("faux_numero", "Numéro faux / injoignable")]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="contacts")
    rappel = models.ForeignKey(Rappel, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    canal = models.CharField(max_length=10, choices=Client.CANAUX)
    resultat = models.CharField("Résultat", max_length=12, choices=RESULTATS)
    note = models.CharField(max_length=250, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date"]


class Journal(models.Model):
    """Historique de toutes les modifications (rien n'est effacé en silence)."""
    date = models.DateTimeField(auto_now_add=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    objet = models.CharField(max_length=60)
    objet_id = models.PositiveIntegerField()
    champ = models.CharField(max_length=60)
    ancienne = models.TextField(blank=True)
    nouvelle = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]


class Parametres(models.Model):
    """Coordonnées du garage affichées sur les factures (une seule ligne)."""
    nom = models.CharField("Nom du garage", max_length=120, default="CAR SERVICE PLUS")
    slogan = models.CharField("Sous-titre", max_length=150, blank=True, default="GARAGE")
    phrase_pied = models.CharField("Phrase en bas des documents", max_length=150, blank=True,
                                   default="LA PASSION AU SERVICE DE VOTRE AUTO")
    gerant = models.CharField("Nom du gérant (signature)", max_length=120, blank=True)
    banque = models.CharField("Banque", max_length=60, blank=True)
    rib = models.CharField("RIB", max_length=60, blank=True)
    taux_tva = models.DecimalField("TVA (%)", max_digits=5, decimal_places=2, default=0,
                                   help_text="0 = pas de TVA sur les factures (« total net »)")
    prochain_numero_facture = models.PositiveIntegerField("Prochain numéro de facture", default=1,
                                                          help_text="Ex. : 18 pour continuer après FAC-000017")
    adresse = models.CharField(max_length=250, blank=True)
    telephone = models.CharField("Téléphone", max_length=60, blank=True)
    email = models.EmailField(blank=True)
    nif = models.CharField("NIF", max_length=40, blank=True)
    stat = models.CharField("STAT", max_length=40, blank=True)
    pied_facture = models.TextField("Mention supplémentaire sur la facture (facultatif)", blank=True, default="")
    mois_entretien = models.PositiveIntegerField("Rappel d'entretien après (mois)", default=6)
    alerte_jours = models.PositiveIntegerField("Prévenir … jours avant l'échéance d'un entretien", default=15)
    alerte_km = models.PositiveIntegerField("Prévenir … km avant l'échéance d'un entretien", default=1000)
    jours_retard = models.PositiveIntegerField("Réparation en retard après … jours à l'atelier", default=7)
    mois_inactif = models.PositiveIntegerField("Client inactif après … mois sans visite", default=6)

    class Meta:
        verbose_name = "Paramètres du garage"
        verbose_name_plural = "Paramètres du garage"

    def __str__(self):
        return self.nom

    @classmethod
    def get(cls):
        return cls.objects.first() or cls.objects.create()
