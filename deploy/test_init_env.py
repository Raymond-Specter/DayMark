"""Configuration generator tests; no network or cloud resources are used."""
import base64
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).with_name("init_env.py")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_public_address_preview_creates_no_file(tmp_path):
    output = tmp_path / "config"
    result = run("--public-ip", "8.8.8.8", "--print-domain", "--output", str(output))
    assert result.returncode == 0
    assert result.stdout.strip() == "daymark-8-8-8-8.sslip.io"
    assert not output.exists()


def test_private_reserved_and_invalid_addresses_are_rejected(tmp_path):
    for address in ("127.0.0.1", "192.168.1.1", "169.254.1.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "203.0.113.1", "::1", "bad-ip"):
        output = tmp_path / "config"
        assert run("--public-ip", address, "--output", str(output)).returncode != 0
        assert not output.exists()


def test_generation_keeps_existing_secrets_and_does_not_print_them(tmp_path):
    output = tmp_path / "config"
    assert run("--public-ip", "8.8.8.8", "--output", str(output)).returncode == 0
    original = output.read_bytes()
    fields = dict(line.split("=", 1) for line in original.decode().splitlines())
    assert len(base64.urlsafe_b64decode(fields["DAYMARK_ENCRYPTION_KEY"])) == 32
    assert len(fields["DAYMARK_INVITE_CODE"]) >= 32
    retry = run("--public-ip", "1.1.1.1", "--output", str(output))
    assert retry.returncode != 0
    assert output.read_bytes() == original
    assert fields["DAYMARK_ENCRYPTION_KEY"] not in retry.stdout + retry.stderr
    assert fields["DAYMARK_INVITE_CODE"] not in retry.stdout + retry.stderr


def test_custom_domain_and_exclusive_options():
    assert run("--domain", "Plan.Example.COM", "--print-domain").stdout.strip() == "plan.example.com"
    assert run("--domain", "https://plan.example.com", "--print-domain").returncode != 0
    assert run("--domain", "plan.example.com", "--public-ip", "8.8.8.8", "--print-domain").returncode != 0
