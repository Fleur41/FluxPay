"""Report pages, mounted under /admin/accounting/reports/ and wrapped in the admin's login and staff checks."""

from django.contrib import admin
from django.urls import path

from . import views


def staff(view):
    return admin.site.admin_view(view)


urlpatterns = [
    path("", staff(views.index), name="accounting_reports"),
    path("trial-balance/", staff(views.trial_balance), name="accounting_trial_balance"),
    path("balance-sheet/", staff(views.balance_sheet), name="accounting_balance_sheet"),
    path("income-statement/", staff(views.income_statement), name="accounting_income_statement"),
    path("ledger/", staff(views.ledger), name="accounting_ledger"),
    path("cashbook/", staff(views.cashbook), name="accounting_cashbook"),
    path("safeguarding/", staff(views.safeguarding), name="accounting_safeguarding"),
    path("reconcile/", staff(views.reconcile), name="accounting_reconcile"),
    path("business/", staff(views.business_books), name="accounting_business"),
]
