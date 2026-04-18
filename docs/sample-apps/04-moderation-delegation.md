# App 4: Content Moderation Queue

## The Scenario

You run a social media platform. User-generated content flows into a moderation queue. A **reviewer agent** reads flagged posts and decides what to do. When it finds content that violates policy, it delegates narrow authority to a **moderator agent** that has the power to delete posts and suspend accounts — but only for the specific user and post the reviewer identified.

The reviewer cannot delete posts. The moderator cannot review other posts. Delegation is how authority flows from the reviewer to the moderator — and only for what the reviewer decided needs action.

This is the most common delegation pattern in production: a read-only agent identifies work, then delegates narrow write authority to a specialist agent.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Single-hop delegation** | Agent A gives a subset of its authority to Agent B |
| **`agent.delegate()`** | The SDK method for creating scope-attenuated tokens |
| **`DelegatedToken`** | What you get back from delegation — a new JWT scoped to a subset of the delegator's authority |
| **Delegation chain inspection** | How to verify who delegated what to whom |
| **Validating delegated tokens** | Confirming the broker issued the scope you requested |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Moderation Queue Script                                     │
│                                                              │
│  1. Create reviewer agent (broad read + delegate power)      │
│     scope: read:posts:*, read:users:*                        │
│                                                              │
│  2. Reviewer finds violating post by user "usr-482"          │
│                                                              │
│  3. Create moderator agent (no scope yet — empty vessel)     │
│                                                              │
│  4. Reviewer DELEGATES to moderator:                         │
│     scope: delete:posts:usr-482, write:users:usr-482         │
│     ↑ Narrowed from reviewer's authority                     │
│                                                              │
│  5. Moderator uses delegated token to:                       │
│     - Delete post post-91827 (ALLOWED — delete:posts:usr-482)│
│     - Suspend user usr-482    (ALLOWED — write:users:usr-482)│
│     - Suspend user usr-901    (BLOCKED — wrong user)         │
│                                                              │
│  6. Reviewer CANNOT delete posts (read-only scope)           │
│  7. Moderator CANNOT review other posts (narrow delegation)  │
└─────────────────────────────────────────────────────────────┘
```

The reviewer holds broad read access. The moderator holds narrow write access for one specific user. The delegation is the bridge between them.

---

## The Code

```python
# moderation_queue.py
# Run: python moderation_queue.py

from __future__ import annotations

import os
import sys

from agentwrit import (
    Agent,
    AgentWritApp,
    DelegatedToken,
    scope_is_subset,
    validate,
)
from agentwrit.errors import AuthorizationError


