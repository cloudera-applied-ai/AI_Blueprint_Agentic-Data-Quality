"""TLS trust for outbound HTTPS to Cloudera AI Inference and other cluster endpoints.

httpx (used by the OpenAI SDK) trusts only certifi's public CA list by default.
On CML Private Cloud, Cloudera AI Inference is usually signed by the cluster's
internal CA, which the runtime image adds to the SYSTEM trust store, not to
certifi. So we trust the system store, then certifi, then any bundle named in
CAII_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE.
"""

import os
import ssl
from functools import lru_cache

CA_ENV = ("CAII_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE")


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()  # system trust store
    try:
        import certifi

        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    for name in CA_ENV:
        path = os.environ.get(name)
        if path and os.path.exists(path):
            try:
                if os.path.isdir(path):
                    ctx.load_verify_locations(capath=path)
                else:
                    ctx.load_verify_locations(cafile=path)
            except (ssl.SSLError, OSError):
                pass
    return ctx
