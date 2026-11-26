import asyncio
from datetime import datetime, timedelta
import flet as ft
import database as db
import ai_engine as ai

# Design Tokens
BG_COLOR = "#F4F7FB"
CARD_BG = "#FFFFFF"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1E3A8A"
TEXT_DARK = "#0F172A"
TEXT_MUTED = "#64748B"
BORDER_COLOR = "#E2E8F0"

GREEN_BG = "#ECFDF5"
GREEN_FG = "#059669"
RED_BG = "#FEF2F2"
RED_FG = "#DC2626"
AMBER_BG = "#FFFBEB"
AMBER_FG = "#D97706"
PURPLE_BG = "#F5F3FF"
PURPLE_FG = "#7C3AED"

# 60-minute Wash Cycle Stages (stage_name, duration_seconds)
CYCLE_STAGES = [
    ("Wash", 20 * 60),
    ("Drain", 5 * 60),
    ("Refill & Rinse", 15 * 60),
    ("Drying / Spin", 20 * 60),
]
TOTAL_CYCLE_SECS = sum(s[1] for s in CYCLE_STAGES)


def main(page: ft.Page):
    db.init_db()

    page.title = "WashSlot Pro • Smart Hostel Laundry"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BG_COLOR
    page.window.width = 420
    page.window.height = 820
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO

    today_str = datetime.now().strftime("%Y-%m-%d")
    current_user = {"id": None, "name": None, "role": None}
    selected_date = {"value": today_str}
    selected_slot = {"value": db.TIME_SLOTS[3][0]}  # Default 4-5 PM
    active_tab = {"index": 0}  # 0=Book, 1=Timer, 2=AI, 3=Reports/Admin

    # Live Cycle Timer state
    timer_state = {
        "running": False,
        "elapsed": 0,
        "demo_fast": False,  # 60x speed toggle for lab faculty demo
    }

    def show_msg(text: str, color=PRIMARY):
        sb = ft.SnackBar(
            content=ft.Text(text, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500),
            bgcolor=color,
        )
        page.show_dialog(sb)

    def status_pill(label: str, bg: str, fg: str):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=7, height=7, border_radius=4, bgcolor=fg),
                    ft.Text(label, size=11, weight=ft.FontWeight.W_600, color=fg),
                ],
                spacing=5,
                tight=True,
            ),
            bgcolor=bg,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=20,
        )

    def styled_field(label: str, hint: str, icon, is_password: bool = False, visible: bool = True, multiline: bool = False):
        return ft.TextField(
            label=label,
            hint_text=hint,
            prefix_icon=icon,
            password=is_password,
            can_reveal_password=is_password,
            multiline=multiline,
            min_lines=2 if multiline else 1,
            filled=True,
            bgcolor="#F8FAFC",
            border=ft.OutlineInputBorder(
                border_radius=12,
                side=ft.BorderSide(width=1, color=BORDER_COLOR),
            ),
            visible=visible,
        )

    def get_cycle_stage(elapsed_secs: int):
        acc = 0
        for idx, (name, dur) in enumerate(CYCLE_STAGES):
            if elapsed_secs < acc + dur:
                return idx, name, (acc + dur) - elapsed_secs, dur
            acc += dur
        return len(CYCLE_STAGES) - 1, "Completed", 0, 1

    # ==========================================================
    # LOGIN & REGISTER SCREEN
    # ==========================================================
    def show_login():
        timer_state["running"] = False
        page.clean()
        is_register = {"mode": False}

        id_field = styled_field("Student ID", "e.g., 50012345", ft.Icons.BADGE_OUTLINED)
        name_field = styled_field("Full Name", "e.g., Ishan Sharma", ft.Icons.PERSON_OUTLINE, visible=False)
        pass_field = styled_field("Password", "Enter password", ft.Icons.LOCK_OUTLINE, is_password=True)
        submit_label = ft.Text("Sign In", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, size=15)

        def set_mode(register_mode: bool):
            is_register["mode"] = register_mode
            name_field.visible = register_mode
            submit_label.value = "Create Account" if register_mode else "Sign In"
            login_tab.bgcolor = CARD_BG if not register_mode else ft.Colors.TRANSPARENT
            login_tab_text.color = PRIMARY if not register_mode else TEXT_MUTED
            reg_tab.bgcolor = CARD_BG if register_mode else ft.Colors.TRANSPARENT
            reg_tab_text.color = PRIMARY if register_mode else TEXT_MUTED
            page.update()

        def handle_submit(e):
            if not id_field.value or not pass_field.value:
                show_msg("Please enter your ID and password.", RED_FG)
                return

            if is_register["mode"]:
                if not name_field.value:
                    show_msg("Please enter your full name.", RED_FG)
                    return
                ok, msg = db.register_user(id_field.value, name_field.value, pass_field.value)
                show_msg(msg, GREEN_FG if ok else RED_FG)
                if ok:
                    set_mode(False)
            else:
                user = db.login_user(id_field.value, pass_field.value)
                if user:
                    current_user["id"], current_user["name"], current_user["role"] = user
                    active_tab["index"] = 0
                    show_dashboard()
                else:
                    show_msg("Invalid Student ID or Password.", RED_FG)

        login_tab_text = ft.Text("Login", weight=ft.FontWeight.BOLD, color=PRIMARY, size=13)
        reg_tab_text = ft.Text("Register", weight=ft.FontWeight.BOLD, color=TEXT_MUTED, size=13)

        login_tab = ft.Container(
            content=login_tab_text,
            alignment=ft.Alignment.CENTER,
            bgcolor=CARD_BG,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=10),
            expand=True,
            on_click=lambda _: set_mode(False),
        )
        reg_tab = ft.Container(
            content=reg_tab_text,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.TRANSPARENT,
            border_radius=10,
            padding=ft.Padding.symmetric(vertical=10),
            expand=True,
            on_click=lambda _: set_mode(True),
        )

        hero = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[PRIMARY_DARK, PRIMARY],
            ),
            padding=ft.Padding.only(top=50, bottom=40, left=24, right=24),
            border_radius=ft.BorderRadius.only(bottom_left=32, bottom_right=32),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.LOCAL_LAUNDRY_SERVICE, size=42, color=ft.Colors.WHITE),
                        bgcolor="#33FFFFFF",
                        padding=16,
                        border_radius=20,
                    ),
                    ft.Text("WashSlot Pro", size=30, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text("AI-Powered Hostel Laundry Management", size=13, color="#DBEAFE"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            width=float("inf"),
        )

        form_card = ft.Container(
            bgcolor=CARD_BG,
            border_radius=20,
            padding=22,
            margin=ft.Margin.symmetric(horizontal=20, vertical=18),
            border=ft.Border.all(1, BORDER_COLOR),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=18, color="#120F172A", offset=ft.Offset(0, 6)),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row([login_tab, reg_tab], spacing=4),
                        bgcolor="#E2E8F0",
                        padding=4,
                        border_radius=12,
                    ),
                    ft.Container(height=4),
                    id_field,
                    name_field,
                    pass_field,
                    ft.Container(height=4),
                    ft.Container(
                        content=submit_label,
                        alignment=ft.Alignment.CENTER,
                        bgcolor=PRIMARY,
                        height=48,
                        border_radius=12,
                        on_click=handle_submit,
                        ink=True,
                    ),
                ],
                spacing=12,
            ),
        )

        demo_hint = ft.Column(
            [
                ft.Text("Warden Login: admin / admin123", size=12, color=TEXT_MUTED),
                ft.Text("Demo Student: 50010001 / 1234", size=12, color=TEXT_MUTED),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=3,
        )

        page.add(ft.Column([hero, form_card, demo_hint], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER))

    # ==========================================================
    # MAIN DASHBOARD
    # ==========================================================
    def show_dashboard():
        page.clean()
        released_count = db.release_missed_slots(grace_minutes=15)
        if released_count > 0:
            show_msg(f"Auto-released {released_count} missed slot(s) (>15 min grace).", AMBER_FG)

        is_admin = current_user["role"] == "admin"

        def switch_tab(idx: int):
            active_tab["index"] = idx
            show_dashboard()

        def handle_book(m_id: int, slot_override: str | None = None):
            slot_to_use = slot_override or selected_slot["value"]
            ok, msg = db.book_machine(current_user["id"], m_id, selected_date["value"], slot_to_use)
            show_msg(msg, GREEN_FG if ok else RED_FG)
            show_dashboard()

        def handle_cancel(b_id: int):
            db.cancel_booking(b_id)
            show_msg("Booking cancelled and slot released.", AMBER_FG)
            show_dashboard()

        def handle_checkin(b_id: int):
            db.check_in_booking(b_id)
            show_msg("Checked in! You can now start your 60-min wash timer.", GREEN_FG)
            active_tab["index"] = 1
            show_dashboard()

        def handle_maintenance(m_id: int):
            db.toggle_maintenance(m_id)
            show_msg("Machine status updated.", PRIMARY)
            show_dashboard()

        def handle_resolve_report(r_id: int):
            db.resolve_damage_report(r_id)
            show_msg("Damage report marked as resolved.", GREEN_FG)
            show_dashboard()

        # 1. Top Gradient Bar
        top_bar = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[PRIMARY_DARK, PRIMARY],
            ),
            padding=ft.Padding.only(top=20, bottom=18, left=18, right=14),
            border_radius=ft.BorderRadius.only(bottom_left=24, bottom_right=24),
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    current_user["name"][0].upper(),
                                    color=PRIMARY,
                                    weight=ft.FontWeight.BOLD,
                                    size=18,
                                ),
                                width=42,
                                height=42,
                                border_radius=21,
                                bgcolor=ft.Colors.WHITE,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column(
                                [
                                    ft.Text(f"Hi, {current_user['name']}", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ft.Container(
                                        content=ft.Text(
                                            "WARDEN MODE" if is_admin else f"ID: {current_user['id']}",
                                            size=10,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.WHITE,
                                        ),
                                        bgcolor="#33FFFFFF",
                                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=10,
                                    ),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.LOGOUT_ROUNDED,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Logout",
                        on_click=lambda _: show_login(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

        # 2. 4-Tab Navigation Bar
        def nav_btn(label: str, icon, idx: int):
            sel = active_tab["index"] == idx
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(icon, size=18, color=PRIMARY if sel else TEXT_MUTED),
                        ft.Text(label, size=11, weight=ft.FontWeight.BOLD if sel else ft.FontWeight.W_500, color=PRIMARY if sel else TEXT_MUTED),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                bgcolor=CARD_BG if sel else ft.Colors.TRANSPARENT,
                border_radius=10,
                padding=ft.Padding.symmetric(vertical=7),
                expand=True,
                on_click=lambda _, i=idx: switch_tab(i),
            )

        tab_bar = ft.Container(
            content=ft.Row(
                [
                    nav_btn("Book", ft.Icons.LOCAL_LAUNDRY_SERVICE_OUTLINED, 0),
                    nav_btn("Timer", ft.Icons.TIMER_OUTLINED, 1),
                    nav_btn("AI", ft.Icons.AUTO_AWESOME_OUTLINED, 2),
                    nav_btn("Admin" if is_admin else "Reports", ft.Icons.BUILD_CIRCLE_OUTLINED, 3),
                ],
                spacing=3,
            ),
            bgcolor="#E2E8F0",
            padding=4,
            border_radius=12,
            margin=ft.Margin.only(left=14, right=14, top=12),
        )

        body = []

        # ==========================================================
        # TAB 0: BOOKING CALENDAR, 15-MIN ALARM & 4 MACHINES
        # ==========================================================
        if active_tab["index"] == 0:
            # 15-Minute Alarm Banner for Student's Active Booking
            my_booking = db.get_student_active_booking(current_user["id"])
            if my_booking and not is_admin:
                b_id, m_name, b_date, b_slot, checked_in = my_booking
                start_hr = db.SLOT_START_HOUR.get(b_slot, 16)
                slot_dt = datetime.strptime(b_date, "%Y-%m-%d").replace(hour=start_hr, minute=0)
                mins_until = int((slot_dt - datetime.now()).total_seconds() // 60)

                if not checked_in and -15 <= mins_until <= 15:
                    alarm_text = (
                        f"ALARM: Your {m_name} slot starts in {max(0, mins_until)} min! Check in within 15 min or it auto-releases."
                        if mins_until >= 0
                        else f"GRACE PERIOD: Check in within {15 + mins_until} min or your slot auto-releases!"
                    )
                    body.append(
                        ft.Container(
                            bgcolor=AMBER_BG,
                            border=ft.Border.all(1.5, AMBER_FG),
                            border_radius=14,
                            padding=12,
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.ALARM_ON_ROUNDED, color=AMBER_FG, size=22),
                                    ft.Text(alarm_text, size=12, weight=ft.FontWeight.BOLD, color="#92400E", expand=True),
                                ],
                                spacing=10,
                            ),
                        )
                    )

                # Active Booking Ticket
                body.append(
                    ft.Container(
                        bgcolor="#EFF6FF",
                        border=ft.Border.all(1.5, "#93C5FD"),
                        border_radius=16,
                        padding=14,
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Column(
                                            [
                                                ft.Text("YOUR ACTIVE BOOKING", size=10, weight=ft.FontWeight.BOLD, color=PRIMARY),
                                                ft.Text(f"{m_name} • {b_date}", size=15, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                                ft.Text(b_slot, size=12, color=TEXT_MUTED),
                                            ],
                                            spacing=1,
                                        ),
                                        status_pill("Checked In", GREEN_BG, GREEN_FG) if checked_in else status_pill("Awaiting Check-In", AMBER_BG, AMBER_FG),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Text(
                                                "Open Wash Timer" if checked_in else "Check In Now",
                                                size=12,
                                                weight=ft.FontWeight.BOLD,
                                                color=ft.Colors.WHITE,
                                            ),
                                            bgcolor=GREEN_FG if not checked_in else PRIMARY,
                                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                                            border_radius=10,
                                            on_click=(lambda _, bid=b_id: handle_checkin(bid)) if not checked_in else (lambda _: switch_tab(1)),
                                            ink=True,
                                        ),
                                        ft.Container(
                                            content=ft.Text("Cancel Slot", size=12, weight=ft.FontWeight.BOLD, color=RED_FG),
                                            bgcolor=RED_BG,
                                            border=ft.Border.all(1, "#FECACA"),
                                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                                            border_radius=10,
                                            on_click=lambda _, bid=b_id: handle_cancel(bid),
                                            ink=True,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                            ],
                            spacing=10,
                        ),
                    )
                )

            # 7-Day Booking Calendar Strip
            body.append(ft.Text("Booking Calendar", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK))
            cal_chips = []
            base_day = datetime.now().date()
            for offset in range(7):
                d = base_day + timedelta(days=offset)
                d_str = d.strftime("%Y-%m-%d")
                is_sel = selected_date["value"] == d_str
                cal_chips.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(d.strftime("%a"), size=10, color=ft.Colors.WHITE if is_sel else TEXT_MUTED),
                                ft.Text(d.strftime("%d"), size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if is_sel else TEXT_DARK),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=2,
                        ),
                        width=50,
                        padding=ft.Padding.symmetric(vertical=8),
                        bgcolor=PRIMARY if is_sel else CARD_BG,
                        border=ft.Border.all(1, PRIMARY if is_sel else BORDER_COLOR),
                        border_radius=12,
                        on_click=lambda _, ds=d_str: (selected_date.update({"value": ds}), show_dashboard()),
                        ink=True,
                    )
                )
            body.append(ft.Row(cal_chips, spacing=8, scroll=ft.ScrollMode.AUTO))

            # Time Slot Selector
            body.append(
                ft.Row(
                    [
                        ft.Text("1-Hour Time Slot", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                        ft.Text(selected_slot["value"], size=11, color=PRIMARY, weight=ft.FontWeight.W_600),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
            slot_chips = []
            for full_s, short_s, _ in db.TIME_SLOTS:
                is_sel = selected_slot["value"] == full_s
                slot_chips.append(
                    ft.Container(
                        content=ft.Text(short_s, size=12, weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500, color=ft.Colors.WHITE if is_sel else TEXT_DARK),
                        bgcolor=PRIMARY if is_sel else CARD_BG,
                        border=ft.Border.all(1, PRIMARY if is_sel else BORDER_COLOR),
                        padding=ft.Padding.symmetric(horizontal=13, vertical=8),
                        border_radius=20,
                        on_click=lambda _, fs=full_s: (selected_slot.update({"value": fs}), show_dashboard()),
                        ink=True,
                    )
                )
            body.append(ft.Row(slot_chips, spacing=8, scroll=ft.ScrollMode.AUTO))

            # 4 Washing Machines Display
            machines = db.get_machines_status(selected_date["value"], selected_slot["value"])
            body.append(ft.Text("4 Hostel Washing Machines", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK))

            for m_id, m_name, is_maint, booked_by, b_id, booked_name, checked_in in machines:
                if is_maint:
                    pill = status_pill("Maintenance", AMBER_BG, AMBER_FG)
                    icon_bg, icon_fg = AMBER_BG, AMBER_FG
                    sub_text = "Disabled by Warden"
                    action_ctrl = ft.Text("Unavailable", size=12, color=TEXT_MUTED)
                elif booked_by:
                    pill = status_pill("In Use" if checked_in else "Booked", RED_BG, RED_FG)
                    icon_bg, icon_fg = RED_BG, RED_FG
                    owner = "You" if booked_by == current_user["id"] else (booked_name or booked_by)
                    sub_text = f"Reserved by {owner}"
                    action_ctrl = ft.Container(
                        content=ft.Text("Taken", size=12, color=RED_FG, weight=ft.FontWeight.W_600),
                        bgcolor=RED_BG,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                        border_radius=10,
                    )
                else:
                    pill = status_pill("Available", GREEN_BG, GREEN_FG)
                    icon_bg, icon_fg = GREEN_BG, GREEN_FG
                    sub_text = "60-min slot ready"
                    action_ctrl = ft.Container(
                        content=ft.Text("Book", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                        bgcolor=PRIMARY,
                        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                        border_radius=10,
                        on_click=lambda _, mid=m_id: handle_book(mid),
                        ink=True,
                    )

                if is_admin:
                    action_ctrl = ft.Container(
                        content=ft.Text("Enable" if is_maint else "Maintenance", size=11, weight=ft.FontWeight.BOLD, color=GREEN_FG if is_maint else AMBER_FG),
                        bgcolor=GREEN_BG if is_maint else AMBER_BG,
                        border=ft.Border.all(1, "#A7F3D0" if is_maint else "#FDE68A"),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                        border_radius=10,
                        on_click=lambda _, mid=m_id: handle_maintenance(mid),
                        ink=True,
                    )

                body.append(
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=16,
                        padding=13,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(ft.Icons.LOCAL_LAUNDRY_SERVICE, color=icon_fg, size=24),
                                            bgcolor=icon_bg,
                                            padding=10,
                                            border_radius=12,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Row([ft.Text(m_name, size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK), pill], spacing=6),
                                                ft.Text(sub_text, size=12, color=TEXT_MUTED),
                                            ],
                                            spacing=3,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                action_ctrl,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    )
                )

        # ==========================================================
        # TAB 1: WASH / DRAIN / REFILL / DRYING LIVE TIMER
        # ==========================================================
        elif active_tab["index"] == 1:
            stage_idx, stage_name, stage_rem, _ = get_cycle_stage(timer_state["elapsed"])
            total_rem = max(0, TOTAL_CYCLE_SECS - timer_state["elapsed"])
            mins, secs = divmod(total_rem, 60)

            timer_text = ft.Text(f"{mins:02d}:{secs:02d}", size=44, weight=ft.FontWeight.BOLD, color=PRIMARY)
            stage_label = ft.Text(f"Current Stage: {stage_name}", size=15, weight=ft.FontWeight.BOLD, color=TEXT_DARK)
            progress_bar = ft.ProgressBar(value=min(1.0, timer_state["elapsed"] / TOTAL_CYCLE_SECS), color=PRIMARY, bgcolor="#E2E8F0", height=10)

            stage_rows = []
            for idx, (s_name, s_dur) in enumerate(CYCLE_STAGES):
                done = timer_state["elapsed"] >= sum(x[1] for x in CYCLE_STAGES[: idx + 1])
                active = idx == stage_idx and timer_state["elapsed"] < TOTAL_CYCLE_SECS
                stage_rows.append(
                    ft.Container(
                        bgcolor=GREEN_BG if done else ("#EFF6FF" if active else CARD_BG),
                        border=ft.Border.all(1, GREEN_FG if done else (PRIMARY if active else BORDER_COLOR)),
                        border_radius=12,
                        padding=12,
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.CHECK_CIRCLE if done else (ft.Icons.PLAY_CIRCLE_FILLED if active else ft.Icons.RADIO_BUTTON_UNCHECKED),
                                            color=GREEN_FG if done else (PRIMARY if active else TEXT_MUTED),
                                            size=20,
                                        ),
                                        ft.Text(s_name, size=13, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                    ],
                                    spacing=8,
                                ),
                                ft.Text(f"{s_dur // 60} min", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    )
                )

            async def run_timer_loop():
                while timer_state["running"] and timer_state["elapsed"] < TOTAL_CYCLE_SECS:
                    await asyncio.sleep(1)
                    if not timer_state["running"]:
                        break
                    step = 60 if timer_state["demo_fast"] else 1
                    timer_state["elapsed"] = min(TOTAL_CYCLE_SECS, timer_state["elapsed"] + step)
                    if active_tab["index"] == 1:
                        rem = max(0, TOTAL_CYCLE_SECS - timer_state["elapsed"])
                        m_left, s_left = divmod(rem, 60)
                        _, s_name, _, _ = get_cycle_stage(timer_state["elapsed"])
                        timer_text.value = f"{m_left:02d}:{s_left:02d}"
                        stage_label.value = f"Current Stage: {s_name}"
                        progress_bar.value = min(1.0, timer_state["elapsed"] / TOTAL_CYCLE_SECS)
                        page.update()
                if timer_state["elapsed"] >= TOTAL_CYCLE_SECS:
                    timer_state["running"] = False
                    show_msg("Wash cycle complete! Please collect your clothes.", GREEN_FG)
                    if active_tab["index"] == 1:
                        show_dashboard()

            def toggle_timer(e):
                if timer_state["running"]:
                    timer_state["running"] = False
                    show_dashboard()
                else:
                    if timer_state["elapsed"] >= TOTAL_CYCLE_SECS:
                        timer_state["elapsed"] = 0
                    timer_state["running"] = True
                    page.run_task(run_timer_loop)
                    show_dashboard()

            def reset_timer(e):
                timer_state["running"] = False
                timer_state["elapsed"] = 0
                show_dashboard()

            def toggle_fast(e):
                timer_state["demo_fast"] = e.control.value
                show_msg("Demo 60x speed enabled (1 sec = 1 min)" if timer_state["demo_fast"] else "Real-time 1x speed enabled", PRIMARY)

            body.append(
                ft.Container(
                    bgcolor=CARD_BG,
                    border_radius=18,
                    padding=20,
                    border=ft.Border.all(1, BORDER_COLOR),
                    content=ft.Column(
                        [
                            ft.Text("60-MIN LAUNDRY CYCLE TIMER", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                            timer_text,
                            stage_label,
                            progress_bar,
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text("Pause" if timer_state["running"] else "Start Cycle", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                        bgcolor=AMBER_FG if timer_state["running"] else PRIMARY,
                                        padding=ft.Padding.symmetric(horizontal=22, vertical=10),
                                        border_radius=12,
                                        on_click=toggle_timer,
                                        ink=True,
                                    ),
                                    ft.Container(
                                        content=ft.Text("Reset", color=TEXT_DARK, weight=ft.FontWeight.BOLD),
                                        bgcolor="#E2E8F0",
                                        padding=ft.Padding.symmetric(horizontal=18, vertical=10),
                                        border_radius=12,
                                        on_click=reset_timer,
                                        ink=True,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=12,
                            ),
                            ft.Switch(label="Faculty Demo Mode (60x Fast-Forward)", value=timer_state["demo_fast"], on_change=toggle_fast),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
            )
            body.append(ft.Text("Cycle Stages (Wash → Drain → Refill → Drying)", size=13, weight=ft.FontWeight.BOLD, color=TEXT_DARK))
            body.extend(stage_rows)

        # ==========================================================
        # TAB 2: AI SCHEDULING OPTIMIZER & DEMAND PREDICTION
        # ==========================================================
        elif active_tab["index"] == 2:
            rec = ai.recommend_optimal_slot(selected_date["value"])
            preds = ai.predict_slot_demand(selected_date["value"])

            # AI Recommendation Card
            if rec:
                body.append(
                    ft.Container(
                        bgcolor=PURPLE_BG,
                        border=ft.Border.all(1.5, "#C4B5FD"),
                        border_radius=18,
                        padding=16,
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.AUTO_AWESOME, color=PURPLE_FG, size=20),
                                        ft.Text("AI SCHEDULING OPTIMIZER", size=11, weight=ft.FontWeight.BOLD, color=PURPLE_FG),
                                    ],
                                    spacing=6,
                                ),
                                ft.Text(f"Best Pick: {rec['machine_name']} • {rec['short']}", size=17, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                ft.Text(rec["reason"], size=12, color=TEXT_MUTED),
                                ft.Container(
                                    content=ft.Text("One-Tap Smart Book", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, size=13),
                                    bgcolor=PURPLE_FG,
                                    alignment=ft.Alignment.CENTER,
                                    height=40,
                                    border_radius=10,
                                    on_click=lambda _: handle_book(rec["machine_id"], rec["slot"]),
                                    ink=True,
                                ) if not is_admin else ft.Text("Admin View: AI recommends this slot to students.", size=11, color=PURPLE_FG),
                            ],
                            spacing=8,
                        ),
                    )
                )

            # Demand Prediction Chart
            body.append(ft.Text(f"Demand Prediction ({selected_date['value']})", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK))
            chart_rows = []
            for p in preds:
                bar_color = RED_FG if p["level"] == "Peak" else (AMBER_FG if p["level"] == "Moderate" else GREEN_FG)
                bar_bg = RED_BG if p["level"] == "Peak" else (AMBER_BG if p["level"] == "Moderate" else GREEN_BG)
                chart_rows.append(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(p["short"], size=12, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                    status_pill(f"{p['demand_pct']}% • {p['level']}", bar_bg, bar_color),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.ProgressBar(value=p["demand_pct"] / 100.0, color=bar_color, bgcolor="#E2E8F0", height=8),
                        ],
                        spacing=4,
                    )
                )

            body.append(
                ft.Container(
                    bgcolor=CARD_BG,
                    border_radius=16,
                    padding=16,
                    border=ft.Border.all(1, BORDER_COLOR),
                    content=ft.Column(chart_rows, spacing=12),
                )
            )

        # ==========================================================
        # TAB 3: DAMAGE REPORTING & WARDEN LIVE MANAGEMENT
        # ==========================================================
        else:
            if not is_admin:
                # Student Machine Damage Reporting Form
                machines_list = db.get_all_machines()
                sel_m = {"id": machines_list[0][0]}
                sel_issue = {"val": "Not Draining Water"}
                desc_field = styled_field("Issue Details", "Describe the problem briefly...", ft.Icons.DESCRIPTION_OUTLINED, multiline=True)

                m_chips = []
                for mid, mname, _ in machines_list:
                    m_chips.append(
                        ft.Container(
                            content=ft.Text(mname, size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if sel_m["id"] == mid else TEXT_DARK),
                            bgcolor=PRIMARY if sel_m["id"] == mid else "#F1F5F9",
                            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                            border_radius=10,
                            on_click=lambda _, m=mid: (sel_m.update({"id": m}), show_msg(f"Selected Machine 0{m}", PRIMARY)),
                        )
                    )

                def submit_report(e):
                    if not desc_field.value:
                        show_msg("Please enter a short description of the issue.", RED_FG)
                        return
                    db.submit_damage_report(current_user["id"], sel_m["id"], sel_issue["val"], desc_field.value)
                    show_msg("Damage report sent to Hostel Warden!", GREEN_FG)
                    show_dashboard()

                body.append(
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=16,
                        padding=16,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            [
                                ft.Text("Report Machine Damage", size=15, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                ft.Text("Select Machine:", size=12, color=TEXT_MUTED),
                                ft.Row(m_chips, spacing=6, scroll=ft.ScrollMode.AUTO),
                                desc_field,
                                ft.Container(
                                    content=ft.Text("Submit Damage Report", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                    bgcolor=RED_FG,
                                    alignment=ft.Alignment.CENTER,
                                    height=44,
                                    border_radius=12,
                                    on_click=submit_report,
                                    ink=True,
                                ),
                            ],
                            spacing=10,
                        ),
                    )
                )
            else:
                # Warden Live Damage Reports Queue
                reports = db.get_damage_reports()
                body.append(ft.Text("Warden: Machine Damage Reports", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK))
                if not reports:
                    body.append(ft.Text("No damage reports filed.", size=12, color=TEXT_MUTED))
                for r_id, m_name, m_id, u_name, s_id, issue_type, desc, r_status, created_at in reports:
                    is_open = r_status == "open"
                    body.append(
                        ft.Container(
                            bgcolor=CARD_BG,
                            border_radius=14,
                            padding=12,
                            border=ft.Border.all(1, "#FECACA" if is_open else BORDER_COLOR),
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(f"{m_name} • {u_name}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                            status_pill("Open" if is_open else "Resolved", RED_BG if is_open else GREEN_BG, RED_FG if is_open else GREEN_FG),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Text(desc, size=12, color=TEXT_MUTED),
                                    ft.Row(
                                        [
                                            ft.Container(
                                                content=ft.Text("Mark Resolved", size=11, color=GREEN_FG, weight=ft.FontWeight.BOLD),
                                                bgcolor=GREEN_BG,
                                                padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                                                border_radius=8,
                                                on_click=lambda _, rid=r_id: handle_resolve_report(rid),
                                            ),
                                            ft.Container(
                                                content=ft.Text("Toggle Maintenance", size=11, color=AMBER_FG, weight=ft.FontWeight.BOLD),
                                                bgcolor=AMBER_BG,
                                                padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                                                border_radius=8,
                                                on_click=lambda _, mid=m_id: handle_maintenance(mid),
                                            ),
                                        ],
                                        spacing=8,
                                    ) if is_open else ft.Container(),
                                ],
                                spacing=6,
                            ),
                        )
                    )

            # Booking History / Warden All Bookings
            history = db.get_booking_history(current_user["id"], current_user["role"])
            body.append(ft.Text("All Hostel Bookings" if is_admin else "My Booking History", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK))
            for b_id, u_name, s_id, m_name, b_date, s_time, status, created_at in history[:12]:
                p_bg = GREEN_BG if status in ("active", "completed") else RED_BG
                p_fg = GREEN_FG if status in ("active", "completed") else RED_FG
                body.append(
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=12,
                        padding=12,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(f"{m_name} • {b_date}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
                                        ft.Text(f"{s_time} • {u_name}" if is_admin else s_time, size=11, color=TEXT_MUTED),
                                    ],
                                    spacing=2,
                                ),
                                ft.Column(
                                    [
                                        status_pill(status.title(), p_bg, p_fg),
                                        ft.Container(
                                            content=ft.Text("Cancel", size=11, color=RED_FG, weight=ft.FontWeight.BOLD),
                                            on_click=lambda _, bid=b_id: handle_cancel(bid),
                                        ) if (status == "active" and is_admin) else ft.Container(),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=4,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    )
                )

        content_area = ft.Container(
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            content=ft.Column(body, spacing=12),
        )
        page.add(ft.Column([top_bar, tab_bar, content_area], spacing=0))

    show_login()


ft.run(main)
