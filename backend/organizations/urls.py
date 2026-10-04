from django.urls import path

from . import views

urlpatterns = [
    path("organizations/", views.OrganizationListCreateView.as_view(), name="org-list"),
    path("organizations/<uuid:org_id>/", views.OrganizationDetailView.as_view(), name="org-detail"),
    path("organizations/<uuid:org_id>/members/", views.MemberListView.as_view(), name="org-members"),
    path(
        "organizations/<uuid:org_id>/members/<uuid:member_id>/",
        views.MemberDetailView.as_view(),
        name="org-member-detail",
    ),
    path("organizations/<uuid:org_id>/invitations/", views.InvitationListCreateView.as_view(), name="org-invitations"),
    path(
        "organizations/<uuid:org_id>/invitations/<uuid:invitation_id>/",
        views.InvitationRevokeView.as_view(),
        name="org-invitation-revoke",
    ),
    path("organizations/<uuid:org_id>/accounts/", views.OrgAccountListView.as_view(), name="org-accounts"),
    path("organizations/<uuid:org_id>/transactions/", views.OrgTransactionListView.as_view(), name="org-transactions"),
    path("organizations/<uuid:org_id>/payments/", views.PaymentListCreateView.as_view(), name="org-payments"),
    path(
        "organizations/<uuid:org_id>/payments/<uuid:payment_id>/<str:action>/",
        views.PaymentActionView.as_view(),
        name="org-payment-action",
    ),
    path(
        "organizations/<uuid:org_id>/beneficiaries/",
        views.BeneficiaryListCreateView.as_view(),
        name="org-beneficiaries",
    ),
    path(
        "organizations/<uuid:org_id>/beneficiaries/<uuid:beneficiary_id>/",
        views.BeneficiaryDetailView.as_view(),
        name="org-beneficiary-detail",
    ),
    path(
        "organizations/<uuid:org_id>/beneficiaries/<uuid:beneficiary_id>/verify/",
        views.BeneficiaryVerifyView.as_view(),
        name="org-beneficiary-verify",
    ),
    path("organizations/<uuid:org_id>/statements/", views.OrgStatementView.as_view(), name="org-statements"),
    path("organizations/<uuid:org_id>/audit-events/", views.OrgAuditEventListView.as_view(), name="org-audit-events"),
    path("invitations/accept/", views.AcceptInvitationView.as_view(), name="invitation-accept"),
]
