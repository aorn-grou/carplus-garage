from django.conf import settings
from django.shortcuts import redirect

LIBRES = ("/connexion/", "/static/", "/premier-demarrage/")


class ConnexionObligatoire:
    """Toutes les pages demandent d'être connecté."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(LIBRES):
            from django.contrib.auth import get_user_model
            if not get_user_model().objects.filter(is_superuser=True).exists():      # tout premier lancement chez le client
                return redirect("/premier-demarrage/")
            return redirect(f"/connexion/?next={request.path}")
        return self.get_response(request)
