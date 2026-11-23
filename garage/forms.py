from django import forms
from django.contrib.auth import get_user_model

from .models import Client, Depense, LigneOrdre, OrdreReparation, Paiement, PhotoDegat, Rappel, Vehicule, MODES


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["type", "nom", "telephone", "telephone2", "whatsapp", "facebook", "email", "canal_prefere", "adresse",
                  "nif", "stat", "contact", "langue", "accepte_rappels", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class VehiculeForm(forms.ModelForm):
    class Meta:
        model = Vehicule
        fields = ["proprietaire", "categorie", "immatriculation", "marque", "modele", "annee", "vin",
                  "moteur", "carburant", "couleur", "kilometrage", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class ChangementProprioForm(forms.Form):
    nouveau = forms.ModelChoiceField(Client.objects.all(), label="Nouveau propriétaire")
    date = forms.DateField(label="Date du changement", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class OrdreForm(forms.ModelForm):
    class Meta:
        model = OrdreReparation
        fields = ["vehicule", "client", "kilometrage", "deposant", "probleme", "mecanicien"]
        widgets = {"probleme": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["client"].required = False
        self.fields["client"].help_text = "Laisser vide = le propriétaire du véhicule"
        self.fields["mecanicien"].queryset = get_user_model().objects.filter(is_active=True)


class LigneForm(forms.ModelForm):
    class Meta:
        model = LigneOrdre
        fields = ["type", "designation", "quantite", "prix_unitaire"]
        widgets = {
            "designation": forms.TextInput(attrs={"placeholder": "Désignation (ex. : plaquettes de frein avant)"}),
            "quantite": forms.NumberInput(attrs={"placeholder": "Qté", "step": "0.5"}),
            "prix_unitaire": forms.NumberInput(attrs={"placeholder": "Prix unitaire (Ar)"}),
        }


class PaiementForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ["montant", "mode"]
        widgets = {"montant": forms.NumberInput(attrs={"placeholder": "Montant (Ar)"})}


class PhotoForm(forms.ModelForm):
    class Meta:
        model = PhotoDegat
        fields = ["image", "legende"]


class DepenseForm(forms.ModelForm):
    class Meta:
        model = Depense
        fields = ["avec_facture", "montant", "categorie", "motif", "fournisseur", "numero_document",
                  "mode", "photo", "ordre"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["ordre"].queryset = OrdreReparation.objects.select_related("vehicule").exclude(statut="annule")
        self.fields["ordre"].required = False

    def clean(self):
        d = super().clean()
        if d.get("avec_facture") and not d.get("photo"):
            self.add_error("photo", "Une dépense avec facture doit avoir la photo de la facture.")
        if (d.get("montant") or 0) <= 0:
            self.add_error("montant", "Le montant doit être supérieur à 0.")
        return d


class CaisseRapideForm(forms.Form):
    sens = forms.ChoiceField(choices=[("entree", "Entrée d'argent"), ("sortie", "Sortie d'argent")],
                             widget=forms.RadioSelect, initial="entree")
    montant = forms.DecimalField(min_value=1, decimal_places=0, max_digits=14)
    libelle = forms.CharField(max_length=200, label="Pour quoi ?")
    mode = forms.ChoiceField(choices=MODES)


class RappelForm(forms.ModelForm):
    class Meta:
        model = Rappel
        fields = ["client", "vehicule", "motif", "date_prevue", "note"]
        widgets = {"date_prevue": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vehicule"].required = False


from .models import Entretien, NoteVisite, Systeme, TypeEntretien  # noqa: E402


class ReceptionForm(forms.Form):
    """Réception en un seul écran : véhicule existant OU nouveau véhicule + client, sans changer de page."""
    immatriculation = forms.CharField(max_length=20, label="Immatriculation",
                                      widget=forms.TextInput(attrs={"placeholder": "Ex. : 1234 TBA", "autocomplete": "off",
                                                                    "style": "text-transform:uppercase;font-size:1.2rem"}))
    # Nouveau véhicule (si la plaque est inconnue)
    categorie = forms.ChoiceField(choices=Vehicule.CATEGORIES, required=False, label="Catégorie")
    marque = forms.CharField(max_length=60, required=False)
    modele = forms.CharField(max_length=60, required=False, label="Modèle")
    annee = forms.IntegerField(required=False, label="Année", min_value=1950, max_value=2100)
    carburant = forms.ChoiceField(choices=Vehicule.CARBURANTS, required=False)
    vin = forms.CharField(max_length=40, required=False, label="VIN / n° de cadre")
    # Propriétaire
    client_existant = forms.ModelChoiceField(Client.objects.all(), required=False, label="Propriétaire déjà enregistré")
    client_nom = forms.CharField(max_length=150, required=False, label="Ou nouveau propriétaire : nom")
    client_type = forms.ChoiceField(choices=Client.TYPES, required=False, label="Type")
    client_telephone = forms.CharField(max_length=30, required=False, label="Téléphone")
    client_facebook = forms.CharField(max_length=200, required=False, label="Facebook (facultatif)")
    # Visite
    kilometrage = forms.IntegerField(min_value=0, required=False, label="Kilométrage au compteur")
    niveau_carburant = forms.ChoiceField(choices=OrdreReparation.NIVEAUX, required=False, label="Niveau de carburant")
    deposant = forms.CharField(max_length=120, required=False, label="Déposé par (si ce n'est pas le propriétaire)")
    probleme = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Problème signalé par le client")
    systemes = forms.ModelMultipleChoiceField(Systeme.objects.all(), required=False, label="Parties concernées",
                                              widget=forms.CheckboxSelectMultiple)
    etat_carrosserie = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False,
                                       label="État de la carrosserie (rayures, chocs…)")
    accessoires = forms.CharField(max_length=250, required=False, label="Objets laissés dans le véhicule")
    mecanicien = forms.ModelChoiceField(get_user_model().objects.filter(is_active=True), required=False, label="Mécanicien")

    def clean(self):
        d = super().clean()
        immat = (d.get("immatriculation") or "").upper().replace(" ", "")
        d["immatriculation"] = immat
        self.vehicule = Vehicule.objects.filter(immatriculation=immat).first()
        if not self.vehicule:
            if not d.get("marque") or not d.get("modele"):
                self.add_error("marque", "Véhicule inconnu : indiquez au moins la marque et le modèle.")
            if not d.get("client_existant") and not d.get("client_nom"):
                self.add_error("client_nom", "Choisissez le propriétaire ou saisissez son nom.")
        return d


class EntretienForm(forms.Form):
    type = forms.ModelChoiceField(TypeEntretien.objects.all(), required=False, label="Entretien",
                                  empty_label="— choisir dans la liste —")
    autre = forms.CharField(max_length=150, required=False, label="ou autre entretien")
    fait_le = forms.DateField(label="Fait le", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fait_km = forms.IntegerField(required=False, min_value=0, label="Fait à (km)")
    prochaine_date = forms.DateField(required=False, label="Le client doit revenir le",
                                     widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    prochain_km = forms.IntegerField(required=False, min_value=1, label="ou à … km au compteur")

    def clean(self):
        d = super().clean()
        t = d.get("type")
        d["designation"] = (t.nom if t else (d.get("autre") or "").strip())
        if not d["designation"]:
            self.add_error("type", "Choisissez l'entretien ou écrivez-le.")
        if d.get("prochaine_date") and d.get("fait_le") and d["prochaine_date"] <= d["fait_le"]:
            self.add_error("prochaine_date", "La date de retour doit être après la date de l'entretien.")
        if d.get("prochain_km") and d.get("fait_km") and d["prochain_km"] <= d["fait_km"]:
            self.add_error("prochain_km", "Le kilométrage de retour doit être supérieur au kilométrage actuel.")
        return d


class NoteForm(forms.ModelForm):
    class Meta:
        model = NoteVisite
        fields = ["texte"]
        widgets = {"texte": forms.Textarea(attrs={"rows": 2, "placeholder": "Ex. : bruit au freinage confirmé à l'essai routier…"})}
        labels = {"texte": ""}
