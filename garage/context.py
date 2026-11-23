from django.utils import timezone

from .roles import est_patron, role, voit_argent


def roles(request):
    u = request.user
    from .models import Parametres
    try:
        p = Parametres.get()
    except Exception:          # base pas encore créée
        p = None
    if not u.is_authenticated:
        return {"p": p}
    from .models import Rappel
    nb_alertes = Rappel.objects.filter(statut="a_faire", date_prevue__lte=timezone.localdate()).count()
    from django.conf import settings
    return {
        "version": settings.VERSION_CARPLUS,
        "p": p,
        "role": role(u),
        "voit_argent": voit_argent(u),
        "est_patron": est_patron(u),
        "nb_alertes": nb_alertes,
    }
