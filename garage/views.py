import datetime as dt
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (CaisseRapideForm, ChangementProprioForm, ClientForm, DepenseForm, EntretienForm, LigneForm,
                    NoteForm, PaiementForm, PhotoForm, RappelForm, ReceptionForm, VehiculeForm)
from .models import (Client, ContactClient, Depense, Entretien, Journal, LigneOrdre, OrdreReparation, Paiement, Parametres,
                     Pointage, Rappel, Systeme, Vehicule)
from .services import generer_alertes_entretien
from .roles import CAISSE, MECANICIEN, PATRON, exige, voit_argent

ARGENT = (PATRON, CAISSE)


def _hx(request):
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------- Accueil
def accueil(request):
    generer_alertes_entretien()
    aujourd_hui = timezone.localdate()
    p = Parametres.get()
    limite = timezone.now() - dt.timedelta(days=p.jours_retard)
    ctx = {
        "retards": OrdreReparation.objects.filter(statut__in=OrdreReparation.STATUTS_ACTIFS, date_reception__lt=limite)
                   .select_related("vehicule", "mecanicien"),
        "jours_retard": p.jours_retard,
        "en_cours": OrdreReparation.objects.filter(statut__in=OrdreReparation.STATUTS_ACTIFS)
                    .select_related("vehicule", "client", "mecanicien"),
        "rappels": Rappel.objects.filter(statut="a_faire", date_prevue__lte=aujourd_hui)
                   .select_related("client", "vehicule")[:10],
    }
    if voit_argent(request.user):
        debut = timezone.make_aware(dt.datetime.combine(aujourd_hui, dt.time.min))
        ctx["entrees_jour"] = Paiement.objects.filter(date__gte=debut).aggregate(s=Sum("montant"))["s"] or 0
        ctx["sorties_jour"] = Depense.objects.filter(date__gte=debut).aggregate(s=Sum("montant"))["s"] or 0
        impayes = [o for o in OrdreReparation.objects.filter(statut="livre").prefetch_related("lignes", "paiements")
                   if o.reste > 0]
        ctx["impayes"] = impayes[:8]
        ctx["total_impayes"] = sum(o.reste for o in impayes)
    if request.user.groups.filter(name=MECANICIEN).exists():
        ctx["en_cours"] = ctx["en_cours"].filter(mecanicien=request.user)
    return render(request, "garage/accueil.html", ctx)


# ---------------------------------------------------------------- Recherche globale
MENUS = [
    ("Tableau de bord", "accueil", "accueil maison début", None),
    ("Clients et sociétés", "clients", "clients client société societe particulier", None),
    ("Nouveau client", "client_nouveau", "nouveau client ajouter créer", None),
    ("Véhicules", "vehicules", "véhicules vehicules voiture moto registre", None),
    ("Nouveau véhicule", "vehicule_nouveau", "nouveau véhicule voiture moto ajouter", None),
    ("Atelier (réparations)", "ordres", "atelier réparations ordre or travaux", None),
    ("Réception d'un véhicule", "ordre_nouveau", "réception reception nouvel ordre entrée véhicule", None),
    ("Caisse", "caisse", "caisse argent recettes entrées jour semaine mois année", ARGENT),
    ("Dépenses", "depenses", "dépenses depenses sorties factures achats", ARGENT),
    ("Nouvelle dépense", "depense_nouvelle", "nouvelle dépense facture photo bon", ARGENT),
    ("Alertes / à contacter", "rappels", "alertes rappels contacter relance entretien", None),
    ("Clients inactifs", "rappels", "inactifs fidélisation relance anciens clients", None),
    ("Campagne (véhicules de plus de 5 ans…)", "vehicules", "campagne promotion offre ciblée âge", None),
    ("Historique des modifications", "journal", "historique journal modifications", (PATRON,)),
    ("Paramètres du garage", "parametres", "paramètres parametres nif stat logo facture", (PATRON,)),
]


def recherche(request):
    q = (request.GET.get("q") or "").strip()
    res = {"q": q}
    if len(q) >= 2:
        ql = q.lower()
        from .roles import role
        r = role(request.user)
        res["menus"] = [(n, reverse(u)) for n, u, mots, roles in MENUS
                        if (roles is None or r in roles) and (ql in n.lower() or any(m.startswith(ql) for m in mots.split()))][:5]
        res["clients"] = Client.objects.filter(Q(nom__icontains=q) | Q(telephone__icontains=q) | Q(whatsapp__icontains=q)
                                               | Q(telephone2__icontains=q) | Q(facebook__icontains=q) | Q(email__icontains=q)
                                               | Q(nif__icontains=q))[:6]
        qv = q.upper().replace(" ", "")
        res["vehicules"] = Vehicule.objects.filter(Q(immatriculation__icontains=qv) | Q(vin__icontains=q) | Q(marque__icontains=q)
                                                   | Q(modele__icontains=q)).select_related("proprietaire")[:6]
        res["ordres"] = OrdreReparation.objects.filter(Q(numero__icontains=q) | Q(probleme__icontains=q)
                                                       | Q(vehicule__immatriculation__icontains=qv)).select_related("vehicule")[:6]
        if voit_argent(request.user):
            res["depenses"] = Depense.objects.filter(Q(motif__icontains=q) | Q(fournisseur__icontains=q)
                                                     | Q(numero_document__icontains=q) | Q(numero_bon__icontains=q))[:6]
        res["vide"] = not any(res.get(k) for k in ("menus", "clients", "vehicules", "ordres", "depenses"))
    tpl = "garage/_recherche.html" if _hx(request) else "garage/recherche.html"
    return render(request, tpl, res)


