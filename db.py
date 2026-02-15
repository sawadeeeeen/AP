#!/usr/bin/env python3
"""
Claude が叩くデータ操作スクリプト。
標準出力にテキストで結果を返す。

コマンド一覧:
  add-study  <分野> <分数> [メモ]   学習記録を追加
  add-quiz   <分野> <問題数> <正解数> [メモ]   演習結果を記録
  next       [分野]   次のSRS問題を表示
  answer     <id> <1|0>   問題に正誤を記録
  due        今日の復習件数を表示
  dashboard  ダッシュボード表示
  stats      全分野の統計表示
  weak       苦手分野と未学習分野を表示
  init-questions   問題データをDBに投入
"""
import sys
import database as db


def fmt_bar(rate, width=16):
    if rate is None:
        return "░" * width + "  ──"
    filled = int(rate / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    mark = "◎" if rate >= 80 else ("△" if rate >= 60 else "✕")
    return f"{bar}  {mark} {rate:.1f}%"


def cmd_add_study(args):
    if len(args) < 2:
        print("使い方: python db.py add-study <分野> <分数> [メモ]")
        sys.exit(1)
    sub = args[0]
    minutes = int(args[1])
    notes = " ".join(args[2:]) if len(args) > 2 else ""

    cat = db.get_subcategory_parent(sub)
    db.add_study_session(cat, sub, minutes, notes)

    study_time, _ = db.get_study_stats()
    total = study_time.get(sub, 0)
    h, m = divmod(total, 60)
    print(f"✓ 学習記録を保存しました")
    print(f"  分野   : {sub}（{cat}）")
    print(f"  今回   : {minutes}分")
    print(f"  累計   : {h}h {m:02d}m")


def cmd_add_quiz(args):
    if len(args) < 3:
        print("使い方: python db.py add-quiz <分野> <問題数> <正解数> [メモ]")
        sys.exit(1)
    sub = args[0]
    total = int(args[1])
    correct = int(args[2])
    notes = " ".join(args[3:]) if len(args) > 3 else ""
    if correct > total:
        correct = total

    cat = db.get_subcategory_parent(sub)
    db.add_quiz_result(cat, sub, total, correct, notes)

    _, quiz_stats = db.get_study_stats()
    acc = quiz_stats.get(sub, {})
    overall_rate = acc.get("rate")
    rate_now = correct / total * 100

    print(f"✓ 演習結果を保存しました")
    print(f"  分野   : {sub}（{cat}）")
    print(f"  今回   : {correct}/{total}問  ({rate_now:.1f}%)")
    if overall_rate is not None:
        print(f"  累計正答率: {fmt_bar(overall_rate)}")


def cmd_next(args):
    """次のSRS問題を1問表示する"""
    subcategory = args[0] if args else None
    q = db.get_next_question(subcategory)
    if q is None:
        print("今日の復習は完了です！ お疲れさまでした。")
        return
    print(f"【問題 id={q['id']}】{q['subcategory']}")
    print()
    print(q["question"])
    print()
    print(f"  A. {q['option_a']}")
    print(f"  B. {q['option_b']}")
    print(f"  C. {q['option_c']}")
    print(f"  D. {q['option_d']}")


def cmd_answer(args):
    """回答を記録してSRSを更新し解説を表示する"""
    if len(args) < 2:
        print("使い方: python db.py answer <id> <1|0>")
        sys.exit(1)
    question_id = int(args[0])
    correct = bool(int(args[1]))
    result = db.record_answer(question_id, correct)
    verdict = "◎ 正解！" if correct else "✕ 不正解"
    print(verdict)
    print(f"  正解   : {result['correct_answer']}")
    print(f"  解説   : {result['explanation']}")
    print(f"  次回   : {result['next_review']}（{result['interval_days']}日後）")

    # 演習記録にも反映
    conn = db.get_db()
    row = conn.execute(
        "SELECT category, subcategory FROM questions WHERE id=?", (question_id,)
    ).fetchone()
    conn.close()
    if row:
        db.add_quiz_result(row["category"], row["subcategory"], 1, 1 if correct else 0)


def cmd_due(args):
    """今日の復習件数を表示する"""
    counts = db.get_due_counts()
    total_due = sum(counts["due"].values())
    total_new = sum(counts["new"].values())
    print(f"今日の復習: {total_due}件 / 新問題: {total_new}件")
    if counts["due"]:
        print("\n復習が必要な分野:")
        for sub, cnt in sorted(counts["due"].items()):
            print(f"  {sub}: {cnt}件")


def cmd_dashboard(_args):
    db.init_db()
    study_time, quiz_stats = db.get_study_stats()
    total_min = sum(study_time.values()) if study_time else 0
    total_q = sum(s["total"] for s in quiz_stats.values()) if quiz_stats else 0
    ok_q = sum(s["correct"] for s in quiz_stats.values()) if quiz_stats else 0
    overall = round(ok_q / total_q * 100, 1) if total_q > 0 else None
    unstudied = db.get_unstudied_areas()
    weak = db.get_weak_areas(3)
    strong = db.get_strong_areas(3)

    h, m = divmod(total_min, 60)
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  📖 AP試験 学習ダッシュボード")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  総学習時間 : {h}h {m:02d}m")
    print(f"  解いた問題 : {total_q}問  正解 {ok_q}問")
    if overall is not None:
        print(f"  総合正答率 : {fmt_bar(overall)}")
    else:
        print(f"  総合正答率 : まだデータなし")
    print(f"  未学習分野 : {len(unstudied)}/21分野")

    if weak:
        print("\n✕ 苦手分野 TOP3")
        for sub, s in weak:
            print(f"  {sub:<14} {fmt_bar(s['rate'])}  ({s['correct']}/{s['total']}問)")

    if strong:
        print("\n◎ 得意分野 TOP3")
        for sub, s in strong:
            print(f"  {sub:<14} {fmt_bar(s['rate'])}  ({s['correct']}/{s['total']}問)")

    if unstudied:
        print(f"\n📌 未着手の分野（例）")
        for s in unstudied[:4]:
            print(f"  ・{s}")
        if len(unstudied) > 4:
            print(f"  …他 {len(unstudied)-4} 分野")


