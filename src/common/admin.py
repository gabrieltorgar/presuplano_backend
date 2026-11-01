"""Lo que el admin nunca edita de un registro (SEC-03, iteracion-26 #20).

``ProtectedFieldsAdminMixin`` va antes de ``ModelAdmin`` en las bases. Sus
``protected_fields`` —estados, importes que calcula o copia un servicio,
folios— se ven y no se editan, ni al crear: cambian sólo por su servicio. Sus
``set_on_create_fields`` —de qué cuenta, proyecto o persona es el registro— se
eligen al crearlo desde el admin y después ya no cambian: mover un registro
de cuenta lo saca de la empresa que lo hizo.
"""


class ProtectedFieldsAdminMixin:
    protected_fields: tuple[str, ...] = ()
    set_on_create_fields: tuple[str, ...] = ()

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:
        fields = [*super().get_readonly_fields(request, obj), *self.protected_fields]
        if obj is not None:
            fields += self.set_on_create_fields
        return tuple(dict.fromkeys(fields))
