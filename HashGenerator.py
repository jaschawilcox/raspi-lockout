#!/usr/bin/python3
import re, hashlib, random, string

SALT_LENGTH = 10

def hashId(salt, uid):
    instring = salt + uid
    return hashlib.sha256(instring.encode("UTF-8")).hexdigest()

def mainSalted():
    while True:
        raw = input('Swipe ID card:\n')
        uid = re.search('[0-9]+',raw).group(0)
        salt = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(SALT_LENGTH))
        idhash = hashId(salt, uid)
        print('salt+hash:\n' + salt + "+" + idhash)

def main():
    while True:
        raw = input('Swipe ID card:\n')
        uid = re.search('[0-9]+',raw).group(0)
        idhash = hashlib.sha256(uid.encode("UTF-8")).hexdigest()
        print('hash:\n' + idhash)

if __name__ == "__main__":
    main()
