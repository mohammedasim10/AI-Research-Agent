"""
security.py - Security utilities for SSRF prevention, URL validation, and user privacy masking.
"""

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# RFC 1918, RFC 3927 (link-local), RFC 5735 (loopback), RFC 2544 (benchmark), RFC 6598 (carrier-grade NAT)
# and IPv6 private/link-local/loopback ranges.
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),         # Private-use (RFC 1918)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address Space (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local (Cloud metadata e.g. AWS/GCP 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),      # Private-use (RFC 1918)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),     # Private-use (RFC 1918)
    ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-Local Unicast
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
    "instance-data",
}


def is_ip_blocked(ip_str: str) -> bool:
    """Checks if an IP address falls within private, loopback, or reserved ranges."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for net in BLOCKED_IP_NETWORKS:
            if ip_obj in net:
                return True
        return False
    except ValueError:
        return True


def validate_url_for_ssrf(url: str, resolve_dns: bool = True) -> Tuple[bool, str]:
    """
    Validates a URL against SSRF vulnerabilities.
    Blocks non-HTTP/HTTPS schemes, private/internal IPs, localhost, and cloud metadata endpoints.
    
    Returns:
        (is_safe: bool, reason: str)
    """
    if not url or not isinstance(url, str):
        return False, "Invalid URL input"

    url = url.strip()
    if not url:
        return False, "Empty URL"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme} (only http/https allowed)"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in URL"

    hostname_clean = hostname.lower().strip("[]")

    if hostname_clean in BLOCKED_HOSTNAMES:
        return False, f"Blocked internal hostname: {hostname_clean}"

    # Check if hostname itself is an IP address
    try:
        ip_obj = ipaddress.ip_address(hostname_clean)
        if is_ip_blocked(str(ip_obj)):
            return False, f"Blocked private/reserved IP: {hostname_clean}"
    except ValueError:
        pass  # Hostname is a domain name, not a raw IP

    # Resolve DNS to check underlying IP addresses
    if resolve_dns:
        try:
            addr_info = socket.getaddrinfo(hostname_clean, parsed.port or (443 if parsed.scheme == "https" else 80))
            for family, _, _, _, sockaddr in addr_info:
                ip_addr = sockaddr[0]
                if is_ip_blocked(ip_addr):
                    return False, f"Hostname {hostname_clean} resolved to blocked IP {ip_addr}"
        except socket.gaierror as e:
            # DNS resolution failure might occur on air-gapped test environments or invalid domains
            logger.debug(f"DNS lookup failed for {hostname_clean}: {e}")
        except Exception as e:
            logger.debug(f"Socket resolution error for {hostname_clean}: {e}")

    return True, "URL is safe"


def mask_user_id(user_id: Any) -> str:
    """Masks a Telegram user ID or identifier for safe logging."""
    if user_id is None:
        return "anon"
    raw = str(user_id)
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"
