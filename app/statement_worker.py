"""Fresh process with no application imports, credentials, network or file output."""

import os
import json
import sys


def main():
    # Production requires Linux/POSIX hard limits; unsupported hosts fail closed.
    if os.name == "posix":
        import resource

        resource.setrlimit(
            resource.RLIMIT_AS,
            (384 * 1024 * 1024,) * 2
        )

        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    from zoneinfo import ZoneInfo

    # Load parser code/timezone before denying filesystem reads.
    from pypdf import PdfReader  # noqa: F401
    from statement_parser import MAX_BYTES, parse

    ZoneInfo("America/Sao_Paulo")
    from datetime import datetime

    datetime.strptime("2025-01-01", "%Y-%m-%d")
    b"x".decode("cp1252")
    b"x".decode("cp437")
    b"x".decode("utf-8-sig")

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")):
            raise PermissionError("Operation blocked")
        if event == "open":
            raise PermissionError("Filesystem access blocked")

    sys.addaudithook(audit)
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    result = parse(data, sys.argv[1])
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No parser traceback or document contents in logs/API errors.
        sys.exit(2)
