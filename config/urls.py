from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path
from django.views.static import serve

from garage import views as v

urlpatterns = [
    path("admin/", admin.site.urls),
    path("connexion/", auth_views.LoginView.as_view(template_name="garage/connexion.html"), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("premier-demarrage/", v.premier_demarrage, name="premier_demarrage"),
    path("", v.accueil, name="accueil"),
    path("recherche/", v.recherche, name="recherche"),
    path("modifier/<str:cle>/<int:pk>/<str:champ>/", v.editer, name="editer"),
    path("clients/", v.clients, name="clients"),
    path("clients/nouveau/", v.client_form, name="client_nouveau"),
    path("clients/<int:pk>/", v.client_detail, name="client_detail"),
    path("clients/<int:pk>/modifier/", v.client_form, name="client_modifier"),
    path("clients/<int:client_pk>/alertes/", v.rappels_groupes, name="rappels_groupes"),
    path("vehicules/", v.vehicules, name="vehicules"),
    path("vehicules/nouveau/", v.vehicule_form, name="vehicule_nouveau"),
    path("vehicules/<int:pk>/", v.vehicule_detail, name="vehicule_detail"),
    path("vehicules/<int:pk>/modifier/", v.vehicule_form, name="vehicule_modifier"),
    path("vehicules/<int:pk>/proprietaire/", v.vehicule_proprietaire, name="vehicule_proprietaire"),
    path("atelier/", v.ordres, name="ordres"),
    path("atelier/reception/", v.ordre_nouveau, name="ordre_nouveau"),
    path("atelier/reception/vehicule/", v.reception_vehicule, name="reception_vehicule"),
    path("atelier/<int:pk>/", v.ordre_detail, name="ordre_detail"),
    path("atelier/<int:pk>/parties/", v.ordre_systemes, name="ordre_systemes"),
    path("atelier/<int:pk>/lien/", v.ordre_lien, name="ordre_lien"),
    path("atelier/<int:pk>/note/", v.note_ajout, name="note_ajout"),
    path("atelier/<int:pk>/chrono/", v.pointage, name="pointage"),
    path("vehicules/<int:pk>/entretien/", v.entretien_ajout, name="entretien_ajout"),
    path("atelier/<int:pk>/statut/", v.ordre_statut, name="ordre_statut"),
    path("atelier/<int:pk>/ligne/", v.ligne_ajout, name="ligne_ajout"),
    path("atelier/ligne/<int:pk>/supprimer/", v.ligne_suppr, name="ligne_suppr"),
    path("atelier/<int:pk>/totaux/", v.ordre_totaux, name="ordre_totaux"),
    path("atelier/<int:pk>/paiement/", v.paiement_ajout, name="paiement_ajout"),
    path("atelier/<int:pk>/photo/", v.photo_ajout, name="photo_ajout"),
    path("atelier/<int:pk>/imprimer/", v.facture, name="facture"),
    path("atelier/<int:pk>/facture/", v.facture_etablir, name="facture_etablir"),
    path("caisse/", v.caisse, name="caisse"),
    path("depenses/", v.depenses, name="depenses"),
    path("depenses/nouvelle/", v.depense_nouvelle, name="depense_nouvelle"),
    path("depenses/<int:pk>/", v.depense_detail, name="depense_detail"),
    path("alertes/", v.rappels, name="rappels"),
    path("alertes/<int:pk>/", v.rappel_statut, name="rappel_statut"),
    path("alertes/<int:pk>/contact/", v.contact_ajout, name="contact_ajout"),
    path("historique/", v.journal, name="journal"),
    path("parametres/", v.parametres, name="parametres"),
    # Photos : servies uniquement aux utilisateurs connectés (contrôle par le middleware)
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

admin.site.site_header = "CAR PLUS — Administration"
admin.site.site_title = "CAR PLUS"
