#!/usr/bin/env python
# Copyright 2014-2019, The Tor Project, Inc
# See LICENSE for licensing information

# This script parses openssl headers to find ciphersuite names, determines
# which ones we should be willing to use as a server, and sorts them according
# to preference rules.
#
# Run it on all the files in your openssl include directory.

# Future imports for Python 2.7, mandatory in 3.0
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import re
import sys

EPHEMERAL_INDICATORS = [ "_EDH_", "_DHE_", "_ECDHE_" ]
BAD_STUFF = [ "_DES_40_", "MD5", "_RC4_", "_DES_64_",
              "_SEED_", "_CAMELLIA_", "_NULL",
              "_CCM_8", "_DES_", ]

# these never get #ifdeffed.
MANDATORY = [
    "TLS1_TXT_DHE_RSA_WITH_AES_256_SHA",
    "TLS1_TXT_DHE_RSA_WITH_AES_128_SHA",
]

def find_ciphers(filename):
    with open(filename) as f:
        for line in f:
            if m := re.search(r'(?:SSL3|TLS1)_TXT_\w+', line):
                yield m.group(0)

def usable_cipher(ciph):
    ephemeral = any(e in ciph for e in EPHEMERAL_INDICATORS)
    if not ephemeral:
        return False

    return False if "_RSA_" not in ciph else all(b not in ciph for b in BAD_STUFF)

# All fields we sort on, in order of priority.
FIELDS = [ 'cipher', 'fwsec', 'mode',  'digest', 'bitlength' ]
# Map from sorted fields to recognized value in descending order of goodness
FIELD_VALS = { 'cipher' : [ 'AES', 'CHACHA20' ],
               'fwsec' : [ 'ECDHE', 'DHE' ],
               'mode' : [ 'POLY1305', 'GCM', 'CCM', 'CBC', ],
               'digest' : [ 'n/a', 'SHA384', 'SHA256', 'SHA', ],
               'bitlength' : [ '256', '128', '192' ],
}

class Ciphersuite(object):
    def __init__(self, name, fwsec, cipher, bitlength, mode, digest):
        if fwsec == 'EDH':
            fwsec = 'DHE'

        if mode in [ '_CBC3', '_CBC', '' ]:
            mode = 'CBC'
        elif mode == '_GCM':
            mode = 'GCM'

        self.name = name
        self.fwsec = fwsec
        self.cipher = cipher
        self.bitlength = bitlength
        self.mode = mode
        self.digest = digest

        for f in FIELDS:
            assert(getattr(self, f) in FIELD_VALS[f])

    def sort_key(self):
        return tuple(FIELD_VALS[f].index(getattr(self,f)) for f in FIELDS)


def parse_cipher(ciph):
    if m := re.match(
        '(?:TLS1|SSL3)_TXT_(EDH|DHE|ECDHE)_RSA(?:_WITH)?_(AES|DES)_(256|128|192)(|_CBC|_CBC3|_GCM)_(SHA|SHA256|SHA384)$',
        ciph,
    ):
        fwsec, cipher, bits, mode, digest = m.groups()
        return Ciphersuite(ciph, fwsec, cipher, bits, mode, digest)

    if m := re.match(
        '(?:TLS1|SSL3)_TXT_(EDH|DHE|ECDHE)_RSA(?:_WITH)?_(AES|DES)_(256|128|192)_CCM',
        ciph,
    ):
        fwsec, cipher, bits = m.groups()
        return Ciphersuite(ciph, fwsec, cipher, bits, "CCM", "n/a")

    if m := re.match(
        '(?:TLS1|SSL3)_TXT_(EDH|DHE|ECDHE)_RSA(?:_WITH)?_CHACHA20_POLY1305',
        ciph,
    ):
        fwsec, = m.groups()
        return Ciphersuite(ciph, fwsec, "CHACHA20", "256", "POLY1305", "n/a")

    print(f"/* Couldn't parse {ciph} ! */")
    return None


ALL_CIPHERS = []

for fname in sys.argv[1:]:
    for c in find_ciphers(fname):
        if usable_cipher(c):
            parsed = parse_cipher(c)
            if parsed != None:
                ALL_CIPHERS.append(parsed)

ALL_CIPHERS.sort(key=Ciphersuite.sort_key)

indent = " "*7

for c in ALL_CIPHERS:
    colon = '' if c is ALL_CIPHERS[-1] else ' ":"'
    if c.name in MANDATORY:
        print(f"{indent}/* Required */")
        print(f'{indent}{c.name}{colon}')
    else:
        print(f"#ifdef {c.name}")
        print(f'{indent}{c.name}{colon}')
        print("#endif")

print(f'{indent};')

