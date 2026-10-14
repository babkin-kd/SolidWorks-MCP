"""Deterministic provenance of the Python/guide files shipped in a wheel."""

import hashlib
from pathlib import Path


def source_digest(package_root: str | Path) -> str:
    root = Path(package_root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.md') and '__pycache__' not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
            # Source distributions/Git may normalise CRLF; the hash must agree
            # for the same source installed from a Windows or Linux checkout.
            digest.update(path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return digest.hexdigest()
