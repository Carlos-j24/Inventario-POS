from rest_framework import generics

from apps.accounts.drf import require_any

from .models import Customer
from .queries import number_or_phone, only_digits, phone_digits
from .rules import FINAL_CONSUMER_NUMBER
from .serializers import CustomerSerializer

# En la caja: quien cobra o quien toma pedidos busca y registra clientes (spec 005, T1); en el taller,
# recepción (spec 009).
CAN_USE_CUSTOMERS = require_any("cash.operate", "sales.create", "workshop.receive")


class CustomerListCreateView(generics.ListCreateAPIView):
    """Busca clientes activos (?q= por número de documento, teléfono o nombre; máximo 20) o registra uno."""

    serializer_class = CustomerSerializer
    permission_classes = [CAN_USE_CUSTOMERS]
    pagination_class = None

    def get_queryset(self):
        customers = Customer.objects.filter(is_active=True)
        q = self.request.query_params.get("q", "").strip()
        if not q:
            return customers.order_by("name")[:20]
        digits = only_digits(q)
        if digits:  # cédula o NIT que empieza así, o teléfono que lo contiene (spec 009, regla 3)
            customers = customers.annotate(phone_digits=phone_digits())
            return customers.filter(number_or_phone(digits)).order_by("id_number")[:20]
        return customers.filter(name__icontains=q).order_by("name")[:20]


class CustomerDetailView(generics.RetrieveUpdateAPIView):
    """Ver o corregir un cliente. No se borran: se desactivan en el admin (pueden tener documentos)."""

    serializer_class = CustomerSerializer
    permission_classes = [CAN_USE_CUSTOMERS]
    queryset = Customer.objects.all()


class FinalConsumerView(generics.RetrieveAPIView):
    """El consumidor final: el cliente por defecto de la caja."""

    serializer_class = CustomerSerializer
    permission_classes = [CAN_USE_CUSTOMERS]

    def get_object(self):
        return Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)
