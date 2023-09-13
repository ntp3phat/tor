# Future imports for Python 2.7, mandatory in 3.0
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import errno
import logging
import os
import random
import socket
import subprocess
import sys
import time

LOG_TIMEOUT = 60.0
LOG_WAIT = 0.1

def fail(msg):
    logging.error('FAIL')
    sys.exit(msg)

def skip(msg):
    logging.warning(f'SKIP: {msg}')
    sys.exit(77)

def try_connecting_to_socksport():
    socks_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if e := socks_socket.connect_ex(('127.0.0.1', socks_port)):
        tor_process.terminate()
        fail(f'Cannot connect to SOCKSPort: error {os.strerror(e)}')
    socks_socket.close()

def wait_for_log(s):
    cutoff = time.time() + LOG_TIMEOUT
    while time.time() < cutoff:
        l = tor_process.stdout.readline()
        l = l.decode('utf8', 'backslashreplace')
        if s in l:
            logging.info(f'Tor logged: "{l.strip()}"')
            return
        # readline() returns a blank string when there is no output
        # avoid busy-waiting
        if len(l) == 0:
            logging.debug(f'Tor has not logged anything, waiting for "{s}"')
            time.sleep(LOG_WAIT)
        else:
            logging.info(f'Tor logged: "{l.strip()}", waiting for "{s}"')
    fail(f'Could not find "{s}" in logs after {LOG_TIMEOUT} seconds')

def pick_random_port():
    port = 0
    random.seed()

    for _ in range(8):
        port = random.randint(10000, 60000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if s.connect_ex(('127.0.0.1', port)) == 0:
            s.close()
        else:
            break

    if port == 0:
        fail('Could not find a random free port between 10000 and 60000')

    return port

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s.%(msecs)03d %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

if sys.hexversion < 0x02070000:
    fail("ERROR: unsupported Python version (should be >= 2.7)")

if sys.hexversion > 0x03000000 and sys.hexversion < 0x03010000:
    fail("ERROR: unsupported Python3 version (should be >= 3.1)")

if 'TOR_SKIP_TEST_REBIND' in os.environ:
    skip('$TOR_SKIP_TEST_REBIND is set')

control_port = pick_random_port()
socks_port = pick_random_port()

assert control_port != 0
assert socks_port != 0

if len(sys.argv) < 3:
    fail(f'Usage: {sys.argv[0]} <path-to-tor> <data-dir>')

if not os.path.exists(sys.argv[1]):
    fail(f'ERROR: cannot find tor at {sys.argv[1]}')
if not os.path.exists(sys.argv[2]):
    fail(f'ERROR: cannot find datadir at {sys.argv[2]}')

tor_path = sys.argv[1]
data_dir = sys.argv[2]

empty_torrc_path = os.path.join(data_dir, 'empty_torrc')
open(empty_torrc_path, 'w').close()
empty_defaults_torrc_path = os.path.join(data_dir, 'empty_defaults_torrc')
open(empty_defaults_torrc_path, 'w').close()

tor_process = subprocess.Popen(
    [
        tor_path,
        '-DataDirectory',
        data_dir,
        '-ControlPort',
        f'127.0.0.1:{control_port}',
        '-SOCKSPort',
        f'127.0.0.1:{socks_port}',
        '-Log',
        'debug stdout',
        '-LogTimeGranularity',
        '1',
        '-FetchServerDescriptors',
        '0',
        '-f',
        empty_torrc_path,
        '--defaults-torrc',
        empty_defaults_torrc_path,
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

if tor_process is None:
    fail('ERROR: running tor failed')

wait_for_log('Opened Control listener')

try_connecting_to_socksport()

control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
if control_socket.connect_ex(('127.0.0.1', control_port)):
    tor_process.terminate()
    fail('Cannot connect to ControlPort')

control_socket.sendall('AUTHENTICATE \r\n'.encode('ascii'))
control_socket.sendall(
    f'SETCONF SOCKSPort=0.0.0.0:{socks_port}\r\n'.encode('ascii')
)
wait_for_log('Opened Socks listener')

try_connecting_to_socksport()

control_socket.sendall(
    f'SETCONF SOCKSPort=127.0.0.1:{socks_port}\r\n'.encode('ascii')
)
wait_for_log('Opened Socks listener')

try_connecting_to_socksport()

control_socket.sendall('SIGNAL HALT\r\n'.encode('ascii'))

wait_for_log('exiting cleanly')
logging.info('OK')

try:
    tor_process.terminate()
except OSError as e:
    if e.errno == errno.ESRCH: # errno 3: No such process
        # assume tor has already exited due to SIGNAL HALT
        logging.warn("Tor has already exited")
    else:
        raise
