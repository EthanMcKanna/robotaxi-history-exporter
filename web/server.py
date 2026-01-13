#!/usr/bin/env python3
"""
Simple development server that proxies Tesla API requests to avoid CORS issues.
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PORT = 8080

class ProxyHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/token':
            self.proxy_token_request()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path.startswith('/api/rides'):
            self.proxy_rides_request()
        else:
            # Serve static files
            super().do_GET()

    def proxy_token_request(self):
        """Proxy token requests to Tesla OAuth endpoint."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            req = Request(
                'https://auth.tesla.com/oauth2/v3/token',
                data=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST'
            )

            with urlopen(req, timeout=30) as response:
                data = response.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)

        except HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': error_body}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def proxy_rides_request(self):
        """Proxy ride history requests to Tesla API."""
        try:
            auth_header = self.headers.get('Authorization', '')
            parsed = urlparse(self.path)
            query = parsed.query

            # Try endpoints in order
            endpoints = [
                f'https://ownership.tesla.com/mobile-app/ride/history?{query}',
                f'https://akamai-apigateway-charging-ownership.tesla.com/mobile-app/ride/history?{query}',
            ]

            for url in endpoints:
                try:
                    req = Request(url, headers={
                        'Authorization': auth_header,
                        'Content-Type': 'application/json',
                        'Accept': '*/*',
                        'X-Tesla-User-Agent': 'TeslaApp/4.36.5-2659/abc123/ios/18.0',
                    })

                    with urlopen(req, timeout=30) as response:
                        data = response.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(data)
                        return

                except HTTPError as e:
                    if e.code == 401:
                        raise
                    continue

            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'No working endpoint'}).encode())

        except HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'API error: {e.code}'}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def log_message(self, format, *args):
        """Cleaner logging."""
        print(f"[{self.log_date_time_string()}] {args[0]}")


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(('', PORT), ProxyHandler)
    print(f"\n  Robotaxi History Viewer")
    print(f"  http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
