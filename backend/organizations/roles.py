"""Who may do what in a business. The single source of truth for organization permissions."""
from enum import StrEnum

from .models import Membership

Role = Membership.Role


class Perm(StrEnum):
    VIEW = "view"  # wallets, transactions, members, payment requests
    INITIATE_PAYMENT = "initiate_payment"
    APPROVE_PAYMENT = "approve_payment"  # also: verify a beneficiary's payout details
    MANAGE_BENEFICIARIES = "manage_beneficiaries"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_SETTINGS = "manage_settings"
    VIEW_AUDIT = "view_audit"


PERMISSIONS = {
    Perm.VIEW: {Role.OWNER, Role.ADMIN, Role.FINANCE, Role.VIEWER},
    Perm.INITIATE_PAYMENT: {Role.OWNER, Role.ADMIN, Role.FINANCE},
    Perm.APPROVE_PAYMENT: {Role.OWNER, Role.ADMIN},
    Perm.MANAGE_BENEFICIARIES: {Role.OWNER, Role.ADMIN, Role.FINANCE},
    Perm.MANAGE_MEMBERS: {Role.OWNER, Role.ADMIN},
    Perm.MANAGE_SETTINGS: {Role.OWNER},
    Perm.VIEW_AUDIT: {Role.OWNER, Role.ADMIN},
}

# Roles each role may grant, change or remove. Admins manage staff; only owners manage admins and owners.
MANAGEABLE_ROLES = {
    Role.OWNER: {Role.OWNER, Role.ADMIN, Role.FINANCE, Role.VIEWER},
    Role.ADMIN: {Role.FINANCE, Role.VIEWER},
}


def has_perm(role: str, perm: Perm) -> bool:
    return role in PERMISSIONS[perm]


def can_manage(actor_role: str, target_role: str) -> bool:
    return target_role in MANAGEABLE_ROLES.get(actor_role, set())
