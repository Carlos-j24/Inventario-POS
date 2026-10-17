from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Customer
from .rules import clean_customer

CHECKED = ("id_type", "id_number", "check_digit", "person_type", "name", "tax_responsibilities")


class CustomerSerializer(serializers.ModelSerializer):
    id_type_label = serializers.CharField(source="get_id_type_display", read_only=True)
    is_final_consumer = serializers.BooleanField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id", "id_type", "id_type_label", "id_number", "check_digit", "person_type", "name",
            "email", "phone", "address", "city", "tax_responsibilities", "is_final_consumer",
        ]
        extra_kwargs = {"check_digit": {"required": False}}
        validators = []  # el documento repetido se valida abajo, ya normalizado

    def validate(self, attrs):
        if self.instance is not None and self.instance.is_final_consumer:
            raise serializers.ValidationError("El consumidor final no se puede modificar.")
        data = {f: getattr(self.instance, f) for f in CHECKED} if self.instance else {}
        data.update(attrs)
        if "check_digit" not in attrs:
            data["check_digit"] = ""  # sin dígito enviado, se calcula
        try:
            data = clean_customer(data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.message_dict)
        attrs.update(id_number=data["id_number"], check_digit=data["check_digit"], name=data["name"])
        taken = Customer.objects.filter(id_type=data["id_type"], id_number=data["id_number"])
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError({"id_number": "Ya existe un cliente con ese documento."})
        return attrs
