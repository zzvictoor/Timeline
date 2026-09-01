"""Timeline authentication/crypto helpers."""

from hashlib import md5 as MD5
import logging
from random import choice, shuffle
from string import ascii_letters, digits

import bcrypt

from Timeline.Server.Constants import AS3_PROTOCOL, TIMELINE_LOGGER


class Crypto(object):
    BCRYPT_SALT = b"$2b$12$xxcjQIy5KifXvMdfSdq25O"

    def __init__(self, penguin):
        super(Crypto, self).__init__()
        self.penguin = penguin
        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.random_literals = list(
            ascii_letters + digits + "+_=/_@#$%^&*()-':;!?,.`~\\|<>{}"
        )
        self.randomKey = self.random(5) + "-" + self.random(4)
        self.salt = (
            "a1ebe00441f5aecb185d0ec178ca2305Y(02.>'H}t\":E1_root"
            if self.penguin.Protocol == AS3_PROTOCOL
            else "Y(02.>'H}t\":E1"
        )

    @staticmethod
    def _bytes(value):
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    def swap(self, text, length):
        return text[length:] + text[:length]

    def md5(self, text):
        return MD5(self._bytes(text)).hexdigest()

    def bcrypt(self, text):
        return bcrypt.hashpw(self._bytes(text), self.BCRYPT_SALT).decode("ascii")

    def bcheck(self, password, hashed):
        try:
            return bcrypt.hashpw(self._bytes(password), self.BCRYPT_SALT) == self._bytes(hashed)
        except (TypeError, ValueError):
            return False

    def pureMD5(self, text):
        return MD5(self._bytes(text))

    def random(self, length=10):
        shuffle(self.random_literals)
        return "".join(choice(self.random_literals) for _ in range(length))

    def loginHash(self):
        if self.penguin["password"] is None:
            return None
        value = self.swap(self.penguin["password"], 16)
        value += self.randomKey
        value += self.salt
        return self.swap(self.md5(value), 16)

    def confirmHash(self):
        if self.penguin["swid"] is None:
            return None
        adkey = self.randomKey.split("-")[1]
        antekey = self.penguin["swid"][1:-1].split("-")
        usab = antekey[0][:4] + antekey[-1][:6]
        return usab + adkey
