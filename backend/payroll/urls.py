from django.urls import path

from . import views

ORG = "organizations/<uuid:org_id>/"

urlpatterns = [
    path(ORG + "workers/", views.WorkerListCreateView.as_view(), name="org-workers"),
    path(ORG + "workers/import/", views.WorkerImportView.as_view(), name="org-workers-import"),
    path(ORG + "workers/<uuid:worker_id>/", views.WorkerDetailView.as_view(), name="org-worker-detail"),
    path(ORG + "workers/<uuid:worker_id>/<str:action>/", views.WorkerActionView.as_view(), name="org-worker-action"),
    path(ORG + "worker-join-code/", views.JoinCodeView.as_view(), name="org-worker-join-code"),
    path(ORG + "pay-runs/", views.PayRunListCreateView.as_view(), name="org-pay-runs"),
    path(ORG + "pay-runs/<uuid:run_id>/", views.PayRunDetailView.as_view(), name="org-pay-run-detail"),
    path(ORG + "pay-runs/<uuid:run_id>/payslips/", views.PayslipAddView.as_view(), name="org-payslip-add"),
    path(
        ORG + "pay-runs/<uuid:run_id>/payslips/<uuid:payslip_id>/",
        views.PayslipEditView.as_view(),
        name="org-payslip-edit",
    ),
    path(ORG + "pay-runs/<uuid:run_id>/<str:action>/", views.PayRunActionView.as_view(), name="org-pay-run-action"),
    path(ORG + "payslips/<uuid:payslip_id>/reverse/", views.PayslipReverseView.as_view(), name="org-payslip-reverse"),
    path(ORG + "books/cashbook/", views.CashbookView.as_view(), name="org-books-cashbook"),
    path(ORG + "books/summary/", views.BooksSummaryView.as_view(), name="org-books-summary"),
    path(ORG + "books/reconciliation/", views.ReconciliationView.as_view(), name="org-books-reconciliation"),
    path(ORG + "books/categories/", views.CategoryListCreateView.as_view(), name="org-books-categories"),
    path(ORG + "books/entries/<uuid:entry_id>/", views.BookEntryView.as_view(), name="org-books-entry"),
    path(ORG + "books/invoices/", views.InvoiceListCreateView.as_view(), name="org-books-invoices"),
    path(ORG + "books/invoices/<uuid:invoice_id>/", views.InvoiceDetailView.as_view(), name="org-books-invoice"),
    path(
        ORG + "books/invoices/<uuid:invoice_id>/payable-entries/",
        views.InvoicePayableEntriesView.as_view(),
        name="org-books-invoice-entries",
    ),
    path(ORG + "books/invoices/<uuid:invoice_id>/pay/", views.InvoicePayView.as_view(), name="org-books-invoice-pay"),
    path(
        ORG + "books/invoices/<uuid:invoice_id>/cancel/", views.InvoiceCancelView.as_view(), name="org-books-invoice-cancel"
    ),
    path("payslips/", views.MyPayslipListView.as_view(), name="my-payslips"),
    path("worker-invitations/preview/", views.InvitationPreviewView.as_view(), name="worker-invitation-preview"),
    path("worker-invitations/accept/", views.InvitationAcceptView.as_view(), name="worker-invitation-accept"),
    path("employers/", views.MyEmployersView.as_view(), name="my-employers"),
    path("employers/join/", views.JoinRequestView.as_view(), name="employer-join"),
    path("employers/<uuid:worker_id>/leave/", views.LeaveEmployerView.as_view(), name="employer-leave"),
]
