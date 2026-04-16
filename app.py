from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import date, timedelta
import calendar

app = Flask(__name__)
app.secret_key = "secret123"


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            completed_date TEXT NOT NULL,
            UNIQUE(habit_id, completed_date),
            FOREIGN KEY (habit_id) REFERENCES habits (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS water_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            cups INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, log_date),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    conn.commit()
    conn.close()


def get_theme():
    return session.get("theme", "pink")


def get_completed_habit_ids_today(user_id):
    today = date.today().isoformat()
    conn = get_db()

    rows = conn.execute("""
        SELECT habits.id
        FROM habits
        JOIN habit_logs
        ON habits.id = habit_logs.habit_id
        WHERE habits.user_id = ? AND habit_logs.completed_date = ?
    """, (user_id, today)).fetchall()

    conn.close()
    return {row["id"] for row in rows}


def get_streak_for_habit(habit_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT completed_date
        FROM habit_logs
        WHERE habit_id = ?
        ORDER BY completed_date DESC
    """, (habit_id,)).fetchall()
    conn.close()

    completed_dates = {row["completed_date"] for row in rows}
    streak = 0
    current_day = date.today()

    while current_day.isoformat() in completed_dates:
        streak += 1
        current_day -= timedelta(days=1)

    return streak


def get_month_calendar(user_id):
    today = date.today()
    year = today.year
    month = today.month

    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT habit_logs.completed_date
        FROM habit_logs
        JOIN habits ON habits.id = habit_logs.habit_id
        WHERE habits.user_id = ?
          AND substr(habit_logs.completed_date, 1, 7) = ?
    """, (user_id, today.strftime("%Y-%m"))).fetchall()
    conn.close()

    completed_days = {
        int(row["completed_date"].split("-")[2])
        for row in rows
    }

    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]

    return cal, completed_days, month_name, year


def get_water_today(user_id):
    today = date.today().isoformat()
    conn = get_db()
    row = conn.execute("""
        SELECT cups FROM water_logs
        WHERE user_id = ? AND log_date = ?
    """, (user_id, today)).fetchone()
    conn.close()

    if row:
        return row["cups"]
    return 0


def get_achievement(best_streak):
    if best_streak >= 30:
        return "Master 🏆"
    elif best_streak >= 14:
        return "Strong 🔥"
    elif best_streak >= 7:
        return "Consistent 💪"
    elif best_streak >= 3:
        return "Starter 🌱"
    return "Beginner ✨"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password)
        )
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect("/dashboard")
        else:
            return "Invalid email or password ❌"

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]

        conn.execute(
            "INSERT INTO habits (user_id, title, description) VALUES (?, ?, ?)",
            (user_id, title, description)
        )
        conn.commit()

    habits = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    ).fetchall()
    conn.close()

    completed_today_ids = get_completed_habit_ids_today(user_id)

    habits_data = []
    best_streak = 0

    for habit in habits:
        streak = get_streak_for_habit(habit["id"])
        if streak > best_streak:
            best_streak = streak

        habits_data.append({
            "id": habit["id"],
            "title": habit["title"],
            "description": habit["description"] if habit["description"] else "",
            "completed_today": habit["id"] in completed_today_ids,
            "streak": streak
        })

    total_habits = len(habits_data)
    completed_count = sum(1 for habit in habits_data if habit["completed_today"])
    progress_percent = int((completed_count / total_habits) * 100) if total_habits > 0 else 0

    water_cups = get_water_today(user_id)
    water_goal = 8
    water_percent = int((water_cups / water_goal) * 100) if water_goal > 0 else 0
    if water_percent > 100:
        water_percent = 100

    achievement = get_achievement(best_streak)

    if progress_percent == 100 and total_habits > 0:
        daily_message = "Amazing! You completed all your habits today 🎉"
    elif progress_percent >= 60:
        daily_message = "Great job! You're doing really well today 💗"
    elif progress_percent > 0:
        daily_message = "Nice start. Keep going 🌱"
    else:
        daily_message = "A new day, a new chance ✨"

    calendar_data, completed_days, month_name, year = get_month_calendar(user_id)

    return render_template(
        "dashboard.html",
        username=session["username"],
        habits=habits_data,
        theme=get_theme(),
        progress_percent=progress_percent,
        completed_count=completed_count,
        total_habits=total_habits,
        calendar_data=calendar_data,
        completed_days=completed_days,
        month_name=month_name,
        year=year,
        water_cups=water_cups,
        water_goal=water_goal,
        water_percent=water_percent,
        achievement=achievement,
        best_streak=best_streak,
        daily_message=daily_message
    )


