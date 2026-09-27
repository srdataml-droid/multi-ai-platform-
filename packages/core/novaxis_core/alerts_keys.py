"""Print a new VAPID key pair for browser push alerts.

    uv run python -m novaxis_core.alerts_keys

Put the public key in NOVAXIS_VAPID_PUBLIC_KEY and the private key in
NOVAXIS_VAPID_PRIVATE_KEY (keep it secret). Changing keys drops every existing device
subscription, so staff must turn alerts on again.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return b64(public), b64(raw_private)


if __name__ == "__main__":
    pub, priv = generate()
    print(f"NOVAXIS_VAPID_PUBLIC_KEY={pub}")
    print(f"NOVAXIS_VAPID_PRIVATE_KEY={priv}")
