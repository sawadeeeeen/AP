from flask import Flask, render_template, request, redirect, url_for, jsonify
import database as db

app = Flask(__name__)


@app.before_request
def setup():
    db.init_db()


@app.route("/")
def index():
    study_time, quiz_stats = db.get_study_stats()
    weak = db.get_weak_areas()
    strong = db.get_strong_areas()
    unstudied = db.get_unstudied_areas()
    recent_sessions = db.get_recent_sessions(5)
    recent_quizzes = db.get_recent_quizzes(5)

    total_study_minutes = sum(study_time.values()) if study_time else 0
    total_questions = sum(s["total"] for s in quiz_stats.values()) if quiz_stats else 0
    overall_correct = sum(s["correct"] for s in quiz_stats.values()) if quiz_stats else 0
    overall_rate = round(overall_correct / total_questions * 100, 1) if total_questions > 0 else None

    return render_template(
        "index.html",
        categories=db.CATEGORIES,
        study_time=study_time,
        quiz_stats=quiz_stats,
        weak=weak,
        strong=strong,
        unstudied=unstudied,
        recent_sessions=recent_sessions,
        recent_quizzes=recent_quizzes,
        total_study_minutes=total_study_minutes,
        total_questions=total_questions,
        overall_rate=overall_rate,
    )


@app.route("/study", methods=["GET", "POST"])
def study():
    if request.method == "POST":
        category = request.form["category"]
        subcategory = request.form["subcategory"]
        duration = int(request.form["duration"])
        notes = request.form.get("notes", "")
        db.add_study_session(category, subcategory, duration, notes)
        return redirect(url_for("index"))
    return render_template("study.html", categories=db.CATEGORIES)


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if request.method == "POST":
        category = request.form["category"]
        subcategory = request.form["subcategory"]
        total = int(request.form["total"])
        correct = int(request.form["correct"])
        notes = request.form.get("notes", "")
        if correct > total:
            correct = total
        db.add_quiz_result(category, subcategory, total, correct, notes)
        return redirect(url_for("index"))
    return render_template("quiz.html", categories=db.CATEGORIES)


@app.route("/stats")
def stats():
    study_time, quiz_stats = db.get_study_stats()
    weak = db.get_weak_areas(10)
    strong = db.get_strong_areas(10)
    unstudied = db.get_unstudied_areas()

    # Chart.js 用データ: カテゴリ別学習時間
    chart_labels = []
    chart_study = []
    chart_rate = []
    for parent, subs in db.CATEGORIES.items():
        for sub in subs:
            chart_labels.append(sub)
            chart_study.append(study_time.get(sub, 0))
            rate = quiz_stats.get(sub, {}).get("rate")
            chart_rate.append(rate if rate is not None else 0)

    return render_template(
        "stats.html",
        categories=db.CATEGORIES,
        study_time=study_time,
        quiz_stats=quiz_stats,
        weak=weak,
        strong=strong,
        unstudied=unstudied,
        chart_labels=chart_labels,
        chart_study=chart_study,
        chart_rate=chart_rate,
    )


@app.route("/api/subcategories/<category>")
def api_subcategories(category):
    subs = db.CATEGORIES.get(category, [])
    return jsonify(subs)


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
