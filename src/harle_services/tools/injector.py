import re
from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser
from harle_domain.tools import HarleToolStore, ToolFamily
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


@dataclass(frozen=True, slots=True)
class ToolInjectionContext:
    resolved_user: ResolvedUser
    timezone: str
    prompt: str


@dataclass(frozen=True, slots=True)
class ToolsInjector:
    registry: ToolRegistry
    access_policy: ToolAccessPolicy

    def inject(
        self,
        context: ToolInjectionContext,
    ) -> HarleToolStore:
        authorized = self.access_policy.authorized_families(context.resolved_user)
        families = _relevant_families(context.prompt, authorized)
        log.info(
            "Injecting tool families %s from authorized %s and registered %s",
            families,
            authorized,
            self.registry.families,
        )
        return self.registry.build_store(
            user_id=context.resolved_user.user.id,
            timezone=context.timezone,
            authorized_families=families,
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
    return frozenset(selected).intersection(authorized) if selected else authorized


def _contains_any_term(prompt: str, terms: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", prompt) is not None
        for term in terms
    )
