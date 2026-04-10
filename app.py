def normalize(data):
    """Convert Firebase dict → list safely"""
    if isinstance(data, dict):
        return list(data.values())
    return data or []

"""Flask application for the online quiz system (Firebase FIXED)."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request, session, redirect, url_for, make_response

from auth import login_required, role_required
from storage import DataStore
from services import (
    authenticate,
    assign_lecturer_to_module,
    build_lecturer_report,
    build_student_report,
    create_module,
    create_quiz,
    create_user,
    enroll_student_in_module,
    export_payload,
    get_attempts,
    get_module_by_id,
    get_public_modules,
    get_user_modules,
    grade_attempt,
    seed_demo_data,
    submit_quiz,
    get_list,
)

# -----------------------------
# INIT
# -----------------------------
STORE = DataStore()

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-for-production"
app.config["JSON_SORT_KEYS"] = False

seed_demo_data(STORE)


# -----------------------------
# HELPER
# -----------------------------
def current_user():
    return session.get("user")


def normalize(data):
    """Firebase dict → list"""
    if isinstance(data, dict):
        return list(data.values())
    return data or []


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    if session.get("user"):
        role = session["user"].get("role")
        if role == "admin":
            return redirect(url_for("admin_dashboard"))
        if role == "lecturer":
            return redirect(url_for("lecturer_dashboard"))
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/signup")
def signup_page():
    modules = get_public_modules(STORE)
    return render_template("signup.html", modules=modules)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    return render_template("admin_dashboard.html", user=current_user())


@app.route("/lecturer")
@login_required
@role_required("lecturer")
def lecturer_dashboard():
    return render_template("lecturer_dashboard.html", user=current_user())


@app.route("/student")
@login_required
@role_required("student")
def student_dashboard():
    return render_template("student_dashboard.html", user=current_user())


# -----------------------------
# AUTH API
# -----------------------------
@app.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or request.form or {}
    user = authenticate(STORE, data.get("username", ""), data.get("password", ""))

    if not user:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
    }

    return jsonify({"success": True, "user": session["user"]})


@app.post("/api/signup")
def api_signup():
    data = request.get_json(force=True, silent=True) or {}

    user = create_user(
        STORE,
        data.get("username", ""),
        data.get("password", ""),
        data.get("full_name", ""),
        "student",
    )

    if data.get("module_id"):
        enroll_student_in_module(STORE, user["id"], data["module_id"])

    return jsonify({"success": True, "user_id": user["id"]})


@app.get("/api/me")
@login_required
def api_me():
    return jsonify({"success": True, "user": current_user()})


# -----------------------------
# ADMIN API
# -----------------------------
@app.get("/api/admin/summary")
@login_required
@role_required("admin")
def api_admin_summary():
    users = normalize(get_list(STORE, "users"))
    modules = normalize(get_list(STORE, "modules"))
    quizzes = normalize(get_list(STORE, "quizzes"))
    attempts = normalize(get_list(STORE, "attempts"))

    return jsonify({
        "success": True,
        "summary": {
            "users": len(users),
            "lecturers": sum(1 for u in users if u.get("role") == "lecturer"),
            "students": sum(1 for u in users if u.get("role") == "student"),
            "modules": len(modules),
            "quizzes": len(quizzes),
            "attempts": len(attempts),
        }
    })


@app.get("/api/admin/users")
@login_required
@role_required("admin")
def api_admin_users():
    return jsonify({"success": True, "users": normalize(get_list(STORE, "users"))})


@app.get("/api/admin/modules")
@login_required
@role_required("admin")
def api_admin_modules():
    return jsonify({"success": True, "modules": normalize(get_list(STORE, "modules"))})


@app.post("/api/admin/modules")
@login_required
@role_required("admin")
def api_admin_create_module():
    data = request.get_json(force=True, silent=True) or {}
    module = create_module(STORE, data["code"], data["name"], data.get("lecturer_id", ""))
    return jsonify({"success": True, "module": module})


@app.post("/api/admin/assign-student")
@login_required
@role_required("admin")
def api_admin_assign_student():
    data = request.get_json(force=True, silent=True) or {}
    module = enroll_student_in_module(STORE, data["student_id"], data["module_id"])
    return jsonify({"success": True, "module": module})


@app.post("/api/admin/assign-lecturer")
@login_required
@role_required("admin")
def api_admin_assign_lecturer():
    data = request.get_json(force=True, silent=True) or {}
    module = assign_lecturer_to_module(STORE, data["module_id"], data["lecturer_id"])
    return jsonify({"success": True, "module": module})


# -----------------------------
# LECTURER API
# -----------------------------
@app.get("/api/lecturer/modules")
@login_required
@role_required("lecturer")
def api_lecturer_modules():
    return jsonify({
        "success": True,
        "modules": get_user_modules(STORE, current_user())
    })


@app.get("/api/lecturer/attempts")
@login_required
@role_required("lecturer")
def api_lecturer_attempts():
    modules = [m["id"] for m in get_user_modules(STORE, current_user())]
    quizzes = normalize(get_list(STORE, "quizzes"))

    quiz_ids = {q["id"] for q in quizzes if q["module_id"] in modules}
    attempts = [a for a in normalize(get_attempts(STORE)) if a["quiz_id"] in quiz_ids]

    return jsonify({"success": True, "attempts": attempts})


@app.post("/api/lecturer/attempts/<attempt_id>/grade")
@login_required
@role_required("lecturer")
def api_grade(attempt_id):
    data = request.get_json(force=True, silent=True) or {}
    attempt = grade_attempt(STORE, current_user()["id"], attempt_id, int(data["score"]), data.get("comment", ""))
    return jsonify({"success": True, "attempt": attempt})


@app.get("/api/lecturer/report")
@login_required
@role_required("lecturer")
def api_lecturer_report():
    return jsonify({
        "success": True,
        "report": build_lecturer_report(STORE, current_user()["id"])
    })


# -----------------------------
# STUDENT API
# -----------------------------
@app.get("/api/student/modules")
@login_required
@role_required("student")
def api_student_modules():
    return jsonify({
        "success": True,
        "modules": get_user_modules(STORE, current_user())
    })


@app.get("/api/student/quizzes")
@login_required
@role_required("student")
def api_student_quizzes():
    quizzes = normalize(get_list(STORE, "quizzes"))
    attempts = normalize(get_attempts(STORE))
    modules = get_user_modules(STORE, current_user())

    module_ids = {m["id"] for m in modules}

    rows = []
    for q in quizzes:
        if q["module_id"] in module_ids:
            attempt = next((a for a in attempts if a["quiz_id"] == q["id"]), None)
            rows.append({**q, "attempted": bool(attempt), "attempt": attempt})

    return jsonify({"success": True, "quizzes": rows})


@app.post("/api/student/quizzes/<quiz_id>/submit")
@login_required
@role_required("student")
def api_submit(quiz_id):
    data = request.get_json(force=True, silent=True) or {}
    attempt = submit_quiz(STORE, current_user()["id"], quiz_id, data.get("answers", {}))
    return jsonify({"success": True, "attempt": attempt})


@app.get("/api/student/report")
@login_required
@role_required("student")
def api_student_report():
    return jsonify({
        "success": True,
        "report": build_student_report(STORE, current_user()["id"])
    })


# -----------------------------
# EXPORT
# -----------------------------
@app.get("/api/export/<kind>")
@login_required
def api_export(kind):
    format_name = request.args.get("format", "json")
    content, filename = export_payload(STORE, kind, format_name, user=current_user())

    mimetype = "application/json" if format_name == "json" else "text/csv"
    response = make_response(content)
    response.headers["Content-Type"] = f"{mimetype}; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# -----------------------------
# DEBUG
# -----------------------------
@app.get("/api/debug/state")
@login_required
def debug():
    return jsonify({
        "users": normalize(get_list(STORE, "users")),
        "modules": normalize(get_list(STORE, "modules")),
        "quizzes": normalize(get_list(STORE, "quizzes")),
        "attempts": normalize(get_list(STORE, "attempts")),
    })


if __name__ == "__main__":
    app.run(debug=True)