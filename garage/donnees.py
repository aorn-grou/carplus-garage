"""Sauvegarde, restauration, export et import des données (page « Sauvegarde et données »)."""
import csv
import io
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

DOSSIER = Path(settings.BASE_DIR) / "sauvegardes"


def creer_sauvegarde(dossier=None, garder=30):
    """Crée un .zip daté (base + photos) et renvoie son chemin, ou None s'il n'y a pas encore de données."""
    dossier = Path(dossier or DOSSIER)
    dossier.mkdir(parents=True, exist_ok=True)
    base = Path(settings.DATABASES["default"]["NAME"])
    if not base.exists():
        return None
    nom = dossier / f"carplus_{datetime.now():%Y-%m-%d_%Hh%M%S}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "carplus.sqlite3"
        src, dst = sqlite3.connect(base), sqlite3.connect(copie)
        with dst:
            src.backup(dst)                      # copie sûre même pendant l'utilisation
        src.close()
        dst.close()
        with zipfile.ZipFile(nom, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copie, "carplus.sqlite3")
            photos = Path(settings.MEDIA_ROOT)
            if photos.exists():
                for f in photos.rglob("*"):
                    if f.is_file():
                        z.write(f, Path("photos") / f.relative_to(photos))
    for f in sorted(dossier.glob("carplus_*.zip"))[:-garder]:
        f.unlink()
    return nom


def liste_sauvegardes():
    if not DOSSIER.exists():
        return []
    fichiers = sorted(DOSSIER.rglob("carplus_*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"nom": f.name, "dossier": f.parent.name if f.parent != DOSSIER else "", "taille": f.stat().st_size,
             "date": datetime.fromtimestamp(f.stat().st_mtime), "chemin": f} for f in fichiers[:40]]


class SauvegardeInvalide(Exception):
    pass


def restaurer(fichier_zip):
    """Remplace les données par celles d'une sauvegarde. Une copie de sécurité est faite avant.

    La base est recopiée DANS la base ouverte (API backup de SQLite) : fonctionne même logiciel ouvert.
    """
    with zipfile.ZipFile(fichier_zip) as z:
        noms = z.namelist()
        if "carplus.sqlite3" not in noms:
            raise SauvegardeInvalide("Ce fichier n'est pas une sauvegarde CAR PLUS.")
        for n in noms:
            if n.startswith("/") or ".." in Path(n).parts:
                raise SauvegardeInvalide("Sauvegarde invalide.")
        securite = creer_sauvegarde(DOSSIER / "avant_restauration")
        with tempfile.TemporaryDirectory() as tmp:
            z.extract("carplus.sqlite3", tmp)
            src = sqlite3.connect(Path(tmp) / "carplus.sqlite3")
            try:
                ok = src.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not ok or "garage_client" not in tables:
                    raise SauvegardeInvalide("La sauvegarde est abîmée ou ne vient pas de CAR PLUS.")
                connection.close()
                dst = sqlite3.connect(settings.DATABASES["default"]["NAME"])
                with dst:
                    src.backup(dst)
                dst.close()
            finally:
                src.close()
            photos = Path(settings.MEDIA_ROOT)
            nouvelles = [n for n in noms if n.startswith("photos/") and not n.endswith("/")]
            if photos.exists():
                shutil.rmtree(photos)
            for n in nouvelles:
                cible = photos / Path(n).relative_to("photos")
                cible.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as s, open(cible, "wb") as d:
                    shutil.copyfileobj(s, d)
    return securite


# ---------------------------------------------------------------- Export (CSV lisible par Excel)
def _csv(entetes, lignes):
    sortie = io.StringIO()
    sortie.write("﻿")                         # Excel reconnaît les accents
    w = csv.writer(sortie, delimiter=";")
    w.writerow(entetes)
    for l in lignes:
        w.writerow(["" if v is None else v for v in l])
    return sortie.getvalue().encode("utf-8")


def _tableau(entetes, lignes):
    return entetes, lignes


