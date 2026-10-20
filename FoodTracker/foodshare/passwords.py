"""Password hashing with Python's standard library only.

Hashes use the same "method$salt$hash" format as Werkzeug, so data files made by
the earlier Flask version of this app keep working. Passwords are never stored.
"""

import hashlib
import hmac
import secrets
import string

SALT_CHARS = string.ascii_letters + string.digits
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
PBKDF2_DEFAULT_ITERATIONS = 1_000_000


def _scrypt(password, salt, n, r, p):
    return hashlib.scrypt(password.encode(), salt=salt.encode(), n=n, r=r, p=p,
                          maxmem=132 * n * r * p).hex()


def hash_password(password):
    salt = "".join(secrets.choice(SALT_CHARS) for _ in range(16))
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}${salt}${digest}"


def check_password(stored, password):
    """True if password matches the stored hash."""
    try:
        method, salt, expected = stored.split("$", 2)
        name, *args = method.split(":")
        if name == "scrypt":
            n, r, p = map(int, args) if args else (SCRYPT_N, SCRYPT_R, SCRYPT_P)
            actual = _scrypt(password, salt, n, r, p)
        elif name == "pbkdf2":
            hash_name = args[0] if args else "sha256"
            iterations = int(args[1]) if len(args) > 1 else PBKDF2_DEFAULT_ITERATIONS
            actual = hashlib.pbkdf2_hmac(hash_name, password.encode(), salt.encode(),
                                         iterations).hex()
        else:
            return False
    except (AttributeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)
