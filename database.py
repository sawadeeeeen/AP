import sqlite3
from datetime import datetime

DB_PATH = "study_tracker.db"

CATEGORIES = {
    "テクノロジ系": [
        "基礎理論",
        "アルゴリズムとプログラミング",
        "コンピュータ構成要素",
        "システム構成要素",
        "ソフトウェア",
        "ハードウェア",
        "マルチメディア",
        "データベース",
        "ネットワーク",
        "セキュリティ",
        "システム開発技術",
        "ソフトウェア開発管理技術",
    ],
    "マネジメント系": [
        "プロジェクトマネジメント",
        "サービスマネジメント",
        "システム監査",
    ],
    "ストラテジ系": [
        "システム戦略",
        "システム企画",
        "経営戦略マネジメント",
        "技術戦略マネジメント",
        "ビジネスインダストリ",
        "企業と法務",
    ],
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # 学習セッションテーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 問題演習テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            correct_answers INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def add_study_session(category, subcategory, duration_minutes, notes=""):
    conn = get_db()
    conn.execute(
        """INSERT INTO study_sessions (category, subcategory, duration_minutes, notes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (category, subcategory, duration_minutes, notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def add_quiz_result(category, subcategory, total_questions, correct_answers, notes=""):
    conn = get_db()
    conn.execute(
        """INSERT INTO quiz_results (category, subcategory, total_questions, correct_answers, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            category,
            subcategory,
            total_questions,
            correct_answers,
            notes,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_study_stats():
    """各サブカテゴリの学習時間と正答率を集計"""
    conn = get_db()

    study_time = {}
    rows = conn.execute(
        """SELECT subcategory, SUM(duration_minutes) as total
           FROM study_sessions GROUP BY subcategory"""
    ).fetchall()
    for row in rows:
        study_time[row["subcategory"]] = row["total"]

    quiz_stats = {}
    rows = conn.execute(
        """SELECT subcategory,
                  SUM(total_questions) as total,
                  SUM(correct_answers) as correct
           FROM quiz_results GROUP BY subcategory"""
    ).fetchall()
    for row in rows:
        total = row["total"]
        correct = row["correct"]
        quiz_stats[row["subcategory"]] = {
            "total": total,
            "correct": correct,
            "rate": round(correct / total * 100, 1) if total > 0 else None,
        }

    conn.close()
    return study_time, quiz_stats


def get_recent_sessions(limit=10):
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM study_sessions ORDER BY created_at DESC LIMIT ?""", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_quizzes(limit=10):
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM quiz_results ORDER BY created_at DESC LIMIT ?""", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_weak_areas(top_n=5):
    """正答率が低いサブカテゴリを返す（問題数が1問以上のもの）"""
    _, quiz_stats = get_study_stats()
    scored = [
        (sub, s) for sub, s in quiz_stats.items() if s["rate"] is not None
    ]
    scored.sort(key=lambda x: x[1]["rate"])
    return scored[:top_n]


def get_strong_areas(top_n=5):
    """正答率が高いサブカテゴリを返す"""
    _, quiz_stats = get_study_stats()
    scored = [
        (sub, s) for sub, s in quiz_stats.items() if s["rate"] is not None
    ]
    scored.sort(key=lambda x: x[1]["rate"], reverse=True)
    return scored[:top_n]


def get_unstudied_areas():
    """まだ学習していないサブカテゴリを返す"""
    study_time, quiz_stats = get_study_stats()
    all_subs = [sub for subs in CATEGORIES.values() for sub in subs]
    return [s for s in all_subs if s not in study_time and s not in quiz_stats]


def get_subcategory_parent(subcategory):
    for parent, subs in CATEGORIES.items():
        if subcategory in subs:
            return parent
    return "不明"
