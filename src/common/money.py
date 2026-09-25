"""Cómo viaja el dinero en esta API."""

from decimal import Decimal

CENTS = Decimal("0.01")


def money(value: Decimal | int | float | str) -> str:
    """Un importe tal como viaja en esta API: cadena con dos decimales.

    Decimal rendered as JSON becomes a float, and a float is not money: the
    rest of the API sends amounts as strings and the app reads them so.
    """
    return str(Decimal(value).quantize(CENTS))
