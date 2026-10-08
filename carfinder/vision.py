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


def check(photos, cfg):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not photos:
        return None
    content = [{"type": "image", "source": {"type": "url", "url": u}}
               for u in photos[:cfg["vision"]["maxPhotos"]]]
    content.append({"type": "text", "text": prompt})
    try:
        r = requests.post(apiUrl, timeout=60, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": cfg["vision"]["model"], "max_tokens": 300,
                  "messages": [{"role": "user", "content": content}]})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        hit = re.search(r"\{.*\}", text, re.S)
        return json.loads(hit.group(0)) if hit else None
    except Exception as e:
        return {"error": str(e)[:200]}


def isDealbreaker(v):
    if not v or v.get("error") or not v.get("photosUseful", True):
        return False
    return v.get("paint") == "poor" or v.get("body") == "major" or v.get("rust") == "heavy" \
        or v.get("floodSigns") is True or v.get("verdict") == "skip"
