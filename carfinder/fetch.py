## polite http: one shared throttle, normal browser headers, stop on a block

import time
import requests

userAgent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


class Blocked(Exception):
    pass


class Fetcher:
    def __init__(self, delaySeconds=1.5):
        self.delaySeconds = delaySeconds
        self.lastHit = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": userAgent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.requestCount = 0

    def get(self, url, **kwargs):
        wait = self.delaySeconds - (time.time() - self.lastHit)
        if wait > 0:
            time.sleep(wait)
        self.lastHit = time.time()
        self.requestCount += 1
        resp = self.session.get(url, timeout=30, **kwargs)
        # a site saying no once means we stop hitting it this run
        if resp.status_code in (403, 406, 429) or "captcha" in resp.text[:5000].lower():
            raise Blocked(f"{resp.status_code} from {url.split('?')[0]}")
        resp.raise_for_status()
        return resp
