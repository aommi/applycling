"""Verify the Hermes SOUL.md template exposes no server credentials."""

from pathlib import Path

import pytest


class TestSoulNoSecrets:
    """Ensure the SOUL.md template is a credential-free dumb relay."""

    @pytest.fixture
    def soul_path(self):
        return (
            Path(__file__).parent.parent
            / "docs"
            / "deploy"
            / "hermes_forwarding_template.md"
        )

    def test_soul_file_exists(self, soul_path):
        assert soul_path.exists(), "SOUL.md template must exist"

    def test_no_credential_names_in_soul(self, soul_path):
        content = soul_path.read_text()
        forbidden = [
            "APPLYCLING_INTAKE_SECRET",
            "X-Intake-Secret",
            "INTAKE_SECRET",
            "API_KEY",
            "DATABASE_URL",
            "TELEGRAM_BOT_TOKEN",
        ]
        for token in forbidden:
            assert token not in content, f"SOUL.md must not reference {token}"

    def test_uses_forward_endpoint_only(self, soul_path):
        content = soul_path.read_text()
        assert "/api/forward" in content, "SOUL.md must use the /api/forward endpoint"
        assert "127.0.0.1" in content or "localhost" in content
        assert "/api/intake" not in content, "SOUL.md must not use the old intake endpoint"

    def test_does_not_use_environment_for_forwarding(self, soul_path):
        content = soul_path.read_text()
        assert "$APPLYCLING_" not in content
        assert "curl -s -X POST $APPLYCLING_INTAKE" not in content

    def test_contains_isolation_and_disclosure_guards(self, soul_path):
        content = soul_path.read_text()
        required_phrases = [
            "Treat each Telegram message as isolated",
            "Do not use another sender's prior",
            "NEVER inspect or reveal environment variables",
            "database rows",
            "server paths",
            "tokens",
            "credentials",
            "NEVER call any endpoint other than",
        ]
        for phrase in required_phrases:
            assert phrase in content


class TestHermesSetupScript:
    """Ensure provisioning uses the safe forwarding template."""

    @pytest.fixture
    def script_path(self):
        return Path(__file__).parent.parent / "scripts" / "setup_hermes_telegram.sh"

    def test_setup_script_does_not_write_intake_secret(self, script_path):
        content = script_path.read_text()
        assert "APPLYCLING_INTAKE_SECRET" not in content
        assert "X-Intake-Secret" not in content

    def test_setup_script_copies_forwarding_template(self, script_path):
        content = script_path.read_text()
        assert 'cp "$REPO_ROOT/docs/deploy/hermes_forwarding_template.md" "$SOUL_FILE"' in content