# ---------------------------------------------------------------- Édition directe
EDITABLE = {
    "client": (Client, {"nom", "telephone", "telephone2", "whatsapp", "facebook", "email", "adresse", "nif", "stat", "contact",
                        "notes"}, None),
    "vehicule": (Vehicule, {"marque", "modele", "annee", "vin", "moteur", "couleur", "kilometrage", "notes"}, None),
    "ordre": (OrdreReparation, {"probleme", "diagnostic", "cause", "travaux", "recommandations", "travaux_refuses",
                                "risque", "deposant", "kilometrage", "accessoires", "etat_carrosserie"}, None),
    "ordre_argent": (OrdreReparation, {"remise", "forfait"}, ARGENT),
    "ligne": (LigneOrdre, {"designation", "quantite", "prix_unitaire"}, ARGENT),
    "depense": (Depense, {"motif", "fournisseur", "numero_document", "montant"}, ARGENT),
    "entretien": (Entretien, {"prochaine_date", "prochain_km"}, None),
    "rappel": (Rappel, {"date_prevue", "motif", "note"}, None),
}


def editer(request, cle, pk, champ):
    if cle not in EDITABLE:
        raise PermissionDenied
    modele, champs, roles = EDITABLE[cle]
    from .roles import role
    if champ not in champs or (roles and role(request.user) not in roles):
        raise PermissionDenied
    obj = get_object_or_404(modele, pk=pk)
    field = modele._meta.get_field(champ)
    ctx = {"obj": obj, "cle": cle, "champ": champ, "label": field.verbose_name,
           "multiligne": field.get_internal_type() == "TextField",
           "type_input": "date" if field.get_internal_type() == "DateField" else "text"}
    if request.method == "POST":
        brut = request.POST.get("valeur", "")
        ancienne = getattr(obj, champ)
        try:
            formfield = field.formfield()
            valeur = formfield.clean(brut)
            setattr(obj, champ, valeur)
            obj.full_clean(validate_unique=False)
        except ValidationError as e:
            setattr(obj, champ, ancienne)
            ctx.update(erreur=" ".join(e.messages), valeur=brut)
            return render(request, "garage/_edit_input.html", ctx)
        if str(ancienne) != str(valeur):
            obj.save(update_fields=[champ])
            Journal.objects.create(utilisateur=request.user, objet=cle, objet_id=obj.pk, champ=champ,
                                   ancienne="" if ancienne is None else str(ancienne), nouvelle=str(valeur))
        resp = render(request, "garage/_edit_display.html", ctx)
        if cle in ("ligne", "ordre_argent"):
            resp["HX-Trigger"] = "totaux-changes"
        return resp
    if request.GET.get("annuler"):
        return render(request, "garage/_edit_display.html", ctx)
    v = getattr(obj, champ)
    ctx["valeur"] = "" if v is None else (v.isoformat() if hasattr(v, "isoformat") else v)
    return render(request, "garage/_edit_input.html", ctx)


# ---------------------------------------------------------------- Clients
def clients(request):
    qs = Client.objects.annotate(nb_vehicules=Count("vehicules"))
    t = request.GET.get("type")
    if t in ("particulier", "societe"):
        qs = qs.filter(type=t)
    q = request.GET.get("q")
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))
    return render(request, "garage/clients.html", {"clients": qs, "type": t, "q": q or ""})


def client_form(request, pk=None):
    obj = get_object_or_404(Client, pk=pk) if pk else None
    form = ClientForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        messages.success(request, f"Client « {c.nom} » enregistré.")
        return redirect(c)
    return render(request, "garage/form.html", {"form": form, "titre": "Modifier le client" if obj else "Nouveau client"})


def client_detail(request, pk):
    c = get_object_or_404(Client, pk=pk)
    ordres = c.ordres.select_related("vehicule").prefetch_related("lignes", "paiements")
    faits = [o for o in ordres if o.statut != "annule"]
    return render(request, "garage/client_detail.html", {
        "c": c, "vehicules": c.vehicules.all(), "ordres": ordres,
        "nb_visites": len(faits), "total_depense": sum(o.total for o in faits if o.statut == "livre"),
        "dernier_passage": faits[0].date_reception if faits else None,
        "total_du": sum(o.reste for o in faits if o.statut == "livre" and o.reste > 0),
        "rappels": c.rappels.select_related("vehicule").order_by("-date_prevue")[:10],
        "contacts": c.contacts.select_related("par")[:30],
    })


# ---------------------------------------------------------------- Véhicules
def vehicules(request):
    qs = Vehicule.objects.select_related("proprietaire")
    cat = request.GET.get("categorie")
    if cat:
        qs = qs.filter(categorie=cat)
    age = request.GET.get("age")
    if age and age.isdigit():
        qs = qs.filter(annee__lte=timezone.localdate().year - int(age))
    marque = request.GET.get("marque")
    if marque:
        qs = qs.filter(marque__iexact=marque)
    if request.method == "POST" and request.POST.get("motif"):
        n = 0
        for v in qs:
            if v.proprietaire.accepte_rappels:
                Rappel.objects.create(client=v.proprietaire, vehicule=v, motif=request.POST["motif"],
                                      date_prevue=request.POST.get("date") or timezone.localdate())
                n += 1
        messages.success(request, f"Campagne créée : {n} client(s) ajouté(s) dans « À contacter ».")
        return redirect("rappels")
    q = request.GET.get("q")
    if q:
        qv = q.upper().replace(" ", "")
        qs = qs.filter(Q(immatriculation__icontains=qv) | Q(marque__icontains=q) | Q(modele__icontains=q)
                       | Q(proprietaire__nom__icontains=q) | Q(vin__icontains=q))
    return render(request, "garage/vehicules.html", {"vehicules": qs, "categorie": cat, "q": q or "", "age": age or "",
                                                     "marque": marque or "", "categories": Vehicule.CATEGORIES,
                                                     "marques": Vehicule.objects.values_list("marque", flat=True).distinct().order_by("marque")})


