"""
URL configuration for makwanpur_mart project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("apps.core.urls")),
    # Google OAuth — django-allauth — must come BEFORE apps.accounts.urls
    # to allow /accounts/google/login/ etc., while keeping local login at /accounts/login/
    path("accounts/social/", include("allauth.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("core/", RedirectView.as_view(url="/", permanent=False)),
    path("catalog/", include("apps.catalog.urls")),
    path("orders/", include("apps.orders.urls")),
    path("support/", include("apps.support.urls")),
    path("delivery/", include("apps.delivery.urls")),
]
