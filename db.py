#!/usr/bin/env python3
"""
AP試験学習トラッカー - SRS（間隔反復）システム
使い方:
  python db.py init                    # DBを初期化して問題を投入
  python db.py next [分野名]            # 次の問題を1問JSON出力
  python db.py answer <id> <1|0>       # 正誤を記録してSRSパラメータ更新
  python db.py due                     # 今日の復習件数を表示
  python db.py stats                   # 分野別正答率を表示
  python db.py categories              # 分野一覧を表示
"""

import json
import math
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from questions import QUESTIONS

DB_PATH = Path(__file__).parent / "ap_study.db"

# ── SM-2 アルゴリズム定数 ─────────────────────────────────────
INITIAL_INTERVAL = 1      # 初回: 翌日
SECOND_INTERVAL  = 6      # 2回目: 6日後
MIN_EASINESS     = 1.3    # EFの最小値


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_init():
    """DBを初期化し全問題を登録する"""
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS questions (
            id          INTEGER PRIMARY KEY,
            category    TEXT NOT NULL,
            question    TEXT NOT NULL,
            choices     TEXT NOT NULL,   -- JSON配列
            answer      INTEGER NOT NULL,
            explanation TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress (
            question_id  INTEGER PRIMARY KEY REFERENCES questions(id),
            repetition   INTEGER NOT NULL DEFAULT 0,
            easiness     REAL    NOT NULL DEFAULT 2.5,
            interval     INTEGER NOT NULL DEFAULT 1,
            next_date    TEXT    NOT NULL,
            correct_total INTEGER NOT NULL DEFAULT 0,
            attempt_total INTEGER NOT NULL DEFAULT 0
        );
    """)

    for q in QUESTIONS:
        cur.execute(
            """INSERT OR REPLACE INTO questions (id, category, question, choices, answer, explanation)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (q["id"], q["category"], q["question"],
             json.dumps(q["choices"], ensure_ascii=False),
             q["answer"], q["explanation"]),
        )
        cur.execute(
            """INSERT OR IGNORE INTO progress (question_id, next_date)
               VALUES (?, ?)""",
            (q["id"], str(date.today())),
        )

    conn.commit()
    conn.close()
    total = len(QUESTIONS)
    cats  = len({q["category"] for q in QUESTIONS})
    print(json.dumps({"status": "ok", "questions": total, "categories": cats}, ensure_ascii=False))


def cmd_next(category: str | None = None):
    """次に学習すべき問題を1問JSONで返す"""
    conn = get_conn()
    cur = conn.cursor()
    today = str(date.today())

    if category:
        row = cur.execute(
            """SELECT q.*, p.next_date, p.repetition
               FROM questions q JOIN progress p ON q.id = p.question_id
               WHERE p.next_date <= ? AND q.category = ?
               ORDER BY p.next_date ASC, p.repetition ASC
               LIMIT 1""",
            (today, category),
        ).fetchone()
    else:
        row = cur.execute(
            """SELECT q.*, p.next_date, p.repetition
               FROM questions q JOIN progress p ON q.id = p.question_id
               WHERE p.next_date <= ?
               ORDER BY p.next_date ASC, p.repetition ASC
               LIMIT 1""",
            (today,),
        ).fetchone()

    conn.close()

    if row is None:
        # 今日の分が終わった場合、最も早い次回日を案内
        conn2 = get_conn()
        nxt = conn2.execute(
            "SELECT MIN(next_date) as nd FROM progress"
        ).fetchone()
        conn2.close()
        print(json.dumps({"status": "done", "next_review": nxt["nd"]}, ensure_ascii=False))
        return

    choices = json.loads(row["choices"])
    out = {
        "status": "ok",
        "id": row["id"],
        "category": row["category"],
        "question": row["question"],
        "choices": {str(i + 1): c for i, c in enumerate(choices)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_answer(question_id: int, correct: int):
    """正誤を記録してSM-2でスケジュールを更新する"""
    conn = get_conn()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT * FROM progress WHERE question_id = ?", (question_id,)
    ).fetchone()

    if row is None:
        print(json.dumps({"status": "error", "message": f"id={question_id} が見つかりません"}, ensure_ascii=False))
        conn.close()
        return

    # SM-2 アルゴリズム
    # quality: 正解=5（簡単）, 不正解=0
    quality = 5 if correct else 0

    repetition = row["repetition"]
    easiness   = row["easiness"]
    interval   = row["interval"]

    if quality >= 3:  # 正解
        if repetition == 0:
            interval = INITIAL_INTERVAL
        elif repetition == 1:
            interval = SECOND_INTERVAL
        else:
            interval = round(interval * easiness)
        repetition += 1
    else:             # 不正解 → リセット
        repetition = 0
        interval   = INITIAL_INTERVAL

    # EF更新
    easiness = max(MIN_EASINESS, easiness + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    next_date     = str(date.today() + timedelta(days=interval))
    correct_total = row["correct_total"] + (1 if correct else 0)
    attempt_total = row["attempt_total"] + 1

    cur.execute(
        """UPDATE progress
           SET repetition=?, easiness=?, interval=?, next_date=?,
               correct_total=?, attempt_total=?
           WHERE question_id=?""",
        (repetition, round(easiness, 4), interval, next_date,
         correct_total, attempt_total, question_id),
    )

    # 解説を返す
    q_row = cur.execute(
        "SELECT explanation, answer, choices FROM questions WHERE id = ?", (question_id,)
    ).fetchone()

    conn.commit()
    conn.close()

    choices = json.loads(q_row["choices"])
    correct_text = choices[q_row["answer"]]

    print(json.dumps({
        "status": "ok",
        "correct": bool(correct),
        "correct_answer": correct_text,
        "explanation": q_row["explanation"],
        "next_review": next_date,
        "interval_days": interval,
    }, ensure_ascii=False, indent=2))


def cmd_due():
    """今日学習すべき問題数を表示する"""
    conn = get_conn()
    today = str(date.today())
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM progress WHERE next_date <= ?", (today,)
    ).fetchone()["cnt"]
    conn.close()
    print(json.dumps({"status": "ok", "due_today": total, "date": today}, ensure_ascii=False))


def cmd_stats():
    """分野別の正答率と進捗を表示する"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT q.category,
                  COUNT(*) as total,
                  SUM(p.attempt_total) as attempts,
                  SUM(p.correct_total) as corrects
           FROM questions q JOIN progress p ON q.id = p.question_id
           GROUP BY q.category
           ORDER BY q.category"""
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        attempts = r["attempts"] or 0
        corrects = r["corrects"] or 0
        rate = round(corrects / attempts * 100, 1) if attempts > 0 else None
        result.append({
            "category": r["category"],
            "questions": r["total"],
            "attempts": attempts,
            "corrects": corrects,
            "accuracy_pct": rate,
        })

    print(json.dumps({"status": "ok", "stats": result}, ensure_ascii=False, indent=2))


def cmd_categories():
    """分野一覧を表示する"""
    cats = sorted({q["category"] for q in QUESTIONS})
    print(json.dumps({"status": "ok", "categories": cats}, ensure_ascii=False, indent=2))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "init":
        cmd_init()
    elif cmd == "next":
        category = args[1] if len(args) > 1 else None
        cmd_next(category)
    elif cmd == "answer":
        if len(args) < 3:
            print("使い方: python db.py answer <id> <1|0>")
            sys.exit(1)
        cmd_answer(int(args[1]), int(args[2]))
    elif cmd == "due":
        cmd_due()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "categories":
        cmd_categories()
    else:
        print(f"不明なコマンド: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
