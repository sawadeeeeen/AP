import sqlite3
import math
from datetime import datetime, timedelta

DB_PATH = "study_tracker.db"

CATEGORIES = {
    "テクノロジ系": [
        "基礎理論", "アルゴリズムとプログラミング", "コンピュータ構成要素",
        "システム構成要素", "ソフトウェア", "ハードウェア", "マルチメディア",
        "データベース", "ネットワーク", "セキュリティ",
        "システム開発技術", "ソフトウェア開発管理技術",
    ],
    "マネジメント系": [
        "プロジェクトマネジメント", "サービスマネジメント", "システム監査",
    ],
    "ストラテジ系": [
        "システム戦略", "システム企画", "経営戦略マネジメント",
        "技術戦略マネジメント", "ビジネスインダストリ", "企業と法務",
    ],
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            question    TEXT NOT NULL,
            option_a    TEXT NOT NULL,
            option_b    TEXT NOT NULL,
            option_c    TEXT NOT NULL,
            option_d    TEXT NOT NULL,
            answer      TEXT NOT NULL,
            explanation TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            question_id     INTEGER PRIMARY KEY REFERENCES questions(id),
            ease_factor     REAL    NOT NULL DEFAULT 2.5,
            interval_days   INTEGER NOT NULL DEFAULT 0,
            repetitions     INTEGER NOT NULL DEFAULT 0,
            next_review     TEXT    NOT NULL DEFAULT '2000-01-01',
            last_reviewed   TEXT,
            total_attempts  INTEGER NOT NULL DEFAULT 0,
            correct_count   INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ── 問題登録 ──────────────────────────────────────────────────────

def upsert_questions(questions: list):
    conn = get_db()
    c = conn.cursor()
    inserted = 0
    for q in questions:
        exists = c.execute(
            "SELECT id FROM questions WHERE question = ?", (q["question"],)
        ).fetchone()
        if exists:
            continue
        c.execute("""
            INSERT INTO questions
                (category, subcategory, question,
                 option_a, option_b, option_c, option_d,
                 answer, explanation)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (q["category"], q["subcategory"], q["question"],
              q["option_a"], q["option_b"], q["option_c"], q["option_d"],
              q["answer"], q["explanation"]))
        qid = c.lastrowid
        c.execute("INSERT OR IGNORE INTO progress (question_id) VALUES (?)", (qid,))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


# ── SRS（SM-2 簡易版） ────────────────────────────────────────────

def _srs_next(ease: float, interval: int, reps: int, correct: bool):
    if correct:
        if reps == 0:
            new_interval = 1
        elif reps == 1:
            new_interval = 3
        else:
            new_interval = math.ceil(interval * ease)
        new_ease = min(3.0, ease + 0.1)
        new_reps = reps + 1
    else:
        new_interval = 1
        new_ease = max(1.3, ease - 0.2)
        new_reps = 0
    next_review = (datetime.now() + timedelta(days=new_interval)).strftime("%Y-%m-%d")
    return new_ease, new_interval, new_reps, next_review


def record_answer(question_id: int, correct: bool) -> int:
    """回答を記録してSRSを更新。次回まで何日かを返す。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM progress WHERE question_id = ?", (question_id,)
    ).fetchone()
    ease     = row["ease_factor"]
    interval = row["interval_days"]
    reps     = row["repetitions"]

    new_ease, new_interval, new_reps, next_review = _srs_next(ease, interval, reps, correct)

    conn.execute("""
        UPDATE progress SET
            ease_factor    = ?,
            interval_days  = ?,
            repetitions    = ?,
            next_review    = ?,
            last_reviewed  = ?,
            total_attempts = total_attempts + 1,
            correct_count  = correct_count + ?
        WHERE question_id = ?
    """, (new_ease, new_interval, new_reps, next_review,
          datetime.now().strftime("%Y-%m-%d"),
          1 if correct else 0,
          question_id))
    conn.commit()
    conn.close()
    return new_interval


# ── 問題選択 ──────────────────────────────────────────────────────

def get_next_question(subcategory: str = None) -> dict:
    """
    優先順位:
      1. 復習期限が来ている問題（期限が古い順）
      2. 未出題の新問題
    """
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    sub_filter = "AND q.subcategory = ?" if subcategory else ""
    p_due = [today, subcategory] if subcategory else [today]
    p_new = [subcategory]        if subcategory else []

    row = conn.execute(f"""
        SELECT q.*, p.ease_factor, p.interval_days, p.repetitions,
               p.total_attempts, p.correct_count, p.next_review
        FROM questions q JOIN progress p ON q.id = p.question_id
        WHERE p.next_review <= ? AND p.total_attempts > 0 {sub_filter}
        ORDER BY p.next_review ASC
        LIMIT 1
    """, p_due).fetchone()

    if row is None:
        row = conn.execute(f"""
            SELECT q.*, p.ease_factor, p.interval_days, p.repetitions,
                   p.total_attempts, p.correct_count, p.next_review
            FROM questions q JOIN progress p ON q.id = p.question_id
            WHERE p.total_attempts = 0 {sub_filter}
            ORDER BY RANDOM()
            LIMIT 1
        """, p_new).fetchone()

    conn.close()
    return dict(row) if row else None


def get_due_counts() -> dict:
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    due, new = {}, {}
    for r in conn.execute("""
        SELECT q.subcategory, COUNT(*) as cnt
        FROM questions q JOIN progress p ON q.id = p.question_id
        WHERE p.next_review <= ? AND p.total_attempts > 0
        GROUP BY q.subcategory
    """, [today]).fetchall():
        due[r["subcategory"]] = r["cnt"]

    for r in conn.execute("""
        SELECT q.subcategory, COUNT(*) as cnt
        FROM questions q JOIN progress p ON q.id = p.question_id
        WHERE p.total_attempts = 0
        GROUP BY q.subcategory
    """).fetchall():
        new[r["subcategory"]] = r["cnt"]

    conn.close()
    return {"due": due, "new": new}


def get_stats() -> dict:
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    total_q  = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    studied  = conn.execute(
        "SELECT COUNT(*) FROM progress WHERE total_attempts > 0"
    ).fetchone()[0]
    due_today = conn.execute(
        "SELECT COUNT(*) FROM progress WHERE next_review <= ? AND total_attempts > 0",
        [today]
    ).fetchone()[0]

    rates = {}
    for r in conn.execute("""
        SELECT q.subcategory,
               SUM(p.total_attempts) as total,
               SUM(p.correct_count)  as correct
        FROM questions q JOIN progress p ON q.id = p.question_id
        WHERE p.total_attempts > 0
        GROUP BY q.subcategory
    """).fetchall():
        t = r["total"]
        rates[r["subcategory"]] = {
            "total": t,
            "correct": r["correct"],
            "rate": round(r["correct"] / t * 100, 1) if t > 0 else None,
        }

    conn.close()
    return {
        "total_questions": total_q,
        "studied": studied,
        "due_today": due_today,
        "rates": rates,
    }


def get_subcategory_parent(sub: str) -> str:
    for parent, subs in CATEGORIES.items():
        if sub in subs:
            return parent
    return "不明"
