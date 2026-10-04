"""Business-account API. Every view resolves the caller's membership first (services.membership_for)."""
from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit.models import AuditEvent
from banking.filters import TransactionFilter
from banking.models import Account, Transaction
from banking.serializers import AccountSerializer, TransactionSerializer
from banking.views import statement_response

from . import services
from .models import Invitation, Membership, Payment
from .roles import Perm
from .serializers import (
    AcceptInvitationSerializer,
    AuditEventSerializer,
    DecisionSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MemberSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    ReverseSerializer,
    RoleSerializer,
)


class OrgScopedMixin:
    """Resolves `self.membership` for `perm` from the URL's org_id before the view runs."""

    perm = Perm.VIEW

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.membership = services.membership_for(request.user, kwargs["org_id"], self.perm_for(request))

    def perm_for(self, request) -> Perm:
        return self.perm


class OrganizationListCreateView(APIView):
    def get(self, request):
        memberships = Membership.objects.select_related("organization").filter(user=request.user, is_active=True)
        roles = {m.organization_id: m.role for m in memberships}
        organizations = [m.organization for m in memberships]
        return Response(OrganizationSerializer(organizations, many=True, context={"roles": roles}).data)

    def post(self, request):
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.create_organization(user=request.user, **serializer.validated_data)
        context = {"roles": {organization.id: Membership.Role.OWNER}}
        return Response(OrganizationSerializer(organization, context=context).data, status=status.HTTP_201_CREATED)


class OrganizationDetailView(OrgScopedMixin, APIView):
    def perm_for(self, request):
        return Perm.MANAGE_SETTINGS if request.method == "PATCH" else Perm.VIEW

    def get(self, request, org_id):
        context = {"roles": {self.membership.organization_id: self.membership.role}}
        return Response(OrganizationSerializer(self.membership.organization, context=context).data)

    def patch(self, request, org_id):
        serializer = OrganizationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        organization = services.update_settings(membership=self.membership, **serializer.validated_data)
        context = {"roles": {organization.id: self.membership.role}}
        return Response(OrganizationSerializer(organization, context=context).data)


class MemberListView(OrgScopedMixin, generics.ListAPIView):
    serializer_class = MemberSerializer
    pagination_class = None

    def get_queryset(self):
        return Membership.objects.select_related("user").filter(
            organization_id=self.membership.organization_id, is_active=True
        )


