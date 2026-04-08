from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_keypair() -> ed25519.Ed25519PrivateKey:
    """Generate a new Ed25519 private key.

    Business Logic:
    Required for the agent registration ceremony. The private key is used
    to sign the cryptographic nonce (challenge) provided by the broker,
    proving the agent possesses the identity it claims to have.
    """
    return ed25519.Ed25519PrivateKey.generate()

def sign_nonce(private_key: ed25519.Ed25519PrivateKey, nonce_hex: str) -> bytes:
    """Hex-decode the nonce and sign the resulting bytes.

    Returns the raw 64-byte signature.

    Business Logic:
    The broker provides a random hex string as a nonce to prevent
    replay attacks. The agent must sign the literal bytes represented
    by that hex string to complete the challenge-response handshake.
    """
    nonce_bytes = bytes.fromhex(nonce_hex)
    return private_key.sign(nonce_bytes)

def export_public_key_b64(private_key: ed25519.Ed25519PrivateKey) -> str:
    """Extract the raw 32-byte public key and base64-encode it.

    Business Logic:
    The public key is sent to the broker during the `POST /v1/register`
    call. It allows the broker to verify the signature produced in
    the signing step.
    """
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes_raw()
    return base64.b64encode(public_bytes).decode("utf-8")

def encode_signature_b64(signature: bytes) -> str:
    """Base64-encode a raw Ed25519 signature.

    Business Logic:
    The signature must be transmitted in a base64-encoded format as part
    of the registration JSON body.
    """
    return base64.b64encode(signature).decode("utf-8")
