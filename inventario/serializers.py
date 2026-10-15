from rest_framework import serializers

from catalogo.models import Categoria, Marca, ModeloTelefono, Variante

from .models import Movimiento, Ubicacion
from .permisos import es_admin


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre"]


class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = ["id", "nombre"]


class ModeloTelefonoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModeloTelefono
        fields = ["id", "marca", "nombre"]


class UbicacionSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Ubicacion
        fields = ["id", "codigo", "nombre", "zona", "nivel", "caja"]


class VarianteSerializer(serializers.ModelSerializer):
    """Variante con su stock por ubicación. Espera existencias precargadas (cantidad > 0)."""

    descripcion = serializers.CharField(source="__str__", read_only=True)
    categoria = serializers.CharField(source="producto.categoria.nombre", read_only=True)
    marca = serializers.CharField(source="producto.modelo_telefono.marca.nombre", read_only=True)
    modelo = serializers.CharField(source="producto.modelo_telefono.nombre", read_only=True)
    stock_total = serializers.SerializerMethodField()
    existencias = serializers.SerializerMethodField()

    class Meta:
        model = Variante
        fields = [
            "id", "codigo_barras", "descripcion", "categoria", "marca", "modelo",
            "color", "material", "precio", "costo", "stock_total", "existencias",
        ]

    def _existencias(self, obj):
        return [e for e in obj.existencias.all() if e.cantidad > 0]

    def get_stock_total(self, obj):
        return sum(e.cantidad for e in self._existencias(obj))

    def get_existencias(self, obj):
        return [
            {"ubicacion": UbicacionSerializer(e.ubicacion).data, "cantidad": e.cantidad}
            for e in self._existencias(obj)
        ]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        if not es_admin(getattr(request, "user", None)):
            data.pop("costo", None)
        return data


class MovimientoCrearSerializer(serializers.Serializer):
    variante = serializers.PrimaryKeyRelatedField(queryset=Variante.objects.filter(activo=True))
    ubicacion = serializers.PrimaryKeyRelatedField(queryset=Ubicacion.objects.filter(activo=True))
    tipo = serializers.ChoiceField(choices=Movimiento.Tipo.choices)
    motivo = serializers.ChoiceField(choices=Movimiento.Motivo.choices)
    cantidad = serializers.IntegerField()
    nota = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    uuid_cliente = serializers.UUIDField(required=False, allow_null=True, default=None)


class AltaRapidaSerializer(serializers.Serializer):
    codigo_barras = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.all())
    modelo_telefono = serializers.PrimaryKeyRelatedField(queryset=ModeloTelefono.objects.all())
    nombre_producto = serializers.CharField(max_length=120)
    color = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    material = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    precio = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    costo = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, default=0)
    cantidad = serializers.IntegerField(min_value=0, default=1)
    ubicacion = serializers.PrimaryKeyRelatedField(
        queryset=Ubicacion.objects.filter(activo=True), required=False, allow_null=True, default=None
    )
