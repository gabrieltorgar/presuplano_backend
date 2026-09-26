"""Frases de negocio que varias apps dicen igual."""


def quotes_phrase(count: int) -> str:
    """«1 cotización» / «3 cotizaciones», para decir por qué algo no se borra."""
    return f"{count} cotización" if count == 1 else f"{count} cotizaciones"
