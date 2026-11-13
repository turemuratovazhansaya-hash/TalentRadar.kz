import sqlite3

conn = sqlite3.connect("talentradar.db")
cur = conn.cursor()
cur.execute("DELETE FROM certificates WHERE title IN ('Пустой лист', 'Диплом NIS')")
cur.execute("DELETE FROM offers WHERE title = 'Грант 20%'")
cur.execute("DELETE FROM activity_joins")
cur.execute(
    "UPDATE students SET visibility_score = 88 WHERE name = 'Ученик #402' AND visibility_score > 88"
)
user = cur.execute("SELECT id FROM users WHERE email = 'new.student.demo@talentradar.kz'").fetchone()
if user:
    cur.execute("DELETE FROM students WHERE user_id = ?", (user[0],))
    cur.execute("DELETE FROM users WHERE id = ?", (user[0],))
conn.commit()
print("cleaned", cur.execute("SELECT visibility_score FROM students WHERE name = 'Ученик #402'").fetchone()[0])
