"""FluxPay's own books: a double-entry general ledger, the bank cashbook and bank reconciliations.

How the books relate to the wallets
-----------------------------------
Customer wallet balances are money FluxPay owes its customers: a liability, kept in the control account
"Customer wallet balances". The bank accounts (the cashbook) hold the cash that backs it. Money only
enters a wallet from a recorded bank receipt (allocated by staff), from a payment provider, or as a
staff-approved promotion, and each of those posts a balanced journal here. Transfers between wallets
move money inside the control account, so they post nothing.

Rules every entry follows: debits equal credits, entries are never edited or deleted (a mistake is
fixed with a reversing entry), and nothing may be dated inside a closed period.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

MONEY = {"max_digits": 16, "decimal_places": 2}
ZERO = Decimal("0.00")


class LedgerAccount(models.Model):
    """One line of the chart of accounts, in one currency (each currency keeps its own set of books)."""

    class Type(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"
        EQUITY = "EQUITY", "Equity"
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"

    # Empty for FluxPay's own books; set for a business's books (each business keeps its own set).
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_accounts",
        editable=False,
    )
    code = models.CharField(max_length=10, help_text="Accounts are listed in code order, e.g. 5910 for rent.")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    currency = models.CharField(max_length=3)
    # Set on the accounts FluxPay's own logic posts to ("customer_funds", "bank:<id>", ...).
    role = models.CharField(max_length=60, blank=True, editable=False)
    # Control accounts are only posted through their sub-ledger (wallets, cashbook), never by hand.
    is_control = models.BooleanField(default=False, editable=False)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("currency", "code")
        verbose_name = "ledger account"
        verbose_name_plural = "chart of accounts"
        constraints = [
            models.UniqueConstraint(
                fields=("code", "currency"), condition=Q(organization__isnull=True), name="ledger_account_unique_code"
            ),
            models.UniqueConstraint(
                fields=("role", "currency"),
                condition=~Q(role="") & Q(organization__isnull=True),
                name="ledger_account_unique_role",
            ),
            models.UniqueConstraint(
                fields=("organization", "code", "currency"),
                condition=Q(organization__isnull=False),
                name="business_ledger_account_unique_code",
            ),
            models.UniqueConstraint(
                fields=("organization", "role", "currency"),
                condition=~Q(role="") & Q(organization__isnull=False),
                name="business_ledger_account_unique_role",
            ),
        ]
        permissions = [
            ("view_financial_reports", "Can view financial reports"),
            ("post_journal", "Can post manual journals"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name} ({self.currency})"

    @property
    def debit_normal(self) -> bool:
        """Assets and expenses grow with debits; liabilities, equity and income with credits."""
        return self.type in (self.Type.ASSET, self.Type.EXPENSE)


class JournalEntry(models.Model):
    class Source(models.TextChoices):
        CASHBOOK = "CASHBOOK", "Cashbook"
        ALLOCATION = "ALLOCATION", "Wallet top-up / correction"
        WALLET = "WALLET", "Wallet activity"
        MANUAL = "MANUAL", "Manual journal"
        OPENING = "OPENING", "Opening balances"
        REVERSAL = "REVERSAL", "Reversal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Empty for FluxPay's own books; set for a business's books. Numbers run per set of books.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_entries",
        editable=False,
    )
    number = models.CharField(max_length=12, editable=False)
    date = models.DateField(help_text="The accounting date: the day the money moved.")
    currency = models.CharField(max_length=3, editable=False)
    memo = models.CharField(max_length=255)
    source = models.CharField(max_length=10, choices=Source.choices, editable=False)
    # The wallet reference (FP...), cashbook number (RCT-...) or provider reference this entry books.
    reference = models.CharField(max_length=40, blank=True, db_index=True, editable=False)
    reverses = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by", editable=False
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-date", "-created_at")
        verbose_name = "journal entry"
        verbose_name_plural = "journals"
        constraints = [
            models.UniqueConstraint(
                fields=("number",), condition=Q(organization__isnull=True), name="journal_unique_number"
            ),
            models.UniqueConstraint(
                fields=("organization", "number"),
                condition=Q(organization__isnull=False),
                name="business_journal_unique_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} {self.memo}"


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(**MONEY, default=ZERO, validators=[MinValueValidator(ZERO)])
    credit = models.DecimalField(**MONEY, default=ZERO, validators=[MinValueValidator(ZERO)])
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0) & Q(credit=0)) | (Q(credit__gt=0) & Q(debit=0)),
                name="journal_line_one_side",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account.code} Dr {self.debit} Cr {self.credit}"


class BankAccount(models.Model):
    """A real bank account FluxPay holds. Its cashbook is the list of CashbookEntry rows against it."""

    class Purpose(models.TextChoices):
        SAFEGUARDING = "SAFEGUARDING", "Customer funds (safeguarding)"
        OPERATING = "OPERATING", "FluxPay's own money (operating)"

    name = models.CharField(
        max_length=80, help_text='How staff will recognise it, e.g. "Equity Bank – customer funds".'
    )
    bank_name = models.CharField(max_length=80)
    account_number = models.CharField(max_length=40)
    branch = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3)
    purpose = models.CharField(
        max_length=12,
        choices=Purpose.choices,
        help_text="Customer deposits may only be banked in a safeguarding account, kept apart from FluxPay's own money.",
    )
    ledger_account = models.OneToOneField(
        LedgerAccount, on_delete=models.PROTECT, related_name="bank_account", editable=False
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("bank_name", "account_number"), name="bank_account_unique_number")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency})"


class CashbookEntry(models.Model):
    """One line of the cashbook: money that actually came into, or left, a FluxPay bank account."""

    class Direction(models.TextChoices):
        RECEIPT = "RECEIPT", "Money in"
        PAYMENT = "PAYMENT", "Money out"

    class Category(models.TextChoices):
        CUSTOMER_DEPOSIT = "CUSTOMER_DEPOSIT", "Customer deposit"
        CAPITAL = "CAPITAL", "Owner's capital"
        INTEREST = "INTEREST", "Interest from the bank"
        OTHER_INCOME = "OTHER_INCOME", "Other income"
        CUSTOMER_PAYOUT = "CUSTOMER_PAYOUT", "Customer withdrawal"
        BANK_PAYOUT = "BANK_PAYOUT", "Bank payout requested in the app"
        BANK_CHARGES = "BANK_CHARGES", "Bank charges"
        EXPENSE = "EXPENSE", "Business expense"
        DRAWINGS = "DRAWINGS", "Owner's drawings"
        BANK_TRANSFER = "BANK_TRANSFER", "Transfer between FluxPay bank accounts"
        REVERSAL = "REVERSAL", "Reversal of an earlier entry"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=12, unique=True, editable=False)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="entries")
    direction = models.CharField(max_length=7, choices=Direction.choices)
    category = models.CharField(max_length=16, choices=Category.choices)
    date = models.DateField(help_text="The date the money moved in the bank (as on the bank statement).")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    counterparty = models.CharField(max_length=120, help_text="Who paid in, or who was paid.")
    bank_reference = models.CharField(
        max_length=60, blank=True, help_text="Deposit slip, cheque or bank transaction number, to match the statement."
    )
    description = models.CharField(max_length=255)
    # Income or expense account for OTHER_INCOME and EXPENSE (defaults to 4900 / 5900).
    ledger_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="cashbook_entries"
    )
    # Customer deposits: how much has been credited to wallets so far (never more than `amount`).
    allocated = models.DecimalField(**MONEY, default=ZERO, editable=False)
    # A bank transfer's two entries (and their reversals) share one journal.
    journal = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, null=True, related_name="cashbook_entries", editable=False
    )
    # Bank transfers produce a pair of entries; a reversal points at the entry it cancels.
    counterpart = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )
    reverses = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by", editable=False
    )
    cleared_on = models.DateField(
        null=True, blank=True, editable=False, help_text="The bank statement date this entry was matched to."
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-date", "-created_at")
        verbose_name = "cashbook entry"
        verbose_name_plural = "cashbook entries"
        permissions = [("record_cashbook", "Can record bank receipts and payments")]
        constraints = [
            models.CheckConstraint(
                condition=Q(allocated__gte=0) & Q(allocated__lte=models.F("amount")),
                name="cashbook_allocation_within_amount",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} · {self.counterparty} · {self.bank_account.currency} {self.amount:,.2f}"

    @property
    def unallocated(self) -> Decimal:
        return self.amount - self.allocated

    @property
    def is_reversed(self) -> bool:
        return hasattr(self, "reversed_by")

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction == self.Direction.RECEIPT else -self.amount


class BankReconciliation(models.Model):
    """A signed-off match of the cashbook to a bank statement, kept for the auditors."""

    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="reconciliations")
    statement_date = models.DateField()
    statement_balance = models.DecimalField(**MONEY)
    cashbook_balance = models.DecimalField(**MONEY)
    uncleared_receipts = models.DecimalField(**MONEY)
    uncleared_payments = models.DecimalField(**MONEY)
    entries_cleared = models.PositiveIntegerField()
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-statement_date", "-created_at")
        permissions = [("reconcile_bank", "Can reconcile bank accounts")]

    def __str__(self) -> str:
        return f"{self.bank_account} at {self.statement_date}"


class AccountingSettings(models.Model):
    """The single row (id=1) of bookkeeping controls. Created by migration."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    books_closed_until = models.DateField(
        null=True,
        blank=True,
        help_text="Nothing can be posted on or before this date. Set it once a month's accounts are final.",
    )
    require_second_person = models.BooleanField(
        default=False,
        help_text="Segregation of duties: the person who credits a customer's wallet must not be the person who "
        "recorded the bank receipt.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )

    class Meta:
        verbose_name = verbose_name_plural = "accounting settings"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="accounting_settings_single_row")]

    def __str__(self) -> str:
        return "Accounting settings"


