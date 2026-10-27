#!/usr/bin/env python3
"""One-time OAuth setup for Todoist data:read token.

Usage:
    python3 oauth_setup.py <client_id> <client_secret>

Opens browser for authorization, catches callback, exchanges for token,
saves to ~/.todoist_token with 0600 permissions.
"""
import http.server
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

TOKEN_FILE = os.path.expanduser("~/.todoist_token")
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <client_id> <client_secret>")
        sys.exit(1)

    client_id = sys.argv[1]
    client_secret = sys.argv[2]
    state = secrets.token_hex(16)

    auth_url = (
        f"https://todoist.com/oauth/authorize?"
        f"client_id={client_id}&scope=data:read&state={state}"
    )

    print(f"Opening browser for Todoist authorization...")
    print(f"URL: {auth_url}")
    webbrowser.open(auth_url)

    code = None
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal code
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/callback" and "code" in params:
                returned_state = params.get("state", [""])[0]
                if returned_state != state:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"State mismatch! Possible CSRF.")
                    return

                code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authorization successful!</h1>"
                    b"<p>You can close this tab.</p>"
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress request logs

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    print(f"Waiting for callback on http://localhost:{REDIRECT_PORT}/callback ...")
    server.handle_request()  # Handle exactly one request
    server.server_close()

    if not code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    print("Got authorization code. Exchanging for token...")

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }).encode()

    req = urllib.request.Request(
        "https://todoist.com/oauth/access_token",
        data=data,
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    token = result.get("access_token")
    if not token:
        print(f"ERROR: No access_token in response: {result}")
        sys.exit(1)

    # Save token with 0600 permissions
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)

    print(f"Token saved to {TOKEN_FILE} (permissions: 0600)")
    print(f"Token type: {result.get('token_type', 'unknown')}")
    print("Done! You can now run:")
    print(f"  PYTHONPATH=. python3 bin/full-offline-backup-for-todoist download --with-attachments --token-file {TOKEN_FILE}")


if __name__ == "__main__":
    main()
