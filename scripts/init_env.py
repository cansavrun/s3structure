import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
try:
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print(".env zaten var; değiştirilmedi.")
else:
    with os.fdopen(fd, "w") as file:
        file.write(
            f"APP_SECRET={secrets.token_hex(32)}\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\n"
            "PUBLIC_ORIGIN=http://localhost:8080\n"
        )
    print(".env rastgele sırlarla oluşturuldu.")
