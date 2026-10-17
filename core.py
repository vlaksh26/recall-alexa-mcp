"""Recall core: SM-2 spaced-repetition scheduling + SQLite storage.

No MCP imports here on purpose: this is the part that must be correct, so it
is plain Python that can be unit-tested without a server.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta

# Anki-style ratings are easier for a voice agent to choose than SM-2's 0-5.
RATINGS = {"again": 1, "hard": 3, "good": 4, "easy": 5}

MASTERED_INTERVAL_DAYS = 21


def sm2(quality: int, repetitions: int, interval: int, ease: float):
    """One SM-2 step. Returns (repetitions, interval_days, ease)."""
    if quality < 3:
        repetitions, interval = 0, 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * ease)
        repetitions += 1
    ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return repetitions, interval, ease


def score_explanation(explanation: str, key_points: list[dict]):
    """Check which key points a spoken explanation covered.

    Each key point is {"point": "...", "keywords": ["...", ...]}. A point counts
    as covered if ANY of its keywords appears at the start of a word in the
    explanation, so the keyword "photosynthes" matches "photosynthesis".
    Returns (covered_points, missed_points, ratio).
    """
    text = re.sub(r"[^a-z0-9\s]", " ", explanation.lower())
    covered, missed = [], []
    for kp in key_points:
        hit = any(
            re.search(r"\b" + re.escape(kw.lower().strip()), text)
            for kw in kp.get("keywords", [])
            if kw.strip()
        )
        (covered if hit else missed).append(kp["point"])
    ratio = len(covered) / len(key_points) if key_points else 0.0
    return covered, missed, ratio


def rating_for(ratio: float) -> str:
    """Turn explanation coverage into a review rating."""
    if ratio >= 0.85:
        return "good"
    if ratio >= 0.5:
        return "hard"
    return "again"


SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  deck          TEXT    NOT NULL,
  front         TEXT    NOT NULL,
  back          TEXT    NOT NULL,
  repetitions   INTEGER NOT NULL DEFAULT 0,
  interval_days INTEGER NOT NULL DEFAULT 0,
  ease          REAL    NOT NULL DEFAULT 2.5,
  due           TEXT    NOT NULL,
  lapses        INTEGER NOT NULL DEFAULT 0,
  points        TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL REFERENCES cards(id),
  day     TEXT    NOT NULL,
  rating  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(cards)")]
        if "points" not in cols:  # older recall.db files
            self.db.execute("ALTER TABLE cards ADD COLUMN points TEXT")
            self.db.commit()

    # ---- clock (the offset lets you demo a whole week in seconds) ----------
    def _offset(self) -> int:
        row = self.db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()
        return int(row["value"]) if row else 0

    def today(self) -> date:
        return date.today() + timedelta(days=self._offset())

    def advance_days(self, n: int) -> str:
        self.db.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('offset', ?)",
            (str(self._offset() + n),),
        )
        self.db.commit()
        return self.today().isoformat()

    # ---- cards --------------------------------------------------------------
    def add_cards(self, deck: str, cards: list[dict]) -> list[int]:
        ids = []
        for c in cards:
            cur = self.db.execute(
                "INSERT INTO cards(deck, front, back, due) VALUES(?,?,?,?)",
                (deck, c["front"].strip(), c["back"].strip(), self.today().isoformat()),
            )
            ids.append(cur.lastrowid)
        self.db.commit()
        return ids

    def _due_where(self, deck: str | None):
        sql, args = "due <= ?", [self.today().isoformat()]
        if deck:
            sql += " AND deck = ?"
            args.append(deck)
        return sql, args

    def next_due(self, deck: str | None = None, limit: int = 1) -> list[dict]:
        where, args = self._due_where(deck)
        rows = self.db.execute(
            f"SELECT * FROM cards WHERE {where} ORDER BY due, id LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_due(self, deck: str | None = None) -> int:
        where, args = self._due_where(deck)
        return self.db.execute(
            f"SELECT COUNT(*) FROM cards WHERE {where}", args
        ).fetchone()[0]

    def grade(self, card_id: int, rating: str) -> dict:
        if rating not in RATINGS:
            raise ValueError(f"rating must be one of {sorted(RATINGS)}")
        card = self.db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if card is None:
            raise KeyError(f"no card with id {card_id}")
        quality = RATINGS[rating]
        reps, interval, ease = sm2(
            quality, card["repetitions"], card["interval_days"], card["ease"]
        )
        due = self.today() + timedelta(days=interval)
        lapses = card["lapses"] + (1 if quality < 3 else 0)
        self.db.execute(
            "UPDATE cards SET repetitions=?, interval_days=?, ease=?, due=?, lapses=? "
            "WHERE id=?",
            (reps, interval, ease, due.isoformat(), lapses, card_id),
        )
        self.db.execute(
            "INSERT INTO reviews(card_id, day, rating) VALUES(?,?,?)",
            (card_id, self.today().isoformat(), rating),
        )
        self.db.commit()
        return {
            "card_id": card_id,
            "back": card["back"],
            "rating": rating,
            "interval_days": interval,
            "ease": round(ease, 2),
            "due": due.isoformat(),
        }

    # ---- teach-back ---------------------------------------------------------
    def add_concept(self, deck: str, title: str, key_points: list[dict]) -> int:
        """Add a concept the user must explain in their own words."""
        cleaned = [
            {"point": kp["point"].strip(), "keywords": [k.strip() for k in kp["keywords"] if k.strip()]}
            for kp in key_points
            if kp.get("point", "").strip() and kp.get("keywords")
        ]
        if not cleaned:
            raise ValueError("give at least one key point with some keywords")
        cur = self.db.execute(
            "INSERT INTO cards(deck, front, back, due, points) VALUES(?,?,?,?,?)",
            (
                deck,
                f"Explain {title.strip()} in your own words.",
                "; ".join(kp["point"] for kp in cleaned),
                self.today().isoformat(),
                json.dumps(cleaned),
            ),
        )
        self.db.commit()
        return cur.lastrowid

    def teach_back(self, card_id: int, explanation: str) -> dict:
        """Score a spoken explanation against the card's key points, then reschedule."""
        row = self.db.execute("SELECT points FROM cards WHERE id=?", (card_id,)).fetchone()
        if row is None:
            raise KeyError(f"no card with id {card_id}")
        if not row["points"]:
            raise ValueError("this card has no key points; use grade_answer instead")
        covered, missed, ratio = score_explanation(explanation, json.loads(row["points"]))
        graded = self.grade(card_id, rating_for(ratio))
        return {
            "covered": covered,
            "missed": missed,
            "coverage": round(ratio, 2),
            **{k: graded[k] for k in ("rating", "interval_days", "due")},
        }

    # ---- progress -----------------------------------------------------------
    def stats(self, deck: str | None = None) -> dict:
        deck_sql = " AND c.deck = ?" if deck else ""
        deck_args = [deck] if deck else []
        today = self.today()

        total = self.db.execute(
            f"SELECT COUNT(*) FROM cards c WHERE 1=1{deck_sql}", deck_args
        ).fetchone()[0]
        mastered = self.db.execute(
            f"SELECT COUNT(*) FROM cards c WHERE interval_days >= ?{deck_sql}",
            [MASTERED_INTERVAL_DAYS, *deck_args],
        ).fetchone()[0]
        reviewed_today = self.db.execute(
            "SELECT COUNT(*) FROM reviews r JOIN cards c ON c.id = r.card_id "
            f"WHERE r.day = ?{deck_sql}",
            [today.isoformat(), *deck_args],
        ).fetchone()[0]
        days = {
            r[0]
            for r in self.db.execute(
                "SELECT DISTINCT r.day FROM reviews r JOIN cards c ON c.id = r.card_id "
                f"WHERE 1=1{deck_sql}",
                deck_args,
            )
        }
        # Streak: consecutive days with a review, ending today (or yesterday).
        d = today if today.isoformat() in days else today - timedelta(days=1)
        streak = 0
        while d.isoformat() in days:
            streak += 1
            d -= timedelta(days=1)

        return {
            "total_cards": total,
            "due_today": self.count_due(deck),
            "reviewed_today": reviewed_today,
            "mastered": mastered,
            "streak_days": streak,
        }
