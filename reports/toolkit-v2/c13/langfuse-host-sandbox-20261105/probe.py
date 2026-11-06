import errno, json, os, socket, sys

def blocked(operation):
    try:
        operation()
    except OSError as exc:
        return exc.errno in (errno.EACCES, errno.EPERM)
    return False

path, approved, port, alternate = sys.argv[1:]
with open(approved, 'rb') as stream:
    readable = bool(stream.read(1))
with socket.create_connection(('127.0.0.1', int(port)), timeout=2):
    allowed = True
print(json.dumps({
    'approved_path_read': readable,
    'approved_loopback_connect': allowed,
    'unrelated_read_denied': blocked(lambda: os.close(os.open(path, os.O_RDONLY))),
    'unrelated_write_denied': blocked(lambda: os.close(os.open(path, os.O_WRONLY))),
    'unrelated_loopback_denied': blocked(lambda: socket.create_connection(('127.0.0.1', int(alternate)), timeout=2)),
}))
