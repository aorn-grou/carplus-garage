"""Compression des photos (factures et dégâts) côté serveur.

Le téléphone/la tablette compresse déjà avant l'envoi (voir static/garage/app.js) ;
ce code sert de seconde sécurité : redimensionne, enlève les métadonnées
(GPS…), réoriente et enregistre en JPEG léger.
"""
import io
import uuid

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageOps


def compresser_photo(fichier):
    img = Image.open(fichier)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    max_px = settings.PHOTO_MAX_PX
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    sortie = io.BytesIO()
    img.save(sortie, format="JPEG", quality=settings.PHOTO_QUALITE, optimize=True, progressive=True)
    taille = sortie.tell()
    sortie.seek(0)
    nom = f"{uuid.uuid4().hex[:12]}.jpg"
    return InMemoryUploadedFile(sortie, "ImageField", nom, "image/jpeg", taille, None)
