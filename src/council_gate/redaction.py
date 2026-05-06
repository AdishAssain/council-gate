"""Secret redaction before dispatch.

The artifact body is sent to external LLM APIs. This module scrubs it first.

The patterns are deliberately conservative — false positives (over-redaction)
are acceptable; false negatives (a leaked secret) are not.
"""
import re
from pathlib import Path

# Filenames that almost certainly contain secrets and should not be reviewed.
REFUSED_NAME_PATTERNS = (
    re.compile(r"(^|/)\.env(\..+)?$"),
    re.compile(r"(^|/)env\.local$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"\.kdbx$"),
    re.compile(r"\.gpg$"),
    re.compile(r"id_rsa(\.pub)?$"),
    re.compile(r"id_ed25519(\.pub)?$"),
    re.compile(r"id_ecdsa(\.pub)?$"),
    re.compile(r"credentials?(\.[a-z]+)?$", re.IGNORECASE),
    re.compile(r"secrets?(\.[a-z]+)?$", re.IGNORECASE),
    re.compile(r"(^|/)\.pgpass$"),
    re.compile(r"(^|/)\.netrc$"),
    re.compile(r"(^|/)\.npmrc$"),
    re.compile(r"(^|/)\.pypirc$"),
    re.compile(r"\.aws/credentials$"),
    re.compile(r"\.aws/config$"),
    re.compile(r"(^|/)kubeconfig$"),
    re.compile(r"\.kube/config$"),
    re.compile(r"(^|/)wallet\.dat$"),
    re.compile(r"\.dockerconfigjson$"),
)

# In-text secret patterns. Each is (regex, redaction_label).
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # OpenAI / Anthropic
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "[REDACTED:anthropic-key]"),
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "[REDACTED:openai-key]"),
    # Stripe
    (re.compile(r"sk_live_[a-zA-Z0-9]{20,}"), "[REDACTED:stripe-live-key]"),
    (re.compile(r"sk_test_[a-zA-Z0-9]{20,}"), "[REDACTED:stripe-test-key]"),
    (re.compile(r"rk_live_[a-zA-Z0-9]{20,}"), "[REDACTED:stripe-restricted-key]"),
    # AWS
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws-access-key]"),
    (re.compile(r"ASIA[0-9A-Z]{16}"), "[REDACTED:aws-temp-access-key]"),
    # Slack
    (re.compile(r"xox[baprs]-[a-zA-Z0-9-]{10,}"), "[REDACTED:slack-token]"),
    # GitHub
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED:github-token]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36}"), "[REDACTED:github-oauth]"),
    (re.compile(r"ghu_[a-zA-Z0-9]{36}"), "[REDACTED:github-user-token]"),
    (re.compile(r"ghs_[a-zA-Z0-9]{36}"), "[REDACTED:github-server-token]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "[REDACTED:github-pat]"),
    # GitLab
    (re.compile(r"glpat-[a-zA-Z0-9_-]{20}"), "[REDACTED:gitlab-token]"),
    # Google
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "[REDACTED:google-api-key]"),
    # Twilio
    (re.compile(r"AC[0-9a-fA-F]{32}"), "[REDACTED:twilio-account-sid]"),
    (re.compile(r"SK[0-9a-fA-F]{32}"), "[REDACTED:twilio-api-key]"),
    # Azure storage (DefaultEndpointsProtocol=https;AccountName=…;AccountKey=…)
    (
        re.compile(r"AccountKey=[a-zA-Z0-9+/=]{40,}", re.IGNORECASE),
        "[REDACTED:azure-storage-key]",
    ),
    # GCP service-account JSON private_key field
    (
        re.compile(
            r'"private_key"\s*:\s*"-----BEGIN[^"]+-----END[^"]+-----[\\n]*"',
            re.DOTALL,
        ),
        '"private_key":"[REDACTED:gcp-service-account-key]"',
    ),
    # JWT (three base64url chunks)
    (
        re.compile(
            r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}"
        ),
        "[REDACTED:jwt]",
    ),
    # PEM private-key blocks
    (
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED:private-key-block]",
    ),
    # Generic Bearer tokens in headers (length-bounded; avoids redacting prose)
    (
        re.compile(r"[Bb]earer\s+[a-zA-Z0-9_\-\.=]{20,}"),
        "[REDACTED:bearer-token]",
    ),
    # Generic password / api_key / secret assignments. Redacts the VALUE only.
    # Conservative: requires an explicit assignment operator + quoted/unquoted
    # value of at least 8 chars; won't match prose like "password is unset".
    (
        re.compile(
            r"((?i:password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*)"
            r"(['\"]?)([a-zA-Z0-9_\-\.+/=]{8,})(\2)"
        ),
        r"\1\2[REDACTED:assignment]\2",
    ),
)


class RefusedFilename(ValueError):
    pass


def check_filename(path: Path) -> None:
    name = str(path)
    for pat in REFUSED_NAME_PATTERNS:
        if pat.search(name):
            raise RefusedFilename(
                f"refusing to review {path}: filename matches secret-bearing pattern. "
                f"council-gate sends artifact bodies to external LLM APIs; pass a "
                f"non-secret file or use --skip-redaction-check to override."
            )


def redact(text: str) -> tuple[str, int]:
    """Returns (redacted_text, redaction_count)."""
    count = 0
    for pat, label in SECRET_PATTERNS:
        text, n = pat.subn(label, text)
        count += n
    return text, count
