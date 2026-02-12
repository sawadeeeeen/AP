#!/usr/bin/env python3
"""AP試験 学習トラッカー CLI"""
import sys
import os
import textwrap
from database import (
    init_db, add_study_session, add_quiz_result,
    get_study_stats, get_weak_areas, get_strong_areas,
    get_unstudied_areas, get_recent_sessions, get_recent_quizzes,
    CATEGORIES,
)

# ── ターミナル表示ユーティリティ ──────────────────────────────────

def clr():
    os.system("clear" if os.name == "posix" else "cls")

def hr(char="─", width=44):
    print(char * width)

def title(text):
    hr("═")
    print(f"  {text}")
    hr("═")

def section(text):
    print(f"\n── {text} {'─'*(40-len(text)-4)}")

def bar(rate, width=20):
    """ASCII進捗バー"""
    if rate is None:
        return "[" + "?" * width + "]"
    filled = int(rate / 100 * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {rate:.0f}%"

def rate_label(rate):
    if rate is None:
        return "──"
    if rate >= 80:
        return f"◎ {rate:.1f}%"
    if rate >= 60:
        return f"△ {rate:.1f}%"
    return f"✕ {rate:.1f}%"

def choose(prompt, options, allow_back=True):
    """番号選択メニュー。0 で戻る。"""
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    if allow_back:
        print("  0. 戻る")
    while True:
        raw = input(f"\n{prompt} > ").strip()
        if allow_back and raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  1〜{len(options)} の番号を入力してください")

def input_int(prompt, min_val=1, max_val=9999):
    while True:
        raw = input(f"{prompt} > ").strip()
        if raw.isdigit():
            v = int(raw)
            if min_val <= v <= max_val:
                return v
        print(f"  {min_val}〜{max_val} の整数を入力してください")


# ── 画面: ダッシュボード ──────────────────────────────────────────

def show_dashboard():
    clr()
    title("AP試験 学習トラッカー  📖")
    study_time, quiz_stats = get_study_stats()
    total_min = sum(study_time.values()) if study_time else 0
    total_q = sum(s["total"] for s in quiz_stats.values()) if quiz_stats else 0
    ok_q = sum(s["correct"] for s in quiz_stats.values()) if quiz_stats else 0
    overall = round(ok_q / total_q * 100, 1) if total_q > 0 else None
    unstudied = get_unstudied_areas()

    h, m = divmod(total_min, 60)
    print(f"  総学習時間   : {h}h {m:02d}m")
    print(f"  解いた問題   : {total_q} 問  正解 {ok_q} 問")
    print(f"  総合正答率   : {rate_label(overall)}")
    print(f"  未学習分野   : {len(unstudied)} / 21 分野")

    # 苦手 TOP3
    weak = get_weak_areas(3)
    if weak:
        section("苦手分野 ✕ TOP3")
        for sub, s in weak:
            print(f"  {sub[:12]:<12} {bar(s['rate'], 14)} {s['correct']}/{s['total']}問")

    # 得意 TOP3
    strong = get_strong_areas(3)
    if strong:
        section("得意分野 ◎ TOP3")
        for sub, s in strong:
            print(f"  {sub[:12]:<12} {bar(s['rate'], 14)} {s['correct']}/{s['total']}問")

    # おすすめ
    section("おすすめ学習 💡")
    if weak:
        print(f"  今日取り組む: {weak[0][0]}（正答率 {weak[0][1]['rate']}%）")
    if unstudied:
        print(f"  まだ未着手 : {unstudied[0]}  など {len(unstudied)} 分野")

    hr()
    input("  Enter で戻る...")


# ── 画面: 学習記録 ────────────────────────────────────────────────

def record_study():
    clr()
    title("学習記録を追加  📝")
    cats = list(CATEGORIES.keys())
    print("\n大カテゴリを選んでください")
    cat = choose("番号", cats)
    if cat is None:
        return

    subs = CATEGORIES[cat]
    print(f"\n【{cat}】の分野を選んでください")
    sub = choose("番号", subs)
    if sub is None:
        return

    print()
    minutes = input_int("学習時間（分）", 1, 600)
    notes = input("メモ（Enterでスキップ）> ").strip()

    add_study_session(cat, sub, minutes, notes)
    print(f"\n  ✓ {sub}  {minutes}分  を記録しました！")
    input("  Enter で戻る...")


# ── 画面: 問題演習 ────────────────────────────────────────────────

def record_quiz():
    clr()
    title("問題演習を記録  ✏️")
    cats = list(CATEGORIES.keys())
    print("\n大カテゴリを選んでください")
    cat = choose("番号", cats)
    if cat is None:
        return

    subs = CATEGORIES[cat]
    print(f"\n【{cat}】の分野を選んでください")
    sub = choose("番号", subs)
    if sub is None:
        return

    print()
    total = input_int("解いた問題数", 1, 500)
    correct = input_int(f"正解数（0〜{total}）", 0, total)
    notes = input("メモ（Enterでスキップ）> ").strip()

    rate = correct / total * 100
    label = "◎ 良い調子！" if rate >= 80 else ("△ もう少し！" if rate >= 60 else "✕ 要復習！")
    print(f"\n  今回の正答率: {rate:.1f}%  {label}")

    add_quiz_result(cat, sub, total, correct, notes)
    print(f"  ✓ {sub}  {correct}/{total}問  を記録しました！")
    input("  Enter で戻る...")


# ── 画面: 統計 ────────────────────────────────────────────────────

def show_stats():
    clr()
    title("統計  📊")
    study_time, quiz_stats = get_study_stats()

    for parent, subs in CATEGORIES.items():
        section(parent)
        print(f"  {'分野':<14} {'時間':>5}  {'正答率'}")
        hr("-", 44)
        for sub in subs:
            mins = study_time.get(sub, 0)
            qs = quiz_stats.get(sub)
            rate_str = rate_label(qs["rate"]) if qs else "──"
            flag = ""
            if not mins and not qs:
                flag = " [未]"
            print(f"  {sub[:14]:<14} {mins:>4}分  {rate_str}{flag}")

    hr()
    input("  Enter で戻る...")


# ── 画面: 履歴 ────────────────────────────────────────────────────

def show_history():
    clr()
    title("最近の記録  🕐")

    section("学習記録（直近5件）")
    sessions = get_recent_sessions(5)
    if sessions:
        for s in sessions:
            date = s["created_at"][:10]
            memo = f"  {s['notes'][:20]}" if s["notes"] else ""
            print(f"  {date}  {s['subcategory'][:10]:<10}  {s['duration_minutes']}分{memo}")
    else:
        print("  まだ記録がありません")

    section("問題演習（直近5件）")
    quizzes = get_recent_quizzes(5)
    if quizzes:
        for q in quizzes:
            date = q["created_at"][:10]
            rate = q["correct_answers"] / q["total_questions"] * 100
            memo = f"  {q['notes'][:20]}" if q["notes"] else ""
            print(f"  {date}  {q['subcategory'][:10]:<10}  "
                  f"{q['correct_answers']}/{q['total_questions']}問 ({rate:.0f}%){memo}")
    else:
        print("  まだ記録がありません")

    hr()
    input("  Enter で戻る...")


# ── メインループ ──────────────────────────────────────────────────

def main():
    init_db()
    MENU = [
        ("ダッシュボード（苦手・得意・おすすめ）", show_dashboard),
        ("学習記録を追加",                        record_study),
        ("問題演習を記録",                        record_quiz),
        ("統計（全分野一覧）",                    show_stats),
        ("最近の記録を見る",                      show_history),
    ]

    while True:
        clr()
        title("AP試験 学習トラッカー")
        print()
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {i}. {label}")
        print("  0. 終了")
        raw = input("\n選択 > ").strip()
        if raw == "0":
            print("\n  お疲れさまでした！\n")
            break
        if raw.isdigit() and 1 <= int(raw) <= len(MENU):
            MENU[int(raw) - 1][1]()


if __name__ == "__main__":
    main()
