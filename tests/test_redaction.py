"""Redaction tests.

Test fixtures that match real-secret patterns are constructed at runtime
via string concatenation so the literal source text does not look like a
real secret to source-scanning tools (GitHub's secret-scanning, gitleaks,
trufflehog). The runtime values still match the redaction regexes.
"""
from pathlib import Path

import pytest

from council_gate.redaction import RefusedFilename, check_filename, redact


# --- filename refusal ----------------------------------------------------


def test_refuses_dotenv_filenames():
    with pytest.raises(RefusedFilename):
        check_filename(Path(".env"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("/some/path/.env.production"))


def test_refuses_pem_and_keys():
    with pytest.raises(RefusedFilename):
        check_filename(Path("server.pem"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("/home/me/.ssh/id_rsa"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("/home/me/.ssh/id_ed25519"))


def test_refuses_credentials_file_case_insensitive():
    with pytest.raises(RefusedFilename):
        check_filename(Path("Credentials.json"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("aws-secrets.yaml"))


def test_refuses_aws_credentials():
    with pytest.raises(RefusedFilename):
        check_filename(Path("/home/me/.aws/credentials"))


def test_refuses_dotfile_credential_stores():
    for name in (".pgpass", ".netrc", ".npmrc", ".pypirc"):
        with pytest.raises(RefusedFilename):
            check_filename(Path(f"/home/me/{name}"))


def test_refuses_kubeconfig_and_dockercreds():
    with pytest.raises(RefusedFilename):
        check_filename(Path("kubeconfig"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("/home/me/.kube/config"))
    with pytest.raises(RefusedFilename):
        check_filename(Path("/home/me/.dockerconfigjson"))


def test_allows_normal_artifacts():
    check_filename(Path("spec.md"))
    check_filename(Path("/tmp/diff.patch"))
    check_filename(Path("notes/proposal.md"))


# --- inline redaction ----------------------------------------------------
# NOTE: each fixture is built via concatenation so the literal source text
# does not pattern-match real-secret scanners. The composed runtime value
# still matches the redaction regex.

_OAI_PREFIX = "sk" + "-"
_ANT_PREFIX = "sk" + "-ant-"
_STRIPE_PREFIX = "sk" + "_live_"
_TWILIO_PREFIX = "A" + "C"
_AKIA_PREFIX = "AKI" + "A"


def test_redacts_openai_key():
    fixture = _OAI_PREFIX + "x" * 30
    text = f"before {fixture} after"
    out, n = redact(text)
    assert n == 1
    assert fixture not in out
    assert "[REDACTED:openai-key]" in out


def test_redacts_anthropic_key_separately():
    fixture = _ANT_PREFIX + "x" * 30
    text = f"k={fixture}"
    out, n = redact(text)
    assert n == 1
    assert "[REDACTED:anthropic-key]" in out


def test_redacts_aws_access_key():
    fixture = _AKIA_PREFIX + "ABCDEFGHIJKLMNOP"
    text = f"{fixture} inline"
    out, n = redact(text)
    assert n == 1
    assert fixture not in out


def test_redacts_stripe_live_key():
    fixture = _STRIPE_PREFIX + "x" * 24
    text = f"key={fixture}"
    out, n = redact(text)
    assert n == 1
    assert "[REDACTED:stripe-live-key]" in out


def test_redacts_twilio_account_sid():
    fixture = _TWILIO_PREFIX + "0" * 32
    text = f"{fixture} in config"
    out, n = redact(text)
    assert n == 1
    assert "[REDACTED:twilio-account-sid]" in out


def test_redacts_azure_storage_key():
    fixture = "Account" + "Key=" + "x" * 60 + "=="
    out, n = redact(fixture)
    assert n == 1
    assert "[REDACTED:azure-storage-key]" in out


def test_redacts_gcp_service_account_private_key():
    body = "M" * 30
    text = (
        '{"type":"service_account","private_key":"-----BEGIN PRIVATE KEY-----\\n'
        + body
        + '\\n-----END PRIVATE KEY-----\\n"}'
    )
    out, n = redact(text)
    assert n >= 1
    assert body not in out


def test_redacts_pem_block():
    body = "M" * 30
    text = (
        "lead\n-----BEGIN RSA PRIVATE KEY-----\n"
        + body
        + "\n-----END RSA PRIVATE KEY-----\ntrail"
    )
    out, n = redact(text)
    assert n == 1
    assert body not in out
    assert "[REDACTED:private-key-block]" in out


def test_redacts_bearer_token():
    fixture = "x" * 30
    text = f"Authorization: Bearer {fixture}\nNext line"
    out, n = redact(text)
    assert n == 1
    assert "[REDACTED:bearer-token]" in out
    assert fixture not in out


def test_redacts_assignment_password():
    fixture = "x" * 16
    text = f'config: password="{fixture}"'
    out, n = redact(text)
    assert n == 1
    assert fixture not in out
    assert "[REDACTED:assignment]" in out


def test_redacts_assignment_api_key():
    fixture = "x" * 16
    text = f"api_key={fixture}"
    out, n = redact(text)
    assert n == 1
    assert fixture not in out


def test_does_not_redact_short_assignments_or_prose():
    text = "the password is unset for this user"
    out, n = redact(text)
    assert n == 0
    assert out == text


def test_passes_through_clean_text():
    text = "totally normal spec content with no secrets"
    out, n = redact(text)
    assert n == 0
    assert out == text
