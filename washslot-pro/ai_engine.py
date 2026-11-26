from datetime import datetime
import database as db


def predict_slot_demand(target_date: str) -> list[dict]:
    """
    Predicts demand percentage (0-100%) for each 1-hour slot on target_date
    using historical SQLite booking frequency + day-of-week weekend weighting.
    """
    conn = db.get_connection()
    cur = conn.cursor()

    # Historical booking counts per slot
    cur.execute("""
        SELECT slot_time, COUNT(*)
        FROM bookings
        WHERE status IN ('active', 'completed')
        GROUP BY slot_time
    """)
    hist_counts = dict(cur.fetchall())

    # Active bookings already placed on target_date
    cur.execute("""
        SELECT slot_time, COUNT(*)
        FROM bookings
        WHERE booking_date = ? AND status = 'active'
        GROUP BY slot_time
    """, (target_date,))
    live_counts = dict(cur.fetchall())

    # Total working machines
    cur.execute("SELECT COUNT(*) FROM machines WHERE is_maintenance = 0")
    working_machines = max(cur.fetchone()[0], 1)
    conn.close()

    # Weekend multiplier (Saturday/Sunday have ~25% higher hostel laundry demand)
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        weekend_boost = 1.25 if dt.weekday() >= 5 else 1.0
    except ValueError:
        weekend_boost = 1.0

    max_hist = max(hist_counts.values()) if hist_counts else 1
    predictions = []

    for full_slot, short_slot, _ in db.TIME_SLOTS:
        hist_score = (hist_counts.get(full_slot, 1) / max_hist) * 70.0 * weekend_boost
        live_pct = (live_counts.get(full_slot, 0) / working_machines) * 100.0
        # Blend historical trend (60%) with live occupancy (40%)
        predicted_pct = min(100, int(round(0.6 * min(hist_score, 100) + 0.4 * live_pct)))

        if predicted_pct >= 70:
            level = "Peak"
        elif predicted_pct >= 40:
            level = "Moderate"
        else:
            level = "Quiet"

        predictions.append({
            "slot": full_slot,
            "short": short_slot,
            "demand_pct": predicted_pct,
            "level": level,
            "live_booked": live_counts.get(full_slot, 0),
            "working_machines": working_machines,
        })

    return predictions


def recommend_optimal_slot(target_date: str) -> dict | None:
    """
    AI Scheduling Optimizer:
    Finds the lowest-congestion available slot and the least-used working machine
    (load balancing across machines to reduce mechanical wear).
    """
    predictions = predict_slot_demand(target_date)
    # Sort slots by lowest predicted demand first
    ranked_slots = sorted(predictions, key=lambda x: (x["demand_pct"], x["live_booked"]))

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT machine_id, COUNT(*)
        FROM bookings
        WHERE status IN ('active', 'completed')
        GROUP BY machine_id
    """)
    machine_usage = dict(cur.fetchall())
    conn.close()

    for slot_info in ranked_slots:
        machines = db.get_machines_status(target_date, slot_info["slot"])
        available = [m for m in machines if not m[2] and not m[3]]
        if available:
            # Pick the available machine with the fewest historical washes (load balancing)
            best_m = min(available, key=lambda m: machine_usage.get(m[0], 0))
            return {
                "slot": slot_info["slot"],
                "short": slot_info["short"],
                "demand_pct": slot_info["demand_pct"],
                "level": slot_info["level"],
                "machine_id": best_m[0],
                "machine_name": best_m[1],
                "reason": (
                    f"Lowest predicted congestion ({slot_info['demand_pct']}% demand) "
                    f"and {best_m[1]} has the lightest recent workload."
                ),
            }
    return None
