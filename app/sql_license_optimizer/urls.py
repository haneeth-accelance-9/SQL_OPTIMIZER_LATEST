"""
URL configuration for SQL License Optimizer.
"""
from django.urls import path, include

urlpatterns = [
    path("", include("optimizer.urls")),
]
