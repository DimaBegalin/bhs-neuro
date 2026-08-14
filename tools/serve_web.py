"""Локальный статический сервер для страниц теста и монитора."""
import http.server
import os
import socketserver

PORT = 8080
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

if __name__ == "__main__":
    os.chdir(ROOT)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"монитор: http://127.0.0.1:{PORT}/monitor.html")
        httpd.serve_forever()
