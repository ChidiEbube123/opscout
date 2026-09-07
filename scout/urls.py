from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("opportunities/", views.opportunity_list_partial, name="opportunity_list_partial"),
    path("opportunities/<slug:slug>/", views.opportunity_detail_partial, name="opportunity_detail"),
    path("opportunities/<slug:slug>/save/", views.toggle_save, name="toggle_save"),
    path("opportunities/<slug:slug>/unsave/", views.unsave, name="unsave"),
    path("tracker/", views.tracker_view, name="tracker"),
    path("preferences/", views.preferences_view, name="preferences"),
]
