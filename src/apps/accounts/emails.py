"""Los correos que manda la cuenta: verificar el alta, cambiar la contraseña y
cambiar el correo."""

from apps.accounts.models import OtpCode, User
from common import mail
from common.branding import house_brand
from common.emails import render_code_email, render_email

#: Qué dice cada código, según para qué sirve.
_COPY = {
    OtpCode.Purpose.SIGNUP: (
        "Tu código de CUOTREKA",
        "Tu código de verificación",
        "Escribe este código para terminar de crear tu cuenta.",
    ),
    OtpCode.Purpose.PASSWORD_RESET: (
        "Código para cambiar tu contraseña",
        "Cambio de contraseña",
        "Escribe este código para poder fijar tu contraseña nueva.",
    ),
    OtpCode.Purpose.EMAIL_CHANGE: (
        "Confirma tu correo nuevo en CUOTREKA",
        "Confirma tu correo nuevo",
        "Escribe este código en tu perfil para que tu cuenta use este correo.",
    ),
}


#: Cuánto dura el código, dicho como lo diría una persona.
def _vigencia(minutes: int) -> str:
    return f"El código vence en {minutes} minutos."


def send_otp_email(
    *, user: User, code: str, purpose: str, minutes: int, to: str | None = None
) -> bool:
    """Le hace llegar su código a quien se está dando de alta o recuperando.

    Va con la marca de CUOTREKA y no con la de la organización: quien lo
    recibe es el arquitecto, no su cliente, y lo que está haciendo es entrar a
    la herramienta.
    """
    subject, title, intro = _COPY[purpose]
    html = render_code_email(
        brand=house_brand(),
        title=title,
        intro=intro,
        code=code,
        note=(
            f"{_vigencia(minutes)} Si no fuiste tú, puedes ignorar este mensaje: "
            "sin el código no se puede hacer nada."
        ),
    )
    # El código de un cambio de correo va al correo nuevo: es el que se prueba.
    return mail.send_email(to=to or user.email or "", subject=subject, html=html)


def send_email_changed_notice(*, old_email: str, new_email: str) -> bool:
    """Avisarle al correo de antes que la cuenta ya no lo usa.

    Si el cambio no lo hizo su dueño, es la única forma de enterarse.
    """
    html = render_email(
        brand=house_brand(),
        title="Tu cuenta cambió de correo",
        intro=(
            f"Tu cuenta de CUOTREKA ahora usa {new_email} para entrar. "
            "Este correo ya no sirve para iniciar sesión."
        ),
        note=(
            "Si no fuiste tú, responde a este mensaje o escríbenos desde el "
            "formulario de contacto de CUOTREKA."
        ),
    )
    return mail.send_email(
        to=old_email, subject="Tu cuenta de CUOTREKA cambió de correo", html=html
    )
