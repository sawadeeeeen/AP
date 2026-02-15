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
    c.executescript("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            category         TEXT    NOT NULL,
            subcategory      TEXT    NOT NULL,
            duration_minutes INTEGER NOT NULL,
            notes            TEXT    NOT NULL DEFAULT '',
            created_at       TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quiz_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            category        TEXT    NOT NULL,
            subcategory     TEXT    NOT NULL,
            total_questions INTEGER NOT NULL,
            correct_answers INTEGER NOT NULL,
            notes           TEXT    NOT NULL DEFAULT '',
            created_at      TEXT    NOT NULL
        );
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
        );
        CREATE TABLE IF NOT EXISTS progress (
            question_id     INTEGER PRIMARY KEY REFERENCES questions(id),
            ease_factor     REAL    NOT NULL DEFAULT 2.5,
            interval_days   INTEGER NOT NULL DEFAULT 0,
            repetitions     INTEGER NOT NULL DEFAULT 0,
            next_review     TEXT    NOT NULL DEFAULT '2000-01-01',
            last_reviewed   TEXT,
            total_attempts  INTEGER NOT NULL DEFAULT 0,
            correct_count   INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


# ── 学習記録 ──────────────────────────────────────────────────────

def add_study_session(category: str, subcategory: str, minutes: int, notes: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO study_sessions (category, subcategory, duration_minutes, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (category, subcategory, minutes, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def add_quiz_result(category: str, subcategory: str, total: int, correct: int, notes: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO quiz_results (category, subcategory, total_questions, correct_answers, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (category, subcategory, total, correct, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_study_stats() -> tuple[dict, dict]:
    """(study_time: {sub: minutes}, quiz_stats: {sub: {total, correct, rate}})"""
    conn = get_db()
    study_time = {}
    for r in conn.execute(
        "SELECT subcategory, SUM(duration_minutes) AS m FROM study_sessions GROUP BY subcategory"
    ):
        study_time[r["subcategory"]] = r["m"]

    quiz_stats = {}
    for r in conn.execute(
        "SELECT subcategory, SUM(total_questions) AS t, SUM(correct_answers) AS c "
        "FROM quiz_results GROUP BY subcategory"
    ):
        t = r["t"]
        quiz_stats[r["subcategory"]] = {
            "total": t,
            "correct": r["c"],
            "rate": round(r["c"] / t * 100, 1) if t > 0 else None,
        }
    conn.close()
    return study_time, quiz_stats


def get_weak_areas(n: int = 5) -> list:
    _, quiz_stats = get_study_stats()
    with_data = [(sub, s) for sub, s in quiz_stats.items() if s["rate"] is not None]
    return sorted(with_data, key=lambda x: x[1]["rate"])[:n]


def get_strong_areas(n: int = 5) -> list:
    _, quiz_stats = get_study_stats()
    with_data = [(sub, s) for sub, s in quiz_stats.items() if s["rate"] is not None]
    return sorted(with_data, key=lambda x: -x[1]["rate"])[:n]


def get_unstudied_areas() -> list:
    study_time, quiz_stats = get_study_stats()
    all_subs = [sub for subs in CATEGORIES.values() for sub in subs]
    return [sub for sub in all_subs if sub not in study_time and sub not in quiz_stats]


def get_recent_sessions(n: int = 5) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM study_sessions ORDER BY created_at DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_quizzes(n: int = 5) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM quiz_results ORDER BY created_at DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_subcategory_parent(sub: str) -> str:
    for parent, subs in CATEGORIES.items():
        if sub in subs:
            return parent
    return "不明"


# ── SRS 問題管理 ──────────────────────────────────────────────────

def upsert_questions(questions: list):
    """問題リストをDBに投入（既存は重複スキップ）"""
    conn = get_db()
    c = conn.cursor()
    inserted = 0
    for q in questions:
        exists = c.execute(
            "SELECT id FROM questions WHERE question = ?", (q["question"],)
        ).fetchone()
        if exists:
            continue
        c.execute(
            "INSERT INTO questions "
            "(category, subcategory, question, option_a, option_b, option_c, option_d, answer, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (q["category"], q["subcategory"], q["question"],
             q["option_a"], q["option_b"], q["option_c"], q["option_d"],
             q["answer"], q["explanation"]),
        )
        qid = c.lastrowid
        c.execute("INSERT OR IGNORE INTO progress (question_id) VALUES (?)", (qid,))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def _sm2_next(ease: float, interval: int, reps: int, correct: bool):
    if correct:
        new_interval = 1 if reps == 0 else (3 if reps == 1 else math.ceil(interval * ease))
        new_ease = min(3.0, ease + 0.1)
        new_reps = reps + 1
    else:
        new_interval = 1
        new_ease = max(1.3, ease - 0.2)
        new_reps = 0
    next_review = (datetime.now() + timedelta(days=new_interval)).strftime("%Y-%m-%d")
    return new_ease, new_interval, new_reps, next_review


def record_answer(question_id: int, correct: bool) -> dict:
    """回答を記録してSRSを更新。結果dictを返す。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM progress WHERE question_id = ?", (question_id,)
    ).fetchone()
    ease, interval, reps = row["ease_factor"], row["interval_days"], row["repetitions"]
    new_ease, new_interval, new_reps, next_review = _sm2_next(ease, interval, reps, correct)

    conn.execute(
        "UPDATE progress SET ease_factor=?, interval_days=?, repetitions=?, next_review=?, "
        "last_reviewed=?, total_attempts=total_attempts+1, correct_count=correct_count+? "
        "WHERE question_id=?",
        (new_ease, new_interval, new_reps, next_review,
         datetime.now().strftime("%Y-%m-%d"),
         1 if correct else 0,
         question_id),
    )

    q = conn.execute(
        "SELECT option_a, option_b, option_c, option_d, answer, explanation "
        "FROM questions WHERE id=?", (question_id,)
    ).fetchone()
    conn.commit()
    conn.close()

    opts = {"A": q["option_a"], "B": q["option_b"], "C": q["option_c"], "D": q["option_d"]}
    return {
        "correct": correct,
        "correct_answer": opts[q["answer"]],
        "explanation": q["explanation"],
        "next_review": next_review,
        "interval_days": new_interval,
    }


def get_next_question(subcategory: str = None) -> dict | None:
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

    row = conn.execute(
        f"SELECT q.*, p.ease_factor, p.interval_days, p.repetitions, "
        f"p.total_attempts, p.correct_count, p.next_review "
        f"FROM questions q JOIN progress p ON q.id = p.question_id "
        f"WHERE p.next_review <= ? AND p.total_attempts > 0 {sub_filter} "
        f"ORDER BY p.next_review ASC LIMIT 1",
        p_due,
    ).fetchone()

    if row is None:
        row = conn.execute(
            f"SELECT q.*, p.ease_factor, p.interval_days, p.repetitions, "
            f"p.total_attempts, p.correct_count, p.next_review "
            f"FROM questions q JOIN progress p ON q.id = p.question_id "
            f"WHERE p.total_attempts = 0 {sub_filter} "
            f"ORDER BY RANDOM() LIMIT 1",
            p_new,
        ).fetchone()

    conn.close()
    return dict(row) if row else None


def get_due_counts() -> dict:
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    due_rows = conn.execute(
        "SELECT q.subcategory, COUNT(*) as cnt FROM questions q "
        "JOIN progress p ON q.id = p.question_id "
        "WHERE p.next_review <= ? AND p.total_attempts > 0 GROUP BY q.subcategory",
        [today],
    ).fetchall()
    new_rows = conn.execute(
        "SELECT q.subcategory, COUNT(*) as cnt FROM questions q "
        "JOIN progress p ON q.id = p.question_id "
        "WHERE p.total_attempts = 0 GROUP BY q.subcategory",
    ).fetchall()
    conn.close()
    return {
        "due": {r["subcategory"]: r["cnt"] for r in due_rows},
        "new": {r["subcategory"]: r["cnt"] for r in new_rows},
    }


def get_srs_stats() -> dict:
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    total_q  = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    studied  = conn.execute("SELECT COUNT(*) FROM progress WHERE total_attempts > 0").fetchone()[0]
    due_today = conn.execute(
        "SELECT COUNT(*) FROM progress WHERE next_review <= ? AND total_attempts > 0", [today]
    ).fetchone()[0]
    new_q = total_q - studied
    rates = {}
    for r in conn.execute(
        "SELECT q.subcategory, SUM(p.total_attempts) as total, SUM(p.correct_count) as correct "
        "FROM questions q JOIN progress p ON q.id = p.question_id "
        "WHERE p.total_attempts > 0 GROUP BY q.subcategory"
    ).fetchall():
        t = r["total"]
        rates[r["subcategory"]] = {
            "total": t, "correct": r["correct"],
            "rate": round(r["correct"] / t * 100, 1) if t > 0 else None,
        }
    conn.close()
    return {
        "total_questions": total_q,
        "studied": studied,
        "new": new_q,
        "due_today": due_today,
        "rates": rates,
    }
