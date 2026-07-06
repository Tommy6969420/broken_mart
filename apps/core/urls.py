"""
URL patterns for core app.
"""
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("contact/", views.ContactView.as_view(), name="contact"),
    path("return-policy/", views.ReturnPolicyView.as_view(), name="return_policy"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("faq/", views.FAQView.as_view(), name="faq"),
    path("search/", views.SearchResultsView.as_view(), name="search_results"),
    path("search/suggestions/", views.search_suggestions_htmx, name="search_suggestions"),
]