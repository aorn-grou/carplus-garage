"""Lance le serveur du garage sur le réseau local et affiche l'adresse pour la tablette."""
import socket

from django.core.management import call_command
from django.core.management.base import BaseCommand


def ip_locale():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))   # aucun envoi réel : sert à trouver l'adresse réseau
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class Command(BaseCommand):
    help = "Démarre CAR PLUS pour l'ordinateur et la tablette du garage."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8000)

    def handle(self, *a, port, **kw):
        from waitress import serve
        from config.wsgi import application
        call_command("sauvegarder")
        ip = ip_locale()
        self.stdout.write(self.style.SUCCESS("\n  CAR PLUS est démarré. NE FERMEZ PAS cette fenêtre.\n"))
        self.stdout.write(f"  Sur cet ordinateur :  http://localhost:{port}")
        self.stdout.write(f"  Sur la tablette     :  http://{ip}:{port}\n")
        serve(application, host="0.0.0.0", port=port, threads=8)
