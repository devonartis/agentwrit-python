"""Ed25519 keypair generation and nonce signing for AgentAuth.

Implements pattern component C1 (Ephemeral Identity Issuance):
  - Keys are ephemeral -- generated in memory, never persisted to disk.
  - Public keys are raw 32-byte base64-encoded (what the broker expects).
  - Nonces are hex-decoded before signing; signatures are base64-encoded.

Security invariant: private key material NEVER touches disk. The key object
exists only in Python process memory and goes out of scope after signing.
This is the core property that makes agent identity truly ephemeral (NIST
IR 8596: "issuing AI systems unique identities and credentials").
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Generate an Ed25519 keypair.

    Returns:
        (private_key, base64_public_key) where the public key is the raw
        32-byte key, base64-encoded (NOT DER format).
    """
    private_key = Ed25519PrivateKey.generate()
    raw_pub = private_key.public_key().public_bytes_raw()
    pub_b64 = base64.b64encode(raw_pub).decode("ascii")
    return private_key, pub_b64


def sign_nonce(private_key: Ed25519PrivateKey, nonce_hex: str) -> str:
    """Sign a hex-encoded nonce with the given private key.

    The broker sends nonces as 64-character hex strings. This function
    hex-decodes the nonce, signs the raw bytes, and returns the signature
    as a base64-encoded string.

    Args:
        private_key: Ed25519 private key from generate_keypair().
        nonce_hex: Hex-encoded nonce string from the broker's GET /v1/challenge.

    Returns:
        Base64-encoded Ed25519 signature (64 bytes when decoded).
    """
    try:
        nonce_bytes = bytes.fromhex(nonce_hex)
    except ValueError as exc:
        from agentauth.errors import AgentAuthError

        raise AgentAuthError(
            f"broker returned malformed nonce (expected hex string): {exc}"
        ) from exc
    sig_bytes = private_key.sign(nonce_bytes)
    return base64.b64encode(sig_bytes).decode("ascii")
