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


def sendLot(lot):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    src = "Copart" if lot["source"] == "copart" else "IAA"
    lines = []
    if lot.get("retailValue"):
        rc = f", est repair ${lot['repairCost']:,.0f}" if lot.get("repairCost") else ""
        lines.append(f"retail ~${lot['retailValue']:,.0f}{rc}")
    bid = f"bid ${lot['currentBid']:,.0f}" if lot.get("currentBid") else "no bids yet"
    lines.append(f"{bid} · sale {lot.get('saleText') or lot.get('saleDate') or 'TBD'}")
    miles = f" · {lot['miles']:,} mi" if isinstance(lot.get("miles"), int) and lot["miles"] > 0 else ""
    lines.append(f"{lot.get('damage', '').title()} · {lot.get('condition', '').title()}{miles}")
    where = lot.get("yard") or ""
    if lot.get("distance") is not None:
        where += f" ({lot['distance']:.0f} mi from shop)"
    lines.append(where)
    v = lot.get("vision")
    if v and not v.get("error"):
        lines.append(f"photos: {v.get('severity')} damage. {v.get('notes', '')}")
    for f in lot.get("flags", [])[:2]:
        lines.append("⚠ " + f)
    headers = {"Title": f"{src}: {lot['year']} {lot['make']} {lot['model']}", "Click": lot["url"],
               "Priority": "default", "Tags": "wrench"}
    if lot.get("photos"):
        headers["Attach"] = lot["photos"][0]
    try:
        return requests.post(f"https://ntfy.sh/{topic}", data="\n".join(lines).encode("utf-8"),
                             headers=headers, timeout=20).ok
    except Exception:
        return False
