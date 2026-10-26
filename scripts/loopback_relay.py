#!/usr/bin/env python3
"""Disposable TCP bridges: fixed loopback listeners to inspected private IPv4s."""
import argparse
import ipaddress
import select
import signal
import socket
import socketserver
import threading


def private_ipv4(value):
    address = ipaddress.IPv4Address(value)
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
        raise argparse.ArgumentTypeError("Expected an inspected private container IPv4 address")
    return str(address)


class RelayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.create_connection(self.server.destination, timeout=5) as upstream:
                self.request.settimeout(5)
                peers = (self.request, upstream)
                while True:
                    readable, _, _ = select.select(peers, [], [], 30)
                    if not readable:
                        return
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.request else self.request).sendall(data)
        except OSError:
            pass  # No traffic, headers, tokens, or exception text are logged.


class RelayServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, listener, destination):
        self.destination = destination
        super().__init__(listener, RelayHandler)

    def handle_error(self, request, client_address):
        pass  # Do not print request/client data or tracebacks.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-ip", type=private_ipv4)
    parser.add_argument("--frontend-ip", type=private_ipv4)
    args = parser.parse_args()
    servers = []
    try:
        for address, port in ((args.backend_ip, 8000), (args.frontend_ip, 3000)):
            if address:
                servers.append(RelayServer(("127.0.0.1", port), (address, port)))
        if not servers:
            parser.error("At least one inspected service address is required")
        # Bind every requested listener before starting threads; partial bind
        # failure closes earlier sockets, never replacing an occupied listener.
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        signal.pause()
    finally:
        for server in servers:
            server.server_close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except OSError:
        raise SystemExit(1)
