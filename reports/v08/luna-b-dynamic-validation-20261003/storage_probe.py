"""Read macOS NSURL important-usage and ordinary volume capacity without Swift."""

from __future__ import annotations

import ctypes

ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")


objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
objc.objc_getClass.argtypes = [ctypes.c_char_p]
objc.objc_getClass.restype = ctypes.c_void_p
objc.sel_registerName.argtypes = [ctypes.c_char_p]
objc.sel_registerName.restype = ctypes.c_void_p
message = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
send0 = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(message)
send1 = ctypes.CFUNCTYPE(
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)(message)
send_string = ctypes.CFUNCTYPE(
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
)(message)
send_resource = ctypes.CFUNCTYPE(
    ctypes.c_bool,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
)(message)
send_long = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_void_p)(message)


def selector(name: str) -> int:
    return objc.sel_registerName(name.encode())


pool_class = objc.objc_getClass(b"NSAutoreleasePool")
pool = send0(send0(pool_class, selector("alloc")), selector("init"))
try:
    nsstring = objc.objc_getClass(b"NSString")
    path = send_string(nsstring, selector("stringWithUTF8String:"), b"/")
    url = send1(objc.objc_getClass(b"NSURL"), selector("fileURLWithPath:"), path)

    def capacity(key_name: bytes) -> int:
        key = send_string(nsstring, selector("stringWithUTF8String:"), key_name)
        value = ctypes.c_void_p()
        error = ctypes.c_void_p()
        ok = send_resource(
            url,
            selector("getResourceValue:forKey:error:"),
            ctypes.byref(value),
            key,
            ctypes.byref(error),
        )
        if not ok or not value.value:
            raise RuntimeError(f"NSURL resource lookup failed for {key_name!r}")
        return send_long(value, selector("longLongValue"))

    important = capacity(b"NSURLVolumeAvailableCapacityForImportantUsageKey")
    ordinary = capacity(b"NSURLVolumeAvailableCapacityKey")
    print(f"NSURLVolumeAvailableCapacityForImportantUsageKey_bytes={important}")
    print(f"NSURLVolumeAvailableCapacityKey_bytes={ordinary}")
finally:
    send0(pool, selector("drain"))
