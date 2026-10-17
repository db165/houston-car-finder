## photo check with claude haiku: paint, body, rust, flood signs

import json
import os
import re
import requests

apiUrl = "https://api.anthropic.com/v1/messages"

prompt = """You are inspecting used-car listing photos for a buyer who wants a car that needs little to no work and whose paint does not look bad.
Look only at what is visible. Reply with ONLY this JSON:
{"paint": "good|fair|poor", "body": "good|minor|major", "rust": "none|surface|heavy",
 "floodSigns": true/false, "photosUseful": true/false,
 "verdict": "looks good|minor issues|skip", "notes": "one short sentence on anything a buyer should check"}
"poor" paint = faded/peeling clear coat, big oxidized panels, mismatched panels. "major" body = crash damage, crumpled panels, missing parts.
floodSigns = waterline marks, silt/mud in interior, corroded seat rails, mildew. If photos are stock images or only show text, photosUseful=false."""


damagePrompt = """These are salvage auction photos of a damaged car. The buyer's dad owns a body shop and wants cars with MILD, cosmetic-to-moderate front damage that a body shop can fix cheaply (bumper cover, grille, headlight, hood, fender).
Look only at what is visible. Reply with ONLY this JSON:
{"severity": "mild|moderate|severe", "airbagsDeployed": true/false, "structural": true/false,
 "partsLikely": ["short part names"], "photosUseful": true/false,
 "verdict": "good candidate|maybe|skip", "notes": "one short sentence for the body shop"}
"severe" = crumpled frame rails, pushed-in radiator support, engine/suspension damage, damage past the front wheels.
structural = frame/unibody, strut tower, or radiator support visibly bent. If photos don't show the damage, photosUseful=false."""


def check(photos, cfg, text=None):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not photos:
        return None
    content = [{"type": "image", "source": {"type": "url", "url": u}}
               for u in photos[:cfg["vision"]["maxPhotos"]]]
    content.append({"type": "text", "text": text or prompt})
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    body = {"model": cfg["vision"]["model"], "max_tokens": 1024,
            "thinking": {"type": "disabled"},  # a yes/no photo check doesn't need reasoning tokens
            "messages": [{"role": "user", "content": content}]}
    try:
        r = requests.post(apiUrl, timeout=60, headers=headers, json=body)
        if r.status_code == 400:
            # model may not allow thinking off; let it think but leave room for the answer
            body.pop("thinking")
            body["max_tokens"] = 4096
            r = requests.post(apiUrl, timeout=90, headers=headers, json=body)
        if not r.ok:
            return {"error": f"{r.status_code}: {r.text[:200]}"}
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        hit = re.search(r"\{.*\}", text, re.S)
        if not hit:
            kinds = [b.get("type") for b in data.get("content", [])]
            return {"error": f"no json (stop: {data.get('stop_reason')}, blocks: {kinds}) {text[:80]}"}
        return json.loads(hit.group(0))
    except Exception as e:
        return {"error": str(e)[:200]}


def isDealbreaker(v):
    if not v or v.get("error") or not v.get("photosUseful", True):
        return False
    return v.get("paint") == "poor" or v.get("body") == "major" or v.get("rust") == "heavy" \
        or v.get("floodSigns") is True or v.get("verdict") == "skip"


def isDamageDealbreaker(v):
    if not v or v.get("error") or not v.get("photosUseful", True):
        return False
    return v.get("severity") == "severe" or v.get("airbagsDeployed") is True or v.get("structural") is True \
        or v.get("verdict") == "skip"
