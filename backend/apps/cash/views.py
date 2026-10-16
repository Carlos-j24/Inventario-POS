from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from .models import Shift
from .serializers import CloseShiftSerializer, OpenShiftSerializer, ShiftSerializer
from .services import close_shift, open_shift


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


class ShiftOpenView(APIView):
    permission_classes = [require("cash.operate")]

    def post(self, request):
        data = OpenShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shift = _call(open_shift, user=request.user, **data.validated_data)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftDetailView(generics.RetrieveAPIView):
    """Turno con sus totales por medio de pago y el efectivo esperado."""

    permission_classes = [require("cash.operate")]
    serializer_class = ShiftSerializer
    queryset = Shift.objects.select_related("register", "opened_by", "closed_by")


class ShiftCloseView(APIView):
    permission_classes = [require("cash.operate")]

    def post(self, request, pk):
        data = CloseShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shift = _call(
            close_shift, shift=get_object_or_404(Shift, pk=pk), user=request.user, **data.validated_data
        )
        return Response(ShiftSerializer(shift).data)
