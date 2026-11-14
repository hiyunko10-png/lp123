"""가족 여행 보드
실행: pip install -r requirements.txt && streamlit run app.py
GitHub 저장소에 두 파일을 올린 뒤 Streamlit Community Cloud에서 app.py를 선택하세요.
기본: SQLite(자동 생성). Community Cloud의 로컬 파일은 재시작/재배포 시 사라질 수 있습니다.
영구 공유 저장: Supabase 프로젝트의 SQL Editor에서 아래 SUPABASE_SQL 실행 후
Streamlit 앱 Settings > Secrets에 다음을 입력하세요(따옴표 안은 실제 값).
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_SERVER_SIDE_SERVICE_ROLE_KEY"
APP_PASSWORD = "가족만 아는 비밀번호"
서비스 역할 키는 GitHub에 올리지 마세요. Secrets에서만 사용됩니다.
Supabase 사용 시 APP_PASSWORD 설정이 필수입니다. 별도 회원가입 없이 가족 공용 암호로 보호합니다.
구성원 선택은 담당자 표시용이며 개인 인증은 아닙니다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from datetime import date
from urllib.parse import quote, urlparse

import streamlit as st

st.set_page_config(page_title="우리 가족 여행 보드", page_icon="🧳", layout="wide")

SUPABASE_SQL = """create table if not exists public.family_travel_records (
 id text primary key,
 kind text not null,
 payload jsonb not null
);
alter table public.family_travel_records enable row level security;
-- 클라이언트용 공개 정책은 만들지 않습니다. 서버 Secrets의 service_role 키만 사용합니다.
"""


def setting(name):
    try:
        return str(st.secrets.get(name, os.getenv(name, "")))
    except Exception:
        return os.getenv(name, "")


URL, KEY, PASSWORD = (setting(k) for k in ("SUPABASE_URL", "SUPABASE_KEY", "APP_PASSWORD"))
if bool(URL) != bool(KEY):
    st.error("SUPABASE_URL과 SUPABASE_KEY를 모두 설정해야 합니다.")
    st.stop()
if URL and not PASSWORD:
    st.error("공유 데이터 보호를 위해 Secrets에 APP_PASSWORD를 먼저 설정해 주세요.")
    st.stop()
if PASSWORD and not st.session_state.get("authenticated"):
    st.title("🧳 우리 가족 여행 보드")
    with st.form("login"):
        entered = st.text_input("가족 공용 비밀번호", type="password")
        submit = st.form_submit_button("입장하기", use_container_width=True)
    if submit:
        if hmac.compare_digest(hashlib.sha256(entered.encode()).digest(), hashlib.sha256(PASSWORD.encode()).digest()):
            st.session_state.authenticated = True
            st.rerun()
        st.error("비밀번호가 맞지 않습니다.")
    st.stop()


@st.cache_resource
def remote_client(url, key):
    from supabase import create_client
    return create_client(url, key)


class Store:
    def __init__(self):
        self.remote = remote_client(URL, KEY) if URL else None
        self.path = "family_travel.sqlite3"
        if not self.remote:
            with sqlite3.connect(self.path, timeout=20) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)")

    def all(self, kind):
        if self.remote:
            rows, start = [], 0
            while True:
                batch = self.remote.table("family_travel_records").select("id,payload").eq("kind", kind).order("id").range(start, start + 499).execute().data
                rows.extend(batch)
                if len(batch) < 500:
                    break
                start += 500
        else:
            with sqlite3.connect(self.path, timeout=20) as conn:
                rows = [{"id": r[0], "payload": json.loads(r[1])} for r in conn.execute("SELECT id,payload FROM records WHERE kind=? ORDER BY id", (kind,))]
        return [dict(r["payload"], id=r["id"]) for r in rows]

    def save(self, kind, payload, record_id=None):
        rid = record_id or str(uuid.uuid4())
        payload = {k: v for k, v in payload.items() if k != "id"}
        if self.remote:
            self.remote.table("family_travel_records").upsert({"id": rid, "kind": kind, "payload": payload}).execute()
        else:
            with sqlite3.connect(self.path, timeout=20) as conn:
                conn.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,payload=excluded.payload", (rid, kind, json.dumps(payload, ensure_ascii=False)))
        return rid

    def delete(self, rid):
        if self.remote:
            self.remote.table("family_travel_records").delete().eq("id", rid).execute()
        else:
            with sqlite3.connect(self.path, timeout=20) as conn:
                conn.execute("DELETE FROM records WHERE id=?", (rid,))


def valid_link(value):
    return urlparse(value).scheme in ("https", "http") and bool(urlparse(value).netloc)


def remove_button(record, label="삭제"):
    with st.popover(label):
        st.caption("삭제하면 복구할 수 없습니다.")
        if st.button("정말 삭제", key="del_" + record["id"], type="primary"):
            store.delete(record["id"])
            st.rerun()


def main():
    global store
    store = Store()
    st.markdown("""<style>
    .stApp {background-color:#f7f9fc;}
    h1,h2,h3 {letter-spacing:-.04em;}
    div[data-testid="stMetric"] {background:white;border:1px solid #e3e8ef;border-radius:16px;padding:16px;}
    .stButton>button {border-radius:10px;min-height:44px;}
    </style>""", unsafe_allow_html=True)
    with st.sidebar:
        st.header("🧳 가족 여행 보드")
        st.caption("각자의 취향을 모아, 함께 떠나요")
        if not URL:
            st.warning("현재 로컬 저장 모드입니다. 클라우드 재시작·재배포 시 데이터가 사라질 수 있어요. 영구 공유하려면 Supabase를 연결하세요.")
        if not PASSWORD:
            st.warning("비밀번호가 없습니다. 인터넷에 공개하기 전 Secrets의 APP_PASSWORD를 설정하세요.")
        with st.expander("배포·영구 저장 설정"):
            st.markdown("1. GitHub에 app.py와 requirements.txt 업로드\n2. Streamlit Community Cloud에서 저장소와 app.py 선택\n3. Supabase SQL Editor에서 아래 SQL 실행\n4. Streamlit Secrets에 연결 정보와 암호 입력")
            st.code(SUPABASE_SQL, language="sql")
            st.code('SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\nSUPABASE_KEY = "YOUR_SERVER_SIDE_SERVICE_ROLE_KEY"\nAPP_PASSWORD = "가족 공용 비밀번호"', language="toml")
            st.caption("키는 GitHub에 올리지 마세요. 예약번호·여권·신분증 등 민감한 정보는 저장하지 마세요.")
        if PASSWORD and st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        if st.button("🔄 최신 내용 불러오기", use_container_width=True):
            st.rerun()
        st.caption("다른 가족의 수정은 새로고침 후 반영됩니다. 같은 항목의 동시 수정은 마지막 저장이 적용됩니다.")

    trips = store.all("trip")
    st.title("우리 가족 여행 보드 🧳")
    st.caption("가고 싶은 곳부터 준비물까지, 가족이 함께 만드는 여행")
    with st.expander("➕ 새 여행 만들기", expanded=not trips):
        with st.form("new_trip", clear_on_submit=True):
            name = st.text_input("여행 이름", placeholder="예: 우리 가족 제주 여행", max_chars=80)
            destination = st.text_input("여행 지역", max_chars=100)
            a, b = st.columns(2)
            start = a.date_input("출발일", value=date.today())
            end = b.date_input("마지막 날", value=date.today())
            members = st.text_input("가족 이름 (쉼표로 구분)", value="엄마, 아빠, 자녀1, 자녀2", max_chars=200)
            budget = st.number_input("총예산 (원)", min_value=0, step=10000)
            if st.form_submit_button("여행 만들기", type="primary"):
                people = list(dict.fromkeys(x.strip() for x in members.split(",") if x.strip()))
                if not name.strip() or not people:
                    st.error("여행 이름과 가족 이름을 입력하세요.")
                elif end < start:
                    st.error("마지막 날은 출발일보다 빠를 수 없습니다.")
                else:
                    rid = store.save("trip", {"name": name.strip(), "destination": destination.strip(), "start": str(start), "end": str(end), "members": people, "budget": int(budget)})
                    st.session_state.trip_choice = rid
                    st.rerun()
    if not trips:
        st.info("첫 여행을 만들고, 가고 싶은 장소를 하나씩 등록해 보세요!")
        return
    trip_map = {t["id"]: t for t in trips}
    if st.session_state.get("trip_choice") not in trip_map:
        st.session_state.trip_choice = trips[0]["id"]
    tid = st.selectbox("여행 선택", list(trip_map), format_func=lambda x: trip_map[x]["name"], key="trip_choice")
    trip = trip_map[tid]
    member = st.selectbox("지금 사용하는 가족", trip["members"], key="member_" + tid)
    st.caption(f"📍 {trip['destination'] or '지역 미정'} · {trip['start']} ~ {trip['end']} · 금액 단위: 원")
    def records(kind):
        return [r for r in store.all(kind) if r.get("trip") == tid]
    places, votes, plans, tasks, expenses = [records(k) for k in ("place", "vote", "plan", "task", "expense")]
    place_map = {p["id"]: p for p in places}
    spent = sum(e["amount"] for e in expenses)
    c1, c2, c3 = st.columns(3)
    c1.metric("장소 후보", f"{len(places)}곳")
    c2.metric("준비 완료", f"{sum(t['done'] for t in tasks)} / {len(tasks)}")
    c3.metric("실제 지출", f"{spent:,}원")
    today_tab, vote_tab, plan_tab, task_tab, budget_tab = st.tabs(["☀️ 오늘", "🗳️ 장소·투표", "🗓️ 일정", "🎒 준비물", "💰 예산"])
    with today_tab:
        selected_day = st.date_input("확인할 날짜", value=date.today(), key="today_" + tid)
        day_plans = sorted([p for p in plans if p["day"] == str(selected_day)], key=lambda x: x["time"])
        st.subheader("오늘의 일정")
        if not day_plans:
            st.info("이 날짜에 등록된 일정이 없어요. 일정 탭에서 추가해 주세요.")
        for p in day_plans:
            show_plan(p, place_map)
        st.subheader(f"{member} 님이 챙길 것")
        pending = [t for t in tasks if not t["done"] and t["owner"] in (member, "함께")]
        for t in pending:
            st.write(f"☐ {t['name']} · {t['owner']}")
        if not pending:
            st.success("남은 담당 준비물이 없어요!")
    with vote_tab:
        with st.expander("➕ 장소 후보 등록"):
            with st.form("place_" + tid, clear_on_submit=True):
                pname = st.text_input("장소 이름", max_chars=100)
                category = st.selectbox("유형", ["맛집", "체험", "관광", "쇼핑", "휴식", "숙소", "기타"])
                link = st.text_input("지도 또는 소개 링크 (선택)")
                reason = st.text_area("추천 이유", max_chars=600)
                cost = st.number_input("가족 전체 예상 비용 (원)", min_value=0, step=1000)
                indoor = st.checkbox("실내 장소 / 우천 시 후보")
                if st.form_submit_button("후보 추가"):
                    if not pname.strip():
                        st.error("장소 이름을 입력하세요.")
                    elif link and not valid_link(link):
                        st.error("http:// 또는 https://로 시작하는 올바른 링크를 입력하세요.")
                    else:
                        store.save("place", {"trip": tid, "name": pname.strip(), "category": category, "link": link, "reason": reason, "cost": int(cost), "indoor": indoor, "author": member})
                        st.rerun()
        st.caption("꼭 가고 싶어요 +2점 / 괜찮아요 +1점 / 안 가고 싶어요 -1점. 미투표는 점수에 포함하지 않습니다.")
        labels = ["미투표", "꼭 가고 싶어요", "괜찮아요", "안 가고 싶어요"]
        scores = {"꼭 가고 싶어요": 2, "괜찮아요": 1, "안 가고 싶어요": -1}
        for p in sorted(places, key=lambda x: -sum(scores.get(v["choice"], 0) for v in votes if v["place"] == x["id"])):
            pv = [v for v in votes if v["place"] == p["id"]]
            with st.container(border=True):
                st.subheader(p["name"])
                st.caption(f"{p['category']} · {'실내' if p['indoor'] else '실외/미지정'} · 가족 예상 {p['cost']:,}원 · 제안: {p['author']}")
                if p["reason"]:
                    st.write(p["reason"])
                if valid_link(p["link"]):
                    st.link_button("장소 링크 열기", p["link"])
                st.write(f"총점 {sum(scores.get(v['choice'], 0) for v in pv)}점 · {len(pv)}/{len(trip['members'])}명 참여")
                dislikes = [v["member"] for v in pv if v["choice"] == labels[3]]
                if dislikes:
                    st.warning("의견 조율 필요: " + ", ".join(dislikes))
                elif len(pv) == len(trip["members"]):
                    st.success("가족 모두 괜찮은 후보예요!")
                with st.expander("가족별 투표 보기"):
                    for who in trip["members"]:
                        v = next((v for v in pv if v["member"] == who), None)
                        st.write(f"{who}: {v['choice'] if v else '미투표'}")
                old = next((v for v in pv if v["member"] == member), None)
                with st.form("vote_" + p["id"] + member):
                    choice = st.radio("내 선호도", labels, index=labels.index(old["choice"]) if old else 0)
                    if st.form_submit_button("투표 저장"):
                        vid = hashlib.sha256(json.dumps([tid, p["id"], member], ensure_ascii=False).encode()).hexdigest()
                        if choice == "미투표":
                            if old:
                                store.delete(old["id"])
                        else:
                            store.save("vote", {"trip": tid, "place": p["id"], "member": member, "choice": choice}, vid)
                        st.rerun()
        if not places:
            st.info("가족이 가고 싶은 장소를 먼저 등록해 주세요.")
    with plan_tab:
        if places:
            with st.expander("➕ 일정 추가"):
                with st.form("plan_" + tid, clear_on_submit=True):
                    day = st.date_input("날짜", value=date.fromisoformat(trip["start"]), min_value=date.fromisoformat(trip["start"]), max_value=date.fromisoformat(trip["end"]))
                    when = st.time_input("시간")
                    pid = st.selectbox("장소", list(place_map), format_func=lambda x: place_map[x]["name"])
                    alternatives = {"": "대체 장소 없음", **{p["id"]: p["name"] for p in places}}
                    backup = st.selectbox("우천·휴무 시 대체 장소", list(alternatives), format_func=alternatives.get)
                    memo = st.text_area("이동·예약 등 메모 (민감정보 제외)", max_chars=600)
                    if st.form_submit_button("일정 추가"):
                        if backup == pid:
                            st.error("대체 장소는 원래 장소와 다르게 골라 주세요.")
                        else:
                            store.save("plan", {"trip": tid, "day": str(day), "time": when.strftime("%H:%M"), "place": pid, "backup": backup, "memo": memo})
                            st.rerun()
        else:
            st.info("장소·투표 탭에서 장소를 먼저 추가하세요.")
        for p in sorted(plans, key=lambda x: (x["day"], x["time"])):
            with st.container(border=True):
                show_plan(p, place_map)
                remove_button(p, "일정 삭제")
    with task_tab:
        with st.form("task_" + tid, clear_on_submit=True):
            task_name = st.text_input("준비물 또는 할 일", placeholder="충전기 챙기기, 숙소 예약 확인", max_chars=150)
            owner = st.selectbox("담당자", ["함께"] + trip["members"])
            if st.form_submit_button("준비물 추가"):
                if task_name.strip():
                    store.save("task", {"trip": tid, "name": task_name.strip(), "owner": owner, "done": False})
                    st.rerun()
                st.error("준비물 이름을 입력하세요.")
        only_mine = st.checkbox("내 담당 / 공동 준비물만 보기")
        for t in sorted(tasks, key=lambda x: x["done"]):
            if only_mine and t["owner"] not in (member, "함께"):
                continue
            left, right = st.columns([5, 1])
            checked = left.checkbox(f"{t['name']} · {t['owner']}", value=t["done"], key="check_" + t["id"])
            if checked != t["done"]:
                store.save("task", {**t, "done": checked}, t["id"])
                st.rerun()
            with right:
                remove_button(t)
    with budget_tab:
        with st.form("set_budget_" + tid):
            new_budget = st.number_input("가족 총예산 (원)", min_value=0, value=int(trip["budget"]), step=10000)
            if st.form_submit_button("총예산 변경"):
                store.save("trip", {**trip, "budget": int(new_budget)}, tid)
                st.rerun()
        st.metric("남은 예산", f"{trip['budget'] - spent:,}원")
        if trip["budget"] > 0:
            st.progress(min(spent / trip["budget"], 1.0))
            if spent > trip["budget"]:
                st.warning(f"예산을 {spent - trip['budget']:,}원 초과했어요.")
        st.caption("후보 장소의 예상 비용은 실제 지출에 자동 합산하지 않습니다. 아래에 확정 지출만 기록하세요.")
        with st.form("expense_" + tid, clear_on_submit=True):
            ename = st.text_input("지출 내용", max_chars=150)
            ecategory = st.selectbox("분류", ["숙소", "교통", "식비", "체험·관광", "쇼핑", "기타"])
            amount = st.number_input("금액 (원)", min_value=0, step=1000)
            eday = st.date_input("결제일", value=date.today())
            if st.form_submit_button("지출 기록"):
                if not ename.strip() or amount <= 0:
                    st.error("지출 내용과 0원보다 큰 금액을 입력하세요.")
                else:
                    store.save("expense", {"trip": tid, "name": ename.strip(), "category": ecategory, "amount": int(amount), "day": str(eday), "author": member})
                    st.rerun()
        for e in sorted(expenses, key=lambda x: x["day"], reverse=True):
            with st.container(border=True):
                st.write(f"{e['day']} · {e['name']} · {e['amount']:,}원")
                st.caption(f"{e['category']} · 기록: {e['author']}")
                remove_button(e, "지출 삭제")
    st.divider()
    export = {"trip": trip, "places": places, "votes": votes, "plans": plans, "tasks": tasks, "expenses": expenses}
    st.download_button("📥 이 여행 백업 다운로드 (JSON)", json.dumps(export, ensure_ascii=False, indent=2), file_name=f"travel_{tid[:8]}.json", mime="application/json")
    st.caption("백업 파일은 외부 보관용입니다. 이 버전에는 백업 복원 기능이 없습니다.")


def show_plan(p, place_map):
    place = place_map.get(p["place"], {"name": "삭제된 장소", "link": ""})
    st.markdown(f"**{p['day']} {p['time']}**")
    st.write(place["name"])
    if valid_link(place["link"]):
        st.link_button("지도·장소 열기", place["link"])
    else:
        st.link_button("지도에서 검색", "https://map.naver.com/p/search/" + quote(place["name"]))
    if p.get("backup"):
        st.caption("☔ 대체 장소: " + place_map.get(p["backup"], {}).get("name", "삭제된 장소"))
    if p.get("memo"):
        st.write(p["memo"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("데이터 처리에 실패했습니다. 연결 상태와 Secrets를 확인해 주세요. Supabase 사용 시 안내 SQL 실행 여부와 service_role 키를 확인하세요. 로컬 모드에서는 저장 폴더의 쓰기 권한을 확인하세요.")
        st.info("새로고침 후 다시 시도해 주세요. 비밀 키나 비밀번호가 들어간 화면은 공유하지 마세요.")
