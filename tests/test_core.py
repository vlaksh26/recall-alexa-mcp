"""Run with `python tests/test_core.py` (no dependencies) or `pytest`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import Store, sm2  # noqa: E402


def test_sm2_interval_progression():
    reps, interval, ease = 0, 0, 2.5
    reps, interval, ease = sm2(4, reps, interval, ease)
    assert (reps, interval) == (1, 1)
    reps, interval, ease = sm2(4, reps, interval, ease)
    assert (reps, interval) == (2, 6)
    reps, interval, ease = sm2(4, reps, interval, ease)
    assert reps == 3 and interval == round(6 * 2.5)


def test_sm2_failure_resets_and_ease_has_floor():
    reps, interval, ease = sm2(1, 5, 30, 2.5)
    assert (reps, interval) == (0, 1)
    for _ in range(20):
        reps, interval, ease = sm2(1, reps, interval, ease)
    assert ease == 1.3


def test_new_cards_are_due_immediately_in_order():
    s = Store()
    ids = s.add_cards("bio", [{"front": "Q1", "back": "A1"}, {"front": "Q2", "back": "A2"}])
    assert s.count_due("bio") == 2
    assert s.next_due("bio")[0]["id"] == ids[0]
    assert s.next_due("other") == []


def test_grading_pushes_card_into_the_future():
    s = Store()
    (cid,) = s.add_cards("bio", [{"front": "Q", "back": "A"}])
    result = s.grade(cid, "good")
    assert result["back"] == "A" and result["interval_days"] == 1
    assert s.count_due() == 0          # not due again today
    s.advance_days(1)
    assert s.count_due() == 1          # due tomorrow


def test_again_counts_a_lapse_and_bad_input_is_rejected():
    s = Store()
    (cid,) = s.add_cards("bio", [{"front": "Q", "back": "A"}])
    s.grade(cid, "again")
    assert s.db.execute("SELECT lapses FROM cards").fetchone()[0] == 1
    for bad in (lambda: s.grade(cid, "meh"), lambda: s.grade(999, "good")):
        try:
            bad()
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError("expected an error")


def test_streak_and_stats():
    s = Store()
    (cid,) = s.add_cards("bio", [{"front": "Q", "back": "A"}])
    for _ in range(3):
        s.grade(cid, "good")
        s.advance_days(1)
    st = s.stats()
    assert st["streak_days"] == 3
    assert st["total_cards"] == 1
    assert st["reviewed_today"] == 0   # the clock moved on to a fresh day


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"{len(tests)} passed")
