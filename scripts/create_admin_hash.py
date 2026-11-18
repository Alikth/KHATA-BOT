from getpass import getpass
from argon2 import PasswordHasher
password = getpass("New admin access code: ")
if len(password) < 12:
    raise SystemExit("Use at least 12 characters.")
print("ADMIN_PASSWORD_HASH=" + PasswordHasher().hash(password))
