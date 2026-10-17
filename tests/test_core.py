"""Run with `python tests/test_core.py` (no dependencies) or `pytest`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import Store, rating_for, score_explanation, sm2  # noqa: E402


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


PHOTO = [
    {"point": "plants use sunlight", "keywords": ["sunlight", "light"]},
    {"point": "chlorophyll captures the light", "keywords": ["chlorophyll"]},
    {"point": "carbon dioxide and water go in", "keywords": ["carbon dioxide", "co2"]},
    {"point": "glucose and oxygen come out", "keywords": ["glucose", "sugar"]},
]


def test_score_explanation_matches_keywords_and_prefixes():
    covered, missed, ratio = score_explanation(
        "Plants take in Sunlight and CO2, and chlorophyll helps.", PHOTO
    )
    assert len(covered) == 3 and missed == ["glucose and oxygen come out"]
    assert ratio == 0.75
    # prefix matching: the keyword "photosynthes" matches "photosynthesis"
    c, _, _ = score_explanation(
        "photosynthesis", [{"point": "p", "keywords": ["photosynthes"]}]
    )
    assert c == ["p"]
    # a keyword must start a word, so "light" does not match "delightful"
    c, _, _ = score_explanation("delightful", [{"point": "p", "keywords": ["light"]}])
    assert c == []


def test_rating_for_thresholds():
    assert rating_for(1.0) == "good"
    assert rating_for(0.85) == "good"
    assert rating_for(0.6) == "hard"
    assert rating_for(0.49) == "again"


def test_teach_back_scores_and_reschedules():
    s = Store()
    cid = s.add_concept("bio", "photosynthesis", PHOTO)
    assert s.next_due("bio")[0]["front"] == "Explain photosynthesis in your own words."
    r = s.teach_back(cid, "Sunlight, chlorophyll, carbon dioxide and glucose are involved")
    assert r["coverage"] == 1.0 and r["rating"] == "good" and r["missed"] == []
    assert s.count_due() == 0            # rescheduled into the future
    s.advance_days(1)
    r = s.teach_back(cid, "I have no idea")
    assert r["rating"] == "again" and len(r["missed"]) == 4


def test_teach_back_errors():
    s = Store()
    (plain,) = s.add_cards("bio", [{"front": "Q", "back": "A"}])
    for bad in (
        lambda: s.teach_back(plain, "anything"),                  # no key points
        lambda: s.teach_back(999, "anything"),                    # no such card
        lambda: s.add_concept("bio", "x", [{"point": "p", "keywords": []}]),
    ):
        try:
            bad()
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError("expected an error")


def test_old_database_gets_the_points_column():
    import sqlite3
    import tempfile

    path = os.path.join(tempfile.mkdtemp(), "old.db")
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY AUTOINCREMENT, deck TEXT NOT NULL,"
        " front TEXT NOT NULL, back TEXT NOT NULL, repetitions INTEGER NOT NULL DEFAULT 0,"
        " interval_days INTEGER NOT NULL DEFAULT 0, ease REAL NOT NULL DEFAULT 2.5,"
        " due TEXT NOT NULL, lapses INTEGER NOT NULL DEFAULT 0);"
    )
    old.commit()
    old.close()
    s = Store(path)  # must upgrade the old table without losing it
    assert s.add_concept("bio", "x", [{"point": "p", "keywords": ["k"]}]) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"{len(tests)} passed")
