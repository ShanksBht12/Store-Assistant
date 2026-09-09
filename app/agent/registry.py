"""
registry.py — Business-agnostic ToolRegistry interface.

WHY THIS EXISTS
  agent.py runs the core LLM loop: load history, call LLM, dispatch tools,
  accumulate results, save history, return a reply. None of that is specific
  to a retail store — it works identically for a marketing agency, a service
  business, a booking platform, or anything else.

  What IS business-specific:
    - Which tools exist and what they query (Product ORM vs. Campaign ORM vs. …)
    - What "interesting" post-call state to surface back to the frontend
      (a product card for retail, a campaign summary for an agency, nothing
      for a service chatbot that just answers questions)
    - How to inject a conversation_id into tool arguments (retail needs it
      for create_order; other business types may need it elsewhere or not at all)

  ToolRegistry is the seam between the two halves. agent.py depends only on
  this interface. Each business type ships its own concrete implementation:

    RetailToolRegistry   → app/agent/retail_registry.py  (this repo)
    AgencyToolRegistry   → app/agent/agency_registry.py  (future adapter)
    BookingToolRegistry  → app/agent/booking_registry.py (future adapter)

  Onboarding a new business type = writing a new *_registry.py that implements
  ToolRegistry. agent.py, prompt.py, router.py, and the LLM provider layer
  stay completely unchanged.

USAGE IN agent.py
  The registry is injected into handle_chat_message() at call time:

      registry = RetailToolRegistry(tenant)
      reply, extra, pm = await handle_chat_message(db, conversation_id, message, registry)

  agent.py never imports tools.py, Product, Order, or any ORM model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class TurnResult:
    """
    Everything the agent loop needs to return to the API layer after one turn.

    The core loop always populates `reply`. The remaining fields are
    business-specific — a retail registry sets `card_data` to a product dict
    when the customer is browsing; an agency registry might set it to a
    campaign summary; a pure Q&A bot leaves everything None.

    Fields
    ------
    reply : str
        The plain-text assistant reply to send to the customer.
    card_data : dict | None
        Arbitrary JSON-serialisable dict the frontend should render as a
        "rich card" (product card, campaign card, booking summary, etc.).
        None means no card this turn.
    payment_method : str | None
        Set when the business flow completed a payment step that requires
        the frontend to show a QR code or payment widget. The value is a
        normalised lowercase string the frontend maps to its UI component
        (e.g. "esewa", "khalti"). None for cash/no-action turns.
    order_confirmation : str | None
        Pre-formatted order/transaction confirmation text the agent loop
        should use as the reply instead of asking the LLM to generate one.
        When set, the loop skips the LLM reply step for this turn and
        returns this string directly. None means let the LLM reply normally.
    """
    reply:              str
    card_data:          dict | None  = None
    payment_method:     str | None   = None
    order_confirmation: str | None   = None


@runtime_checkable
class ToolRegistry(Protocol):
    """
    Interface every business-type adapter must implement.

    The agent loop calls these four methods and nothing else from tools.py.
    Implementations are free to query any ORM, call any external API, or
    return static data — the loop does not care.
    """

    @property
    def tool_specs(self) -> list[dict[str, Any]]:
        """
        OpenAI/Groq function-calling schemas for all tools this registry
        exposes. Passed verbatim to llm.chat(..., tools=tool_specs).
        """
        ...

    def run_tool(
        self,
        db: Any,
        name: str,
        arguments: dict[str, Any],
        conversation_id: str,
    ) -> dict[str, Any]:
        """
        Execute the named tool with the given arguments.

        Parameters
        ----------
        db : SQLAlchemy Session (or any data-access object the adapter needs)
        name : tool name as returned by the LLM in tool_calls[*].function.name
        arguments : decoded JSON arguments dict
        conversation_id : active session ID — passed so tools that need to
            associate a transaction with a session (e.g. create_order) can do
            so without agent.py knowing why

        Returns
        -------
        JSON-serialisable result dict. On error, return {"error": "..."} rather
        than raising — the loop will feed the error back to the LLM.
        """
        ...

    def extract_turn_extras(
        self,
        db: Any,
        tool_calls_made: list[dict[str, Any]],
    ) -> tuple[dict | None, str | None]:
        """
        After all tools in a turn have been executed, decide what rich extras
        (card, payment method) to surface to the frontend.

        Parameters
        ----------
        db : same session passed to run_tool
        tool_calls_made : list of {"name", "arguments", "result"} dicts,
            one entry per tool call executed this turn

        Returns
        -------
        (card_data, payment_method)
          card_data      — dict to render as a card, or None
          payment_method — lowercase payment method string for QR, or None
        """
        ...

    def build_order_confirmation(
        self,
        tool_calls_made: list[dict[str, Any]],
        digital_payments: set[str],
    ) -> tuple[str | None, str | None]:
        """
        Inspect this turn's tool results for any completed transactions
        (orders placed, payments updated, bookings confirmed, etc.) and
        return a pre-formatted confirmation string if appropriate.

        The agent loop uses this to bypass the LLM reply step for
        transactional turns — the confirmation is deterministic and
        must be accurate, so generating it in code is safer than asking
        the LLM to format numbers and IDs.

        Parameters
        ----------
        tool_calls_made : same list as extract_turn_extras
        digital_payments : set of lowercase payment method strings that
            trigger a QR code (from TenantContext.digital_payments)

        Returns
        -------
        (confirmation_text, payment_method)
          confirmation_text — ready-to-send string, or None if no transaction
          payment_method    — lowercase QR-trigger method, or None
        """
        ...
