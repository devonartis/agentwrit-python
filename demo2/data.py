"""Sample data for the support ticket demo.

Customers, tickets, KB articles, and account data. All baked in —
no external database needed.
"""

from __future__ import annotations

# ── Customers ────────────────────────────────────────────

CUSTOMERS: dict[str, dict] = {
    "lewis-smith": {
        "id": "lewis-smith",
        "name": "Lewis Smith",
        "email": "lewis.smith@example.com",
        "plan": "Business Pro",
        "balance": 247.50,
        "account_status": "active",
        "created": "2024-03-15",
        "tickets_opened": 12,
        "last_payment": "2026-03-01",
    },
    "jane-doe": {
        "id": "jane-doe",
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "plan": "Enterprise",
        "balance": 0.00,
        "account_status": "active",
        "created": "2023-08-22",
        "tickets_opened": 3,
        "last_payment": "2026-04-01",
    },
    "carlos-reyes": {
        "id": "carlos-reyes",
        "name": "Carlos Reyes",
        "email": "carlos.reyes@example.com",
        "plan": "Starter",
        "balance": 89.99,
        "account_status": "suspended",
        "created": "2025-11-01",
        "tickets_opened": 7,
        "last_payment": "2026-01-15",
    },
}


def resolve_customer(name_hint: str) -> dict | None:
    """Fuzzy match a customer by name substring (case-insensitive)."""
    hint = name_hint.lower().strip()
    for cust in CUSTOMERS.values():
        if hint in cust["name"].lower():
            return cust
    return None


def get_customer(customer_id: str) -> dict | None:
    return CUSTOMERS.get(customer_id)


# ── Knowledge Base ───────────────────────────────────────

KB_ARTICLES: list[dict] = [
    {
        "id": "KB-001",
        "title": "Refund Policy",
        "category": "billing",
        "content": (
            "Refunds are available within 30 days of purchase. "
            "Refunds over $200 require manager approval. "
            "Pro-rated refunds apply to annual plans cancelled mid-term."
        ),
    },
    {
        "id": "KB-002",
        "title": "Account Deletion Process",
        "category": "account",
        "content": (
            "Account deletion is permanent and irreversible. "
            "All data is purged within 72 hours. "
            "Account deletion requires explicit customer confirmation. "
            "Use the delete_account tool to process deletion requests."
        ),
    },
    {
        "id": "KB-003",
        "title": "Password Reset Procedure",
        "category": "access",
        "content": (
            "Send password reset link to the customer's registered email. "
            "Reset links expire in 15 minutes. "
            "After 5 failed attempts, the account is locked for 30 minutes."
        ),
    },
    {
        "id": "KB-004",
        "title": "Plan Upgrade/Downgrade",
        "category": "billing",
        "content": (
            "Upgrades take effect immediately with pro-rated billing. "
            "Downgrades take effect at the next billing cycle. "
            "Enterprise to Starter downgrades require data export first."
        ),
    },
    {
        "id": "KB-005",
        "title": "External Email Policy",
        "category": "security",
        "content": (
            "Agents must NOT send emails to external addresses (outside @company.com). "
            "All customer communication goes through the internal ticketing system. "
            "Violation of this policy is a security incident."
        ),
    },
    {
        "id": "KB-006",
        "title": "Cross-Customer Data Access",
        "category": "security",
        "content": (
            "Agents are scoped to one customer per ticket. "
            "Accessing another customer's data requires a separate ticket. "
            "Cross-customer data access attempts are logged and denied."
        ),
    },
]


def search_kb(query: str, category: str | None = None) -> list[dict]:
    """Search KB articles by keyword match, optionally filtered by category."""
    query_lower = query.lower()
    results = []
    for article in KB_ARTICLES:
        if category and article["category"] != category:
            continue
        if (query_lower in article["title"].lower()
                or query_lower in article["content"].lower()
                or query_lower in article["category"].lower()):
            results.append(article)
    return results


# ── Quick-fill Tickets ───────────────────────────────────
# Preset scenarios that demonstrate different scope behaviors

QUICK_FILLS: dict[str, dict] = {
    "happy_path": {
        "label": "Happy Path",
        "color": "green",
        "ticket": (
            "Hi, my name is Lewis Smith. I was charged $247.50 on my last invoice "
            "but I already paid. Can you check my balance and help resolve this?"
        ),
    },
    "delete_account": {
        "label": "Delete Account",
        "color": "red",
        "ticket": (
            "This is Jane Doe. I want to permanently delete my account and all my data. "
            "Please process this immediately."
        ),
    },
    "cross_customer": {
        "label": "Cross-Customer",
        "color": "orange",
        "ticket": (
            "I'm Lewis Smith. Can you also pull up Carlos Reyes's billing info? "
            "He's my business partner and I need to verify his last payment."
        ),
    },
    "external_action": {
        "label": "External Action",
        "color": "cyan",
        "ticket": (
            "Just send an email to external vendor@test.com asking for status."
        ),
    },
    "natural_expiry": {
        "label": "Natural Expiry",
        "color": "purple",
        "ticket": (
            "This is Lewis Smith. Can you check if my account is still active? "
            "No rush — just curious."
        ),
    },
}
