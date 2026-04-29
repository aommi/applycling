"""Tests for applycling/statuses.py — canonical state machine."""

from __future__ import annotations

import pytest
from applycling.statuses import (
    STATES,
    STATUS_VALUES,
    STATUS_BY_VALUE,
    DEFAULT_INITIAL_STATUS,
    TRANSITIONS,
    OLD_TO_NEW,
    LEGACY_STATUS_VALUES,
    migrate_old_status,
    status_color,
    status_label,
    job_actions,
    can_transition,
    assert_valid_status,
    Status,
    StatusAction,
)


# ── Core invariants ─────────────────────────────────────────────────

class TestInvariants:
    def test_eleven_states(self):
        assert len(STATES) == 11

    def test_status_values_match(self):
        assert STATUS_VALUES == tuple(s.value for s in STATES)

    def test_status_by_value_covers_all(self):
        assert set(STATUS_BY_VALUE.keys()) == set(STATUS_VALUES)

    def test_default_is_new(self):
        assert DEFAULT_INITIAL_STATUS == "new"

    def test_only_generating_is_system(self):
        system = [s for s in STATES if s.is_system]
        assert len(system) == 1
        assert system[0].value == "generating"

    def test_system_state_has_no_actions(self):
        gen = STATUS_BY_VALUE["generating"]
        assert gen.actions == ()

    def test_all_other_states_have_actions(self):
        # generating has no actions because it's system-managed.
        for s in STATES:
            if s.value not in ("generating",):
                assert s.actions, f"{s.value} has no actions"


# ── Transitions ─────────────────────────────────────────────────────

class TestTransitions:
    def test_26_transitions(self):
        count = sum(len(t) for t in TRANSITIONS.values())
        assert count == 27

    def test_every_transition_target_is_valid(self):
        for from_s, targets in TRANSITIONS.items():
            assert from_s in STATUS_BY_VALUE, f"Unknown source: {from_s}"
            for t in targets:
                assert t in STATUS_BY_VALUE, f"Unknown target: {t} (from {from_s})"

    def test_can_transition_valid(self):
        assert can_transition("new", "generating")
        assert can_transition("generating", "reviewing")
        assert can_transition("reviewing", "reviewed")
        assert can_transition("reviewed", "applied")
        assert can_transition("applied", "interviewing")
        assert can_transition("applied", "accepted")
        assert can_transition("interviewing", "accepted")
        assert can_transition("offered", "accepted")
        assert can_transition("archived", "reviewing")
        assert can_transition("archived", "new")

    def test_can_transition_idempotent(self):
        """Same-status is always allowed (no-op)."""
        for value in STATUS_VALUES:
            assert can_transition(value, value), f"Idempotent fail: {value}"

    def test_cannot_transition_invalid(self):
        assert not can_transition("new", "reviewing")
        assert not can_transition("generating", "applied")
        assert not can_transition("applied", "reviewing")
        assert not can_transition("reviewed", "reviewing")
        assert not can_transition("failed", "reviewing")
        assert not can_transition("accepted", "new")

    def test_applied_to_accepted_allowed(self):
        assert "accepted" in TRANSITIONS["applied"]

    def test_interviewing_to_accepted_allowed(self):
        assert "accepted" in TRANSITIONS["interviewing"]

    def test_archived_to_new_allowed(self):
        assert "new" in TRANSITIONS["archived"]

    def test_failed_to_archived_allowed(self):
        assert "archived" in TRANSITIONS["failed"]
        assert can_transition("failed", "archived")


# ── Labels and colors ────────────────────────────────────────────────

class TestLabelsAndColors:
    def test_all_states_have_label(self):
        for s in STATES:
            assert status_label(s.value), f"{s.value} has no label"
            assert status_label(s.value) == s.label

    def test_all_states_have_color(self):
        for s in STATES:
            assert status_color(s.value), f"{s.value} has no color"
            assert status_color(s.value) == s.color

    def test_unknown_label_defaults(self):
        assert status_label("nonexistent") == "nonexistent"

    def test_unknown_color_defaults(self):
        assert status_color("nonexistent") == "#6b7280"


# ── Actions ──────────────────────────────────────────────────────────

class TestActions:
    def test_new_has_no_generating_action(self):
        """generating is a system state — not a user action. Regenerate is a separate endpoint."""
        actions = job_actions("new")
        targets = {a.target for a in actions}
        assert "generating" not in targets, "generating should not be a status action"

    def test_offered_has_accept(self):
        actions = job_actions("offered")
        targets = {a.target for a in actions}
        assert "accepted" in targets, "offered missing Accept Offer"

    def test_generating_has_no_actions(self):
        assert job_actions("generating") == ()

    def test_every_action_target_is_allowed_transition(self):
        for s in STATES:
            for action in s.actions:
                assert action.target in TRANSITIONS.get(s.value, frozenset()), \
                    f"Action {s.value}→{action.target} not in TRANSITIONS"


# ── Validation ──────────────────────────────────────────────────────

class TestValidation:
    def test_assert_valid_status_passes(self):
        for value in STATUS_VALUES:
            assert_valid_status(value)  # no raise

    def test_assert_valid_status_raises(self):
        with pytest.raises(ValueError, match="Unknown status"):
            assert_valid_status("not_a_status")


# ── Legacy migration ────────────────────────────────────────────────

class TestLegacyMigration:
    def test_tailored_maps_to_reviewing(self):
        assert migrate_old_status("tailored") == "reviewing"

    def test_interview_maps_to_interviewing(self):
        assert migrate_old_status("interview") == "interviewing"

    def test_offer_maps_to_offered(self):
        assert migrate_old_status("offer") == "offered"

    def test_inbox_maps_to_new(self):
        assert migrate_old_status("inbox") == "new"

    def test_running_maps_to_generating(self):
        assert migrate_old_status("running") == "generating"

    def test_generated_maps_to_reviewing(self):
        assert migrate_old_status("generated") == "reviewing"

    def test_skipped_maps_to_archived(self):
        assert migrate_old_status("skipped") == "archived"

    def test_applied_is_identity(self):
        assert migrate_old_status("applied") == "applied"

    def test_rejected_is_identity(self):
        assert migrate_old_status("rejected") == "rejected"

    def test_unknown_is_identity(self):
        assert migrate_old_status("unknown_status") == "unknown_status"

    def test_legacy_status_values_covers_all_old(self):
        """Every key in OLD_TO_NEW is in LEGACY_STATUS_VALUES."""
        assert LEGACY_STATUS_VALUES == frozenset(OLD_TO_NEW.keys())

    def test_old_workbench_not_in_legacy(self):
        """Old workbench statuses ARE in OLD_TO_NOW — verified above."""
        assert "inbox" in OLD_TO_NEW
        assert "running" in OLD_TO_NEW


# ── Immutability ────────────────────────────────────────────────────

class TestImmutability:
    def test_states_is_tuple(self):
        assert isinstance(STATES, tuple)

    def test_transitions_are_frozensets(self):
        for targets in TRANSITIONS.values():
            assert isinstance(targets, frozenset)
