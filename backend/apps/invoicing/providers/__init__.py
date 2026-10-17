"""Adaptador de proveedor tecnológico (spec 005, decisión 1).

El resto del sistema solo usa get_provider() y la interfaz de base.Provider: cambiar de
proveedor es escribir otro adaptador y apuntar INVOICING_PROVIDER a él.
"""
from django.conf import settings
from django.utils.module_loading import import_string

from .base import Provider, ProviderResult, ProviderUnavailable

__all__ = ["Provider", "ProviderResult", "ProviderUnavailable", "get_provider"]


def get_provider() -> Provider:
    return import_string(settings.INVOICING_PROVIDER)()