def vehicule_form(request, pk=None):
    obj = get_object_or_404(Vehicule, pk=pk) if pk else None
    initial = {"proprietaire": request.GET.get("client")} if not obj else None
    form = VehiculeForm(request.POST or None, instance=obj, initial=initial)
    if obj:
        form.fields["proprietaire"].disabled = True
        form.fields["proprietaire"].help_text = "Pour changer de propriétaire, utilisez « Changer de propriétaire »."
    if request.method == "POST" and form.is_valid():
        v = form.save()
        messages.success(request, f"Véhicule {v.immatriculation} enregistré.")
        return redirect(v)
    return render(request, "garage/form.html", {"form": form, "titre": "Modifier le véhicule" if obj else "Nouveau véhicule"})


def vehicule_detail(request, pk):
    v = get_object_or_404(Vehicule.objects.select_related("proprietaire"), pk=pk)
    ordres = v.ordres.select_related("mecanicien", "client").prefetch_related("lignes", "photos", "paiements")
    km = v.km_estime()
    carnet = [(e, e.etat(km_actuel=km)) for e in v.entretiens.filter(actif=True)]
    return render(request, "garage/vehicule_detail.html", {
        "v": v, "ordres": ordres.prefetch_related("notes", "systemes", "pointages"),
        "changements": v.changements.select_related("ancien", "nouveau"),
        "premiere": ordres.last(), "km_estime": km, "km_jour": v.km_par_jour(), "carnet": carnet,
        "anciens_entretiens": v.entretiens.filter(actif=False)[:30], "surveiller": v.a_surveiller(),
        "recurrents": v.problemes_recurrents(),
        "entretien_form": EntretienForm(initial={"fait_le": timezone.localdate(), "fait_km": km or None}),
    })


def vehicule_proprietaire(request, pk):
    v = get_object_or_404(Vehicule, pk=pk)
    form = ChangementProprioForm(request.POST or None, initial={"date": timezone.localdate()})
    form.fields["nouveau"].queryset = Client.objects.exclude(pk=v.proprietaire_id)
    if request.method == "POST" and form.is_valid():
        v.changer_proprietaire(form.cleaned_data["nouveau"], request.user, form.cleaned_data["date"])
        messages.success(request, "Propriétaire changé. L'historique technique du véhicule est conservé.")
        return redirect(v)
    return render(request, "garage/form.html", {"form": form, "titre": f"Changer le propriétaire de {v.immatriculation}",
                                                "aide": f"Propriétaire actuel : {v.proprietaire}"})


# ---------------------------------------------------------------- Atelier
def ordres(request):
    qs = OrdreReparation.objects.select_related("vehicule", "client", "mecanicien")
    if request.user.groups.filter(name=MECANICIEN).exists() and not request.user.is_superuser:
        qs = qs.filter(mecanicien=request.user)
    vue = request.GET.get("vue", "tableau")
    actifs = qs.filter(statut__in=OrdreReparation.STATUTS_ACTIFS)
    colonnes = [(code, nom, [o for o in actifs if o.statut == code])
                for code, nom in OrdreReparation.STATUTS if code in OrdreReparation.STATUTS_ACTIFS]
    termines = qs.filter(statut__in=["livre", "annule"])[:50]
    return render(request, "garage/ordres.html", {"colonnes": colonnes, "termines": termines, "vue": vue})


def ordre_nouveau(request):
    """Réception en un seul écran (véhicule et client créés sur place si nouveaux)."""
    initial = {}
    if request.GET.get("vehicule"):
        v = Vehicule.objects.filter(pk=request.GET["vehicule"]).first()
        if v:
            initial = {"immatriculation": v.immatriculation, "kilometrage": v.km_estime() or None}
    form = ReceptionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            v = form.vehicule
            if not v:
                client = d["client_existant"]
                if not client:
                    client = Client.objects.create(nom=d["client_nom"], type=d["client_type"] or "particulier",
                                                   telephone=d["client_telephone"], whatsapp=d["client_telephone"],
                                                   facebook=d["client_facebook"])
                v = Vehicule.objects.create(proprietaire=client, immatriculation=d["immatriculation"],
                                            categorie=d["categorie"] or "voiture", marque=d["marque"], modele=d["modele"],
                                            annee=d["annee"], carburant=d["carburant"], vin=d["vin"],
                                            kilometrage=d["kilometrage"] or 0)
            o = OrdreReparation.objects.create(
                vehicule=v, client=v.proprietaire, kilometrage=d["kilometrage"] or 0, deposant=d["deposant"],
                probleme=d["probleme"], niveau_carburant=d["niveau_carburant"], accessoires=d["accessoires"],
                etat_carrosserie=d["etat_carrosserie"], mecanicien=d["mecanicien"], cree_par=request.user)
            o.systemes.set(d["systemes"])
            if (d["kilometrage"] or 0) > v.kilometrage:
                v.kilometrage = d["kilometrage"]
                v.save(update_fields=["kilometrage"])
        messages.success(request, f"Ordre de réparation {o.numero} créé. Vérifiez les antécédents du véhicule ci-dessous.")
        return redirect(o)
    vehicule = getattr(form, "vehicule", None) or (Vehicule.objects.filter(pk=request.GET.get("vehicule")).first()
                                                   if request.GET.get("vehicule") else None)
    return render(request, "garage/reception.html", {"form": form, "vehicule": vehicule,
                                                     **(_fiche_reception(vehicule) if vehicule else {})})


