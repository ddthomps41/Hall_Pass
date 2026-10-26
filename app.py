"""
Hall Pass Tracker — Streamlit app
For Mrs. Alvarez, Foundations of Business Communication and Technology.

This version fixes the exact problems with the Canva "Classroom Made Easy"
hall pass tracker:
  * ONE tracker per period — no more cramming every class into one sheet.
  * NO student limit — each period has its own roster, as large as needed.
  * NAMES ARE SAVED — rosters are stored automatically, so she never has
    to re-type them every time she opens the app.
  * LOGS ARE SAVED — every returned pass is stored automatically.
  * CSV EXPORT, built in — a download button for this period's log, and
    one for all periods combined.

How saving works:
  Everything is saved automatically to `hall_pass_data.json` in the same
  folder as this app, every time something changes (sign out, return,
  roster edit, roster upload, new period, ...).
  - Run on her own computer: the file stays there between opens. Done.
  - Deployed to Streamlit Cloud: the file can reset when the app
    restarts or redeploys, so use the sidebar "Download backup" button
    regularly, and "Upload backup" to restore it. The CSV exports are
    the permanent record of the logs.

Run it:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import streamlit as st


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Hall Pass Tracker",
    page_icon="🎫",
    layout="wide",
)

DATA_FILE = Path(__file__).resolve().parent / "hall_pass_data.json"
LOGO_FILE = Path(__file__).resolve().parent / "assets" / "school-logo.png"

# Theme name -> (header background, header text). Rattler Red & White is
# the Rio Grande City High School theme and the default.
THEME_STYLES = {
    "Rattler Red & White": ("#b01e28", "#ffffff"),
    "Sunshine Yellow": ("#f6c453", "#1f2937"),
    "Sky Blue": ("#6cb4ee", "#1f2937"),
    "Coral Pink": ("#ff8fab", "#1f2937"),
    "Mint Green": ("#7ac74f", "#1f2937"),
    "Lavender": ("#b197fc", "#1f2937"),
}

PASS_TYPES = {
    "Restroom": ("🚻", 10),
    "Drink Water": ("💧", 5),
    "Nurse": ("🩺", 15),
    "Office": ("🏫", 15),
    "Library": ("📚", 20),
    "Counselor": ("🗣️", 15),
    "Cafeteria": ("🍎", 15),
    "Locker": ("🔒", 10),
    "Other": ("📝", 10),
}

SAMPLE_ROSTER = """Ava
Liam
Maya
Noah
Sofia
Ethan
Isabella
Lucas
Amelia
Mason"""


# ---------------------------------------------------------------------------
# Persistence: load / save
# ---------------------------------------------------------------------------
def default_data():
    periods = {"Period 1": {"roster": SAMPLE_ROSTER, "roster_version": 0, "out_now": [], "log": []}}
    for n in range(2, 10):
        periods[f"Period {n}"] = {"roster": "", "roster_version": 0, "out_now": [], "log": []}
    return {
        "teacher": "Mrs. Alvarez",
        "subject": "Foundations of Business Communication and Technology",
        "school": "Rio Grande City High School",
        "theme": "Rattler Red & White",
        "settings_password_hash": "",
        "max_out": 2,
        "current_period": "Period 1",
        "periods": periods,
    }


def _blank_period():
    return {"roster": "", "roster_version": 0, "out_now": [], "log": []}


def _normalise(raw):
    """Merge a loaded file onto the defaults so old / partial files work."""
    data = default_data()
    if not isinstance(raw, dict):
        return data
    for key in ("teacher", "subject", "school", "theme", "max_out", "current_period", "settings_password_hash"):
        if key in raw:
            data[key] = raw[key]
    if isinstance(raw.get("periods"), dict) and raw["periods"]:
        data["periods"] = {}
        for name, period in raw["periods"].items():
            if not isinstance(period, dict):
                continue
            entry = _blank_period()
            entry["roster"] = period.get("roster", "")
            entry["roster_version"] = period.get("roster_version", 0)
            entry["log"] = period.get("log", []) or []
            # out_now times were stored as ISO strings; parse them back.
            out_now = []
            for item in period.get("out_now", []) or []:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                try:
                    item["time_out"] = datetime.fromisoformat(item["time_out"])
                except Exception:
                    continue
                out_now.append(item)
            entry["out_now"] = out_now
            data["periods"][name] = entry
    if data["current_period"] not in data["periods"]:
        data["current_period"] = next(iter(data["periods"]))
    return data


def load_data():
    try:
        return _normalise(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    except Exception:
        return default_data()


def serialisable(data):
    """Copy of the data with datetimes converted for JSON storage."""
    out = json.loads(json.dumps(data, default=str))
    # json.dumps with default=str already turned datetimes into ISO strings.
    return out


def save_data(data):
    try:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(serialisable(data), indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
        return True
    except Exception:
        return False


if "data" not in st.session_state:
    st.session_state.data = load_data()
data = st.session_state.data


# Modern, clean look for high school — Canva-cute, but grown up:
# rounded cards, soft shadows, big touch-friendly buttons, no clutter.
st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif; }
    .stButton > button, .stDownloadButton > button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1rem !important;
        border: 1px solid #e5e7eb !important;
    }
    .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
        background-color: #b01e28 !important;
        border-color: #b01e28 !important;
        color: #ffffff !important;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #f0e3e4;
        border-radius: 16px;
        padding: 0.75rem 1rem;
        box-shadow: 0 2px 10px rgba(176, 30, 40, 0.06);
    }
    div[data-testid="stMetricLabel"] { color: #6b7280; font-weight: 600; }
    div[data-testid="stExpander"] { border-radius: 14px; }
    .stTextInput input, .stSelectbox > div, .stTextArea textarea {
        border-radius: 12px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_roster_file(text, filename):
    """Student names from a .txt (one per line) or .csv export."""
    seen, names = set(), []

    def add(name):
        name = " ".join(str(name).split()).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    if filename.lower().endswith(".csv"):
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return names
        header = [cell.strip().lower() for cell in rows[0]]
        header_words = {"student", "name", "student name", "full name", "first name", "last name"}
        has_header = any(cell in header_words for cell in header)
        data_rows = rows[1:] if has_header else rows
        first_idx = last_idx = name_idx = None
        if has_header:
            for i, cell in enumerate(header):
                if cell in ("student", "name", "student name", "full name"):
                    name_idx = i
                elif cell == "first name":
                    first_idx = i
                elif cell == "last name":
                    last_idx = i
        for row in data_rows:
            cells = [cell.strip() for cell in row]
            if first_idx is not None and last_idx is not None:
                if first_idx < len(cells) and last_idx < len(cells):
                    add(f"{cells[first_idx]} {cells[last_idx]}")
            elif name_idx is not None and name_idx < len(cells):
                add(cells[name_idx])
            else:
                for cell in cells:
                    if cell:
                        add(cell)
                        break
    else:
        for line in text.splitlines():
            add(line)
    return names


def roster_names(roster_text):
    seen, names = set(), []
    for line in roster_text.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def fmt_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def elapsed_minutes(time_out):
    return int((datetime.now() - time_out).total_seconds() // 60)


def log_to_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["Period", "Student", "Destination", "Date", "Time Out", "Time In", "Minutes"],
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def all_log_rows():
    rows = []
    for period_name, period in data["periods"].items():
        for entry in period["log"]:
            row = {"Period": period_name}
            row.update(entry)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Sidebar — classroom setup, period picker, roster, backup
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Classroom Setup")

    # Roster password gate: kids at the classroom computer can sign out
    # on the main page, but they cannot change a roster without this.
    # This is a classroom deterrent, not bank-grade security — the hash
    # lives in hall_pass_data.json, and there is no forgot-password reset
    # in the app, so the teacher should write the password down.
    if "teacher_unlocked" not in st.session_state:
        st.session_state.teacher_unlocked = False
    _pw_hash = data.get("settings_password_hash", "")
    if not _pw_hash:
        st.caption("Set a password to lock roster changes. Do this once — write it down.")
        _new_pw = st.text_input("Set roster password", type="password", key="set_pw")
        _new_pw2 = st.text_input("Confirm roster password", type="password", key="set_pw2")
        if st.button("Set password", use_container_width=True):
            if not _new_pw or _new_pw != _new_pw2:
                st.error("Passwords do not match, or are blank.")
            else:
                data["settings_password_hash"] = hashlib.sha256(_new_pw.encode()).hexdigest()
                st.session_state.teacher_unlocked = True
                save_data(data)
                st.rerun()
        teacher_unlocked = False
    elif not st.session_state.teacher_unlocked:
        st.caption("Roster changes are locked.")
        _pw_try = st.text_input("Teacher password to unlock roster changes", type="password", key="unlock_pw")
        if st.button("Unlock roster", use_container_width=True):
            if hashlib.sha256(_pw_try.encode()).hexdigest() == _pw_hash:
                st.session_state.teacher_unlocked = True
                st.rerun()
            else:
                st.error("Wrong password.")
        teacher_unlocked = False
    else:
        teacher_unlocked = True
        if st.button("Lock roster", use_container_width=True):
            st.session_state.teacher_unlocked = False
            st.rerun()
        _change_pw = st.text_input("Change roster password", type="password", key="change_pw")
        if st.button("Save new password", use_container_width=True):
            if _change_pw:
                data["settings_password_hash"] = hashlib.sha256(_change_pw.encode()).hexdigest()
                save_data(data)
                st.success("Password changed.")

    teacher = st.text_input("Teacher's name", value=data["teacher"])
    if teacher != data["teacher"]:
        data["teacher"] = teacher
        save_data(data)
    subject = st.text_input("Class / subject", value=data["subject"])
    if subject != data["subject"]:
        data["subject"] = subject
        save_data(data)
    school = st.text_input("School", value=data["school"])
    if school != data["school"]:
        data["school"] = school
        save_data(data)
    theme_names = list(THEME_STYLES.keys())
    theme = st.selectbox(
        "Classroom color theme",
        theme_names,
        index=theme_names.index(data["theme"]) if data["theme"] in theme_names else 0,
    )
    if theme != data["theme"]:
        data["theme"] = theme
        save_data(data)
    st.caption("Current logo: the RGC Rattlers logo, in the header.")
    logo_upload = st.file_uploader(
        "Replace school logo", type=["png", "jpg", "jpeg"], key="logo_upload"
    )
    if logo_upload is not None:
        logo_hash = hashlib.sha256(logo_upload.getvalue()).hexdigest()
        if logo_hash != st.session_state.get("logo_upload_hash"):
            LOGO_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOGO_FILE.write_bytes(logo_upload.getvalue())
            st.session_state["logo_upload_hash"] = logo_hash
            st.success("Logo updated.")
            st.rerun()
    max_out = st.number_input(
        "How many students can be out at once (per period)?",
        min_value=1, max_value=10, value=int(data["max_out"]),
    )
    if int(max_out) != int(data["max_out"]):
        data["max_out"] = int(max_out)
        save_data(data)

    st.divider()
    st.subheader("Period")
    st.caption("One tracker per period — each keeps its own roster and log.")
    period_names = list(data["periods"].keys())
    current_period = st.selectbox(
        "Which period is this?",
        period_names,
        index=period_names.index(data["current_period"]),
    )
    if current_period != data["current_period"]:
        data["current_period"] = current_period
        save_data(data)
        st.rerun()

    with st.expander("Add / rename / delete a period"):
        new_name = st.text_input("New period name", placeholder="e.g. Period 7, 1st Period")
        if st.button("Add period", use_container_width=True):
            if not new_name.strip():
                st.error("Give the period a name first.")
            elif new_name.strip() in data["periods"]:
                st.error("That period already exists.")
            else:
                data["periods"][new_name.strip()] = _blank_period()
                data["current_period"] = new_name.strip()
                save_data(data)
                st.rerun()
        rename_to = st.text_input("Rename this period to", value=current_period)
        if st.button("Rename period", use_container_width=True):
            if rename_to.strip() and rename_to.strip() != current_period:
                if rename_to.strip() in data["periods"]:
                    st.error("That period name is already taken.")
                else:
                    rebuilt = {}
                    for name, period in data["periods"].items():
                        rebuilt[rename_to.strip() if name == current_period else name] = period
                    data["periods"] = rebuilt
                    data["current_period"] = rename_to.strip()
                    save_data(data)
                    st.rerun()
        if len(period_names) > 1:
            if st.session_state.get("confirm_delete") == current_period:
                st.warning(f"Delete {current_period} and its roster + log for good?")
                if st.button("Yes, delete this period", use_container_width=True):
                    del data["periods"][current_period]
                    data["current_period"] = next(iter(data["periods"]))
                    st.session_state.pop("confirm_delete", None)
                    save_data(data)
                    st.rerun()
                if st.button("Keep it", use_container_width=True):
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()
            elif st.button("Delete this period", use_container_width=True):
                st.session_state["confirm_delete"] = current_period
                st.rerun()

    st.divider()
    st.subheader(f"Roster — {current_period}")
    st.caption("No student limit. Upload a new roster whenever it changes — it replaces this period's list, and it's saved automatically.")
    period = data["periods"][current_period]

    if teacher_unlocked:
        uploaded = st.file_uploader(
            f"Upload {current_period} roster",
            type=["csv", "txt"],
            key=f"roster_upload_{current_period}",
            help="A .txt file with one student per line, or a .csv export with a Student / Name column (or First + Last Name columns).",
        )
        if uploaded is not None:
            file_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()
            if file_hash != st.session_state.get(f"roster_upload_hash_{current_period}"):
                try:
                    uploaded_text = uploaded.getvalue().decode("utf-8-sig")
                except UnicodeDecodeError:
                    uploaded_text = uploaded.getvalue().decode("latin-1")
                names = parse_roster_file(uploaded_text, uploaded.name)
                if names:
                    period["roster"] = "\n".join(names)
                    period["roster_version"] = period.get("roster_version", 0) + 1
                    st.session_state[f"roster_upload_hash_{current_period}"] = file_hash
                    save_data(data)
                    st.success(f"{len(names)} students loaded from {uploaded.name} — and saved.")
                    st.rerun()
                else:
                    st.error(f"Couldn't find any student names in {uploaded.name}.")
    else:
        st.info("Roster is locked. Enter the teacher password at the top of the sidebar to change it.")
        if period["roster"]:
            st.code(period["roster"])
        else:
            st.caption("No roster loaded for this period yet.")
    st.download_button(
        "Roster template (CSV)",
        data="Student\n",
        file_name="roster-template.csv",
        mime="text/csv",
    )
    st.caption("Or edit names directly — one student per line. Edits save automatically.")
    if teacher_unlocked:
        roster_key = f"roster_{current_period}_{period.get('roster_version', 0)}"
        if roster_key not in st.session_state:
            st.session_state[roster_key] = period["roster"]
        st.text_area("Students", height=220, label_visibility="collapsed", key=roster_key)
        if st.session_state[roster_key] != period["roster"]:
            period["roster"] = st.session_state[roster_key]
            save_data(data)
    else:
        st.caption("Unlock the roster at the top of the sidebar to edit names directly.")

    st.divider()
    st.divider()
    st.subheader("Saved data")
    st.caption(
        "Rosters and logs save automatically to hall_pass_data.json. "
        "Download a backup regularly — especially if this runs on Streamlit Cloud, "
        "where the saved file can reset on a restart."
    )
    st.download_button(
        "Download backup (all periods)",
        data=json.dumps(serialisable(data), indent=2),
        file_name="hall-pass-backup.json",
        mime="application/json",
        use_container_width=True,
    )
    backup = st.file_uploader("Upload backup to restore", type=["json"], key="backup_upload")
    if backup is not None:
        backup_hash = hashlib.sha256(backup.getvalue()).hexdigest()
        if backup_hash != st.session_state.get("backup_hash"):
            try:
                restored = _normalise(json.loads(backup.getvalue().decode("utf-8")))
                st.session_state.data = restored
                st.session_state["backup_hash"] = backup_hash
                save_data(restored)
                st.success("Backup restored.")
                st.rerun()
            except Exception:
                st.error("That backup file couldn't be read.")

    st.divider()
    if not teacher_unlocked:
        st.caption("Start a new day is locked with the roster password.")
    elif st.button("Start a new day (this period only)", use_container_width=True):
        period["out_now"] = []
        period["log"] = []
        save_data(data)
        st.rerun()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
period = data["periods"][data["current_period"]]
accent, header_text = THEME_STYLES.get(data["theme"], ("#b01e28", "#ffffff"))

logo_html = ""
if LOGO_FILE.exists():
    logo_b64 = base64.b64encode(LOGO_FILE.read_bytes()).decode()
    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" '
        'style="height:88px; width:auto; background:#ffffff; '
        'border-radius:16px; padding:6px; box-shadow:0 4px 14px rgba(0,0,0,0.18);" '
        'alt="School logo" />'
    )
rattler_tag = (
    '<span style="background:#ffffff; color:#b01e28; padding:0.2rem 0.7rem; '
    'border-radius:999px; font-weight:700; font-size:0.85rem;">🐍 Go Rattlers!</span>'
    if "Rio Grande" in data["school"]
    else ""
)

st.markdown(
    f"""
    <div style="background:{accent}; color:{header_text}; padding:1.25rem 1.5rem; border-radius:20px; box-shadow:0 8px 24px rgba(176,30,40,0.18);">
      <div style="display:flex; align-items:center; gap:1.25rem; flex-wrap:wrap;">
        {logo_html}
        <div style="flex:1; min-width:240px;">
          <h1 style="margin:0; font-size:2rem; letter-spacing:-0.5px;">Hall Pass Tracker</h1>
          <p style="margin:0.35rem 0 0; font-size:1.05rem; opacity:0.95;">
            <b>{data['teacher']}'s Classroom</b> &nbsp;·&nbsp; {data['subject']}
            {f" &nbsp;·&nbsp; {data['school']}" if data['school'] else ""}
          </p>
          <p style="margin:0.6rem 0 0; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap;">
            <span style="background:#ffffff; color:{accent}; padding:0.25rem 0.9rem; border-radius:999px; font-weight:700;">{data['current_period']}</span>
            {rattler_tag}
          </p>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

