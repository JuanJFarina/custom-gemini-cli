import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser
from harle_domain.messaging import RecentMedia
from harle_domain.tools import (
    HarleToolStore,
    NotificationAllowance,
    ToolEffect,
    ToolFamily,
)
from harle_utils import log

from .authorization import ToolAccessPolicy
from .registry import ToolRegistry

EXPENSE_TERMS = (
    "expense",
    "expenses",
    "refund",
    "refunds",
    "installment",
    "installments",
    "gasto",
    "gastos",
    "compra",
    "compras",
    "cuota",
    "cuotas",
    "reembolso",
    "reembolsos",
    "devolución",
    "devoluciones",
)
EVENT_TERMS = (
    "event",
    "events",
    "calendar",
    "calendars",
    "appointment",
    "appointments",
    "meeting",
    "meetings",
    "schedule",
    "schedules",
    "evento",
    "eventos",
    "calendario",
    "calendarios",
    "agenda",
    "agendas",
    "cita",
    "citas",
    "reunión",
    "reuniones",
)
PROFILE_TERMS = (
    "interaction frequency",
    "message frequency",
    "proactive message",
    "check in",
    "frequency",
    "interaction",
    "profile",
    "frecuencia de interacción",
    "frecuencia de mensajes",
    "mensaje proactivo",
    "frecuencia",
    "interacción",
    "perfil",
)


@dataclass(frozen=True, slots=True)
class ToolInjectionContext:
    resolved_user: ResolvedUser
    timezone: str
    prompt: str
    recent_media: Sequence[RecentMedia] = ()


@dataclass(frozen=True, slots=True)
class ToolsInjector:
    registry: ToolRegistry
    access_policy: ToolAccessPolicy

    def inject(
        self,
        context: ToolInjectionContext,
    ) -> HarleToolStore:
        authorized = self.access_policy.authorized_families(context.resolved_user)
        if not context.recent_media:
            authorized = authorized - {ToolFamily.RECENT_MEDIA}
        families = _relevant_families(context.prompt, authorized)
        if ToolFamily.RECENT_MEDIA in authorized:
            families = families | {ToolFamily.RECENT_MEDIA}
        log.info(
            "Injecting tool families %s from authorized %s and registered %s",
            families,
            authorized,
            self.registry.families,
        )
        store = self.registry.build_store(
            user_id=context.resolved_user.user.id,
            timezone=context.timezone,
            authorized_families=families,
            notification_allowance=NotificationAllowance(
                limit=context.resolved_user.plan.monthly_notification_limit,
                period=context.resolved_user.user.require_subscription_period(),
            ),
        )
        if not context.recent_media:
            return store
        return HarleToolStore(
            tools=store.tools,
            family_instructions=(
                *store.family_instructions,
                _recent_media_prompt(context.recent_media),
            ),
        )

    def inject_scheduled(
        self,
        context: ToolInjectionContext,
    ) -> HarleToolStore:
        authorized = self.access_policy.authorized_families(context.resolved_user)
        if not context.recent_media:
            authorized = authorized - {ToolFamily.RECENT_MEDIA}
        store = self.registry.build_store(
            user_id=context.resolved_user.user.id,
            timezone=context.timezone,
            authorized_families=authorized,
            notification_allowance=NotificationAllowance(
                limit=context.resolved_user.plan.monthly_notification_limit,
                period=context.resolved_user.user.require_subscription_period(),
            ),
        )
        instructions = (
            (_recent_media_prompt(context.recent_media),)
            if context.recent_media
            else ()
        )
        return HarleToolStore(
            tools=tuple(
                tool
                for tool in store.tools
                if tool.definition.effect is ToolEffect.READ
            ),
            family_instructions=instructions,
        )

    def inject_for_explicit_user_id(self, user_id: UUID) -> HarleToolStore:
        families = self.access_policy.authorized_families_for_user_id(user_id)
        return self.registry.build_store(
            user_id=user_id,
            timezone="UTC",
            authorized_families=families,
        )


def _relevant_families(
    prompt: str,
    authorized: frozenset[ToolFamily],
) -> frozenset[ToolFamily]:
    normalized = prompt.casefold()
    selected: set[ToolFamily] = set()
    if _contains_any_term(normalized, EXPENSE_TERMS):
        selected.update(
            {
                ToolFamily.INTERNAL_EXPENSES,
                ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES,
            },
        )
    if _contains_any_term(normalized, EVENT_TERMS):
        selected.add(ToolFamily.INTERNAL_EVENTS)
    if _contains_any_term(normalized, PROFILE_TERMS):
        selected.add(ToolFamily.PROFILES)
    return frozenset(selected).intersection(authorized) if selected else authorized


def _contains_any_term(prompt: str, terms: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", prompt) is not None
        for term in terms
    )


def _recent_media_prompt(media: Sequence[RecentMedia]) -> str:
    entries = [
        (
            f"- attachment_id={item.attachment_id}, "
            f"kind={item.reference.kind.value}, "
            f"received_at={item.stored_at.isoformat()}, "
            f"file_name={item.reference.file_name or 'not supplied'}"
        )
        for item in media
    ]
    return "Recent Telegram attachments:\n" + "\n".join(entries)