def excel(feuilles, titre="CAR SERVICE PLUS"):
    """feuilles = [(nom, entetes, lignes)] -> contenu .xlsx (en-tête en gras, colonnes ajustées, montants en Ar)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    wb.remove(wb.active)
    for nom, entetes, lignes in feuilles:
        ws = wb.create_sheet(nom[:31])
        ws.append(entetes)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="15181D")
            c.alignment = Alignment(vertical="center")
        for l in lignes:
            ws.append(["" if v is None else v for v in l])
        for i, e in enumerate(entetes, start=1):
            largeur = max([len(str(e))] + [len(str(l[i - 1])) for l in lignes[:500] if i - 1 < len(l)]) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(max(largeur, 10), 60)
            if "(Ar)" in str(e):
                for cell in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    cell[0].number_format = '# ##0 "Ar"'
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exporter_excel(quoi):
    t = TABLES[quoi]()
    return excel([(t[0], t[1], t[2])])


def exporter(quoi):
    """CSV (gardé pour compatibilité)."""
    t = TABLES[quoi]()
    return _csv(t[1], t[2])


def _t_clients():
    from .models import Client
    return ("Clients", ["Code", "Type", "Nom", "Téléphone", "Téléphone 2", "WhatsApp", "Facebook", "E-mail", "Adresse", "NIF",
                        "STAT", "Contact", "Préfère", "Langue", "Accepte les rappels"],
            [(c.code, c.get_type_display(), c.nom, c.telephone, c.telephone2, c.whatsapp, c.facebook, c.email, c.adresse,
              c.nif, c.stat, c.contact, c.get_canal_prefere_display(), c.get_langue_display(),
              "oui" if c.accepte_rappels else "non") for c in Client.objects.all()])


def _t_vehicules():
    from .models import Vehicule
    return ("Véhicules", ["Immatriculation", "Catégorie", "Marque", "Modèle", "Année", "VIN", "Moteur", "Carburant", "Couleur",
                          "Kilométrage", "Propriétaire", "Code propriétaire", "Téléphone"],
            [(v.immatriculation, v.get_categorie_display(), v.marque, v.modele, v.annee, v.vin, v.moteur,
              v.get_carburant_display(), v.couleur, v.kilometrage, v.proprietaire.nom, v.proprietaire.code,
              v.proprietaire.telephone) for v in Vehicule.objects.select_related("proprietaire")])


def _t_reparations():
    from .models import OrdreReparation
    return ("Réparations", ["N°", "Facture", "Reçu le", "Livré le", "Statut", "Immatriculation", "Véhicule", "Client", "Km",
                            "Problème", "Cause", "Travaux", "Total (Ar)", "Payé (Ar)", "Reste (Ar)", "Coût pièces (Ar)", "Marge (Ar)"],
            [(o.numero, o.numero_facture, f"{o.date_reception:%d/%m/%Y}",
              f"{o.date_livraison:%d/%m/%Y}" if o.date_livraison else "", o.get_statut_display(), o.vehicule.immatriculation,
              f"{o.vehicule.marque} {o.vehicule.modele}", o.client.nom, o.kilometrage, o.probleme, o.cause, o.travaux,
              int(o.total), int(o.paye), int(o.reste), int(o.cout_pieces), int(o.marge))
             for o in OrdreReparation.objects.select_related("vehicule", "client").prefetch_related("lignes")])


def _t_caisse():
    from .models import Depense, Paiement
    lignes = [(p.date, "Entrée", p.libelle, p.get_mode_display(), int(p.montant), "", "") for p in Paiement.objects.all()]
    lignes += [(d.date, "Sortie", d.motif, d.get_mode_display(), -int(d.montant), d.get_categorie_display(),
                "facture" if d.avec_facture else f"bon {d.numero_bon}") for d in Depense.objects.all()]
    lignes.sort(key=lambda l: l[0])
    from django.utils import timezone as tz
    lignes = [(f"{tz.localtime(l[0]):%d/%m/%Y %H:%M}",) + l[1:] for l in lignes]
    return ("Caisse", ["Date", "Sens", "Libellé", "Mode", "Montant (Ar)", "Catégorie", "Justificatif"], lignes)


def _t_depenses():
    from .models import Depense
    from django.utils import timezone as tz
    return ("Dépenses", ["Date", "Montant (Ar)", "Catégorie", "Motif", "Fournisseur", "N° facture", "Justificatif", "Mode",
                         "Réparation"],
            [(f"{tz.localtime(d.date):%d/%m/%Y}", int(d.montant), d.get_categorie_display(), d.motif, d.fournisseur,
              d.numero_document, "facture (photo)" if d.avec_facture else f"bon {d.numero_bon}", d.get_mode_display(),
              d.ordre.numero if d.ordre else "") for d in Depense.objects.select_related("ordre")])


TABLES = {"clients": _t_clients, "vehicules": _t_vehicules, "reparations": _t_reparations, "caisse": _t_caisse,
          "depenses": _t_depenses}


def _norm(s):
    return (str(s or "")).strip().lower().replace("é", "e").replace("è", "e").replace("°", "").replace(" ", "")


def _lire_csv(fichier):
    nom = getattr(fichier, "name", "").lower()
    if nom.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(fichier, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        lignes = list(ws.iter_rows(values_only=True))
        if not lignes:
            return []
        entetes = [_norm(e) for e in lignes[0]]
        def texte(v):
            if v is None:
                return ""
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return str(v).strip()
        return [{e: texte(v) for e, v in zip(entetes, l) if e} for l in lignes[1:] if any(v not in (None, "") for v in l)]
    if nom.endswith(".xls"):
        raise ValueError("ancien format Excel (.xls) : enregistrez le fichier en « Classeur Excel (.xlsx) »")
    brut = fichier.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = brut.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialecte = csv.Sniffer().sniff(texte[:4000], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
        dialecte.delimiter = ";"
    lecteur = csv.DictReader(io.StringIO(texte), dialect=dialecte)
    return [{_norm(k): (v or "").strip() for k, v in ligne.items() if k} for ligne in lecteur]


def _val(ligne, *noms):
    for n in noms:
        if ligne.get(n):
            return ligne[n]
    return ""


@transaction.atomic
def importer_clients(fichier):
    from .models import Client
    crees, ignores = 0, []
    for i, l in enumerate(_lire_csv(fichier), start=2):
        nom = _val(l, "nom", "raisonsociale", "client")
        if not nom:
            ignores.append(f"ligne {i} : pas de nom")
            continue
        tel = _val(l, "telephone", "tel", "phone")
        if Client.objects.filter(nom__iexact=nom, telephone=tel).exists():
            ignores.append(f"ligne {i} : {nom} existe déjà")
            continue
        type_ = "societe" if _val(l, "type").lower().startswith("soc") else "particulier"
        Client.objects.create(nom=nom, type=type_, telephone=tel, telephone2=_val(l, "telephone2"),
                              whatsapp=_val(l, "whatsapp") or tel, facebook=_val(l, "facebook"),
                              email=_val(l, "e-mail", "email", "mail"), adresse=_val(l, "adresse"),
                              nif=_val(l, "nif"), stat=_val(l, "stat"), contact=_val(l, "contact"))
        crees += 1
    return crees, ignores


@transaction.atomic
def importer_vehicules(fichier):
    from .models import Client, Vehicule
    crees, ignores = 0, []
    for i, l in enumerate(_lire_csv(fichier), start=2):
        immat = _val(l, "immatriculation", "plaque", "immat").upper().replace(" ", "")
        marque, modele = _val(l, "marque"), _val(l, "modele")
        proprio = _val(l, "proprietaire", "client", "nom")
        if not (immat and marque and modele and proprio):
            ignores.append(f"ligne {i} : il faut immatriculation, marque, modèle et propriétaire")
            continue
        if Vehicule.objects.filter(immatriculation=immat).exists():
            ignores.append(f"ligne {i} : {immat} existe déjà")
            continue
        code = _val(l, "codeproprietaire")
        client = None
        if code.upper().startswith("CLI-") and code[4:].isdigit():
            client = Client.objects.filter(pk=int(code[4:])).first()
        client = client or Client.objects.filter(nom__iexact=proprio).first() or \
            Client.objects.create(nom=proprio, telephone=_val(l, "telephone"))
        annee = _val(l, "annee")
        km = "".join(c for c in _val(l, "kilometrage", "km") if c.isdigit())
        Vehicule.objects.create(proprietaire=client, immatriculation=immat, marque=marque, modele=modele,
                                annee=int(annee) if annee.isdigit() else None, vin=_val(l, "vin"),
                                moteur=_val(l, "moteur"), couleur=_val(l, "couleur"), kilometrage=int(km) if km else 0,
                                categorie="moto" if "moto" in _val(l, "categorie").lower() else "voiture")
        crees += 1
    return crees, ignores


MODELES = {
    "clients": ("modele_clients.csv", ["Type", "Nom", "Téléphone", "WhatsApp", "Facebook", "E-mail", "Adresse", "NIF", "STAT", "Contact"],
                [["Particulier", "Rakoto Jean", "034 12 345 67", "", "", "", "Ambatobe", "", "", ""],
                 ["Société", "Exemple SARL", "020 22 000 00", "", "", "contact@exemple.mg", "Antananarivo", "1234567890", "", "M. Andry"]]),
    "vehicules": ("modele_vehicules.csv", ["Immatriculation", "Catégorie", "Marque", "Modèle", "Année", "VIN", "Kilométrage", "Propriétaire", "Téléphone"],
                  [["1234 TBA", "Voiture", "Toyota", "Hilux", "2018", "", "142000", "Rakoto Jean", "034 12 345 67"],
                   ["5678 TAB", "Moto", "Yamaha", "Crypton", "2021", "", "23000", "Rakoto Jean", ""]]),
}


def modele(quoi):
    nom, entetes, exemples = MODELES[quoi]
    return nom.replace(".csv", ".xlsx"), excel([("À remplir", entetes, exemples)])