# ---------------------------------------------------------------------------
# Stats for this period
# ---------------------------------------------------------------------------
students = roster_names(period["roster"])
out_now = period["out_now"]
log = period["log"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Out right now", f"{len(out_now)} / {data['max_out']}")
col2.metric("Passes today (this period)", len(log) + len(out_now))
if log:
    avg = sum(entry["Minutes"] for entry in log) / len(log)
    col3.metric("Average time out", f"{avg:.0f} min")
else:
    col3.metric("Average time out", "—")
col4.metric(f"Students on roster ({data['current_period']})", len(students))

# At the top, right beside the Out Right Now number: the names of who is out.
if out_now:
    out_summary = ", ".join(
        f"{entry['student']} → {entry['destination']}" for entry in out_now
    )
    st.markdown(
        f"""
        <div style="background:#fff1f2; border:1px solid #fecdd3; border-radius:14px;
                    padding:0.7rem 1rem; margin-top:0.5rem;">
          <b>Out right now ({len(out_now)} / {data['max_out']}):</b> {out_summary}
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.expander("All periods at a glance"):
    overview = [
        {
            "Period": name,
            "Students": len(roster_names(p["roster"])),
            "Out now": len(p["out_now"]),
            "Passes logged": len(p["log"]),
        }
        for name, p in data["periods"].items()
    ]
    st.dataframe(overview, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Who's out now + sign out (this period only)
# ---------------------------------------------------------------------------
left, right = st.columns([1.15, 1])

with left:
    st.subheader(f"Who's Out Right Now — {data['current_period']} ({len(out_now)})")
    if out_now:
        st.caption("Out: " + ", ".join(entry["student"] for entry in out_now))
    if st.button("↻ Refresh timers"):
        st.rerun()

    if not out_now:
        st.success("Everyone is in class! No passes are out right now.")
    else:
        for i, entry in enumerate(list(out_now)):
            # Custom written destinations aren't in PASS_TYPES — default to 📝 / 10 min.
            emoji, limit = PASS_TYPES.get(entry["destination"], ("📝", 10))
            mins = elapsed_minutes(entry["time_out"])
            overdue = mins > limit
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"### {i + 1}. {emoji} {entry['student']}")
                    st.write(f"**Going to:** {entry['destination']}  ·  **Left at:** {fmt_time(entry['time_out'])}")
                    if entry.get("note"):
                        st.write(f"📝 {entry['note']}")
                    if overdue:
                        st.error(f"⏰ Out for {mins} min — over the {limit} min limit!")
                    elif mins >= limit - 2:
                        st.warning(f"⏰ Out for {mins} min — almost at the {limit} min limit.")
                    else:
                        st.write(f"Out for {mins} min (limit: {limit} min)")
                with c2:
                    if st.button("✅ Back!", key=f"back_{i}", use_container_width=True):
                        time_in = datetime.now()
                        period["log"].append(
                            {
                                "Student": entry["student"],
                                "Destination": entry["destination"],
                                "Date": time_in.strftime("%Y-%m-%d"),
                                "Time Out": fmt_time(entry["time_out"]),
                                "Time In": fmt_time(time_in),
                                "Minutes": elapsed_minutes(entry["time_out"]),
                            }
                        )
                        period["out_now"].pop(i)
                        save_data(data)
                        st.rerun()

with right:
    st.subheader("Sign Out a Pass")

    already_out = {entry["student"] for entry in out_now}
    available = [name for name in students if name not in already_out]

    if len(out_now) >= int(data["max_out"]):
        st.warning(
            f"⚠️ {data['max_out']} student(s) are already out — that's the limit for this period. "
            "Wait for someone to return before signing out another pass."
        )
    elif not available:
        st.info(
            f"No students available to sign out in {data['current_period']} yet. "
            "Upload that period's roster in the sidebar, or add names there."
        )
    else:
        with st.form("sign_out", clear_on_submit=True):
            student = st.selectbox("Student", available)
            destination = st.selectbox("Where are they going?", list(PASS_TYPES.keys()))
            emoji, limit = PASS_TYPES[destination]
            st.caption(f"{emoji} Suggested limit for {destination}: {limit} minutes")
            custom_destination = st.text_input(
                "Or write where they're going",
                placeholder="e.g. Drink water, Restroom, Nurse, Front office, Room 204…",
                help="If you write something here, it will be used instead of the choice above, and it will show up in the log and the CSV export.",
            )
            note = st.text_input("Note (optional)", placeholder="e.g. with a buddy, feeling sick")
            submitted = st.form_submit_button("Sign Out", use_container_width=True, type="primary")
            if submitted:
                final_destination = custom_destination.strip() or destination
                period["out_now"].append(
                    {
                        "student": student,
                        "destination": final_destination,
                        "time_out": datetime.now(),
                        "note": note.strip(),
                    }
                )
                save_data(data)
                st.success(f"{student} signed out to {final_destination}.")
                st.rerun()

    st.divider()
    st.subheader("Quick rules")
    st.write(
        f"""
        - Only **{data['max_out']}** student(s) out at a time, per period
        - Restroom: 10 min · Drink Water: 5 min · Nurse / Office / Counselor / Cafeteria: 15 min · Library: 20 min · Locker: 10 min
        - Or write your own destination in the box — it will be saved in the log and the CSV
        - Sign back in with the **Back!** button when you return
        - Switch periods in the sidebar — each period's names and log stay separate
        """
    )

# ---------------------------------------------------------------------------
# Log + CSV export (embedded buttons)
# ---------------------------------------------------------------------------
st.divider()
st.subheader(f"Pass Log — {data['current_period']}")

if log:
    st.dataframe(log, use_container_width=True, hide_index=True)
else:
    st.caption("No completed passes yet in this period. Returned passes will show up here — and stay saved.")

today = datetime.now().strftime("%Y-%m-%d")
period_slug = data["current_period"].replace(" ", "_")
if not all_log_rows():
    st.caption("The all-periods export will activate once any period has a logged pass.")
export_left, export_right = st.columns(2)
with export_left:
    st.download_button(
        "Export this period's log (CSV)",
        data=log_to_csv([{"Period": data["current_period"], **entry} for entry in log]),
        file_name=f"hall-pass-log-{period_slug}-{today}.csv",
        mime="text/csv",
        use_container_width=True,
        type="primary",
    )
with export_right:
    all_rows = all_log_rows()
    st.download_button(
        "Export ALL periods' log (CSV)",
        data=log_to_csv(all_rows),
        file_name=f"hall-pass-log-all-periods-{today}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not all_rows,
    )