def _fiche_reception(v):
    """Ce que la réceptionniste doit voir dès qu'elle tape la plaque."""
    derniere = v.ordres.exclude(statut="annule").first()
    entretiens = [e for e in v.entretiens.filter(actif=True) if e.etat() != "ok"]
    return {"derniere": derniere, "entretiens_dus": entretiens, "surveiller": v.a_surveiller()[:5],
            "recurrents": v.problemes_recurrents(), "km_estime": v.km_estime(),
            "en_cours": v.ordres.filter(statut__in=OrdreReparation.STATUTS_ACTIFS).first()}


def reception_vehicule(request):
    """Recherche instantanée de la plaque pendant la réception."""
    immat = (request.GET.get("immatriculation") or "").upper().replace(" ", "")
    v = Vehicule.objects.filter(immatriculation=immat).select_related("proprietaire").first() if len(immat) >= 3 else None
    ctx = {"vehicule": v, "immat": immat, "form": ReceptionForm()}
    if v:
        ctx.update(_fiche_reception(v))
    return render(request, "garage/_reception_vehicule.html", ctx)


def ordre_detail(request, pk):
    o = get_object_or_404(OrdreReparation.objects.select_related("vehicule", "client", "mecanicien", "lie_a"), pk=pk)
    pointage_ouvert = o.pointages.filter(mecanicien=request.user, fin__isnull=True).first()
    return render(request, "garage/ordre_detail.html", {
        "o": o, "lignes": o.lignes.all(), "photos": o.photos.all(),
        "paiements": o.paiements.all(), "depenses": o.depenses.all(),
        "ligne_form": LigneForm(), "paiement_form": PaiementForm(initial={"montant": max(o.reste, 0)}),
        "photo_form": PhotoForm(), "statuts": OrdreReparation.STATUTS,
        "aujourdhui": timezone.localdate(),
        "ant": o.antecedents(), "notes": o.notes.select_related("auteur"), "note_form": NoteForm(),
        "entretien_form": EntretienForm(initial={"fait_le": o.date_reception.date(), "fait_km": o.kilometrage or None}),
        "entretiens": o.entretiens.all(), "tous_systemes": Systeme.objects.all(),
        "mes_systemes": set(o.systemes.values_list("pk", flat=True)),
        "precedents": o.vehicule.ordres.exclude(pk=o.pk).exclude(statut="annule"),
        "liens": OrdreReparation.LIENS[1:], "pointage_ouvert": pointage_ouvert,
        "pointages": o.pointages.select_related("mecanicien"),
    })


@require_POST
def ordre_systemes(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    avant = ", ".join(s.nom for s in o.systemes.all())
    o.systemes.set(Systeme.objects.filter(pk__in=request.POST.getlist("systemes")))
    Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=o.pk, champ="parties touchées",
                           ancienne=avant, nouvelle=", ".join(s.nom for s in o.systemes.all()))
    return redirect(reverse("ordre_detail", args=[pk]) + "#antecedents")


@require_POST
def ordre_lien(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    lie = o.vehicule.ordres.exclude(pk=o.pk).filter(pk=request.POST.get("lie_a") or 0).first()
    o.lie_a = lie
    o.nature_lien = request.POST.get("nature_lien", "") if lie else ""
    o.save(update_fields=["lie_a", "nature_lien"])
    Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=o.pk, champ="lien",
                           nouvelle=f"{o.get_nature_lien_display()} → {lie}" if lie else "aucun")
    messages.success(request, "Lien enregistré." if lie else "Lien retiré.")
    return redirect(reverse("ordre_detail", args=[pk]) + "#antecedents")


