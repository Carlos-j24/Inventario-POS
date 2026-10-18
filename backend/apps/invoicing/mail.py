"""Correo opcional al cliente cuando la DIAN valida su documento (spec 005, decisión 4)."""
import logging

from django.core.mail import send_mail

from .ticket import business_data

logger = logging.getLogger(__name__)


def email_customer(document):
    """Envía el resumen y el enlace de consulta de la DIAN si el cliente dio su correo. Devuelve si se envió."""
    customer = document.customer
    if not customer.email or customer.is_final_consumer:
        return False
    business = business_data()
    body = "\n".join([
        f"Hola, {customer.name}:",
        "",
        f"{business['name']} te envía tu {document.get_kind_display().lower()} {document.code}. La DIAN ya lo validó.",
        f"Total: ${document.total}",
        f"CUDE: {document.cude}",
        f"Consúltalo en la DIAN: {document.qr_data}",
    ])
    try:
        send_mail(f"{document.get_kind_display()} {document.code} — {business['name']}", body, None, [customer.email])
    except Exception as err:  # noqa: BLE001 — un correo caído no debe deshacer la validación
        logger.warning("No se pudo enviar el documento %s a %s: %s", document.code, customer.email, err)
        return False
    return True
