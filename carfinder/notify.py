## phone alerts through ntfy.sh (free app, no account; the topic name is the password)

import os
import requests


def sendText(title, body):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    try:
        return requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                             headers={"Title": title, "Tags": "red_car"}, timeout=20).ok
    except Exception:
        return False


def send(rec, kind):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    a = rec["appraisal"]
    pct = f"{a['dealPct'] * 100:.0f}% under" if a.get("dealPct") is not None else "price check"
    miles = f"{rec['miles']:,} mi" if rec.get("miles") else "miles ?"
    where = f"{rec['distance']} mi away" if rec.get("distance") is not None else rec.get("city") or rec["region"]
    lines = [f"${rec['price']:,} vs ~${a['marketValue']:,} market ({pct})" if a.get("marketValue") else f"${rec['price']:,}",
             f"{miles} · {where} · {rec['sellerType']}"]
    if rec.get("vision") and not rec["vision"].get("error"):
        v = rec["vision"]
        lines.append(f"photos: paint {v.get('paint')}, body {v.get('body')}. {v.get('notes', '')}")
    for f in rec.get("flags", [])[:3]:
        lines.append("⚠ " + f)
    label = {"steal": "Deal", "stretch": "Stretch deal", "austin": "Austin no-brainer"}[kind]
    headers = {
        "Title": f"{label}: {rec['year']} {rec['make']} {rec['model']} ${rec['price']:,}",
        "Click": rec["url"],
        "Priority": "high" if kind in ("steal", "austin") else "default",
        "Tags": "red_car",
    }
    if rec.get("photos"):
        headers["Attach"] = rec["photos"][0]
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data="\n".join(lines).encode("utf-8"),
                          headers=headers, timeout=20)
        return r.ok
    except Exception:
        return False