@app.route("/toggle_habit/<int:habit_id>")
def toggle_habit(habit_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    today = date.today().isoformat()

    conn = get_db()

    habit = conn.execute(
        "SELECT * FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, user_id)
    ).fetchone()

    if not habit:
        conn.close()
        return redirect("/dashboard")

    existing = conn.execute(
        "SELECT * FROM habit_logs WHERE habit_id = ? AND completed_date = ?",
        (habit_id, today)
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM habit_logs WHERE habit_id = ? AND completed_date = ?",
            (habit_id, today)
        )
    else:
        conn.execute(
            "INSERT INTO habit_logs (habit_id, completed_date) VALUES (?, ?)",
            (habit_id, today)
        )

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/add_water")
def add_water():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    today = date.today().isoformat()
    conn = get_db()

    existing = conn.execute("""
        SELECT * FROM water_logs
        WHERE user_id = ? AND log_date = ?
    """, (user_id, today)).fetchone()

    if existing:
        conn.execute("""
            UPDATE water_logs
            SET cups = cups + 1
            WHERE user_id = ? AND log_date = ?
        """, (user_id, today))
    else:
        conn.execute("""
            INSERT INTO water_logs (user_id, log_date, cups)
            VALUES (?, ?, 1)
        """, (user_id, today))

    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/remove_water")
def remove_water():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    today = date.today().isoformat()
    conn = get_db()

    existing = conn.execute("""
        SELECT * FROM water_logs
        WHERE user_id = ? AND log_date = ?
    """, (user_id, today)).fetchone()

    if existing and existing["cups"] > 0:
        new_cups = existing["cups"] - 1

        if new_cups == 0:
            conn.execute("""
                DELETE FROM water_logs
                WHERE user_id = ? AND log_date = ?
            """, (user_id, today))
        else:
            conn.execute("""
                UPDATE water_logs
                SET cups = ?
                WHERE user_id = ? AND log_date = ?
            """, (new_cups, user_id, today))

    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/delete_habit/<int:habit_id>")
def delete_habit(habit_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db()

    conn.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))
    conn.execute(
        "DELETE FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/edit_habit/<int:habit_id>", methods=["GET", "POST"])
def edit_habit(habit_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db()

    habit = conn.execute(
        "SELECT * FROM habits WHERE id = ? AND user_id = ?",
        (habit_id, user_id)
    ).fetchone()

    if not habit:
        conn.close()
        return redirect("/dashboard")

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]

        conn.execute(
            "UPDATE habits SET title = ?, description = ? WHERE id = ? AND user_id = ?",
            (title, description, habit_id, user_id)
        )
        conn.commit()
        conn.close()
        return redirect("/dashboard")

    conn.close()
    return render_template("edit_habit.html", habit=habit, theme=get_theme())


@app.route("/set_theme/<theme>")
def set_theme(theme):
    if "user_id" not in session:
        return redirect("/login")

    if theme in ["pink", "grey", "dark"]:
        session["theme"] = theme

    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/calculator", methods=["GET", "POST"])
def calculator():
    tdee = None
    bmi = None
    bmi_status = ""
    maintenance = None
    lose = None
    gain = None

    if request.method == "POST":
        age = int(request.form["age"])
        weight = float(request.form["weight"])
        height = float(request.form["height"])
        gender = request.form["gender"]
        activity = float(request.form["activity"])

        if gender == "male":
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        tdee = int(bmr * activity)

        maintenance = tdee
        lose = tdee - 500
        gain = tdee + 500

        height_m = height / 100
        bmi = round(weight / (height_m ** 2), 1)

        if bmi < 18.5:
            bmi_status = "Underweight"
        elif bmi < 25:
            bmi_status = "Normal"
        elif bmi < 30:
            bmi_status = "Overweight"
        else:
            bmi_status = "Obese"

    return render_template(
        "calculator.html",
        tdee=tdee,
        bmi=bmi,
        bmi_status=bmi_status,
        maintenance=maintenance,
        lose=lose,
        gain=gain
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))