def main() -> None:
    app = AgentWritApp(
        broker_url=os.environ["AGENTWRIT_BROKER_URL"],
        client_id=os.environ["AGENTWRIT_CLIENT_ID"],
        client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
    )

    print("Content Moderation Queue — Delegation Demo")
    print("=" * 55)
    print()

    # ── Step 1: Create the reviewer agent ───────────────────────
    # Broad read access across all posts and users.
    # Does NOT have delete or suspend power.
    reviewer = app.create_agent(
        orch_id="content-moderation",
        task_id="review-queue-001",
        requested_scope=[
            "read:posts:*",
            "read:users:*",
        ],
    )

    print(f"Reviewer agent created")
    print(f"  ID:    {reviewer.agent_id}")
    print(f"  Scope: {reviewer.scope}")
    print()

    # ── Step 2: Reviewer scans flagged posts ────────────────────
    # Simulated — in reality this would be a database query.
    flagged_posts = [
        {"post_id": "post-91827", "user_id": "usr-482", "reason": "harassment"},
        {"post_id": "post-55123", "user_id": "usr-901", "reason": "spam"},
    ]

    violating_post = flagged_posts[0]  # Reviewer decides this one violates policy
    print(f"Reviewer found violating post: {violating_post['post_id']} "
          f"by {violating_post['user_id']} — {violating_post['reason']}")
    print()

    # Reviewer CANNOT delete posts (read-only scope)
    delete_scope = [f"delete:posts:{violating_post['user_id']}"]
    if scope_is_subset(delete_scope, reviewer.scope):
        print("  🚨 PROBLEM: Reviewer can delete posts!")
        sys.exit(1)
    else:
        print(f"  Reviewer cannot delete posts (correct — read-only)")
    print()

    # ── Step 3: Create the moderator agent ──────────────────────
    # The moderator starts with a minimal scope. Its real authority
    # comes from the delegation, not from its registration scope.
    moderator = app.create_agent(
        orch_id="content-moderation",
        task_id="moderate-queue-001",
        requested_scope=[
            "read:posts:*",  # Needs to see what it's deleting
        ],
    )

    print(f"Moderator agent created")
    print(f"  ID:    {moderator.agent_id}")
    print(f"  Scope: {moderator.scope}  (base scope — no delete/suspend yet)")
    print()

    # ── Step 4: Reviewer delegates narrow authority to moderator ─
    # The reviewer decides what authority to hand off. Only for the
    # specific user whose content was flagged.
    target_user = violating_post["user_id"]
    delegated_scope = [
        f"delete:posts:{target_user}",
        f"write:users:{target_user}",
    ]

    print(f"Reviewer delegating to moderator:")
    print(f"  Target:  {moderator.agent_id}")
    print(f"  Scope:   {delegated_scope}")
    print()

    try:
        delegated: DelegatedToken = reviewer.delegate(
            delegate_to=moderator.agent_id,
            scope=delegated_scope,
        )
    except AuthorizationError as e:
        print(f"  Delegation FAILED: {e.problem.detail}")
        print(f"  Error code: {e.problem.error_code}")
        sys.exit(1)

    print(f"Delegation successful")
    print(f"  Token:    {delegated.access_token[:30]}...")
    print(f"  TTL:      {delegated.expires_in}s")
    print(f"  Chain:    {len(delegated.delegation_chain)} entries")
    for i, record in enumerate(delegated.delegation_chain):
        print(f"    [{i}] {record.agent}")
        print(f"        scope: {record.scope}")
        print(f"        at:    {record.delegated_at}")
    print()

    # ── Step 5: Validate the delegated token ────────────────────
    # Confirm the broker issued a token with the scope we requested.
    result = validate(app.broker_url, delegated.access_token)
    if result.valid and result.claims is not None:
        print(f"Delegated token validated:")
        print(f"  Subject: {result.claims.sub}")
        print(f"  Scope:   {result.claims.scope}")
        if result.claims.delegation_chain:
            print(f"  Chain:   {len(result.claims.delegation_chain)} entries")
        print()

    # ── Step 6: Moderator uses the delegated token ──────────────
    # The moderator's effective scope is its base + the delegation.
    # For this demo, we check the delegated scope directly.
    moderator_effective = moderator.scope + delegated_scope

    print(f"Moderator effective scope: {moderator_effective}")
    print()

    # Action: Delete the violating post
    required = [f"delete:posts:{target_user}"]
    if scope_is_subset(required, moderator_effective):
        print(f"  ✅ DELETE post {violating_post['post_id']} by {target_user}")
    else:
        print(f"  ❌ Cannot delete post")

    # Action: Suspend the violating user
    required = [f"write:users:{target_user}"]
    if scope_is_subset(required, moderator_effective):
        print(f"  ✅ SUSPEND user {target_user} — account locked")
    else:
        print(f"  ❌ Cannot suspend user")

    # Action: Try to suspend a DIFFERENT user
    required = [f"write:users:usr-901"]
    if scope_is_subset(required, moderator_effective):
        print(f"  🚨 BREACH: Can suspend usr-901!")
        sys.exit(1)
    else:
        print(f"  🛑 BLOCKED: Cannot suspend usr-901 (not in delegated scope)")

    # Action: Try to delete posts from a different user
    required = [f"delete:posts:usr-901"]
    if scope_is_subset(required, moderator_effective):
        print(f"  🚨 BREACH: Can delete usr-901's posts!")
        sys.exit(1)
    else:
        print(f"  🛑 BLOCKED: Cannot delete usr-901's posts (not in delegated scope)")

    print()

    # ── Step 7: Cleanup ─────────────────────────────────────────
    reviewer.release()
    moderator.release()
    print("Both agents released.")

    # Verify both tokens are dead
    for label, token in [("Reviewer", reviewer.access_token), ("Moderator", moderator.access_token)]:
        r = validate(app.broker_url, token)
        status = "dead" if not r.valid else "STILL VALID"
        print(f"  {label} token: {status}")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:posts:*` | Reviewer reads all flagged posts | `read:posts:*` (reviewer), `read:posts:*` (moderator base) |
| `read:users:*` | Reviewer reads user profiles | `read:users:*` |
| `write:data:*` | Moderator suspends users via delegation | `write:users:{target}` (delegated) |
| `write:records:*` | Moderator deletes posts via delegation | `delete:posts:{target}` (delegated) |

> **Note on delegation:** The reviewer delegates `delete:posts:usr-482` and `write:users:usr-482`. These delegated scopes must also be within the app's ceiling. The universal sample app includes `write:data:*` and `write:records:*` which cover these. If you registered your own app, ensure it includes `write:data:*` and `write:records:*` or the delegation will fail with 403.

## Running It

```bash
export AGENTWRIT_BROKER_URL="http://127.0.0.1:8080"
export AGENTWRIT_CLIENT_ID="<from registration>"
export AGENTWRIT_CLIENT_SECRET="<from registration>"

