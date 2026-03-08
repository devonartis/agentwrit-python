"""Unit tests for agentauth.crypto module.

Tests Ed25519 keypair generation and nonce signing.
Keys are ephemeral (in-memory only). Public keys are raw 32-byte base64.
Nonces are hex-decoded before signing. Signatures are base64-encoded.

============================================================
  TEST: agentauth.crypto -- Ed25519 keypair + nonce signing
============================================================
"""

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from agentauth.crypto import generate_keypair, sign_nonce

# ---------------------------------------------------------------------------
# generate_keypair tests
# ---------------------------------------------------------------------------


class TestGenerateKeypair:
    """Tests for generate_keypair()."""

    def test_returns_private_key_and_base64_string(self):
        """generate_keypair() returns (Ed25519PrivateKey, str)."""
        private_key, pub_b64 = generate_keypair()
        assert isinstance(private_key, Ed25519PrivateKey)
        assert isinstance(pub_b64, str)

    def test_public_key_decodes_to_32_bytes(self):
        """Base64 public key decodes to exactly 32 bytes (raw format, not DER)."""
        _private_key, pub_b64 = generate_keypair()
        raw_bytes = base64.b64decode(pub_b64)
        assert len(raw_bytes) == 32, f"Expected 32 bytes, got {len(raw_bytes)}"

    def test_public_key_is_valid_ed25519(self):
        """Decoded public key bytes can reconstruct a valid Ed25519PublicKey."""
        _private_key, pub_b64 = generate_keypair()
        raw_bytes = base64.b64decode(pub_b64)
        reconstructed = Ed25519PublicKey.from_public_bytes(raw_bytes)
        assert reconstructed is not None

    def test_each_call_generates_different_keys(self):
        """Each call produces a unique keypair."""
        _k1, pub1 = generate_keypair()
        _k2, pub2 = generate_keypair()
        assert pub1 != pub2, "Two calls should produce different public keys"


# ---------------------------------------------------------------------------
# sign_nonce tests
# ---------------------------------------------------------------------------


class TestSignNonce:
    """Tests for sign_nonce()."""

    def test_returns_base64_string(self):
        """sign_nonce() returns a base64-encoded string."""
        private_key, _pub = generate_keypair()
        nonce_hex = "aa" * 32  # 64-char hex string (like broker sends)
        sig_b64 = sign_nonce(private_key, nonce_hex)
        assert isinstance(sig_b64, str)
        # Should be valid base64
        base64.b64decode(sig_b64)

    def test_signature_is_64_bytes(self):
        """Ed25519 signature is 64 bytes when decoded."""
        private_key, _pub = generate_keypair()
        nonce_hex = "bb" * 32
        sig_b64 = sign_nonce(private_key, nonce_hex)
        sig_bytes = base64.b64decode(sig_b64)
        assert len(sig_bytes) == 64, f"Expected 64 bytes, got {len(sig_bytes)}"

    def test_signature_verifies_against_public_key(self):
        """Signature verifies using the corresponding public key."""
        private_key, pub_b64 = generate_keypair()
        nonce_hex = "cc" * 32
        sig_b64 = sign_nonce(private_key, nonce_hex)

        # Reconstruct public key from raw bytes and verify
        pub_bytes = base64.b64decode(pub_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        sig_bytes = base64.b64decode(sig_b64)
        nonce_bytes = bytes.fromhex(nonce_hex)

        # Ed25519PublicKey.verify() raises InvalidSignature on failure, returns None on success
        public_key.verify(sig_bytes, nonce_bytes)

    def test_different_nonces_produce_different_signatures(self):
        """Different nonces yield different signatures with the same key."""
        private_key, _pub = generate_keypair()
        sig1 = sign_nonce(private_key, "aa" * 32)
        sig2 = sign_nonce(private_key, "bb" * 32)
        assert sig1 != sig2, "Different nonces should produce different signatures"
