"""준영이의 공부 기록장 · streamlit run app.py
GitHub에 app.py와 requirements.txt를 업로드하고 Streamlit에서 app.py를 실행하세요.
처음 접속하면 앱 화면에서 가족/부모님 비밀번호를 직접 설정할 수 있습니다.
최초 설정 전에 URL을 공유하지 마세요. 비밀번호는 소금값을 포함한 PBKDF2 해시로 저장됩니다.

선택 사항: 앱 Secrets 또는 환경 변수
APP_URL = "https://실제앱주소.streamlit.app"  # QR 생성용
DATABASE_URL = "postgresql+psycopg://사용자:비밀번호@호스트:5432/DB이름?sslmode=require"
외부 DB 미연결 시 임시 SQLite이므로 재배포/재시작에 기록과 비밀번호가 사라질 수 있습니다.
최초 실행 때만 FAMILY_PASSWORD / PARENT_PIN 설정으로 화면 설정을 대체할 수도 있습니다.
GitHub에는 비밀번호·사진·DB 파일을 올리지 마세요.
알림은 앱 내부 알림입니다. 푸시/SMS 및 기프티콘 자동 구매·발송은 지원하지 않습니다.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import html
import io
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import qrcode
import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String,
                        Text, LargeBinary, UniqueConstraint, select, insert, update,
                        delete, func)
from sqlalchemy.exc import IntegrityError

st.set_page_config(page_title="준영이의 공부 기록장", page_icon="🌱", layout="centered")
KST = ZoneInfo("Asia/Seoul")

def today():
    return datetime.now(KST).date()

def now():
    return datetime.now(KST).isoformat(timespec="seconds")

def config(key, default=""):
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.environ.get(key, default)

def safe(value):
    return html.escape(str(value))

st.markdown("""<style>
.stApp {background:#fbf8f2;color:#263c36;}
.block-container {max-width:900px;padding-top:2rem;padding-bottom:4rem;}
h1,h2,h3 {color:#244b3e;letter-spacing:-.04em;}
.hero {background:#e7f0df;border-radius:28px;padding:34px 26px;margin-bottom:20px;}
.hero .eyebrow {font-size:.8rem;letter-spacing:.15em;color:#436c4b;font-weight:700;}
.hero h1 {font-size:2.5rem;line-height:1.25;margin:14px 0;}
.hero p {color:#3c584a;line-height:1.8;}
.card {background:white;border:1px solid #e0e6da;border-radius:20px;padding:20px;margin:12px 0;}
.box {background:#fff0cb;border:2px dashed #b78631;border-radius:24px;text-align:center;padding:30px;margin:16px 0;}
.box .emoji {font-size:3.4rem;}
.calendar {display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px;margin:12px 0;}
.day {border-radius:12px;min-height:76px;padding:7px 4px;background:#fff;border:1px solid #dce2d8;text-align:center;font-size:.82rem;}
.day .num {font-weight:700;display:block;margin-bottom:6px;}
.day .label {font-size:.68rem;word-break:keep-all;}
.day.today {outline:2px solid #35654e;outline-offset:-2px;}
.day.approved {background:#d8edc9;color:#204d2e;border-color:#97bb81;}
.day.pending {background:#fff0bc;color:#664a04;border-color:#d9bb5e;}
.day.retry {background:#ffe0d4;color:#813e28;border-color:#e4aa92;}
.day.missing {background:#ecebe7;color:#595c55;}
.day.future {background:#f7f7f3;color:#777;}
.weekday {text-align:center;font-size:.75rem;font-weight:700;color:#596558;padding:8px 0;}
.blank {visibility:hidden;}
.legend {font-size:.78rem;line-height:1.8;color:#4c5d50;}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"] {background:#35654e;border:0;border-radius:14px;}
[data-testid="stMetric"] {background:white;border-radius:16px;padding:14px;border:1px solid #e0e6da;}
@media(max-width:480px){.hero{padding:24px 18px}.hero h1{font-size:2rem}.day{min-height:66px;padding:5px 2px}.day .label{font-size:.58rem}.calendar{gap:3px}}
</style>""", unsafe_allow_html=True)



def password_gate():
    # 로그인 후에도 설정 변경 시 이전 인증은 무효화됩니다.
    digest = hashlib.sha256(family_password.encode()).hexdigest()
    if st.session_state.get("family_auth") == digest:
        return
    st.markdown('<div class="hero"><div class="eyebrow">OUR LITTLE STUDY GARDEN</div><h1>🌱 준영이의<br>공부·건강 기록장</h1><p>오늘의 작은 공부가 모여<br>두근두근 선물이 되는 곳!</p></div>', unsafe_allow_html=True)
    locked_until = st.session_state.get("family_lock", 0)
    if time.time() < locked_until:
        st.warning("잠깐 쉬었다가 1분 후 다시 입력해 주세요.")
        st.stop()
    with st.form("family_login"):
        pw = st.text_input("우리 가족 비밀번호", type="password")
        ok = st.form_submit_button("가족 확인하기", type="primary", use_container_width=True)
    if ok:
        if verify_password(pw, family_password):
            st.session_state.family_auth = digest
            st.session_state.family_attempts = 0
            st.rerun()
        else:
            tries = st.session_state.get("family_attempts", 0) + 1
            st.session_state.family_attempts = tries
            if tries % 5 == 0:
                st.session_state.family_lock = time.time() + 60
            st.error("비밀번호를 다시 확인해 주세요.")
    st.caption("가족 비밀번호로 입장해 주세요. QR이나 비밀번호를 공개하지 마세요.")
    st.stop()


@st.cache_resource
def database(url):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)
    meta = MetaData()
    campaigns = Table("jy_campaigns", meta,
        Column("id", Integer, primary_key=True),
        Column("start_day", String(10), nullable=False),
        Column("goal", Integer, nullable=False),
        Column("reward", String(200), nullable=False),
        Column("mission", String(300), nullable=False),
        Column("opened_at", String(40)),
        Column("created_at", String(40), nullable=False))
    entries = Table("jy_entries", meta,
        Column("id", Integer, primary_key=True),
        Column("campaign_id", Integer, nullable=False),
        Column("day", String(10), nullable=False),
        Column("mission", String(300), nullable=False),
        Column("status", String(20), nullable=False),
        Column("photo", LargeBinary, nullable=False),
        Column("note", Text, nullable=False),
        Column("feedback", String(300), nullable=False),
        Column("created_at", String(40), nullable=False),
        Column("reviewed_at", String(40)),
        UniqueConstraint("campaign_id", "day", name="jy_one_entry_per_day"))
    missions = Table("jy_missions", meta,
        Column("id", Integer, primary_key=True),
        Column("campaign_id", Integer, nullable=False),
        Column("day", String(10), nullable=False),
        Column("mission", String(300), nullable=False),
        UniqueConstraint("campaign_id", "day", name="jy_one_mission_per_day"))
    meta.create_all(engine)
    return engine, campaigns, entries, missions

url = config("DATABASE_URL", "sqlite:///junyoung_study.db")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
try:
    engine, campaigns, entries, missions = database(url)
except Exception:
    st.error("저장소에 연결하지 못했어요. 부모님이 DATABASE_URL과 연결 권한을 확인해 주세요.")
    st.stop()


# 최초 설정도 앱 안에서 처리합니다. Secrets 메뉴는 선택 사항입니다.
auth_meta = MetaData()
auth_table = Table("jy_auth_settings", auth_meta,
    Column("id", Integer, primary_key=True),
    Column("family_hash", String(300), nullable=False),
    Column("parent_hash", String(300), nullable=False))
auth_meta.create_all(engine)


def encode_password(value):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), bytes.fromhex(salt), 300000).hex()
    return salt + "$" + digest


def verify_password(value, encoded):
    try:
        salt, expected = encoded.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", value.encode(), bytes.fromhex(salt), 300000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


with engine.connect() as c:
    auth = c.execute(select(auth_table).where(auth_table.c.id == 1)).mappings().first()
if auth is None:
    configured_family = config("FAMILY_PASSWORD")
    configured_parent = config("PARENT_PIN")
    if len(configured_family) >= 4 and len(configured_parent) >= 6 and configured_family != configured_parent:
        try:
            with engine.begin() as c:
                c.execute(insert(auth_table).values(id=1, family_hash=encode_password(configured_family), parent_hash=encode_password(configured_parent)))
        except IntegrityError:
            pass
        st.rerun()
    st.title("🌱 준영이의 공부 기록장")
    st.subheader("처음 한 번만, 여기서 비밀번호를 정해 주세요")
    st.info("다른 설정 메뉴로 갈 필요 없어요. 부모님이 아래 칸에 직접 입력하면 됩니다.")
    st.warning("최초 설정은 부모님이 해 주세요. 설정이 끝나기 전에는 앱 주소를 공유하지 마세요.")
    with st.form("first_setup"):
        first_family = st.text_input("가족 비밀번호 정하기 (4글자 이상 · 숫자도 가능)", type="password")
        first_parent = st.text_input("부모님 전용 비밀번호 정하기 (6글자 이상)", type="password")
        first_confirm = st.text_input("부모님 비밀번호 다시 입력", type="password")
        submit = st.form_submit_button("저장하고 시작하기", type="primary", use_container_width=True)
    if submit:
        if len(first_family) < 4 or len(first_parent) < 6:
            st.error("가족 비밀번호는 4글자 이상, 부모님 비밀번호는 6글자 이상으로 정해 주세요.")
        elif first_family == first_parent:
            st.error("가족용과 부모님용 비밀번호는 다르게 정해 주세요.")
        elif first_parent != first_confirm:
            st.error("부모님 비밀번호 두 칸이 서로 달라요.")
        else:
            family_hash = encode_password(first_family)
            parent_hash = encode_password(first_parent)
            try:
                with engine.begin() as c:
                    c.execute(insert(auth_table).values(id=1, family_hash=family_hash, parent_hash=parent_hash))
                st.session_state.family_auth = hashlib.sha256(family_hash.encode()).hexdigest()
                st.rerun()
            except IntegrityError:
                st.warning("다른 기기에서 이미 설정했어요. 새로고침해 주세요.")
    st.caption("기본 임시 저장소는 재시작 시 기록과 비밀번호 설정이 사라질 수 있어요. 실제 사용에는 외부 PostgreSQL 연결을 권장해요.")
    st.stop()
family_password = auth["family_hash"]
parent_pin = auth["parent_hash"]
password_gate()


def rows(stmt):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings()]

def latest_campaign():
    result = rows(select(campaigns).order_by(campaigns.c.id.desc()).limit(1))
    return result[0] if result else None

def get_entries(cid):
    return rows(select(entries.c.id, entries.c.campaign_id, entries.c.day, entries.c.mission,
                       entries.c.status, entries.c.note, entries.c.feedback,
                       entries.c.created_at, entries.c.reviewed_at)
                .where(entries.c.campaign_id == cid).order_by(entries.c.day.desc()))

def photo_of(eid):
    result = rows(select(entries.c.photo).where(entries.c.id == eid))
    return bytes(result[0]["photo"]) if result else None

def successes(cid):
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(entries).where(
            entries.c.campaign_id == cid, entries.c.status == "approved")).scalar_one()

def mission_for(camp, day):
    result = rows(select(missions.c.mission).where(missions.c.campaign_id == camp["id"], missions.c.day == day))
    return result[0]["mission"] if result else camp["mission"]

def compress_photo(upload):
    if upload.size > 10 * 1024 * 1024:
        raise ValueError("사진은 10MB 이하로 올려 주세요.")
    try:
        with Image.open(upload) as im:
            if im.width * im.height > 24_000_000:
                raise ValueError("너무 큰 사진이에요. 휴대폰에서 크기를 줄여 주세요.")
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1600, 1600))
            # 새 픽셀 이미지로 복사해 위치 정보 등 EXIF 메타데이터 제거.
            clean = Image.new("RGB", im.size, "white")
            clean.paste(im)
            out = io.BytesIO()
            clean.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("사진을 읽을 수 없어요. JPG 또는 PNG로 다시 올려 주세요.") from None


def parent_login():
    digest = hashlib.sha256(parent_pin.encode()).hexdigest()
    if st.session_state.get("parent_auth") == digest and time.time() < st.session_state.get("parent_expires", 0):
        if st.button("부모님 모드 잠그기", key="parent_lock_button"):
            st.session_state.pop("parent_auth", None)
            st.rerun()
        return True
    if time.time() < st.session_state.get("pin_lock", 0):
        st.warning("입력이 여러 번 틀렸어요. 1분 후 다시 시도해 주세요.")
        return False
    with st.form("parent_login"):
        pin = st.text_input("부모님 전용 비밀번호", type="password")
        ok = st.form_submit_button("부모님 입장", type="primary")
    if ok:
        if verify_password(pin, parent_pin):
            st.session_state.parent_auth = digest
            st.session_state.parent_expires = time.time() + 1800
            st.session_state.pin_attempts = 0
            st.rerun()
        else:
            tries = st.session_state.get("pin_attempts", 0) + 1
            st.session_state.pin_attempts = tries
            if tries % 5 == 0:
                st.session_state.pin_lock = time.time() + 60
            st.error("부모님 비밀번호가 맞지 않아요.")
    st.caption("부모님 모드는 30분 뒤 자동으로 잠겨요. 공유 기기에서는 사용 후 잠가 주세요.")
    return False


def render_calendar(camp, records):
    current = today()
    if "month_offset" not in st.session_state:
        st.session_state.month_offset = 0
    left, middle, right = st.columns([1, 4, 1])
    if left.button("◀", help="지난달", use_container_width=True):
        st.session_state.month_offset -= 1
    if right.button("▶", help="다음달", use_container_width=True):
        st.session_state.month_offset += 1
    total = current.year * 12 + current.month - 1 + st.session_state.month_offset
    year, month0 = divmod(total, 12)
    month = month0 + 1
    middle.markdown(f"### {year}년 {month}월")
    by_day = {r["day"]: r for r in records}
    # 지난 도전의 기록도 같은 달력에서 확인 가능.
    for r in rows(select(entries.c.day, entries.c.status).order_by(entries.c.id)):
        if r["day"] not in by_day or r["status"] == "approved":
            by_day[r["day"]] = r
    cells = [f'<div class="weekday">{x}</div>' for x in ["월", "화", "수", "목", "금", "토", "일"]]
    labels = {"approved": "⭐ 성공", "pending": "⏳ 확인 중", "retry": "🌱 다시 도전"}
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        for d in week:
            if not d:
                cells.append('<div class="day blank"></div>')
                continue
            dt = date(year, month, d)
            record = by_day.get(dt.isoformat())
            if record:
                state = record["status"]
                label = labels[state]
            elif dt > current:
                state, label = "future", ""
            elif camp and dt >= date.fromisoformat(camp["start_day"]):
                state, label = "missing", ("오늘의 도전" if dt == current else "기록 없음")
            else:
                state, label = "future", ""
            cls = " today" if dt == current else ""
            cells.append(f'<div class="day {state}{cls}"><span class="num">{d}</span><span class="label">{label}</span></div>')
    st.markdown('<div class="calendar">' + ''.join(cells) + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="legend">🟩 성공 · 🟨 부모님 확인 중 · 🟧 다시 도전 · ⬜ 지난날 기록 없음<br>색과 글자를 함께 표시해요. 하루 빠져도 모은 도장은 사라지지 않아요.</div>', unsafe_allow_html=True)


def child_page(camp):
    st.title("🌱 준영이의 공부 기록장")
    st.caption("조금씩, 꾸준히! 오늘의 노력을 도장으로 남겨요.")
    records = get_entries(camp["id"]) if camp else []
    render_calendar(camp, records)
    if not camp:
        st.info("부모님이 첫 공부 미션과 선물을 준비하고 있어요. 부모님 모드에서 시작해 주세요!")
        return
    count = sum(r["status"] == "approved" for r in records)
    st.markdown("### 🎁 나의 보물상자")
    st.progress(min(count / camp["goal"], 1.0), text=f"성공 도장 {count} / {camp['goal']}개")
    if camp["opened_at"]:
        st.markdown(f'<div class="box"><div class="emoji">🎊</div><h3>준영아, 해냈어!</h3><p>이번 선물은 <strong>{safe(camp["reward"])}</strong></p><p>부모님께 선물을 부탁해 봐!</p></div>', unsafe_allow_html=True)
    elif count >= camp["goal"]:
        st.markdown('<div class="box"><div class="emoji">🎁</div><h3>마지막 도장을 모았어!</h3><p>이제 보물상자를 열 수 있어.</p></div>', unsafe_allow_html=True)
        if st.button("✨ 보물상자 열기", type="primary", use_container_width=True):
            with engine.begin() as c:
                # 승인 수를 서버에서 다시 확인해 URL/화면 조작으로 열리지 않게 함.
                n = c.execute(select(func.count()).select_from(entries).where(entries.c.campaign_id == camp["id"], entries.c.status == "approved")).scalar_one()
                if n >= camp["goal"]:
                    c.execute(update(campaigns).where(campaigns.c.id == camp["id"], campaigns.c.opened_at.is_(None)).values(opened_at=now()))
            st.session_state.celebrate = True
            st.rerun()
    else:
        st.markdown(f'<div class="box"><div class="emoji">🔒 🎁</div><h3>두근두근 비밀 선물</h3><p>성공 도장 {camp["goal"] - count}개를 더 모으면 열려요!</p></div>', unsafe_allow_html=True)
    if st.session_state.pop("celebrate", False):
        st.balloons()
    if camp["opened_at"]:
        st.info("이번 도전은 끝났어요! 부모님이 다음 도전을 만들면 다시 시작할 수 있어요.")
        return
    st.markdown("### ✏️ 오늘의 미션")
    day = today().isoformat()
    mission = mission_for(camp, day)
    st.markdown(f'<div class="card"><strong>{safe(mission)}</strong><br><small>{day} · 사진 한 장이면 인증 끝!</small></div>', unsafe_allow_html=True)
    entry = next((r for r in records if r["day"] == day), None)
    if entry and entry["status"] == "approved":
        st.success("⭐ 오늘 공부 성공! 부모님이 도장을 찍어 주셨어요.")
        if entry["feedback"]:
            st.info("💬 부모님: " + entry["feedback"])
    elif entry and entry["status"] == "pending":
        st.info("⏳ 사진을 보냈어요. 부모님이 확인 중이에요!")
        st.caption("아래 알림함이 자동으로 갱신돼요. 승인 후 ‘화면 새로고침’을 누르면 달력도 바뀌어요.")
    else:
        if entry:
            st.warning("🌱 조금만 더 해 볼까? " + entry["feedback"])
        source = st.radio("사진 인증 방법", ["사진 고르기", "카메라로 찍기"], horizontal=True)
        st.caption("휴대폰에서는 사진 고르기로도 촬영할 수 있어요. 얼굴·이름·주소는 찍지 마세요.")
        upload = (st.file_uploader("공부한 사진 한 장", type=["jpg", "jpeg", "png"], key=f"upload_{camp['id']}_{day}")
                  if source == "사진 고르기" else st.camera_input("공부한 내용을 찰칵!", key=f"camera_{camp['id']}_{day}"))
        if upload:
            st.image(upload, caption="부모님께 보낼 사진", width=320)
        note = st.text_input("한마디 남기기 (선택)", placeholder="오늘도 열심히 했어!", max_chars=100)
        if st.button("📸 부모님께 인증 보내기", type="primary", use_container_width=True, disabled=upload is None):
            try:
                photo = compress_photo(upload)
                with engine.begin() as c:
                    fresh = c.execute(select(campaigns).order_by(campaigns.c.id.desc()).limit(1)).mappings().first()
                    if not fresh or fresh["id"] != camp["id"] or fresh["opened_at"] or fresh["start_day"] > day:
                        raise ValueError("도전이 바뀌었어요. 화면을 새로고침해 주세요.")
                    if entry:
                        result = c.execute(update(entries).where(entries.c.id == entry["id"], entries.c.status == "retry").values(photo=photo, note=note, status="pending", feedback="", created_at=now(), reviewed_at=None))
                        if result.rowcount != 1:
                            raise ValueError("이미 처리된 기록이에요. 새로고침해 주세요.")
                    else:
                        c.execute(insert(entries).values(campaign_id=camp["id"], day=day, mission=mission, status="pending", photo=photo, note=note, feedback="", created_at=now()))
                st.rerun()
            except (ValueError, IntegrityError) as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "오늘 사진은 이미 접수됐어요. 새로고침해 주세요.")
    with st.expander("📖 이전 기록과 부모님 말씀"):
        for r in records[:60]:
            st.write(f"{r['day']} · " + {"approved": "⭐ 성공", "pending": "⏳ 확인 중", "retry": "🌱 다시 도전"}[r["status"]])
            st.caption(r["mission"])
            if r["feedback"]:
                st.write("💬 " + r["feedback"])
            if st.checkbox("사진 보기", key=f"child_photo_{r['id']}"):
                st.image(photo_of(r["id"]), width=320)


def setup_campaign(camp):
    st.subheader("🎁 " + ("다음 도전 만들기" if camp else "첫 도전 만들기"))
    st.caption("하루에 도장 하나! 목표는 ‘연속 일수’가 아니라 부모님이 승인한 총 성공 일수예요.")
    with st.form("new_campaign"):
        mission = st.text_input("기본 공부 미션", value="수학 문제집 2쪽 풀기", max_chars=300)
        goal = st.number_input("상자를 열 성공 일수", min_value=1, max_value=100, value=7, step=1)
        reward = st.text_input("상자 속 선물", placeholder="예: 말랑이 1개 / 5,000원 기프티콘", max_chars=200)
        ok = st.form_submit_button("새 도전 시작하기", type="primary", use_container_width=True)
    if ok:
        if not mission.strip() or not reward.strip():
            st.error("공부 미션과 선물을 모두 입력해 주세요.")
        else:
            created = False
            with engine.begin() as c:
                # PostgreSQL 다중 기기 동시 생성 방지. SQLite는 아래 쓰기 트랜잭션으로 직렬화.
                if engine.dialect.name == "postgresql":
                    c.exec_driver_sql("SELECT pg_advisory_xact_lock(7102026)")
                else:
                    c.exec_driver_sql("BEGIN IMMEDIATE")
                latest = c.execute(select(campaigns).order_by(campaigns.c.id.desc()).limit(1)).mappings().first()
                if latest and not latest["opened_at"]:
                    st.warning("이미 진행 중인 도전이 있어요. 새로고침해 주세요.")
                else:
                    # 같은 날 보상을 여러 번 받지 않도록 다음 도전은 익일부터 인증.
                    start = today() + timedelta(days=1) if latest else today()
                    c.execute(insert(campaigns).values(start_day=start.isoformat(), goal=int(goal), reward=reward.strip(), mission=mission.strip(), created_at=now()))
                    created = True
            if created:
                st.rerun()


# 건강 정보는 공부 기록과 분리하며 자동 진단/복약 추천을 하지 않습니다.
health_meta = MetaData()
health = Table("jy_health_reports", health_meta,
    Column("id", Integer, primary_key=True),
    Column("part", String(80), nullable=False),
    Column("severity", String(40), nullable=False),
    Column("note", String(500), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("seen", Integer, nullable=False, default=0))
contacts = Table("jy_health_contacts", health_meta,
    Column("id", Integer, primary_key=True),
    Column("phone", String(30), nullable=False))
health_meta.create_all(engine)


def health_parent():
    st.subheader("🩺 준영이 건강 확인함")
    st.caption("알림은 앱 안에서만 보여요. 앱을 닫은 휴대폰에 문자·푸시가 자동 발송되지는 않습니다.")
    current = rows(select(contacts).where(contacts.c.id == 1))
    with st.form("health_phone"):
        phone = st.text_input("준영이가 전화할 보호자 번호", value=current[0]["phone"] if current else "", placeholder="01012345678", max_chars=20)
        save = st.form_submit_button("전화번호 저장")
    if save:
        cleaned = phone.replace("-", "").replace(" ", "")
        if cleaned and (not cleaned.isdigit() or not 9 <= len(cleaned) <= 15):
            st.error("전화번호를 숫자로 입력해 주세요.")
        else:
            with engine.begin() as c:
                c.execute(delete(contacts).where(contacts.c.id == 1))
                c.execute(insert(contacts).values(id=1, phone=cleaned))
            st.success("저장했어요. 빈 번호로 저장하면 전화 버튼이 숨겨져요.")
    reports = rows(select(health).order_by(health.c.id.desc()).limit(100))
    if not reports:
        st.info("아직 건강 기록이 없어요.")
    for r in reports:
        with st.container(border=True):
            st.write(("✅ 확인함" if r["seen"] else "🔔 확인 필요") + " · " + r["created_at"])
            st.write(f"{r['part']} · {r['severity']}")
            st.write(r["note"] or "추가 설명 없음")
            st.caption("확인 버튼은 보호자가 기록을 읽었다는 뜻이며 치료 완료를 뜻하지 않습니다.")
            if not r["seen"] and st.button("읽었어요 · 준영이에게 연락할게요", key=f"health_seen_{r['id']}"):
                with engine.begin() as c:
                    c.execute(update(health).where(health.c.id == r["id"]).values(seen=1))
                st.rerun()
            if st.checkbox("이 건강 기록 삭제에 동의", key=f"hdc_{r['id']}"):
                if st.button("건강 기록 삭제", key=f"hd_{r['id']}"):
                    with engine.begin() as c:
                        c.execute(delete(health).where(health.c.id == r["id"]))
                    st.rerun()


def health_child():
    st.title("🩺 내 몸 살피기")
    st.write("몸 모양의 버튼에서 아픈 곳을 콕 눌러줘!")
    st.error("숨쉬기 힘들거나, 정신이 흐려지거나, 입술·혀가 부으면 기록하지 말고 바로 주변 어른에게 알리고 119에 도움을 요청해요.")
    st.warning("혼자 약을 먹지 말고 부모님에게 먼저 알려줘. 여기는 진단이나 약 추천을 하는 곳이 아니야.")
    contact = rows(select(contacts).where(contacts.c.id == 1))
    if contact and contact[0]["phone"]:
        number = contact[0]["phone"]
        st.markdown(f"### [📞 부모님에게 전화하기](tel:{number})")
        st.caption("휴대폰에서 누르면 전화 앱이 열려요. 통화 버튼은 직접 눌러야 해요.")
    else:
        st.info("부모님 관리실에서 전화번호를 등록하면 전화 버튼이 생겨요. 급하면 주변 어른에게 직접 알려줘!")
    view = st.radio("몸의 어느 쪽이야?", ["앞면", "뒷면"], horizontal=True)
    st.caption("화면 왼쪽·오른쪽은 그림에서 보이는 방향이에요. 버튼을 누르면 선택한 곳이 아래에 표시돼요.")
    def part_button(col, label, key):
        full = view + " · " + label
        selected = st.session_state.get("health_part") == full
        if col.button(("✓ " if selected else "") + label, key="body_" + key, type="primary" if selected else "secondary", use_container_width=True):
            st.session_state.health_part = full
            st.rerun()
    # 네이티브 버튼을 몸 형태로 배열하여 작은 휴대폰에서도 직접 터치할 수 있습니다.
    _, center, _ = st.columns([1, 1.4, 1])
    part_button(center, "🙂 머리" if view == "앞면" else "🧑 뒤통수", "head")
    _, center, _ = st.columns([1, 1.4, 1])
    part_button(center, "목", "neck")
    left, center, right = st.columns([1, 1.4, 1])
    part_button(left, "왼쪽 팔", "arm_l")
    part_button(center, "가슴" if view == "앞면" else "등", "chest")
    part_button(right, "오른쪽 팔", "arm_r")
    left, center, right = st.columns([1, 1.4, 1])
    part_button(left, "왼쪽 손", "hand_l")
    part_button(center, "배" if view == "앞면" else "허리", "belly")
    part_button(right, "오른쪽 손", "hand_r")
    _, center, _ = st.columns([1, 1.4, 1])
    part_button(center, "골반·엉덩이", "hip")
    _, l, r, _ = st.columns([.5, 1, 1, .5])
    part_button(l, "왼쪽 다리", "leg_l")
    part_button(r, "오른쪽 다리", "leg_r")
    _, l, r, _ = st.columns([.5, 1, 1, .5])
    part_button(l, "왼쪽 발", "foot_l")
    part_button(r, "오른쪽 발", "foot_r")
    if st.button("다른 곳 / 어디인지 모르겠어", use_container_width=True):
        st.session_state.health_part = "다른 곳 / 위치 불확실"
        st.rerun()
    selected = st.session_state.get("health_part", "")
    if selected:
        st.success("고른 곳: " + selected)
    with st.form("health_submit", clear_on_submit=True):
        severity = st.radio("얼마나 아파?", ["🙂 조금 아파", "😟 많이 아파", "😭 너무 아파"], horizontal=True)
        note = st.text_input("언제부터 아팠어? 더 하고 싶은 말 (안 써도 돼)", max_chars=500)
        sent = st.form_submit_button("📣 부모님 확인함에 남기기", type="primary", use_container_width=True)
    if sent:
        if not selected:
            st.warning("먼저 아픈 곳을 눌러줘!")
        else:
            with engine.begin() as c:
                c.execute(insert(health).values(part=selected, severity=severity, note=note.strip(), created_at=now(), seen=0))
            st.success("부모님 확인함에 저장했어! 자동 문자 알림은 아니니 전화하거나 직접 말해줘.")
            if severity != "🙂 조금 아파":
                st.warning("많이 아프면 기다리지 말고 지금 바로 어른에게 도움을 요청해줘.")
    st.caption("건강 기록은 가족의 민감한 정보예요. 실제 사용 전 보호자와 상의하고 가족 밖에 공유하지 마세요.")


def parent_page(camp):
    st.title("🔐 부모님 관리실")
    if not parent_login():
        return
    health_parent()
    st.divider()
    if not camp or camp["opened_at"]:
        setup_campaign(camp)
    if not camp:
        return
    st.info(f"이번 선물: {camp['reward']} · 목표 {camp['goal']}일 · 시작 {camp['start_day']}")
    st.caption("선물과 목표는 시작 후 고정돼요. 약속을 지키고, 완료 후 새 도전을 만들어 주세요.")
    if not camp["opened_at"]:
        with st.expander("✏️ 날짜별 공부량 설정", expanded=True):
            with st.form("day_mission"):
                target_day = st.date_input("공부할 날짜", value=max(today(), date.fromisoformat(camp["start_day"])), min_value=max(today(), date.fromisoformat(camp["start_day"])))
                text = st.text_input("그날의 공부량", placeholder=camp["mission"], max_chars=300)
                ok = st.form_submit_button("이 날짜의 미션 저장")
            if ok:
                day = target_day.isoformat()
                if not text.strip():
                    st.error("공부량을 입력해 주세요.")
                elif rows(select(entries.c.id).where(entries.c.campaign_id == camp["id"], entries.c.day == day)):
                    st.warning("이미 사진을 제출한 날짜의 미션은 바꿀 수 없어요.")
                else:
                    try:
                        with engine.begin() as c:
                            old = c.execute(select(missions.c.id).where(missions.c.campaign_id == camp["id"], missions.c.day == day)).scalar()
                            if old:
                                c.execute(update(missions).where(missions.c.id == old).values(mission=text.strip()))
                            else:
                                c.execute(insert(missions).values(campaign_id=camp["id"], day=day, mission=text.strip()))
                        st.success("저장했어요! 지정하지 않은 날짜는 기본 미션을 사용해요.")
                    except IntegrityError:
                        st.warning("다른 기기에서 먼저 저장했어요. 새로고침해 주세요.")
            planned = rows(select(missions.c.day, missions.c.mission).where(missions.c.campaign_id == camp["id"], missions.c.day >= today().isoformat()).order_by(missions.c.day))
            for item in planned:
                st.caption(f"{item['day']} · {item['mission']}")
    st.subheader("📬 승인 기다리는 사진")
    pending = rows(select(entries.c.id, entries.c.day, entries.c.mission, entries.c.note).where(entries.c.campaign_id == camp["id"], entries.c.status == "pending").order_by(entries.c.day))
    if not pending:
        st.success("확인할 사진이 없어요.")
    for r in pending:
        with st.container(border=True):
            st.markdown(f"#### {r['day']} 공부 인증")
            st.write(r["mission"])
            st.image(photo_of(r["id"]), width=420)
            if r["note"]:
                st.write("준영이: " + r["note"])
            feedback = st.text_input("칭찬 또는 다시 할 부분", placeholder="끝까지 해냈네! 정말 멋져!", max_chars=300, key=f"feedback_{r['id']}")
            a, b = st.columns(2)
            approve = a.button("⭐ 성공! 도장 찍기", key=f"approve_{r['id']}", type="primary", use_container_width=True)
            retry = b.button("🌱 조금만 더 해볼까?", key=f"retry_{r['id']}", use_container_width=True)
            if approve or retry:
                if retry and not feedback.strip():
                    st.warning("다시 도전할 부분을 짧게 알려 주세요.")
                else:
                    with engine.begin() as c:
                        result = c.execute(update(entries).where(entries.c.id == r["id"], entries.c.status == "pending").values(status="approved" if approve else "retry", feedback=feedback.strip() or "끝까지 해냈네! 정말 멋져!", reviewed_at=now()))
                    if result.rowcount:
                        st.rerun()
                    else:
                        st.info("다른 기기에서 이미 처리했어요. 새로고침해 주세요.")
    with st.expander("📚 승인 기록 / 사진 삭제"):
        st.caption("사진을 삭제하면 해당 공부 기록과 도장도 삭제돼요. 이미 연 상자는 닫히지 않아요.")
        history = get_entries(camp["id"])
        for r in history:
            st.write(f"{r['day']} · {r['status']} · {r['mission']}")
            if st.checkbox("사진 확인", key=f"parent_photo_{r['id']}"):
                st.image(photo_of(r["id"]), width=320)
            confirm = st.checkbox("이 기록·사진·도장 삭제에 동의", key=f"confirm_delete_{r['id']}")
            if st.button("기록 삭제", key=f"delete_{r['id']}", disabled=not confirm):
                with engine.begin() as c:
                    c.execute(delete(entries).where(entries.c.id == r["id"]))
                st.rerun()


@st.fragment(run_every="20s")
def notifications():
    # 알림함만 주기적으로 갱신: 입력 중인 다른 위젯은 방해하지 않음.
    camp = latest_campaign()
    parent_valid = (st.session_state.get("parent_auth") == hashlib.sha256(parent_pin.encode()).hexdigest()
                    and time.time() < st.session_state.get("parent_expires", 0))
    if parent_valid:
        outstanding = rows(select(health.c.id).where(health.c.seen == 0))
        if outstanding:
            st.error(f"🩺 건강 기록 {len(outstanding)}건: 부모님 관리실에서 확인하고 준영이에게 연락해 주세요.")
    if not camp:
        return
    if parent_valid:
        pending = rows(select(entries.c.id).where(entries.c.campaign_id == camp["id"], entries.c.status == "pending"))
        if pending:
            st.warning(f"🔔 부모님! 새 공부 인증 {len(pending)}건이 기다려요. ‘화면 새로고침’ 후 확인해 주세요.")
    else:
        recent = rows(select(entries.c.day, entries.c.status, entries.c.feedback).where(entries.c.campaign_id == camp["id"], entries.c.status.in_(["approved", "retry"])).order_by(entries.c.reviewed_at.desc()).limit(1))
        if recent:
            r = recent[0]
            st.info(f"🔔 {r['day']} · " + ("성공 도장을 받았어요!" if r["status"] == "approved" else "부모님이 다시 도전할 부분을 알려 주셨어요."))
    st.caption("앱 내 알림 · 20초마다 확인 · 휴대폰 푸시/SMS 알림은 아니에요.")

if not st.session_state.get("entered"):
    st.markdown('<div class="hero"><div class="eyebrow">JUNYOUNG’S STUDY JOURNAL</div><h1>🌱 준영이의<br>공부·건강 기록장</h1><p>공부하고, 사진 찍고, 도장 모으고!<br>매일의 작은 도전 끝에 특별한 보물상자가 기다려요.<br>아픈 곳은 내 몸 살피기에서 알려줘요.</p></div>', unsafe_allow_html=True)
    st.markdown("**① 오늘 미션 확인 → ② 사진 인증 → ③ 부모님 성공 도장 → ④ 선물상자 열기**")
    st.caption("도장은 하루 한 개. 쉬어 가는 날이 있어도 괜찮아!")
    if st.button("🚪 입장하기", type="primary", use_container_width=True):
        st.session_state.entered = True
        st.rerun()
    st.stop()

with st.sidebar:
    st.title("🌱 공부 기록장")
    page = st.radio("어디로 갈까요?", ["준영이의 달력", "🩺 내 몸 살피기", "부모님 관리실", "QR로 함께 쓰기"])
    if url.startswith("sqlite"):
        st.warning("현재 임시 저장 모드예요. 재배포·재시작 시 기록이 사라질 수 있어요. 실제 사용 전 PostgreSQL을 연결해 주세요.")
    else:
        st.caption("외부 저장소 연결 모드 · 사진과 기록은 해당 DB에 보관해요.")
    if st.button("🔄 화면 새로고침", use_container_width=True):
        st.rerun()
    if st.button("🚪 가족 로그아웃", use_container_width=True):
        for key in list(st.session_state):
            del st.session_state[key]
        st.rerun()

camp = latest_campaign()
if page == "준영이의 달력":
    # 다음 도전 시작일 전에는 인증 기능을 보이지 않음.
    if camp and date.fromisoformat(camp["start_day"]) > today():
        st.title("🌱 다음 도전도 기대해!")
        render_calendar(camp, get_entries(camp["id"]))
        st.success(f"새 도전은 {camp['start_day']}부터 시작해요. 오늘은 푹 쉬어도 괜찮아!")
    else:
        child_page(camp)
elif page == "🩺 내 몸 살피기":
    health_child()
elif page == "부모님 관리실":
    parent_page(camp)
else:
    st.title("📱 QR로 함께 쓰기")
    st.write("휴대폰 카메라로 QR을 비추면 같은 기록장에 들어올 수 있어요. 별도 앱 설치는 필요 없어요.")
    app_url = config("APP_URL")
    if not app_url:
        st.info("부모님이 앱 Secrets에 배포 완료된 HTTPS 주소를 APP_URL로 입력하면 QR이 생겨요.")
    else:
        parsed = urlparse(app_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            st.error("APP_URL에는 비밀번호가 없는 실제 HTTPS 앱 주소를 입력해 주세요.")
        else:
            image = qrcode.make(app_url)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            st.image(buffer.getvalue(), width=260, caption="우리 가족 공부 기록장")
            st.link_button("공부 기록장 주소 열기", app_url)
            st.download_button("QR 이미지 내려받기", buffer.getvalue(), file_name="junyoung_qr.png", mime="image/png")
    st.warning("QR에 비밀번호는 들어 있지 않아요. 가족 비밀번호는 따로 전달하고, 사진과 QR을 공개 게시하지 마세요.")
    st.caption("휴대폰 홈 화면에 추가하면 앱처럼 편하게 접속할 수 있어요. 카메라 사용에는 HTTPS와 카메라 권한이 필요해요.")

st.divider()
notifications()
st.caption("🌿 잘한 만큼 차곡차곡. 빠뜨린 날보다, 다시 시작한 날이 더 소중해요.")
