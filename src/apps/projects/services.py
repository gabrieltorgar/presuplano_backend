"""Projects business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.folios.codes import DocumentType
from apps.folios.services import assign_folio
from apps.projects.models import Evidence, Progress, Project
from apps.projects.selectors import projects_of
from apps.quotes.models import Quote, QuoteItem
from apps.quotes.selectors import quotes_of
from apps.quotes.services import QUOTE_TRANSITIONS
from common.state_machine import Transitions, register
from common.validators import IMAGES, validate_upload

logger = logging.getLogger("apps")

# Una foto de 48 megapíxeles cabe; una bomba de descompresión, no.
MAX_IMAGE_PIXELS = 50_000_000

#: Un proyecto está en curso hasta que se finaliza, y de ahí ya no sale: ni
#: avances, ni fotos, ni pagos (SEC-03.1, iteracion-26 #20).
PROJECT_TRANSITIONS = register(
    Project,
    Transitions(
        field="status",
        allowed={
            Project.Status.IN_PROGRESS: frozenset({Project.Status.FINISHED}),
            Project.Status.FINISHED: frozenset(),
        },
        terminal=frozenset({Project.Status.FINISHED}),
    ),
)

#: Por qué no cambia nada de un proyecto finalizado.
FINISHED = "El proyecto está finalizado"

#: Por qué una cotización no se vuelve proyecto dos veces.
ALREADY_A_PROJECT = "Esta cotización ya tiene un proyecto asociado"


@transaction.atomic
def start_project(*, owner, quote: Quote) -> Project:
    """Start a project from a quote: exactly one, whatever the clicks or retries.

    Any quote of the account can become a project: its document exists from the
    moment it does, so there is nothing to generate first. The quote is read
    again with its row locked, so a second request —a double click, a retry or
    a concurrent one that waited on the lock— finds it already in a project;
    a race that skipped the lock still hits the one-to-one ``Project.quote``
    (409). SEC-03.2, iteracion-26 #20.

    Raises:
        ValidationError: quote not owned, or it already has a project.
    """
    locked = (
        quotes_of(owner=owner)
        .select_for_update(of=("self",))
        .filter(pk=quote.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("Cotización no encontrada.")
    QUOTE_TRANSITIONS.check(
        locked.status, Quote.Status.IN_PROJECT, message=ALREADY_A_PROJECT
    )
    if Project.objects.filter(quote=locked).exists():
        raise ValidationError(ALREADY_A_PROJECT)

    project = Project.objects.create(
        owner=owner,
        quote=locked,
        folio=assign_folio(owner=owner, document_type=DocumentType.PROJECT),
    )
    locked.status = Quote.Status.IN_PROJECT
    locked.save(update_fields=["status", "updated_at"])
    quote.status = locked.status  # quien la pasó la ve como quedó
    logger.info("Project started", extra={"project_id": str(project.pk)})
    return project


def lock_project(project: Project) -> Project:
    """El proyecto releído de su cuenta, con su fila bloqueada hasta el final.

    Lo que cambia bajo un proyecto —sus avances, sus fotos, sus pagos, su
    reparto— se cuenta y se revisa con él bloqueado: dos peticiones a la vez
    se forman, y lo que una ve ya incluye lo que hizo la otra. Va dentro de
    una transacción (SEC-03, iteracion-26 #20).
    """
    return (
        projects_of(owner=project.owner_id)
        .select_for_update(of=("self",))
        .get(pk=project.pk)
    )


def lock_open_project(project: Project) -> Project:
    """El proyecto bloqueado y releído, si sigue en curso.

    Raises:
        ValidationError: está finalizado, aunque la petición lo leyera abierto.
    """
    locked = lock_project(project)
    PROJECT_TRANSITIONS.ensure_editable(locked, message=FINISHED)
    return locked


def _pending(quote_item: QuoteItem, *, excluding: Progress | None = None) -> Decimal:
    """Lo que queda por avanzar de la partida, sin contar ``excluding``.

    Al corregir un avance, lo que ese avance ya tenía vuelve a estar
    disponible: si no, no se podría subir de 5 a 7 cuando faltan sólo 2.
    """
    others = quote_item.progresses.all()
    if excluding is not None:
        others = others.exclude(pk=excluding.pk)
    already = sum((p.quantity for p in others), Decimal("0"))
    return quote_item.quantity - already


def _check_quantity(quantity: Decimal | None, *, pending: Decimal) -> None:
    if quantity is None or quantity <= 0:
        raise ValidationError("El avance debe ser mayor a 0")
    if quantity > pending:
        raise ValidationError(f"El avance supera la cantidad pendiente ({pending})")


def _labor_price(*, project: Project, quote_item: QuoteItem, worker) -> Decimal | None:
    """El precio acordado con quien lo hizo, o ``None`` si no lo hizo nadie.

    Raises:
        ValidationError: persona de otra cuenta, o sin precio dicho para eso.
    """
    if worker is None:
        return None
    # Import local: el personal conoce los proyectos, y al revés sólo aquí.
    from apps.staff.services import labor_unit_price_for

    if worker.owner_id != project.owner_id:
        raise ValidationError("Personal no encontrado.")
    price = labor_unit_price_for(quote_item=quote_item, worker=worker)
    if price is None:
        raise ValidationError(
            f"Falta decir cuánto se le paga a {worker.name} por {quote_item.name}"
        )
    return price


@transaction.atomic
def register_progress(
    *,
    project: Project,
    quote_item: QuoteItem,
    date,
    quantity: Decimal | None = None,
    worker=None,
) -> Progress:
    """Record an advance on a quote item, by quantity.

    The advance may say WHO did it. When it does, it carries the labour price
    agreed with that person —copied here, not looked up later— because that is
    what turns work done into money owed.

    Raises:
        ValidationError: item not in the project, non-positive advance, an
            advance that would exceed the pending quantity, a worker from another
            account or one with no agreed price; also if the project is finished.
    """
    project = lock_open_project(project)
    if quote_item.quote_id != project.quote_id:
        raise ValidationError("La partida no pertenece a este proyecto.")
    _check_quantity(quantity, pending=_pending(quote_item))

    return Progress.objects.create(
        project=project,
        quote_item=quote_item,
        quantity=quantity,
        date=date,
        worker=worker,
        labor_unit_price=_labor_price(
            project=project, quote_item=quote_item, worker=worker
        ),
    )


UNCHANGED = object()


@transaction.atomic
def update_progress(
    *,
    progress: Progress,
    quantity: Decimal | None = None,
    date=None,
    worker=UNCHANGED,
) -> Progress:
    """Corrige un avance: cuánto, cuándo o quién lo hizo.

    La partida no cambia —un avance de otra cosa es otro avance—. El precio de
    mano de obra se vuelve a tomar sólo si cambia quien lo hizo: corregir la
    cantidad no reescribe el trato con el que se hizo el trabajo.

    Raises:
        ValidationError: proyecto finalizado, cantidad no positiva o que
            supera lo que queda de la partida, o una persona sin precio dicho.
    """
    project = lock_open_project(progress.project)
    fields = ["updated_at"]

    if quantity is not None:
        _check_quantity(
            quantity, pending=_pending(progress.quote_item, excluding=progress)
        )
        progress.quantity = quantity
        fields.append("quantity")
    if date is not None:
        progress.date = date
        fields.append("date")
    if worker is not UNCHANGED and getattr(worker, "pk", None) != progress.worker_id:
        progress.labor_unit_price = _labor_price(
            project=project, quote_item=progress.quote_item, worker=worker
        )
        progress.worker = worker
        fields += ["worker", "labor_unit_price"]

    progress.save(update_fields=fields)
    logger.info("Progress corrected", extra={"progress_id": str(progress.pk)})
    return progress


def _drop_files(evidences) -> None:
    """Quita las fotos del almacenamiento cuando el borrado ya es definitivo.

    Sólo al confirmar la transacción: si el borrado del registro fallara
    después, la foto seguiría en su lugar en vez de quedar un registro que
    apunta a nada. El registro lo borra quien llama.
    """
    for evidence in evidences:
        storage, name = evidence.image.storage, evidence.image.name
        transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))


@transaction.atomic
def delete_progress(*, progress: Progress) -> None:
    """Borra un avance que no ocurrió, y con él sus fotos.

    Raises:
        ValidationError: el proyecto está finalizado.
    """
    lock_open_project(progress.project)
    _drop_files(progress.evidences.all())
    progress_id = str(progress.pk)
    progress.delete()
    logger.info("Progress deleted", extra={"progress_id": progress_id})


@transaction.atomic
def add_evidence(*, progress: Progress, image) -> Evidence:
    """Attach an image to a progress entry, whenever it arrives.

    Raises:
        ValidationError: the project is finished, the file is not an image or
            it exceeds the size limit.
    """
    lock_open_project(progress.project)
    # Por su contenido, no por el tipo que dice el navegador (iteracion-12).
    ext = validate_upload(
        image,
        allowed=IMAGES,
        # El tope de la API: cabe en el cuerpo de Vercel (antes 5 MB, iteracion-26 #19).
        max_bytes=settings.UPLOAD_MAX_BYTES,
        max_pixels=MAX_IMAGE_PIXELS,
        too_big="La imagen supera el tamaño máximo permitido",
        not_allowed="Solo se permiten archivos de imagen",
    )
    image.name = f"foto.{ext}"
    return Evidence.objects.create(progress=progress, image=image)


@transaction.atomic
def delete_evidence(*, evidence: Evidence) -> None:
    """Quita una foto de un avance, también del almacenamiento.

    Raises:
        ValidationError: el proyecto está finalizado.
    """
    lock_open_project(evidence.progress.project)
    _drop_files([evidence])
    evidence.delete()


def build_project_summary(*, project: Project) -> dict:
    """Build the closing summary document (work, dates, payments, totals)."""
    # Local import avoids a circular import with the payments app.
    from apps.payments.services import pending_balance, total_paid
    from apps.projects.selectors import advanced_value, quoted_value

    progresses = [
        {
            "date": progress.date,
            "item": progress.quote_item.name,
            "quantity": progress.quantity,
            "earned_value": progress.earned_value,
        }
        for progress in project.progresses.all()
    ]
    payments = [
        {"date": payment.date, "amount": payment.amount}
        for payment in project.payments.all()
    ]
    return {
        "status": project.status,
        "client_name": project.quote.client.name,
        "quoted_value": quoted_value(project),
        "advanced_value": advanced_value(project),
        "total_paid": total_paid(project),
        "pending_balance": pending_balance(project),
        "progresses": progresses,
        "payments": payments,
    }


@transaction.atomic
def finalize_project(*, project: Project, confirm: bool = False) -> dict:
    """Finalize a project and produce its summary document.

    If a pending balance remains and the caller has not confirmed, the project is
    left open and a warning is raised (the client must confirm explicitly). The
    project is read again with its row locked: one finished meanwhile is not
    finished twice, and no progress or payment enters it while it closes.

    Raises:
        ValidationError: project already finished, or pending balance without
            explicit confirmation.
    """
    from apps.payments.services import pending_balance

    project = lock_project(project)
    PROJECT_TRANSITIONS.check(
        project.status,
        Project.Status.FINISHED,
        message="El proyecto ya está finalizado",
    )

    pending = pending_balance(project)
    if pending > 0 and not confirm:
        raise ValidationError(
            f"El proyecto tiene un saldo pendiente de cobro de {pending}"
        )

    project.status = Project.Status.FINISHED
    project.save(update_fields=["status", "updated_at"])
    logger.info("Project finalized", extra={"project_id": str(project.pk)})
    return build_project_summary(project=project)
