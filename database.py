import sqlite3
import hashlib
from datetime import datetime, timedelta

DB_NAME = "washslot.db"

TIME_SLOTS = [
    ("08:00 AM - 09:00 AM", "8–9 AM", 8),
    ("09:00 AM - 10:00 AM", "9–10 AM", 9),
    ("10:00 AM - 11:00 AM", "10–11 AM", 10),
    ("04:00 PM - 05:00 PM", "4–5 PM", 16),
    ("05:00 PM - 06:00 PM", "5–6 PM", 17),
    ("06:00 PM - 07:00 PM", "6–7 PM", 18),
    ("07:00 PM - 08:00 PM", "7–8 PM", 19),
    ("08:00 PM - 09:00 PM", "8–9 PM", 20),
]

SLOT_START_HOUR = {s[0]: s[2] for s in TIME_SLOTS}


def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            is_maintenance INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            machine_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            slot_time TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            checked_in INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(student_id),
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS damage_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            machine_id INTEGER NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(student_id),
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
    """)

    # Seed 4 washing machines
    cur.execute("SELECT COUNT(*) FROM machines")
    if cur.fetchone()[0] == 0:
        for i in range(1, 5):
            cur.execute("INSERT INTO machines (name) VALUES (?)", (f"Machine 0{i}",))

    # Seed Warden account (admin / admin123)
    cur.execute("SELECT COUNT(*) FROM users WHERE student_id = 'admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (student_id, name, password_hash, role) VALUES (?, ?, ?, ?)",
            ("admin", "Hostel Warden", hash_password("admin123"), "admin"),
        )

    # Seed a demo student & sample historical bookings so AI Demand Prediction works immediately
    cur.execute("SELECT COUNT(*) FROM users WHERE student_id = '50010001'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (student_id, name, password_hash, role) VALUES (?, ?, ?, ?)",
            ("50010001", "Demo Student", hash_password("1234"), "student"),
        )
        today = datetime.now().date()
        sample_slots = [
            ("04:00 PM - 05:00 PM", 1), ("05:00 PM - 06:00 PM", 1),
            ("05:00 PM - 06:00 PM", 2), ("06:00 PM - 07:00 PM", 1),
            ("06:00 PM - 07:00 PM", 2), ("06:00 PM - 07:00 PM", 3),
            ("07:00 PM - 08:00 PM", 1), ("07:00 PM - 08:00 PM", 4),
            ("08:00 AM - 09:00 AM", 2), ("09:00 AM - 10:00 AM", 3),
        ]
        for days_ago in range(1, 8):
            d_str = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            for slot_label, m_id in sample_slots:
                cur.execute(
                    """INSERT INTO bookings
                       (student_id, machine_id, booking_date, slot_time, status, checked_in, created_at)
                       VALUES (?, ?, ?, ?, 'completed', 1, ?)""",
                    ("50010001", m_id, d_str, slot_label, f"{d_str} 08:00"),
                )

    conn.commit()
    conn.close()


def register_user(student_id: str, name: str, password: str) -> tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (student_id, name, password_hash) VALUES (?, ?, ?)",
            (student_id.strip(), name.strip(), hash_password(password)),
        )
        conn.commit()
        return True, "Account created! Please sign in."
    except sqlite3.IntegrityError:
        return False, "Student ID already registered."
    finally:
        conn.close()


def login_user(student_id: str, password: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT student_id, name, role FROM users WHERE student_id = ? AND password_hash = ?",
        (student_id.strip(), hash_password(password)),
    )
    user = cur.fetchone()
    conn.close()
    return user


def release_missed_slots(grace_minutes: int = 15) -> int:
    """Auto-release active bookings that were not checked-in within 15 minutes of slot start."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now()
    cur.execute(
        "SELECT id, booking_date, slot_time FROM bookings WHERE status = 'active' AND checked_in = 0"
    )
    rows = cur.fetchall()
    released = 0
    for b_id, b_date, s_time in rows:
        start_hr = SLOT_START_HOUR.get(s_time)
        if start_hr is None:
            continue
        try:
            slot_start = datetime.strptime(b_date, "%Y-%m-%d").replace(hour=start_hr, minute=0, second=0)
        except ValueError:
            continue
        if now >= slot_start + timedelta(minutes=grace_minutes):
            cur.execute("UPDATE bookings SET status = 'expired' WHERE id = ?", (b_id,))
            released += 1
    conn.commit()
    conn.close()
    return released


