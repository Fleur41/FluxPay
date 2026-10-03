from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from banking.services import open_wallet, transfer_funds

User = get_user_model()

DEMO_USERS = [
    ("amina@fluxpay.dev", "Amina Wanjiru", "+254700000001"),
    ("brian@fluxpay.dev", "Brian Otieno", "+254700000002"),
]
DEMO_PASSWORD = "FluxPay#2026"


class Command(BaseCommand):
    help = "Creates two demo users with wallets and a few transfers between them."

    @transaction.atomic
    def handle(self, *args, **options):
        users = []
        for email, name, phone in DEMO_USERS:
            user, created = User.objects.get_or_create(email=email, defaults={"full_name": name, "phone_number": phone})
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
                open_wallet(user, currency="KES")
            users.append(user)

        amina, brian = users
        a_acc, b_acc = amina.accounts.first(), brian.accounts.first()
        for i, (sender, src, dst, amount, note) in enumerate(
            [
                (amina, a_acc, b_acc, Decimal("1250.00"), "Lunch split"),
                (brian, b_acc, a_acc, Decimal("300.00"), "Matatu fare"),
                (amina, a_acc, b_acc, Decimal("4200.00"), "Rent contribution"),
            ]
        ):
            transfer_funds(
                user=sender,
                source_id=src.id,
                destination_number=dst.account_number,
                amount=amount,
                note=note,
                idempotency_key=f"seed-demo-{i}",
            )

        self.stdout.write(self.style.SUCCESS("Demo data ready. Log in with:"))
        for email, _, _ in DEMO_USERS:
            account = User.objects.get(email=email).accounts.first()
            self.stdout.write(f"  {email} / {DEMO_PASSWORD}   (account {account.account_number})")