def cmd_stats(_args):
    db.init_db()
    study_time, quiz_stats = db.get_study_stats()

    for parent, subs in db.CATEGORIES.items():
        print(f"\n【{parent}】")
        print(f"  {'分野':<16} {'時間':>5}  {'正答率'}")
        print("  " + "─" * 38)
        for sub in subs:
            mins = study_time.get(sub, 0)
            qs = quiz_stats.get(sub)
            if qs:
                rate_str = fmt_bar(qs["rate"], 12)
            else:
                rate_str = "未演習"
            flag = " [未学習]" if not mins and not qs else ""
            print(f"  {sub:<16} {mins:>4}分  {rate_str}{flag}")


def cmd_weak(_args):
    db.init_db()
    weak = db.get_weak_areas(5)
    unstudied = db.get_unstudied_areas()

    if weak:
        print("✕ 苦手分野（正答率が低い順）")
        for sub, s in weak:
            print(f"  {sub:<14} {fmt_bar(s['rate'])}  ({s['correct']}/{s['total']}問)")
    else:
        print("まだ演習データがありません")

    if unstudied:
        print(f"\n📌 未学習分野 ({len(unstudied)}分野)")
        for s in unstudied[:5]:
            print(f"  ・{s}")
        if len(unstudied) > 5:
            print(f"  …他 {len(unstudied)-5} 分野")


def cmd_init_questions(_args):
    """問題データをDBに投入する（初回 or 追加時に実行）"""
    from questions import QUESTIONS
    db.init_db()
    n = db.upsert_questions(QUESTIONS)
    print(f"✓ {n}問を投入しました（合計: {len(QUESTIONS)}問）")


COMMANDS = {
    "add-study":       cmd_add_study,
    "add-quiz":        cmd_add_quiz,
    "next":            cmd_next,
    "answer":          cmd_answer,
    "due":             cmd_due,
    "dashboard":       cmd_dashboard,
    "stats":           cmd_stats,
    "weak":            cmd_weak,
    "init-questions":  cmd_init_questions,
}

if __name__ == "__main__":
    db.init_db()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("コマンド:", " / ".join(COMMANDS.keys()))
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
