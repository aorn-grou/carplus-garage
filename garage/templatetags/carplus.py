from decimal import Decimal

from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


@register.filter
def ar(valeur):
    """Montant en ariary : 1250000 -> « 1 250 000 Ar »."""
    try:
        n = int(Decimal(valeur or 0))
    except Exception:
        return valeur
    return f"{n:,}".replace(",", " ") + " Ar"


@register.filter
def nombre(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float, Decimal)):
        return valeur
    try:
        d = Decimal(valeur or 0)
    except Exception:
        return valeur
    if d == d.to_integral():
        return f"{int(d):,}".replace(",", " ")
    return str(d.normalize()).replace(".", ",")


@register.inclusion_tag("garage/_edit_display.html")
def editable(obj, cle, champ):
    """Champ modifiable directement sur la page (clic -> saisie -> enregistré)."""
    return {"obj": obj, "cle": cle, "champ": champ}


@register.filter
def valeur_champ(obj, champ):
    v = getattr(obj, champ)
    disp = getattr(obj, f"get_{champ}_display", None)
    return disp() if disp else v


@register.filter
def est_montant(champ):
    return champ in ("prix_unitaire", "montant", "remise")


@register.simple_tag
def icone(nom, classe=""):
    """Icône du jeu Lucide (embarqué) : {% icone "car" %}."""
    return format_html('<svg class="ic {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', classe, nom)
