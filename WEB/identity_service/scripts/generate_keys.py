"""Generate persistent hybrid signing keys for the 6IGMA identity service.

Produces a JSON keys file with:
  - ed_private_pem    : Ed25519 private key (PKCS8 PEM)
  - mldsa_secret_b64  : ML-DSA-65 (FIPS 204) secret key, base64url
  - mldsa_public_b64  : ML-DSA-65 public key, base64url
  - hs_secret         : random HMAC secret for refresh/reset tokens

Run inside the identity image (it has constant-time liboqs):
    docker compose run --rm --no-deps -v "$PWD/identity_service/keys:/out" \
        identity python -m scripts.generate_keys /out/identity_keys.json

Always pass an output PATH (liboqs prints a one-line banner to stdout, so the
stdout form is not machine-parseable). Keep the resulting file OUT of git and
mount it read-only (IDENTITY_KEYS_FILE).
"""
import base64
import json
import secrets
import sys

from cryptography.hazmat.primitives import serialization as s
from cryptography.hazmat.primitives.asymmetric import ed25519


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def generate() -> dict:
    ed = ed25519.Ed25519PrivateKey.generate()
    ed_pem = ed.private_bytes(
        s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()).decode()
    try:
        import oqs  # constant-time
        with oqs.Signature("ML-DSA-65") as sig:
            pk = sig.generate_keypair()
            sk = sig.export_secret_key()
    except Exception:
        from dilithium_py.ml_dsa import ML_DSA_65
        pk, sk = ML_DSA_65.keygen()
    return {
        "ed_private_pem": ed_pem,
        "mldsa_secret_b64": _b64(sk),
        "mldsa_public_b64": _b64(pk),
        "hs_secret": secrets.token_urlsafe(48),
    }


if __name__ == "__main__":
    out = json.dumps(generate(), indent=2) + "\n"
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as fh:
            fh.write(out)
        print(f"wrote {sys.argv[1]}")
    else:
        sys.stdout.write(out)
