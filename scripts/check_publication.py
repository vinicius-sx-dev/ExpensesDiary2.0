"""Check only tracked files; never read or print environment credentials."""
import re
import subprocess
from pathlib import Path

paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
secret = re.compile(rb'gsk_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
failures = []
for name in filter(None, paths):
    path = Path(name)
    if (path.name.startswith('.env') and path.name not in {'.env.example', '.env.test.example'}) or set(path.parts) & {'node_modules', '.venv', '.git'}:
        failures.append(name + ': forbidden publication path')
        continue
    if path.suffix in {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.sql', '.db', '.rar', '.zip'}:
        failures.append(name + ': private/generated artifact')
        continue
    if secret.search(path.read_bytes()):
        failures.append(name + ': possible secret; value omitted')
if failures:
    raise SystemExit('\n'.join(failures))
print('Publication path and secret-pattern checks passed.')
