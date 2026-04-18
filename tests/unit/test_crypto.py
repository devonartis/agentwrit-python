"""Unit tests for agentwrit.crypto — Ed25519 helpers.

Tests the four public functions defined in spec Section 6.6:
- generate_keypair() → Ed25519PrivateKey
- sign_nonce(key, nonce_hex) → bytes (raw 64-byte sig)
- export_public_key_b64(key) → str (base64 of raw 32-byte pubkey)
- encode_signature_b64(sig) → str (base64 of raw signature)
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from agentwrit.crypto import (
    encode_signature_b64,
    export_public_key_b64,
    generate_keypair,
    sign_nonce,
)


class TestGenerateKeypair:
    def test_returns_ed25519_private_key(self):
        key = generate_keypair()
        assert isinstance(key, Ed25519PrivateKey)

    def test_each_call_produces_unique_key(self):
        k1 = generate_keypair()
        k2 = generate_keypair()
        pub1 = export_public_key_b64(k1)
        pub2 = export_public_key_b64(k2)
        assert pub1 != pub2


class TestSignNonce:
    def test_returns_raw_bytes(self):
        key = generate_keypair()
        sig = sign_nonce(key, "aa" * 32)
        assert isinstance(sig, bytes)

    def test_signature_is_64_bytes(self):
        key = generate_keypair()
        sig = sign_nonce(key, "bb" * 32)
        assert len(sig) == 64

    def test_signature_verifies(self):
        """Roundtrip: sign with private key, verify with public key."""
        key = generate_keypair()
        nonce_hex = "cc" * 32
        sig = sign_nonce(key, nonce_hex)

        pub_bytes = base64.b64decode(export_public_key_b64(key))
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        # verify() raises InvalidSignature on failure, returns None on success
        public_key.verify(sig, bytes.fromhex(nonce_hex))

    def test_different_nonces_different_sigs(self):
        key = generate_keypair()
        sig1 = sign_nonce(key, "aa" * 32)
        sig2 = sign_nonce(key, "bb" * 32)
        assert sig1 != sig2


class TestExportPublicKeyB64:
    def test_decodes_to_32_bytes(self):
        key = generate_keypair()
        pub_b64 = export_public_key_b64(key)
        raw = base64.b64decode(pub_b64)
        assert len(raw) == 32

    def test_valid_base64(self):
        key = generate_keypair()
        pub_b64 = export_public_key_b64(key)
        # Should not raise
        base64.b64decode(pub_b64)

    def test_reconstructs_valid_public_key(self):
        key = generate_keypair()
        pub_b64 = export_public_key_b64(key)
        raw = base64.b64decode(pub_b64)
        reconstructed = Ed25519PublicKey.from_public_bytes(raw)
        assert reconstructed is not None


class TestEncodeSignatureB64:
    def test_roundtrip(self):
        key = generate_keypair()
        sig_bytes = sign_nonce(key, "dd" * 32)
        sig_b64 = encode_signature_b64(sig_bytes)
        decoded = base64.b64decode(sig_b64)
        assert decoded == sig_bytes

    def test_returns_string(self):
        sig_b64 = encode_signature_b64(b"\x00" * 64)
        assert isinstance(sig_b64, str)
