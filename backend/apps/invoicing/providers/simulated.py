"""Proveedor simulado para desarrollo y tests: nunca habla con la DIAN.

Valida todo y calcula un CUDE con SHA-384 de los datos del documento, como el real. Con
INVOICING_SIMULATED_MODE = "reject" rechaza y con "down" simula que no hay servicio.
"""
import hashlib

from django.conf import settings

from .base import Provider, ProviderResult, ProviderUnavailable

QR_URL = "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey="


class SimulatedProvider(Provider):
    name = "simulado"

    def send(self, document):
        mode = getattr(settings, "INVOICING_SIMULATED_MODE", "ok")
        if mode == "down":
            raise ProviderUnavailable("Proveedor simulado sin servicio.")
        if mode == "reject":
            return ProviderResult(validated=False, message="Rechazo simulado: revisa los datos del documento.")
        seed = "|".join(str(v) for v in (
            document.kind, document.code, document.issued_at.isoformat(), document.total,
            document.customer.id_number,
        ))
        cude = hashlib.sha384(seed.encode()).hexdigest()
        return ProviderResult(validated=True, cude=cude, qr_data=QR_URL + cude, provider_id=f"SIM-{document.pk}")
