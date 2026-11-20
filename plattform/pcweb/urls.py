from django.urls import path, re_path

from planung import views, views_dokumente

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("artikel/<str:nummer>/", views.artikel_detail, name="artikel"),
    path("import/", views.importe, name="import"),
    path("dokumente/", views_dokumente.liste, name="dokumente"),
    path("dokumente/<int:pk>/", views_dokumente.detail, name="dokument"),
    path("ereignisse/", views_dokumente.warteschlange, name="warteschlange"),
    path("ereignisse/messung/", views_dokumente.messung, name="messung"),
    path("artikel/<str:nummer>/akte/", views_dokumente.akte, name="akte"),
    path("matrix/", views.matrix, name="matrix"),
    path("parameter/", views.parameter, name="parameter"),
    path("accuracy/", views.accuracy, name="accuracy"),
    path("hinweise/", views.hinweise, name="hinweise"),
    path("laeufe/", views.laeufe, name="laeufe"),
    path("werke/", views.werke, name="werke"),
    path("werke/<str:standort>.<str:fmt>", views.werke_export, name="werke_export"),
    path("protokoll/", views.protokoll, name="protokoll"),
    path("api/v1/import/<str:art>", views.api_import, name="api_import"),
    path("healthz", views.healthz),
    path("favicon.ico", views.favicon),
    re_path(r"^bericht/(?P<pfad>.*)$", views.bericht, name="bericht"),
]
