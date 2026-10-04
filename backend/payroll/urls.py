from django.urls import path

from . import views

ORG = "organizations/<uuid:org_id>/"

urlpatterns = [
    path(ORG + "workers/", views.WorkerListCreateView.as_view(), name="org-workers"),
    path(ORG + "workers/import/", views.WorkerImportView.as_view(), name="org-workers-import"),
    path(ORG + "workers/<uuid:worker_id>/", views.WorkerDetailView.as_view(), name="org-worker-detail"),
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
    path(ORG + "books/categories/", views.CategoryListCreateView.as_view(), name="org-books-categories"),
    path(ORG + "books/entries/<uuid:entry_id>/", views.BookEntryView.as_view(), name="org-books-entry"),
    path("payslips/", views.MyPayslipListView.as_view(), name="my-payslips"),
]
