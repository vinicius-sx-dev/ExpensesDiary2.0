import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


def send_code(recipient: str, code: str):
    # No debug fallback: codes must never appear in API responses or logs.
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = "Seu código de acesso ao ExpensesDiary"
    message.set_content(
        f"Seu código é {code}. Ele expira em 5 minutos e só pode ser usado uma vez. Se não solicitou, ignore esta mensagem."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
