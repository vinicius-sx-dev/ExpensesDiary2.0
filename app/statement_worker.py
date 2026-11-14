"""Fresh process with no application imports, credentials, network or file output."""

import json
import os
import sys


def main():
    # Production requires Linux/POSIX hard limits; unsupported hosts fail closed.
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)

        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    from zoneinfo import ZoneInfo

    import statement_parsers  # noqa: F401 — preload before filesystem lockdown.

    # Load parser code/timezone before denying filesystem reads.
    from pypdf import PdfReader  # noqa: F401
    from statement_parser import MAX_BYTES, parse

    ZoneInfo("America/Sao_Paulo")
    from datetime import datetime

    datetime.strptime("2025-01-01", "%Y-%m-%d")
    b"x".decode("cp1252")
    b"x".decode("cp437")
    b"x".decode("utf-8-sig")
    # Embedded PDF font ToUnicode CMaps lazily load codecs during extraction.
    # Warm the known codecs before denying filesystem access; keep the deny intact.
    import codecs

    for encoding in ("utf-16-be", "utf-16-le", "utf-16", "latin-1", "unicode-escape", "charmap"):
        codecs.lookup(encoding)

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")):
            raise PermissionError("Operation blocked")
        if event == "open":
            raise PermissionError("Filesystem access blocked")

    sys.addaudithook(audit)
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    result = parse(data, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Only allowlisted codes cross the process boundary, never document text.
        code = (
            "worker_unavailable"
            if isinstance(exc, (ImportError, PermissionError, MemoryError))
            else getattr(exc, "code", "unsupported_layout")
        )
        if code not in {
            "institution_mismatch",
            "invalid_institution",
            "unsupported_layout",
            "worker_unavailable",
        }:
            code = "unsupported_layout"
        sys.stdout.write(json.dumps({"error": code}))
        sys.exit(2)
