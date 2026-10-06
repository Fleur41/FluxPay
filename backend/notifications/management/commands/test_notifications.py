"""Sends one test email and/or SMS through the configured providers, and says plainly what happened.

    python manage.py test_notifications --email you@example.com --phone 0712345678
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from notifications.sms import SmsError, get_sms_backend, normalize_phone


class Command(BaseCommand):
    help = "Sends a test email and/or SMS, to check that notifications reach real inboxes and phones."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Where to send a test email.")
        parser.add_argument("--phone", help="Where to send a test SMS, e.g. 0712345678.")

    def handle(self, *args, email=None, phone=None, **options):
        if not email and not phone:
            raise CommandError("Give --email, --phone or both.")
        if email:
            self.email(email)
        if phone:
            self.sms(phone)

    def email(self, address):
        backend = "console" if settings.EMAIL_BACKEND.endswith("console.EmailBackend") else "smtp"
        if backend == "console":
            self.stdout.write(self.style.WARNING(
                "Email: not set up, so this is only printed below. Set EMAIL_HOST, EMAIL_HOST_USER and "
                "EMAIL_HOST_PASSWORD in .env (see .env.example), then restart."
            ))  # fmt: skip
        try:
            send_mail("FluxPay test email", "If you can read this, FluxPay email alerts work.", None, [address])
        except Exception as exc:  # noqa: BLE001 - report any provider failure in plain words
            self.stdout.write(self.style.ERROR(f"Email to {address} failed: {exc}"))
            return
        from notifications.email import deliverable

        if backend != "console" and not deliverable(address):
            self.stdout.write(self.style.WARNING(f"{address} is a test-only address, so it was printed above, not sent."))
        elif backend != "console":
            self.stdout.write(self.style.SUCCESS(
                f"Email sent to {address} via {settings.EMAIL_HOST} as {settings.DEFAULT_FROM_EMAIL}. "
                "Check the inbox (and spam)."
            ))  # fmt: skip

    def sms(self, raw):
        number = normalize_phone(raw)
        if number is None:
            self.stdout.write(self.style.ERROR(f"{raw} isn't a phone number FluxPay can text (e.g. 0712345678)."))
            return
        real = settings.FLUXPAY_SMS_BACKEND.endswith("AfricasTalkingSmsBackend")
        if not real:
            self.stdout.write(self.style.WARNING(
                "SMS: not set up, so this is only printed below. Set AFRICASTALKING_USERNAME and "
                "AFRICASTALKING_API_KEY in .env (see .env.example), remove FLUXPAY_SMS_BACKEND if set, then restart."
            ))  # fmt: skip
        elif settings.AFRICASTALKING_USERNAME == "sandbox":
            self.stdout.write(self.style.WARNING(
                "SMS: using the Africa's Talking sandbox, which never reaches real phones: open the simulator on "
                "africastalking.com with this number to see it."
            ))  # fmt: skip
        try:
            message_id = get_sms_backend().send(number, "FluxPay: test SMS. If you got this, SMS alerts work.")
        except SmsError as exc:
            self.stdout.write(self.style.ERROR(f"SMS to {number} failed: {exc}"))
            return
        if real:
            self.stdout.write(self.style.SUCCESS(f"SMS accepted by Africa's Talking for {number} (id {message_id})."))
