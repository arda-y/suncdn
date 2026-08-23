"""
Resolves the real client IP behind a reverse proxy.

Only trusts X-Forwarded-For / X-Real-IP when the immediate connecting peer
is in TRUSTED_PROXIES (set in config.yaml, plus the Docker gateway - see
get_docker_gateway_ip()), otherwise falls back to the raw socket address to
avoid trivial IP spoofing.
"""

from fastapi import Request

import config


def get_docker_gateway_ip() -> str | None:
    """
    Reads /proc/net/route to find the default gateway IP as seen from inside
    this container. This is the Docker bridge gateway, which nginx (running on
    the host) appears as when it reaches this container through Docker's
    published-port path.

    Docker can reassign this IP whenever the compose network is recreated
    (e.g. after `docker compose down`), so we resolve it at each startup
    instead of hardcoding a value in config.yaml that goes stale.
    """
    try:
        with open("/proc/net/route", encoding="ascii") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) < 3:
                    continue
                if fields[1] == "00000000":  # destination 0.0.0.0 = default route
                    gateway_int = int(fields[2], 16)
                    # /proc/net/route stores the gateway in little-endian hex
                    gateway_bytes = gateway_int.to_bytes(4, byteorder="little")
                    return ".".join(str(b) for b in gateway_bytes)
    except (OSError, ValueError):
        pass
    return None


_configured_proxies = set(config.get("TRUSTED_PROXIES", []) or [])
_gateway_ip = get_docker_gateway_ip()
if _gateway_ip:
    _configured_proxies.add(_gateway_ip)
TRUSTED_PROXIES = _configured_proxies


def get_client_ip(request: Request) -> str:
    peer_ip = request.client.host if request.client else "unknown"

    if peer_ip not in TRUSTED_PROXIES:
        return peer_ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # left-most entry is the original client
        return forwarded_for.split(",")[0].strip()

    return peer_ip