class MemberDetailView(OrgScopedMixin, APIView):
    def perm_for(self, request):
        # Anyone may leave (DELETE on themselves); the service checks the rest.
        if request.method == "DELETE" and str(self.kwargs["member_id"]) == str(self._own_membership_id(request)):
            return Perm.VIEW
        return Perm.MANAGE_MEMBERS

    def _own_membership_id(self, request):
        own = Membership.objects.filter(organization_id=self.kwargs["org_id"], user=request.user, is_active=True)
        return own.values_list("id", flat=True).first()

    def patch(self, request, org_id, member_id):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.change_role(
            membership=self.membership, target_id=member_id, role=serializer.validated_data["role"]
        )
        return Response(MemberSerializer(member).data)

    def delete(self, request, org_id, member_id):
        services.remove_member(membership=self.membership, target_id=member_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationListCreateView(OrgScopedMixin, APIView):
    perm = Perm.MANAGE_MEMBERS

    def get(self, request, org_id):
        pending = Invitation.objects.select_related("invited_by").filter(
            organization_id=org_id, accepted_at__isnull=True, revoked_at__isnull=True
        )
        return Response(InvitationSerializer(pending, many=True).data)

    def post(self, request, org_id):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, _token = services.invite_member(membership=self.membership, **serializer.validated_data)
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationRevokeView(OrgScopedMixin, APIView):
    perm = Perm.MANAGE_MEMBERS

    def delete(self, request, org_id, invitation_id):
        services.revoke_invitation(membership=self.membership, invitation_id=invitation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptInvitationView(APIView):
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(user=request.user, token=serializer.validated_data["token"])
        context = {"roles": {membership.organization_id: membership.role}}
        return Response(OrganizationSerializer(membership.organization, context=context).data)


class OrgAccountListView(OrgScopedMixin, generics.ListAPIView):
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self):
        return Account.objects.filter(organization_id=self.membership.organization_id, is_active=True)


class OrgTransactionListView(OrgScopedMixin, generics.ListAPIView):
    serializer_class = TransactionSerializer
    filterset_class = TransactionFilter
    search_fields = ("description", "counterparty_name", "counterparty_account", "reference")
    ordering_fields = ("created_at", "amount")
    ordering = ("-created_at",)

    def get_queryset(self):
        return Transaction.objects.select_related("account").filter(
            account__organization_id=self.membership.organization_id
        )


class PaymentListCreateView(OrgScopedMixin, generics.ListAPIView):
    """GET/POST /organizations/<id>/payments/ — every payment out of the cashbook, pay-run payslips included.

    Filters: ?status=, ?type=, ?worker=<worker id>, ?pay_run=<run id> or ?pay_run=none for payments made on their own.
    """

    serializer_class = PaymentSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "transfers"

    def perm_for(self, request):
        return Perm.INITIATE_PAYMENT if request.method == "POST" else Perm.VIEW

    def get_queryset(self):
        payments = Payment.objects.select_related(
            "source_account", "created_by", "decided_by", "reversal"
        ).filter(organization_id=self.membership.organization_id)
        params = self.request.query_params
        for field in ("status", "type"):
            if params.get(field):
                payments = payments.filter(**{field: params[field]})
        if params.get("worker"):
            payments = payments.filter(worker_id=params["worker"])
        if params.get("pay_run") == "none":
            payments = payments.filter(pay_run__isnull=True)
        elif params.get("pay_run"):
            payments = payments.filter(pay_run_id=params["pay_run"])
        return payments

    def post(self, request, org_id):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, created = services.create_payment(membership=self.membership, **serializer.validated_data)
        return Response(
            PaymentSerializer(payment).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class PaymentActionView(OrgScopedMixin, APIView):
    """POST .../payments/<id>/{approve,reject,cancel,reverse}/"""

    actions = {
        "approve": Perm.APPROVE_PAYMENT,
        "reject": Perm.APPROVE_PAYMENT,
        "cancel": Perm.INITIATE_PAYMENT,
        "reverse": Perm.APPROVE_PAYMENT,
    }

    def perm_for(self, request):
        if self.kwargs["action"] not in self.actions:
            raise Http404
        return self.actions[self.kwargs["action"]]

    def post(self, request, org_id, payment_id, action):
        if action == "reverse":
            serializer = ReverseSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            payment = services.reverse_payment(
                membership=self.membership, payment_id=payment_id, reason=serializer.validated_data["reason"]
            )
            return Response(PaymentSerializer(payment).data)
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if action == "cancel":
            payment = services.cancel_payment(membership=self.membership, payment_id=payment_id)
        else:
            decide = services.approve_payment if action == "approve" else services.reject_payment
            payment = decide(membership=self.membership, payment_id=payment_id, note=serializer.validated_data["note"])
        return Response(PaymentSerializer(payment).data)


class OrgAuditEventListView(OrgScopedMixin, generics.ListAPIView):
    perm = Perm.VIEW_AUDIT
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        events = AuditEvent.objects.filter(organization_id=self.membership.organization_id)
        action = self.request.query_params.get("action")
        return events.filter(action__startswith=action) if action else events


class OrgStatementView(OrgScopedMixin, APIView):
    """GET /organizations/<id>/statements/ — same parameters as /statements/, for business wallets."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "statements"

    def get(self, request, org_id):
        accounts = Account.objects.select_related("organization").filter(
            organization_id=self.membership.organization_id, is_active=True
        )
        return statement_response(request, accounts, organization_id=self.membership.organization_id)
