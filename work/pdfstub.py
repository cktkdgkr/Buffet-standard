"""Import pypdf without the broken cryptography extension.

pypdf reaches for cryptography only to decrypt encrypted PDFs. This machine's
cryptography wheel panics on import (its Rust extension cannot load), which
takes pypdf down with it. None of the filings here are encrypted, so stub the
handful of names pypdf's crypt provider imports and let it load.
"""
import sys, types

def _mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

if "cryptography" not in sys.modules or True:
    c = _mod("cryptography"); c.__version__ = "0.0.0-stub"
    _mod("cryptography.hazmat")
    _mod("cryptography.hazmat.primitives")
    _mod("cryptography.hazmat.primitives.ciphers")
    alg = _mod("cryptography.hazmat.primitives.ciphers.algorithms")
    base = _mod("cryptography.hazmat.primitives.ciphers.base")
    modes = _mod("cryptography.hazmat.primitives.ciphers.modes")
    pad = _mod("cryptography.hazmat.primitives.padding")
    class _Unavailable:
        def __init__(self, *a, **k):
            raise RuntimeError("encrypted PDF: cryptography unavailable here")
    for n in ("AES", "ARC4"):
        setattr(alg, n, _Unavailable)
    base.Cipher = _Unavailable
    modes.CBC = _Unavailable
    modes.ECB = _Unavailable
    pad.PKCS7 = _Unavailable
