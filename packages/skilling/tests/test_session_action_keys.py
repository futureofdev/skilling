"""Wire namespaces preserve distinct event IDs while refusing same-event rebinding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from skilling.delivery import roll_forward
from skilling.session import (
    ActionOperation,
    AdvanceOutcome,
    LegacyOutcomeUnavailable,
    SessionRefusal,
    TrustedAction,
    load_course,
)
from skilling.store import FileProgressStore, RecoveryRequired

from .test_session_actions import service
from .test_transition_recovery import bytes_at
from .test_version_roll_forward import patch_bump

EVENT = "different-logical-event"
HASHED_EVENT = hashlib.sha256(EVENT.encode()).hexdigest()


def receipts(state: Path) -> dict[Path, dict]:
    return {
        path: yaml.safe_load(path.read_bytes())
        for path in (state / "clean-course/transition-receipts").glob("*.yaml")
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_distinct_v1_raw_and_hash_shaped_event_ids_remain_compatible(
    clean_dir: Path, tmp_path: Path, reverse: bool
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    keys = [EVENT, HASHED_EVENT]
    if reverse:
        keys.reverse()
    for key in keys:
        assert not session.advance("next", event_id=key).replayed
    assert session.snapshot().beat.name == "concept"
    before = bytes_at(state)
    for key in keys:
        replay = session.advance("next", event_id=key)
        assert replay.replayed and isinstance(replay.original_outcome, LegacyOutcomeUnavailable)
    assert bytes_at(state) == before
    assert len(receipts(state)) == 2


def mixed_claims(course: Path, state: Path, trusted_first: bool):
    session = service(course, state)
    if not trusted_first:
        session.advance("next", event_id=HASHED_EVENT)
    action = TrustedAction.create(
        session.snapshot(), event_id=EVENT, operation=ActionOperation.ADVANCE, payload="next"
    )
    accepted = session.act(action)
    if trusted_first:
        session.advance("next", event_id=HASHED_EVENT)
    assert isinstance(accepted.original_outcome, AdvanceOutcome)
    return session, action, accepted.original_outcome


@pytest.mark.parametrize("trusted_first", [False, True])
@pytest.mark.parametrize("legacy_form", ["receipt", "reservation", "scratch"])
def test_distinct_v1_raw_hash_and_v2_hashed_identity_keep_separate_slots(
    clean_dir: Path, tmp_path: Path, trusted_first: bool, legacy_form: str
) -> None:
    state = tmp_path / "state"
    session, action, original = mixed_claims(clean_dir, state, trusted_first)
    found = receipts(state)
    assert len(found) == 2 and {value["version"] for value in found.values()} == {1, 2}
    legacy_path, legacy = next((p, v) for p, v in found.items() if v["version"] == 1)
    producer_path, producer = next((p, v) for p, v in found.items() if v["version"] == 2)
    assert legacy["identity"]["key"] == producer["identity"]["key"] == HASHED_EVENT
    # Existing v1 filename preimage is unchanged; v2 must occupy a distinct physical slot.
    identity = legacy["identity"]
    preimage = [identity[field] for field in ("learner_id", "course_id", "course_version", "key")]
    assert (
        legacy_path.name
        == hashlib.sha256(json.dumps(preimage, ensure_ascii=True).encode()).hexdigest() + ".yaml"
    )
    producer_bytes = producer_path.read_bytes()
    if legacy_form == "reservation":
        legacy_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "kind": "reserved",
                    **{
                        field: identity[field]
                        for field in ("learner_id", "course_id", "course_version", "key")
                    },
                }
            )
        )
    elif legacy_form == "scratch":
        legacy_path.unlink()
        scratch = state / "clean-course/scratch.yaml"
        data = yaml.safe_load(scratch.read_bytes())
        data["last_key"] = HASHED_EVENT
        scratch.write_text(yaml.safe_dump(data))
    before = bytes_at(state)
    replay = session.act(action)
    assert replay.replayed and replay.original_outcome == original
    assert producer_path.read_bytes() == producer_bytes and bytes_at(state) == before
    if legacy_form == "receipt":
        assert session.advance("next", event_id=HASHED_EVENT).replayed
    else:
        with pytest.raises(SessionRefusal) as error:
            session.advance("next", event_id=HASHED_EVENT)
        assert error.value.code == "idempotency-key-conflict"
    assert bytes_at(state) == before


@pytest.mark.parametrize("trusted_first", [False, True])
def test_upgrade_retains_both_wire_reservations_for_equal_stored_key_fields(
    clean_dir: Path, tmp_path: Path, trusted_first: bool
) -> None:
    state = tmp_path / "state"
    session, _, _ = mixed_claims(clean_dir, state, trusted_first)
    originals = {path: path.read_bytes() for path in receipts(state)}
    patch_bump(clean_dir)
    updated = load_course(clean_dir)
    upgrade = roll_forward(FileProgressStore(state), updated, "local")
    assert upgrade.plan is not None and upgrade.plan.ok
    current = [v for v in receipts(state).values() if v.get("course_version") == updated.version]
    assert {(v["version"], v["key"], v["kind"]) for v in current} == {
        (1, HASHED_EVENT, "reserved"),
        (2, HASHED_EVENT, "reserved"),
    }
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    session = service(clean_dir, state)
    before = bytes_at(state)
    with pytest.raises(SessionRefusal) as error:
        session.advance("next", event_id=HASHED_EVENT)
    assert error.value.code == "idempotency-key-conflict"
    with pytest.raises(SessionRefusal) as error:
        session.act(
            TrustedAction.create(
                session.snapshot(),
                event_id=EVENT,
                operation=ActionOperation.ADVANCE,
                payload="next",
            )
        )
    assert error.value.code == "idempotency-key-conflict"
    assert bytes_at(state) == before


@pytest.mark.parametrize("trusted_first", [False, True])
def test_same_logical_event_remains_refused_across_wire_namespaces(
    clean_dir: Path, tmp_path: Path, trusted_first: bool
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    if trusted_first:
        session.act(
            TrustedAction.create(
                session.snapshot(),
                event_id=EVENT,
                operation=ActionOperation.ADVANCE,
                payload="next",
            )
        )
    else:
        session.advance("next", event_id=EVENT)
    before = bytes_at(state)
    with pytest.raises(SessionRefusal) as error:
        if trusted_first:
            session.advance("next", event_id=EVENT)
        else:
            session.act(
                TrustedAction.create(
                    session.snapshot(),
                    event_id=EVENT,
                    operation=ActionOperation.ADVANCE,
                    payload="next",
                )
            )
    assert error.value.code == "idempotency-key-conflict"
    assert bytes_at(state) == before


def test_wrong_wire_type_in_v2_slot_refuses_without_effects(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    session, action, _ = mixed_claims(clean_dir, state, True)
    found = receipts(state)
    legacy = next(v for v in found.values() if v["version"] == 1)
    producer = next(p for p, v in found.items() if v["version"] == 2)
    producer.write_text(yaml.safe_dump(legacy))
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired, match="wire namespace mismatch"):
        session.act(action)
    assert bytes_at(state) == before