@require_POST
def note_ajout(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        n = form.save(commit=False)
        n.ordre, n.auteur = o, request.user
        n.save()
    return redirect(reverse("ordre_detail", args=[pk]) + "#notes")


def _creer_entretien(vehicule, d, ordre=None):
    return Entretien.objects.create(vehicule=vehicule, designation=d["designation"], ordre=ordre, fait_le=d["fait_le"],
                                    fait_km=d.get("fait_km"), prochain_km=d.get("prochain_km"),
                                    prochaine_date=d.get("prochaine_date"))


@require_POST
def entretien_ajout(request, pk):
    """pk = véhicule. Depuis une réparation (?ordre=) ou pour noter un entretien fait ailleurs."""
    v = get_object_or_404(Vehicule, pk=pk)
    ordre = v.ordres.filter(pk=request.POST.get("ordre") or 0).first()
    form = EntretienForm(request.POST)
    if form.is_valid():
        e = _creer_entretien(v, form.cleaned_data, ordre)
        if not (e.prochain_km or e.prochaine_date):
            messages.warning(request, f"« {e.designation} » enregistré, mais sans échéance : aucune alerte ne sera faite.")
        else:
            messages.success(request, f"« {e.designation} » enregistré dans le carnet. Le garage sera prévenu à l'échéance.")
    else:
        messages.error(request, "Entretien non enregistré : " + " ".join(sum(form.errors.values(), [])))
    return redirect((reverse("ordre_detail", args=[ordre.pk]) if ordre else reverse("vehicule_detail", args=[pk])) + "#carnet")


@require_POST
def pointage(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    ouvert = o.pointages.filter(mecanicien=request.user, fin__isnull=True).first()
    if ouvert:
        ouvert.fin = timezone.now()
        ouvert.save(update_fields=["fin"])
        messages.success(request, f"Travail arrêté ({ouvert.minutes} min).")
    else:
        Pointage.objects.filter(mecanicien=request.user, fin__isnull=True).update(fin=timezone.now())
        Pointage.objects.create(ordre=o, mecanicien=request.user)
        messages.success(request, "Chronomètre démarré.")
    return redirect(o)


@require_POST
def ordre_statut(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    nouveau = request.POST.get("statut")
    if nouveau not in dict(OrdreReparation.STATUTS):
        return HttpResponseBadRequest()
    ancien = o.get_statut_display()
    o.statut = nouveau
    if nouveau == "livre":
        o.date_livraison = timezone.now()
        # Les dates de retour/relance sont choisies par le garage ; le logiciel ne fait que prévenir.
        def _date(nom):
            try:
                return dt.date.fromisoformat(request.POST.get(nom, ""))
            except ValueError:
                return None
        retour, relance_refus, relance_paiement = _date("date_retour"), _date("date_relance_refus"), _date("date_relance_paiement")
        if retour:
            Rappel.objects.create(client=o.client, vehicule=o.vehicule, ordre=o, date_prevue=retour,
                                  motif=request.POST.get("motif_retour") or "Retour prévu au garage")
        if relance_refus and o.travaux_refuses:
            Rappel.objects.create(client=o.client, vehicule=o.vehicule, ordre=o, date_prevue=relance_refus,
                                  motif=f"Travaux conseillés non faits : {o.travaux_refuses[:120]}", note=o.risque[:250])
        if relance_paiement and o.reste > 0:
            Rappel.objects.create(client=o.client, vehicule=o.vehicule, ordre=o, date_prevue=relance_paiement,
                                  motif=f"Facture impayée : reste {int(o.reste):,} Ar (réparation {o.numero})".replace(",", " "))
    if nouveau == "pret":
        Rappel.objects.create(client=o.client, vehicule=o.vehicule,
                              motif="Votre véhicule est prêt, vous pouvez venir le récupérer",
                              date_prevue=timezone.localdate())
    if nouveau == "devis":
        Rappel.objects.create(client=o.client, vehicule=o.vehicule,
                              motif=f"Le devis de la réparation {o.numero} attend votre accord",
                              date_prevue=timezone.localdate())
    o.save()
    Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=o.pk, champ="statut",
                           ancienne=ancien, nouvelle=o.get_statut_display())
    messages.success(request, f"Statut : {o.get_statut_display()}.")
    return redirect(o)


@require_POST
def ligne_ajout(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    form = LigneForm(request.POST)
    if not voit_argent(request.user):
        form.data = form.data.copy()
        form.data["prix_unitaire"] = "0"
    if form.is_valid():
        l = form.save(commit=False)
        l.ordre = o
        l.save()
        Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=o.pk, champ="ligne ajoutée",
                               nouvelle=f"{l.designation} x{l.quantite} @ {l.prix_unitaire}")
    else:
        messages.error(request, "Ligne non ajoutée : vérifiez la désignation et les montants.")
    return redirect(reverse("ordre_detail", args=[pk]) + "#lignes")


@require_POST
@exige(*ARGENT)
def ligne_suppr(request, pk):
    l = get_object_or_404(LigneOrdre, pk=pk)
    Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=l.ordre_id, champ="ligne supprimée",
                           ancienne=f"{l.designation} x{l.quantite} @ {l.prix_unitaire}")
    l.delete()
    return redirect(reverse("ordre_detail", args=[l.ordre_id]) + "#lignes")


def ordre_totaux(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    return render(request, "garage/_totaux.html", {"o": o})


@require_POST
@exige(*ARGENT)
def paiement_ajout(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    form = PaiementForm(request.POST)
    if form.is_valid() and form.cleaned_data["montant"] > 0:
        p = form.save(commit=False)
        p.ordre, p.client, p.par = o, o.client, request.user
        p.libelle = f"Paiement réparation {o.numero} ({o.vehicule.immatriculation})"
        p.save()
        messages.success(request, f"Paiement de {p.montant:,.0f} Ar enregistré.".replace(",", " "))
    else:
        messages.error(request, "Montant invalide.")
    return redirect(reverse("ordre_detail", args=[pk]) + "#paiements")


@require_POST
def photo_ajout(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    form = PhotoForm(request.POST, request.FILES)
    if form.is_valid():
        p = form.save(commit=False)
        p.ordre = o
        p.save()
        messages.success(request, "Photo des dégâts ajoutée.")
    else:
        messages.error(request, "Photo non valide.")
    return redirect(reverse("ordre_detail", args=[pk]) + "#photos")


@exige(*ARGENT)
def facture(request, pk):
    """Documents imprimables au modèle CAR SERVICE PLUS : facture, devis, OR, rapport, état de dépense."""
    from .lettres import montant_en_lettres
    o = get_object_or_404(OrdreReparation.objects.select_related("vehicule", "client"), pk=pk)
    doc = request.GET.get("doc", "facture")
    p = Parametres.get()
    if doc == "facture" and not o.numero_facture:
        return render(request, "garage/facture_a_etablir.html", {"o": o, "p": p})
    titres = {"facture": ("FACTURE", o.numero_facture, o.date_facture),
              "devis": ("DEVIS", f"DEV-{o.numero}", timezone.localdate()),
              "or": ("ORDRE DE RÉPARATION", f"OR-{o.numero}", o.date_reception.date()),
              "rapport": ("RAPPORT DE RÉPARATION", f"RAP-{o.numero}", timezone.localdate()),
              "depenses": ("ÉTAT DE DÉPENSE", f"ED-{o.numero}", timezone.localdate())}
    titre, numero, date = titres.get(doc, titres["devis"])
    depenses = o.depenses.order_by("date", "id") if doc == "depenses" else []
    total_dep = sum(d.montant for d in depenses)
    return render(request, "garage/facture.html", {
        "o": o, "p": p, "doc": doc, "titre": titre, "numero": numero, "date": date,
        "lignes": o.lignes.all(), "depenses": depenses, "total_dep": total_dep,
        "lettres": montant_en_lettres(total_dep if doc == "depenses" else o.total),
    })


@require_POST
@exige(*ARGENT)
def facture_etablir(request, pk):
    o = get_object_or_404(OrdreReparation, pk=pk)
    o.etablir_facture()
    Journal.objects.create(utilisateur=request.user, objet="ordre", objet_id=o.pk, champ="facture établie",
                           nouvelle=o.numero_facture)
    return redirect(reverse("facture", args=[pk]) + "?doc=facture")


# ---------------------------------------------------------------- Caisse
def _periode(request):
    periode = request.GET.get("periode", "jour")
    try:
        ref = dt.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        ref = timezone.localdate()
    if periode == "semaine":
        debut = ref - dt.timedelta(days=ref.weekday())
        fin = debut + dt.timedelta(days=7)
        prec, suiv = ref - dt.timedelta(days=7), ref + dt.timedelta(days=7)
        libelle = f"Semaine du {debut:%d/%m/%Y} au {(fin - dt.timedelta(days=1)):%d/%m/%Y}"
    elif periode == "mois":
        debut = ref.replace(day=1)
        fin = (debut + dt.timedelta(days=32)).replace(day=1)
        prec, suiv = (debut - dt.timedelta(days=1)).replace(day=1), fin
        mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                "octobre", "novembre", "décembre"]
        libelle = f"{mois[debut.month - 1].capitalize()} {debut.year}"
    elif periode == "annee":
        debut, fin = ref.replace(month=1, day=1), ref.replace(year=ref.year + 1, month=1, day=1)
        prec, suiv = debut.replace(year=debut.year - 1), fin
        libelle = f"Année {debut.year}"
    else:
        periode, debut, fin = "jour", ref, ref + dt.timedelta(days=1)
        prec, suiv = ref - dt.timedelta(days=1), fin
        libelle = f"Journée du {ref:%d/%m/%Y}"
    aw = lambda d: timezone.make_aware(dt.datetime.combine(d, dt.time.min))
    return periode, debut, fin, aw(debut), aw(fin), prec, suiv, libelle


@exige(*ARGENT)
def caisse(request):
    if request.method == "POST":
        form = CaisseRapideForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            if d["sens"] == "entree":
                Paiement.objects.create(montant=d["montant"], libelle=d["libelle"], mode=d["mode"], par=request.user)
            else:
                Depense.objects.create(montant=d["montant"], motif=d["libelle"], mode=d["mode"], avec_facture=False,
                                       par=request.user)
            messages.success(request, "Mouvement de caisse enregistré.")
            return redirect(request.get_full_path())
    else:
        form = CaisseRapideForm()
    periode, debut, fin, d0, d1, prec, suiv, libelle = _periode(request)
    entrees = Paiement.objects.filter(date__gte=d0, date__lt=d1)
    sorties = Depense.objects.filter(date__gte=d0, date__lt=d1)
    total_e = entrees.aggregate(s=Sum("montant"))["s"] or 0
    total_s = sorties.aggregate(s=Sum("montant"))["s"] or 0

    # Graphique : par jour (semaine/mois) ou par mois (année)
    barres = []
    if periode in ("semaine", "mois", "annee"):
        trunc = TruncMonth if periode == "annee" else TruncDay
        tz = timezone.get_current_timezone()
        e = {r["k"].date() if hasattr(r["k"], "date") else r["k"]: r["s"] for r in
             entrees.annotate(k=trunc("date", tzinfo=tz)).values("k").annotate(s=Sum("montant"))}
        s = {r["k"].date() if hasattr(r["k"], "date") else r["k"]: r["s"] for r in
             sorties.annotate(k=trunc("date", tzinfo=tz)).values("k").annotate(s=Sum("montant"))}
        jours = []
        if periode == "annee":
            jours = [debut.replace(month=m) for m in range(1, 13)]
            noms = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
            etiq = lambda d: noms[d.month - 1]
        else:
            d = debut
            while d < fin:
                jours.append(d)
                d += dt.timedelta(days=1)
            js = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
            etiq = (lambda d: f"{js[d.weekday()]} {d.day}") if periode == "semaine" else (lambda d: str(d.day))
        maxi = max([e.get(j, 0) for j in jours] + [s.get(j, 0) for j in jours] + [1])
        for j in jours:
            ve, vs = e.get(j, 0), s.get(j, 0)
            barres.append({"label": etiq(j), "e": ve, "s": vs, "he": int(ve * 100 / maxi), "hs": int(vs * 100 / maxi)})

    par_mode = entrees.values("mode").annotate(s=Sum("montant")).order_by("-s")
    noms_modes = dict(Paiement._meta.get_field("mode").choices)
    par_cat = sorties.values("categorie").annotate(s=Sum("montant")).order_by("-s")
    noms_cat = dict(Depense.CATEGORIES)
    ctx = {
        "form": form, "periode": periode, "libelle": libelle, "prec": prec, "suiv": suiv,
        "entrees": entrees.select_related("ordre")[:200], "sorties": sorties.select_related("ordre")[:200],
        "total_e": total_e, "total_s": total_s, "solde": total_e - total_s, "barres": barres,
        "par_mode": [(noms_modes.get(r["mode"], r["mode"]), r["s"]) for r in par_mode],
        "par_cat": [(noms_cat.get(r["categorie"], r["categorie"]), r["s"]) for r in par_cat],
        "avec_facture": sorties.filter(avec_facture=True).aggregate(s=Sum("montant"))["s"] or 0,
        "sans_facture": sorties.filter(avec_facture=False).aggregate(s=Sum("montant"))["s"] or 0,
        "periodes": [("jour", "Jour"), ("semaine", "Semaine"), ("mois", "Mois"), ("annee", "Année")],
        "date_ref": request.GET.get("date", ""),
    }
    return render(request, "garage/caisse.html", ctx)


# ---------------------------------------------------------------- Dépenses
@exige(*ARGENT)
def depenses(request):
    qs = Depense.objects.select_related("ordre", "ordre__vehicule")
    f = request.GET.get("facture")
    if f == "oui":
        qs = qs.filter(avec_facture=True)
    elif f == "non":
        qs = qs.filter(avec_facture=False)
    cat = request.GET.get("categorie")
    if cat:
        qs = qs.filter(categorie=cat)
    q = request.GET.get("q")
    if q:
        qs = qs.filter(Q(motif__icontains=q) | Q(fournisseur__icontains=q) | Q(numero_document__icontains=q))
    total = qs.aggregate(s=Sum("montant"))["s"] or 0
    return render(request, "garage/depenses.html", {"depenses": qs[:300], "total": total, "facture": f,
                                                    "categorie": cat, "categories": Depense.CATEGORIES, "q": q or ""})


@exige(*ARGENT)
def depense_nouvelle(request):
    initial = {"ordre": request.GET.get("ordre")}
    if request.GET.get("ordre"):
        initial["categorie"] = "pieces"
    form = DepenseForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.save(commit=False)
        d.par = request.user
        d.save()
        if d.avec_facture:
            messages.success(request, "Dépense enregistrée avec la photo de la facture.")
        else:
            messages.success(request, f"Dépense sans facture enregistrée : bon interne {d.numero_bon}.")
        return redirect(d.ordre if d.ordre else "depenses")
    return render(request, "garage/depense_form.html", {"form": form})


@exige(*ARGENT)
def depense_detail(request, pk):
    d = get_object_or_404(Depense, pk=pk)
    return render(request, "garage/depense_detail.html", {"d": d, "p": Parametres.get()})


# ---------------------------------------------------------------- Alertes / rappels
def rappels(request):
    generer_alertes_entretien()
    aujourd_hui = timezone.localdate()
    qs = Rappel.objects.select_related("client", "vehicule")
    client_id = request.GET.get("client")
    if client_id:
        qs = qs.filter(client_id=client_id)
    vue = request.GET.get("vue", "aujourdhui")
    if vue == "avenir":
        qs = qs.filter(statut="a_faire", date_prevue__gt=aujourd_hui)
    elif vue == "faits":
        qs = qs.exclude(statut="a_faire").order_by("-contacte_le", "-date_prevue")[:100]
    elif vue == "inactifs":
        from django.db.models import Max
        mois = Parametres.get().mois_inactif
        limite = timezone.now() - dt.timedelta(days=30 * mois)
        inactifs = Client.objects.annotate(derniere=Max("ordres__date_reception"), nb=Count("vehicules", distinct=True)) \
            .filter(nb__gt=0).filter(Q(derniere__lt=limite) | Q(derniere__isnull=True)).order_by("derniere")
        form = RappelForm(initial={"date_prevue": aujourd_hui})
        return render(request, "garage/rappels.html", {"vue": vue, "inactifs": inactifs, "mois_inactif": mois,
                                                       "form": form, "rappels": []})
    else:
        vue = "aujourdhui"
        qs = qs.filter(statut="a_faire", date_prevue__lte=aujourd_hui)
    form = RappelForm(request.POST or None, initial={"date_prevue": aujourd_hui, "client": client_id})
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Alerte ajoutée.")
        return redirect("rappels")
    return render(request, "garage/rappels.html", {"rappels": qs, "vue": vue, "form": form,
                                                   "canaux": Client.CANAUX, "resultats": ContactClient.RESULTATS,
                                                   "client_filtre": Client.objects.filter(pk=client_id).first() if client_id else None})


@require_POST
def contact_ajout(request, pk):
    """Enregistre un contact (appel, SMS, Facebook…) et son résultat."""
    r = get_object_or_404(Rappel, pk=pk)
    canal, resultat = request.POST.get("canal"), request.POST.get("resultat")
    if canal not in dict(Client.CANAUX) or resultat not in dict(ContactClient.RESULTATS):
        return HttpResponseBadRequest("Choisissez le moyen et le résultat.")
    ContactClient.objects.create(client=r.client, rappel=r, canal=canal, resultat=resultat,
                                 note=request.POST.get("note", "")[:250], par=request.user)
    if resultat in ("joint", "message", "refuse"):
        r.statut, r.contacte_le = ("annule" if resultat == "refuse" else "contacte"), timezone.now()
    else:
        try:
            r.date_prevue = dt.date.fromisoformat(request.POST.get("date", ""))
        except ValueError:
            pass
    r.save()
    messages.success(request, f"Contact enregistré : {dict(ContactClient.RESULTATS)[resultat]}.")
    return redirect(request.POST.get("next") or "rappels")


@require_POST
def rappel_statut(request, pk):
    r = get_object_or_404(Rappel, pk=pk)
    action = request.POST.get("action")
    if action == "contacte":
        r.statut, r.contacte_le = "contacte", timezone.now()
    elif action == "annule":
        r.statut = "annule"
    elif action == "reporter":
        try:
            r.date_prevue = dt.date.fromisoformat(request.POST.get("date", ""))
        except ValueError:
            return HttpResponseBadRequest("Choisissez une date.")
    r.save()
    if _hx(request):
        return HttpResponse("")
    return redirect(request.POST.get("next") or "rappels")


@require_POST
def rappels_groupes(request, client_pk):
    """Crée une alerte pour tous les véhicules d'un client (ex. une société)."""
    c = get_object_or_404(Client, pk=client_pk)
    motif = request.POST.get("motif") or "Entretien de votre véhicule à prévoir"
    date = request.POST.get("date") or timezone.localdate()
    for v in c.vehicules.all():
        Rappel.objects.create(client=c, vehicule=v, motif=motif, date_prevue=date)
    messages.success(request, f"{c.vehicules.count()} alertes créées pour {c.nom}.")
    return redirect(c)


# ---------------------------------------------------------------- Administration
@exige(PATRON)
def journal(request):
    return render(request, "garage/journal.html", {"lignes": Journal.objects.select_related("utilisateur")[:300]})


@exige(PATRON)
def parametres(request):
    from django.forms import modelform_factory
    p = Parametres.get()
    Form = modelform_factory(Parametres, exclude=["mois_entretien"])
    form = Form(request.POST or None, instance=p)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Paramètres enregistrés.")
        return redirect("parametres")
    return render(request, "garage/form.html", {"form": form, "titre": "Paramètres du garage",
                                                "aide": "Ces informations apparaissent sur les factures et devis."})


# ---------------------------------------------------------------- Premier démarrage (chez le client)
def premier_demarrage(request):
    """Le client crée lui-même le compte du patron et saisit les informations du garage."""
    from django.contrib.auth import get_user_model, login
    from django.contrib.auth.forms import UserCreationForm
    from django.contrib.auth.models import Group
    from django.forms import modelform_factory
    from .roles import ROLES
    User = get_user_model()
    if User.objects.filter(is_superuser=True).exists():
        return redirect("connexion")
    p = Parametres.get()
    GarageForm = modelform_factory(Parametres, fields=["nom", "adresse", "telephone", "email", "nif", "stat", "gerant",
                                                       "banque", "rib", "prochain_numero_facture"])
    # Pré-rempli d'après les factures papier du garage : le patron vérifie et corrige.
    deja = {"adresse": "Ambatobe", "telephone": "034 89 167 38", "nif": "4 007 634 558", "stat": "45201 11 2026",
            "gerant": "Mr KOTO Tahirisoa", "banque": "MCB", "prochain_numero_facture": 18}
    gform = GarageForm(request.POST or None, instance=p, prefix="g",
                       initial={k: v for k, v in deja.items() if not getattr(p, k) or (k == "prochain_numero_facture" and p.prochain_numero_facture == 1)})
    gform.fields["prochain_numero_facture"].help_text = "Si vous avez déjà des factures papier (ex. FAC-000017), mettez 18."
    class CompteForm(UserCreationForm):
        def clean_username(self):
            brut = self.data.get(self.add_prefix("username"), "")
            if " " in brut.strip():
                raise ValidationError("Pas d'espace dans le nom d'utilisateur. Exemple : mr.koto ou tahirsoa.")
            return super().clean_username()

        def _post_clean(self):
            super()._post_clean()
            brut = self.data.get(self.add_prefix("username"), "")
            if " " in brut.strip() and "username" in self.errors:
                self.errors["username"] = self.error_class(["Pas d'espace dans le nom d'utilisateur. Exemple : mr.koto ou tahirsoa."])
    uform = CompteForm(request.POST or None, prefix="u")
    uform.fields["username"].label = "Nom d'utilisateur du patron"
    uform.fields["username"].help_text = "Un seul mot, SANS ESPACE. Ex. : patron, tahirsoa, mr.koto (lettres, chiffres, . - _ @ +)."
    if request.method == "POST" and gform.is_valid() and uform.is_valid():
        with transaction.atomic():
            for r in ROLES:
                Group.objects.get_or_create(name=r)
            gform.save()
            u = uform.save(commit=False)
            u.is_staff = u.is_superuser = True
            u.save()
            u.groups.add(Group.objects.get(name="Patron"))
        login(request, u)
        messages.success(request, "Bienvenue ! Votre compte est créé. Créez ensuite les comptes de vos employés dans « Utilisateurs ».")
        return redirect("accueil")
    return render(request, "garage/premier_demarrage.html", {"gform": gform, "uform": uform})
