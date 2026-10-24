"""랭킹 수집본을 받아 날짜별 스냅샷·변경 기록을 쌓고 pets_info.json 랭킹을 갱신한다.

사용:
  기준점 만들기(최초 1회):  python3 tools/rank_history.py --baseline-file <이전 pets_info.json> --at 2026-10-24T00:39:00+09:00
  갱신:                    python3 tools/rank_history.py rankings_latest.json --at 2026-10-24T16:40:00+09:00
  (--at 생략 시 현재 시각)

결과:
  history/snapshots/<날짜_시각>.json   그날의 전체 랭킹 (원본 기록, 수정 금지)
  history/changes/<날짜_시각>.json     직전 스냅샷 대비 변경 상세 (레벨업 시 스탯 변화 포함)
  history/changes_index.json           변경 기록 목록과 요약
  history/timeline.json                (펫, 닉네임)별 레벨·스탯 시계열
  pets_info.json                       현재 랭킹으로 갱신 (랭킹 외 필드는 유지)
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "history")
SNAP, CHG = os.path.join(H, "snapshots"), os.path.join(H, "changes")
STATS = ("atk", "def", "agi", "hp")
KEYS = ("nick", "lv") + STATS


def jload(p):
    return json.load(open(p, encoding="utf-8"))


def jdump(p, o, **kw):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, **kw)


def snap_from_pets(pets):
    return {str(p["id"]): [[r["nick"], r["lv"], r["atk"], r["def"], r["agi"], r["hp"]] for r in p["ranking"]] for p in pets}


def snap_from_latest(path):
    rk = jload(path)["rankings"]
    return {i: [[r["nick"], r["lv"], r["atk"], r["def"], r["agi"], r["hp"]] for r in v["ranking"]] for i, v in rk.items()}


def fname(at):
    d = datetime.datetime.fromisoformat(at)
    return d.strftime("%Y-%m-%d_%H%M")


def latest_snapshot():
    if not os.path.isdir(SNAP):
        return None
    fs = sorted(f for f in os.listdir(SNAP) if f.endswith(".json"))
    return (fs[-1], jload(os.path.join(SNAP, fs[-1]))) if fs else None


def row_dict(r):
    return dict(zip(KEYS, r))


def diff(old, new, pets):
    by = {str(p["id"]): p for p in pets}
    out = []
    for pid in sorted(new, key=int):
        o, n = old.get(pid, []), new[pid]
        if o == n:
            continue
        p = by[pid]
        g = p["growth_rates"]
        om = {r[0]: (i + 1, r) for i, r in enumerate(o)}
        nm = {r[0]: (i + 1, r) for i, r in enumerate(n)}
        ev = []
        for nick, (nr, r) in nm.items():
            if nick not in om:
                ev.append({"type": "enter", "nick": nick, "rank": nr, "to": row_dict(r)})
                continue
            orank, orow = om[nick]
            if orow == r and orank == nr:
                continue
            d = {k: r[2 + i] - orow[2 + i] for i, k in enumerate(STATS)}
            dl = r[1] - orow[1]
            e = {"nick": nick, "rank_from": orank, "rank_to": nr, "lv_from": orow[1], "lv_to": r[1],
                 "from": row_dict(orow), "to": row_dict(r), "delta": d}
            if dl > 0:
                e["type"] = "level_up"
                e["levels"] = dl
                e["per_level"] = {k: round(d[k] / dl, 2) for k in STATS}
                e["expected_by_growth"] = {k: round(g[k] * dl, 1) for k in STATS}
            elif dl < 0:
                e["type"] = "level_down"
            elif any(d.values()):
                e["type"] = "stat_change"
            else:
                e["type"] = "rank_move"
            ev.append(e)
        for nick, (orank, orow) in om.items():
            if nick not in nm:
                ev.append({"type": "exit", "nick": nick, "rank_from": orank, "from": row_dict(orow)})
        if ev:
            out.append({"id": p["id"], "name": p["name"], "before": o, "after": n, "events": ev})
    return out


def summarize(changes):
    c = {}
    for ch in changes:
        for e in ch["events"]:
            c[e["type"]] = c.get(e["type"], 0) + 1
    return {"pets_changed": len(changes), "events": c}


def update_timeline(snapshot, at):
    p = os.path.join(H, "timeline.json")
    tl = jload(p) if os.path.exists(p) else {}
    for pid, rows in snapshot.items():
        for r in rows:
            seq = tl.setdefault(pid, {}).setdefault(r[0], [])
            cur = [r[1], r[2], r[3], r[4], r[5]]
            if not seq or seq[-1][1:] != cur:
                seq.append([at] + cur)
    jdump(p, tl, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("latest", nargs="?", help="수집한 rankings_latest.json")
    ap.add_argument("--baseline-file", help="기준점으로 쓸 이전 pets_info.json")
    ap.add_argument("--at", help="수집 시각 ISO (예: 2026-10-24T16:40:00+09:00)")
    a = ap.parse_args()
    at = a.at or datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    pets_path = os.path.join(ROOT, "pets_info.json")
    cur = jload(pets_path)
    pets = cur["pets"]

    if a.baseline_file:
        new = snap_from_pets(jload(a.baseline_file)["pets"])
        kind = "baseline"
    elif a.latest:
        new = snap_from_latest(a.latest)
        kind = "update"
    else:
        sys.exit("rankings_latest.json 또는 --baseline-file 이 필요합니다")
    if set(new) != {str(p["id"]) for p in pets}:
        sys.exit("펫 id 목록이 pets_info.json 과 다릅니다. 새 펫이 추가됐는지 확인하세요")

    prev = latest_snapshot()
    name = fname(at)
    if os.path.exists(os.path.join(SNAP, name + ".json")):
        sys.exit("같은 시각의 스냅샷이 이미 있습니다: " + name)
    jdump(os.path.join(SNAP, name + ".json"), {"collected_at": at, "kind": kind, "rankings": new}, separators=(",", ":"))
    update_timeline(new, at)

    idx_p = os.path.join(H, "changes_index.json")
    idx = jload(idx_p) if os.path.exists(idx_p) else []
    if prev:
        changes = diff(prev[1]["rankings"], new, pets)
        summ = summarize(changes)
        jdump(os.path.join(CHG, name + ".json"),
              {"from": prev[1]["collected_at"], "to": at, "summary": summ, "pets": changes}, indent=1)
        idx.append({"file": "changes/" + name + ".json", "from": prev[1]["collected_at"], "to": at, **summ})
        print("변경 기록:", name, summ)
    else:
        idx.append({"file": None, "from": None, "to": at, "note": "기준 스냅샷(비교 대상 없음)"})
        print("기준 스냅샷 생성:", name)
    jdump(idx_p, idx, indent=1)

    if kind == "update":
        for p in pets:
            p["ranking"] = [row_dict(r) | {} for r in new[str(p["id"])]]
        cur["meta"]["ranking_updated"] = at[:10]
        jdump(pets_path, cur, indent=1)
        print("pets_info.json 랭킹 갱신 완료")


if __name__ == "__main__":
    main()
