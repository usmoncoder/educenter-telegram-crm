"""Role-based access control. Roles are fixed; permissions per role are defined in code so
they are reviewable and versioned with the application."""

from __future__ import annotations

from enum import StrEnum

from app.db.enums import Role


class Perm(StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_MANAGE = "customers.manage"  # exclude / delete customer data
    CONVERSATIONS_VIEW = "conversations.view"
    CONVERSATIONS_REPLY = "conversations.reply"
    CONVERSATIONS_ASSIGN = "conversations.assign"
    CONVERSATIONS_VIEW_ALL = "conversations.view_all"  # not limited to assigned conversations
    INCIDENTS_DISMISS = "incidents.dismiss"
    AUTOREPLY_MANAGE = "autoreply.manage"
    GROUPS_VIEW = "groups.view"
    GROUPS_MANAGE = "groups.manage"
    CAMPAIGNS_VIEW = "campaigns.view"
    CAMPAIGNS_MANAGE = "campaigns.manage"
    HISTORY_VIEW = "history.view"
    REPORTS_VIEW = "reports.view"
    TELEGRAM_VIEW = "telegram.view"
    TELEGRAM_MANAGE = "telegram.manage"
    ADMINS_MANAGE = "admins.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"


_OPERATOR = {
    Perm.DASHBOARD_VIEW,
    Perm.CUSTOMERS_VIEW,
    Perm.CONVERSATIONS_VIEW,
    Perm.CONVERSATIONS_REPLY,
    Perm.INCIDENTS_DISMISS,
    Perm.TELEGRAM_VIEW,
}
_ADMIN = _OPERATOR | {
    Perm.CUSTOMERS_MANAGE,
    Perm.CONVERSATIONS_ASSIGN,
    Perm.CONVERSATIONS_VIEW_ALL,
    Perm.AUTOREPLY_MANAGE,
    Perm.GROUPS_VIEW,
    Perm.GROUPS_MANAGE,
    Perm.CAMPAIGNS_VIEW,
    Perm.CAMPAIGNS_MANAGE,
    Perm.HISTORY_VIEW,
    Perm.REPORTS_VIEW,
}
_SUPER = set(Perm)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OPERATOR: frozenset(_OPERATOR),
    Role.ADMIN: frozenset(_ADMIN),
    Role.SUPER_ADMIN: frozenset(_SUPER),
}


def has_perm(role: Role, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
