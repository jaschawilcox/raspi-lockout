#!/usr/bin/python3
import re, hashlib, random, string

def main():
    while True:
        raw = input('Swipe ID card:\n')
        uid = re.search('[0-9]+',raw).group(0)
        salt = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(5))
        instring = salt + uid
        idhash = hashlib.sha256(instring.encode("UTF-8")).hexdigest()
        print('Salt+hash:', salt + "+" + idhash)

if __name__ == "__main__":
    main()
