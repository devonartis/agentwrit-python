from agentwrit.scope import scope_is_subset


def test_scope_is_subset_exact_match():
    """Tests that identical scopes return True."""
    assert scope_is_subset(["read:data:customers"], ["read:data:customers"]) is True

def test_scope_is_subset_wildcard_identifier():
    """Tests that a wildcard in the identifier position covers specific resources."""
    assert scope_is_subset(["read:data:customers"], ["read:data:*"]) is True
    assert scope_is_subset(["read:data:orders"], ["read:data:*"]) is True

def test_scope_is_subset_mismatch_action():
    """Tests that a different action returns False."""
    assert scope_is_subset(["write:data:customers"], ["read:data:customers"]) is False

def test_scope_is_subset_mismatch_resource():
    """Tests that a different resource returns False."""
    assert scope_is_subset(["read:users:customers"], ["read:data:customers"]) is False

def test_scope_is_subset_mismatch_identifier():
    """Tests that a specific identifier does not match a different specific identifier."""
    assert scope_is_subset(["read:data:orders"], ["read:data:customers"]) is False

def test_scope_is_subset_multiple_requested():
    """Tests that all requested scopes must be covered."""
    allowed = ["read:data:*", "write:logs:system"]
    assert scope_is_subset(["read:data:customers", "write:logs:system"], allowed) is True
    assert scope_is_subset(["read:data:customers", "write:data:users"], allowed) is False

def test_scope_is_subset_empty_inputs():
    """Tests edge cases with empty lists."""
    # If nothing is requested, it's always satisfied
    assert scope_is_subset([], ["read:data:*"]) is True
    # If something is requested but nothing is allowed, it fails
    assert scope_is_subset(["read:data:customers"], []) is False

def test_scope_is_subset_wildcard_only_in_identifier():
    """Broker only wildcards the identifier position, not action or resource.

    Per spec Section 6.4 and authz.ScopeIsSubset in internal/authz/scope.go:
    action and resource must match exactly; only identifier supports *.
    """
    # Wildcard in identifier covers specific identifiers
    assert scope_is_subset(["read:data:customers"], ["read:data:*"]) is True
    # Wildcard in action position does NOT match — action must be exact
    assert scope_is_subset(["read:data:customers"], ["*:data:customers"]) is False
    # Full wildcard *:*:* does NOT match anything — all three must match
    assert scope_is_subset(["read:data:customers"], ["*:*:*"]) is False