def get_machines_status(booking_date: str, slot_time: str):
    release_missed_slots()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.name, m.is_maintenance, b.student_id, b.id, u.name, b.checked_in
        FROM machines m
        LEFT JOIN bookings b
            ON m.id = b.machine_id
            AND b.booking_date = ?
            AND b.slot_time = ?
            AND b.status = 'active'
        LEFT JOIN users u
            ON b.student_id = u.student_id
        ORDER BY m.id
    """, (booking_date, slot_time))
    rows = cur.fetchall()
    conn.close()
    return rows


def book_machine(student_id: str, machine_id: int, booking_date: str, slot_time: str) -> tuple[bool, str]:
    release_missed_slots()
    conn = get_connection()
    cur = conn.cursor()

    # Check machine maintenance
    cur.execute("SELECT is_maintenance FROM machines WHERE id = ?", (machine_id,))
    m_row = cur.fetchone()
    if m_row and m_row[0] == 1:
        conn.close()
        return False, "This machine is currently under maintenance."

    # Daily 60-minute database restriction (max 1 booking per student per date)
    cur.execute(
        """SELECT id FROM bookings
           WHERE student_id = ? AND booking_date = ? AND status IN ('active', 'completed')""",
        (student_id, booking_date),
    )
    if cur.fetchone():
        conn.close()
        return False, f"Daily 60-min limit reached for {booking_date}. Cancel your active slot first."

    # Booking conflict protection
    cur.execute(
        """SELECT id FROM bookings
           WHERE machine_id = ? AND booking_date = ? AND slot_time = ? AND status = 'active'""",
        (machine_id, booking_date, slot_time),
    )
    if cur.fetchone():
        conn.close()
        return False, "Booking conflict: this machine & slot was just taken!"

    cur.execute(
        """INSERT INTO bookings
           (student_id, machine_id, booking_date, slot_time, status, checked_in, created_at)
           VALUES (?, ?, ?, ?, 'active', 0, ?)""",
        (student_id, machine_id, booking_date, slot_time, datetime.now().strftime("%d %b, %I:%M %p")),
    )
    conn.commit()
    conn.close()
    return True, f"Booked for {booking_date} ({slot_time})!"


def check_in_booking(booking_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET checked_in = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()


def complete_booking(booking_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status = 'completed' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()


def cancel_booking(booking_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()


def get_student_active_booking(student_id: str):
    release_missed_slots()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, m.name, b.booking_date, b.slot_time, b.checked_in
        FROM bookings b
        JOIN machines m ON b.machine_id = m.id
        WHERE b.student_id = ? AND b.status = 'active'
        ORDER BY b.booking_date ASC, b.id DESC
        LIMIT 1
    """, (student_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_booking_history(student_id: str, role: str):
    conn = get_connection()
    cur = conn.cursor()
    if role == "admin":
        cur.execute("""
            SELECT b.id, u.name, b.student_id, m.name, b.booking_date, b.slot_time, b.status, b.created_at
            FROM bookings b
            JOIN machines m ON b.machine_id = m.id
            JOIN users u ON b.student_id = u.student_id
            ORDER BY b.id DESC
            LIMIT 40
        """)
    else:
        cur.execute("""
            SELECT b.id, u.name, b.student_id, m.name, b.booking_date, b.slot_time, b.status, b.created_at
            FROM bookings b
            JOIN machines m ON b.machine_id = m.id
            JOIN users u ON b.student_id = u.student_id
            WHERE b.student_id = ?
            ORDER BY b.id DESC
            LIMIT 25
        """, (student_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def toggle_maintenance(machine_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE machines SET is_maintenance = CASE WHEN is_maintenance = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (machine_id,),
    )
    conn.commit()
    conn.close()


def submit_damage_report(student_id: str, machine_id: int, issue_type: str, description: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO damage_reports (student_id, machine_id, issue_type, description, status, created_at)
           VALUES (?, ?, ?, ?, 'open', ?)""",
        (student_id, machine_id, issue_type, description.strip(), datetime.now().strftime("%d %b, %I:%M %p")),
    )
    conn.commit()
    conn.close()


def get_damage_reports():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, m.name, r.machine_id, u.name, r.student_id, r.issue_type, r.description, r.status, r.created_at
        FROM damage_reports r
        JOIN machines m ON r.machine_id = m.id
        JOIN users u ON r.student_id = u.student_id
        ORDER BY CASE WHEN r.status = 'open' THEN 0 ELSE 1 END, r.id DESC
        LIMIT 30
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def resolve_damage_report(report_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE damage_reports SET status = 'resolved' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()


def get_all_machines():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_maintenance FROM machines ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows
