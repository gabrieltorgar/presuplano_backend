"""Los correos que manda la cuenta: verificar el alta y cambiar la contraseña."""

from apps.accounts.models import OtpCode, User
from common import mail
from common.branding import presuplano_brand
from common.emails import render_code_email


#: Cuánto dura el código, dicho como lo diría una persona.
def _vigencia(minutes: int) -> str:
    return f"El código vence en {minutes} minutos."


def send_otp_email(*, user: User, code: str, purpose: str, minutes: int) -> bool:
    """Le hace llegar su código a quien se está dando de alta o recuperando.

    Va con la marca de presuplano y no con la de la organización: quien lo
    recibe es el arquitecto, no su cliente, y lo que está haciendo es entrar a
    la herramienta.
    """
    alta = purpose == OtpCode.Purpose.SIGNUP
    html = render_code_email(
        brand=presuplano_brand(),
        title="Tu código de verificación" if alta else "Cambio de contraseña",
        intro=(
            "Escribe este código para terminar de crear tu cuenta."
            if alta
            else "Escribe este código para poder fijar tu contraseña nueva."
        ),
        code=code,
        note=(
            f"{_vigencia(minutes)} Si no fuiste tú, puedes ignorar este mensaje: "
            "sin el código no se puede hacer nada."
        ),
    )
    return mail.send_email(
        to=user.email or "",
        subject=(
            "Tu código de presuplano" if alta else "Código para cambiar tu contraseña"
        ),
        html=html,
    )
