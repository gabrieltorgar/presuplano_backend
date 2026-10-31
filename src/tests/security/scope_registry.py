"""Cada ruta de detalle de la API, con su alcance por empresa (SEC-02 · MAN-03).

Iteracion-26 #22 (revisión MAN-03 con la RLS puesta). Toda ruta con un id de
un registro en la ruta está en ``SCOPED_DETAIL_ROUTES`` y
``test_scope_registry.py`` la recorre con un registro de otra empresa: 404 y
nada cambia. Las que llevan otro argumento (un tipo de documento, un token
público, el nombre de una acción) están en ``UNSCOPED_DETAIL_ROUTES`` con el
motivo. Un módulo normal, no un conftest: la prueba base de rutas lo importa.
"""

SCOPED_DETAIL_ROUTES: list[tuple[str, str]] = [
    ("get", "/api/tariffs/{pk}/"),
    ("put", "/api/tariffs/{pk}/"),
    ("patch", "/api/tariffs/{pk}/"),
    ("delete", "/api/tariffs/{pk}/"),
    ("get", "/api/clients/{pk}/"),
    ("put", "/api/clients/{pk}/"),
    ("patch", "/api/clients/{pk}/"),
    ("delete", "/api/clients/{pk}/"),
    ("get", "/api/quotes/{pk}/"),
    ("put", "/api/quotes/{pk}/"),
    ("patch", "/api/quotes/{pk}/"),
    ("delete", "/api/quotes/{pk}/"),
    ("post", "/api/quotes/{pk}/plan-sync/"),
    ("get", "/api/projects/{pk}/"),
    ("get", "/api/projects/{pk}/distribution/"),
    ("post", "/api/projects/{pk}/finalize/"),
    ("post", "/api/projects/{pk}/progress/"),
    ("get", "/api/progresses/{pk}/"),
    ("patch", "/api/progresses/{pk}/"),
    ("delete", "/api/progresses/{pk}/"),
    ("post", "/api/progresses/{pk}/evidence/"),
    ("delete", "/api/evidences/{pk}/"),
    ("get", "/api/payments/{pk}/"),
    ("get", "/api/plans/{pk}/"),
    ("put", "/api/plans/{pk}/"),
    ("patch", "/api/plans/{pk}/"),
    ("delete", "/api/plans/{pk}/"),
    ("get", "/api/workers/{pk}/"),
    ("put", "/api/workers/{pk}/"),
    ("patch", "/api/workers/{pk}/"),
    ("delete", "/api/workers/{pk}/"),
    ("get", "/api/assignments/{pk}/"),
    ("put", "/api/assignments/{pk}/"),
    ("patch", "/api/assignments/{pk}/"),
    ("delete", "/api/assignments/{pk}/"),
    ("get", "/api/worker-payments/{pk}/"),
    ("get", "/api/plan-assets/{pk}/"),
    ("patch", "/api/collaborators/members/{pk}/"),
    ("delete", "/api/collaborators/members/{pk}/"),
    ("post", "/api/collaborators/invitations/{pk}/resend/"),
    ("post", "/api/collaborators/invitations/{pk}/cancel/"),
]

#: Rutas de detalle sin un registro de la empresa en la ruta, por su nombre.
UNSCOPED_DETAIL_ROUTES: dict[str, str] = {
    "setting": "el tipo de documento de la empresa del contexto (account_of)",
    "preview": "el tipo de documento de la empresa del contexto (account_of)",
    "document": "documento legal público (términos, privacidad)",
    "invitation-detail": "enlace público: lo que autoriza es el token",
    "invitation-accept": "enlace público: lo que autoriza es el token",
    "team-bulk": "el nombre de la acción; los ids viajan en el cuerpo, acotados",
}