uv run python moderation_queue.py
```

---

## Expected Output

```
Content Moderation Queue — Delegation Demo
=======================================================

Reviewer agent created
  ID:    spiffe://agentwrit.local/agent/content-moderation/review-queue-001/a1b2...
  Scope: ['read:posts:*', 'read:users:*']

Reviewer found violating post: post-91827 by usr-482 — harassment

  Reviewer cannot delete posts (correct — read-only)

Moderator agent created
  ID:    spiffe://agentwrit.local/agent/content-moderation/moderate-queue-001/c3d4...
  Scope: ['read:posts:*']  (base scope — no delete/suspend yet)

Reviewer delegating to moderator:
  Target:  spiffe://agentwrit.local/agent/content-moderation/moderate-queue-001/c3d4...
  Scope:   ['delete:posts:usr-482', 'write:users:usr-482']

Delegation successful
  Token:    eyJhbGciOiJFZERTQSIsInR5cCI6...
  TTL:      60s
  Chain:    1 entries
    [0] spiffe://agentwrit.local/agent/content-moderation/review-queue-001/a1b2...
        scope: ['read:posts:*', 'read:users:*']
        at:    2026-04-09T10:30:00Z

Delegated token validated:
  Subject: spiffe://agentwrit.local/agent/content-moderation/moderate-queue-001/c3d4...
  Scope:   ['delete:posts:usr-482', 'write:users:usr-482']
  Chain:   1 entries

Moderator effective scope: ['read:posts:*', 'delete:posts:usr-482', 'write:users:usr-482']

  ✅ DELETE post post-91827 by usr-482
  ✅ SUSPEND user usr-482 — account locked
  🛑 BLOCKED: Cannot suspend usr-901 (not in delegated scope)
  🛑 BLOCKED: Cannot delete usr-901's posts (not in delegated scope)

Both agents released.
  Reviewer token: dead
  Moderator token: dead
```

---

## Key Takeaways

1. **Delegation is bounded authority transfer, not sharing.** The delegate only receives what was explicitly delegated. In this example the reviewer has `read:posts:*` (all posts) and delegates `delete:posts:usr-482` (one user's posts) — the broker enforces that the delegated scope cannot widen past the reviewer's. Equal-scope delegation is also valid; narrowing is a pattern this example chose, not a rule the broker imposes.

2. **Both agents must be registered before delegation.** `delegate()` takes a `delegate_to` SPIFFE ID — that agent must already exist in the broker. You can't delegate to an agent that hasn't been registered.

3. **The delegation chain proves who authorized what.** The `DelegatedToken.delegation_chain` records which agent delegated, what scope they held at the time, and when. An auditor can trace the authority path.

4. **Delegated tokens have a short TTL (default 60s).** The moderator's delegated authority expires quickly. Even if the delegated token leaks, it's only useful for one minute. This is intentional — delegation tokens are meant for short, specific tasks.

5. **The reviewer and moderator have different SPIFFE IDs.** In the audit trail, you can distinguish "the reviewer read a post" from "the moderator deleted a post." Each action is attributed to the specific agent that performed it.
