"""Generate server-only secrets, without printing them or overwriting a config."""
import argparse
import base64
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument("--domain", required=True)
parser.add_argument("--output", default=".env.cloud")
args = parser.parse_args()
args.domain = args.domain.lower()
if not re.fullmatch(r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}", args.domain):
    parser.error("Use a domain such as plan.example.com, without a URL or path")
path = Path(args.output)
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as target:
    target.write(f"DAYMARK_DOMAIN={args.domain}\n")
    target.write("DAYMARK_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "\n")
    target.write("DAYMARK_INVITE_CODE=" + secrets.token_urlsafe(32) + "\n")
    target.write("DAYMARK_MAX_USERS=100\n")
print(f"Created {path}. Keep it private and include it in your off-server backup.")
