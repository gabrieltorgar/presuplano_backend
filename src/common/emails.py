"""La plantilla de los correos: una sola, pintada con la marca que toque.

HTML de correo, que no es HTML de web: tablas en vez de rejillas y estilos en
el propio atributo, porque la mitad de los clientes de correo tiran la hoja de
estilos y ninguno entiende flexbox.
"""

from html import escape

from common.branding import OPTIMIZED_BY, Brand

#: El pie que llevan todos: qué es esto y de dónde salió.
SIGNATURE = "Este mensaje se generó desde presuplano."


def _row(label: str, value: str) -> str:
    return (
        "<tr>"
        f'<td style="padding:6px 0;color:#64748B;font-size:14px">{escape(label)}</td>'
        f'<td style="padding:6px 0;color:#0F172A;font-size:14px;text-align:right;'
        f'font-weight:600">{escape(value)}</td>'
        "</tr>"
    )


def render_email(
    *,
    brand: Brand,
    title: str,
    intro: str,
    rows: list[tuple[str, str]] | None = None,
    note: str | None = None,
) -> str:
    """El cuerpo del correo, con el encabezado de la marca y su pie."""
    logo = (
        f'<img src="{escape(brand.logo_url)}" alt="{escape(brand.name)}" '
        f'height="36" style="height:36px;display:block;border:0" />'
        if brand.logo_url
        else ""
    )
    detalle = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:16px 0 0">{"".join(_row(k, v) for k, v in rows)}</table>'
        if rows
        else ""
    )
    aviso = (
        f'<p style="margin:16px 0 0;color:#475569;font-size:14px;line-height:22px">'
        f"{escape(note)}</p>"
        if note
        else ""
    )
    pie = f"{OPTIMIZED_BY} · {SIGNATURE}" if brand.optimized else SIGNATURE

    return (
        '<!doctype html><html lang="es"><body style="margin:0;padding:0;'
        'background:#F1F5F9;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#FFFFFF;border-radius:12px;overflow:hidden">'
        f'<tr><td style="background:{escape(brand.color)};padding:20px 24px">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="padding-right:12px">{logo}</td>'
        f'<td style="color:#FFFFFF;font-size:18px;font-weight:700">'
        f"{escape(brand.name)}</td></tr></table></td></tr>"
        '<tr><td style="padding:24px">'
        f'<h1 style="margin:0 0 8px;color:#0F172A;font-size:20px">{escape(title)}</h1>'
        f'<p style="margin:0;color:#334155;font-size:15px;line-height:24px">'
        f"{escape(intro)}</p>"
        f"{detalle}{aviso}</td></tr>"
        f'<tr><td style="padding:16px 24px;border-top:1px solid #E2E8F0;'
        f'color:#94A3B8;font-size:12px">{escape(pie)}</td></tr>'
        "</table></td></tr></table></body></html>"
    )


def render_code_email(
    *, brand: Brand, title: str, intro: str, code: str, note: str
) -> str:
    """El correo de un código: el número, grande y solo, es lo que se copia."""
    caja = (
        f'<div style="margin:20px 0;padding:16px;border-radius:10px;'
        f"background:#F8FAFC;border:1px solid #E2E8F0;text-align:center;"
        f'font-size:32px;letter-spacing:8px;font-weight:700;color:{escape(brand.color)}">'
        f"{escape(code)}</div>"
    )
    cuerpo = render_email(brand=brand, title=title, intro=intro, note=note)
    # El código va justo después del párrafo de entrada.
    return cuerpo.replace("</p>", "</p>" + caja, 1)