class Sequence(models.Model):
    """Gap-free document numbers (JE-000001, RCT-000001, PAY-000001), locked while a number is taken."""

    name = models.CharField(max_length=10, primary_key=True)
    last = models.PositiveIntegerField(default=0)


class BusinessEntry(models.Model):
    """One line of a business's cashbook: money into or out of one of its FluxPay wallets, with what it was for.

    Written automatically whenever a business wallet's balance changes, with a journal in the business's own
    books. The business can change the category later (reclassify); the money and the cashbook don't change.
    """

    class Direction(models.TextChoices):
        IN = "IN", "Money in"
        OUT = "OUT", "Money out"

    class Source(models.TextChoices):
        OPENING = "OPENING", "Opening balance"
        TRANSFER = "TRANSFER", "Transfer"
        PAYROLL = "PAYROLL", "Payroll"
        PAYROLL_REVERSAL = "PAYROLL_REVERSAL", "Payroll reversal"
        REVERSAL = "REVERSAL", "Payment reversal"
        PROVIDER_DEPOSIT = "PROVIDER_DEPOSIT", "Deposit by M-Pesa"
        PAYOUT = "PAYOUT", "Paid out by M-Pesa or bank"
        PAYOUT_RETURNED = "PAYOUT_RETURNED", "Payout returned"
        DEPOSIT = "DEPOSIT", "Deposit at FluxPay"
        CORRECTION = "CORRECTION", "Correction by FluxPay"
        WITHDRAWAL = "WITHDRAWAL", "Cash withdrawal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="book_entries")
    wallet = models.ForeignKey("banking.Account", on_delete=models.PROTECT, related_name="book_entries")
    date = models.DateField()
    direction = models.CharField(max_length=3, choices=Direction.choices)
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    counterparty = models.CharField(max_length=150, blank=True)
    counterparty_account = models.CharField(max_length=10, blank=True)
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=40, blank=True, db_index=True)
    source = models.CharField(max_length=16, choices=Source.choices)
    category = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="book_entries")
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="book_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-date", "-created_at")
        verbose_name = "business cashbook entry"
        verbose_name_plural = "business cashbooks"
        indexes = [models.Index(fields=("organization", "wallet", "date"))]

    def __str__(self) -> str:
        return f"{self.organization} {self.get_direction_display()} {self.amount} ({self.category.name})"

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction == self.Direction.IN else -self.amount


