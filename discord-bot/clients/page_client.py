import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

import trafilatura


def public_page_target(url: str):
    if not isinstance(url, str) or len(url) > 2000 or any(ord(char) < 33 for char in url):
        raise ValueError("Invalid public URL.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) pages without credentials are supported.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Only standard web ports are supported.")
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
    if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
        raise ValueError("Private, loopback and reserved network addresses are blocked.")
    return parsed, port, addresses[0][4][0]


def fetch_page_text(url: str) -> str:
    """Bounded, anonymous public GETs; redirects are revalidated and DNS is pinned."""
    try:
        for _ in range(4):
            parsed, port, address = public_page_target(url)
            connection = http.client.HTTPConnection(parsed.hostname, port=port, timeout=10)
            try:
                # Connect to the validated IP, while keeping the original Host and TLS SNI.
                # A second DNS lookup by a high-level client would allow DNS rebinding.
                connection.sock = socket.create_connection((address, port), timeout=10)
                if parsed.scheme == "https":
                    connection.sock = ssl.create_default_context().wrap_socket(
                        connection.sock, server_hostname=parsed.hostname,
                    )
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                connection.request("GET", path, headers={
                    "User-Agent": "AriesDiscordBot/1.0", "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity",
                })
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        return ""
                    url = urljoin(url, location)
                    continue
                content_type = response.getheader("Content-Type", "").lower()
                if response.status != 200 or not any(kind in content_type for kind in ("text/html", "text/plain")):
                    return ""
                if response.getheader("Content-Encoding", "identity").lower() != "identity":
                    return ""
                raw = response.read(512 * 1024 + 1)
                if len(raw) > 512 * 1024:
                    return ""
                text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                if "text/html" in content_type:
                    text = trafilatura.extract(text, include_comments=False, include_tables=False) or ""
                return text[:3000]
            finally:
                connection.close()
    except (OSError, ValueError, http.client.HTTPException, UnicodeError, LookupError):
        return ""
    return ""
