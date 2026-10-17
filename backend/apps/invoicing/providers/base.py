from dataclasses import dataclass


class ProviderUnavailable(Exception):
    """El proveedor o la DIAN no respondieron: se reintenta después (no es un rechazo)."""


@dataclass
class ProviderResult:
    """Respuesta del proveedor a un documento."""

    validated: bool
    cude: str = ""
    qr_data: str = ""
    provider_id: str = ""
    message: str = ""


class Provider:
    """Interfaz que implementa cada proveedor tecnológico."""

    name = "base"

    def send(self, document) -> ProviderResult:
        """Envía el documento (con sus líneas, cliente y documento que corrige) para validación.

        Devuelve el resultado (validado o rechazado con su motivo) o lanza ProviderUnavailable si
        no se pudo saber (red caída, proveedor o DIAN sin servicio).
        """
        raise NotImplementedError