class Invoice(models.Model):
    """Money a business owes (a bill from a supplier: payable) or is owed (an invoice to a customer: receivable).

    Recording it books the expense or income at once, against Accounts payable or receivable. No money moves:
    it is paid when a cashbook entry (a real payment out, or money received) is linked to it, which moves that
    entry from its category to payables/receivables. See accounting.invoices.
    """

    class Kind(models.TextChoices):
        BILL = "BILL", "Bill to pay"
        INVOICE = "INVOICE", "Invoice to collect"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Not paid"
        PART_PAID = "PART_PAID", "Part paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="invoices")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    number = models.CharField(max_length=20)  # BILL-0001 / INV-0001, per business
    party = models.CharField(max_length=150, help_text="The supplier (bill) or customer (invoice).")
    description = models.CharField(max_length=255, blank=True)
    category = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="invoices")
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    paid_amount = models.DecimalField(**MONEY, default=ZERO)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-issue_date", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("organization", "number"), name="invoice_number_unique_per_business"),
            models.CheckConstraint(condition=Q(paid_amount__lte=models.F("amount")), name="invoice_not_overpaid"),
        ]

    def __str__(self) -> str:
        return f"{self.number} {self.party} {self.amount}"

    @property
    def outstanding(self) -> Decimal:
        return ZERO if self.status == self.Status.CANCELLED else self.amount - self.paid_amount


class InvoicePayment(models.Model):
    """A cashbook entry that pays (part of) a bill, or collects (part of) an invoice. One entry, one invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    entry = models.OneToOneField(BusinessEntry, on_delete=models.PROTECT, related_name="invoice_payment")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    # The entry's category before it was moved to payables/receivables.
    previous_category = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="+")
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
