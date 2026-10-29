"""SPOS_TEST_JITTER=0.4: every request of the live server waits up to that many seconds, so answers arrive late and
out of order, as on a busy CI machine. For finding races; off by default."""

import os
import random
import time


def jitter(get_response):
    most = float(os.environ.get("SPOS_TEST_JITTER") or 0)

    def middleware(request):
        if most:
            time.sleep(random.uniform(0, most))
        return get_response(request)

    return middleware
