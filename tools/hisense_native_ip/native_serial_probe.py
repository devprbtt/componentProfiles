"""Diagnostic client for Hisense's optional native Serial/IP service.

Not a bridge. Keeps one TCP connection open and distinguishes echoes from ACKs.
"""
import argparse
import socket
import time


def frame(operation, command, value, client='ALL'):
    if operation not in ('Q', 'S') or len(command) != 4 or len(value) != 4 or len(client) != 3:
        raise ValueError('Expected Q/S, four-character command/value and three-character ID')
    body = (operation + client + command + value).encode('ascii')
    return body + bytes([(-sum(body)) & 255]) + b'\r'


def exchange(sock, packet, timeout=2):
    sock.sendall(packet)
    deadline = time.monotonic() + timeout
    received = bytearray()
    while time.monotonic() < deadline:
        sock.settimeout(max(.01, deadline - time.monotonic()))
        try:
            part = sock.recv(4096)
        except socket.timeout:
            break
        if not part:
            print('Server closed connection.', flush=True)
            break
        received.extend(part)
    raw = bytes(received)
    print('TX:', packet.hex(' '), flush=True)
    print('RX:', repr(raw), flush=True)
    if raw == packet:
        print('Echo only; no confirmed status or command acknowledgement.', flush=True)
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.5.22')
    parser.add_argument('--port', type=int, default=7310)
    parser.add_argument('--client', default='ALL')
    args = parser.parse_args()
    with socket.create_connection((args.host, args.port), timeout=4) as sock:
        print('Connected. Keeping this socket open. Querying volume.', flush=True)
        exchange(sock, frame('Q', 'VOLM', '????', args.client))
        print('Enter Q COMMAND or S COMMAND VALUE; quit to close.', flush=True)
        while True:
            try:
                line = input().strip()
            except EOFError:
                return
            if line.lower() == 'quit':
                return
            parts = line.upper().split()
            try:
                if len(parts) == 2 and parts[0] == 'Q':
                    parts.append('????')
                if len(parts) != 3:
                    raise ValueError('Use Q VOLM or S VOLM 0018')
                exchange(sock, frame(*parts, client=args.client))
            except ValueError as error:
                print(error, flush=True)


if __name__ == '__main__':
    main()
