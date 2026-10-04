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
    path(
        "organizations/<uuid:org_id>/payment-requests/",
        views.PaymentRequestListCreateView.as_view(),
        name="org-payment-requests",
    ),
    path(
        "organizations/<uuid:org_id>/payment-requests/<uuid:request_id>/<str:decision>/",
        views.PaymentRequestDecisionView.as_view(),
        name="org-payment-request-decision",
    ),
    path("organizations/<uuid:org_id>/statements/", views.OrgStatementView.as_view(), name="org-statements"),
    path("organizations/<uuid:org_id>/audit-events/", views.OrgAuditEventListView.as_view(), name="org-audit-events"),
    path("invitations/accept/", views.AcceptInvitationView.as_view(), name="invitation-accept"),
]
