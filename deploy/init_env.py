"""Generate server-only secrets, without printing them or overwriting a config."""
import argparse
import base64
import ipaddress
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
address = parser.add_mutually_exclusive_group(required=True)
address.add_argument("--domain")
address.add_argument("--public-ip", help="Public IPv4 address for a free sslip.io hostname")
parser.add_argument("--output", default=".env.cloud")
parser.add_argument("--print-domain", action="store_true", help="Validate and print the hostname without creating secrets")
args = parser.parse_args()
if args.public_ip:
    try:
        public_ip = ipaddress.IPv4Address(args.public_ip)
    except ipaddress.AddressValueError:
        parser.error("Use a public IPv4 address")
    if not public_ip.is_global or public_ip.is_multicast:
        parser.error("Use a public IPv4 address, not a private or reserved address")
    args.domain = "daymark-" + str(public_ip).replace(".", "-") + ".sslip.io"
args.domain = args.domain.lower()
if not re.fullmatch(r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}", args.domain):
    parser.error("Use a domain such as plan.example.com, without a URL or path")
if args.print_domain:
    print(args.domain)
    raise SystemExit(0)
path = Path(args.output)
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as target:
    target.write(f"DAYMARK_DOMAIN={args.domain}\n")
    target.write("DAYMARK_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "\n")
    target.write("DAYMARK_INVITE_CODE=" + secrets.token_urlsafe(32) + "\n")
    target.write("DAYMARK_MAX_USERS=100\n")
print(f"Created {path}. Keep it private and include it in your off-server backup.")
