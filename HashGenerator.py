#!/usr/bin/python
import re, hashlib

def main():
    while True:
        raw = raw_input('Swipe ID card:\n')
        uid = re.search('[0-9]+',raw).group(0)
        idhash = hashlib.sha256(uid).hexdigest()
        print 'SHA-256 hash:\n', idhash

if __name__ == "__main__":
    main()
