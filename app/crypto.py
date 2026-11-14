"""Authenticated, purpose-bound envelopes. Keys never live in database rows."""

import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings


def cipher():
    if not settings.statement_encryption_key:
        raise HTTPException(503, "Configure a chave de criptografia no servidor.")
    return Fernet(settings.statement_encryption_key.encode())


def seal(data, uid, purpose, key):
    return cipher().encrypt(
        json.dumps(
            {"v": 1, "uid": uid, "purpose": purpose, "key": str(key), "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode()
    )


def unseal(payload, uid, purpose, key):
    try:
        value = json.loads(cipher().decrypt(payload))
        if (value["v"], value["uid"], value["purpose"], value["key"]) != (
            1,
            uid,
            purpose,
            str(key),
        ):
            raise ValueError()
        return value["data"]
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Dados protegidos indisponíveis.") from None


def protected_field(name, default=None, as_date=False):
    def get(self):
        data = (
            unseal(self.protected_data, self.user_id, "goal", self.crypto_id)
            if self.protected_data
            else {}
        )
        value = data.get(name, default)
        if as_date and value:
            from datetime import date

            return date.fromisoformat(value)
        return value

    def set_value(self, value):
        from uuid import uuid4

        if not self.crypto_id:
            self.crypto_id = str(uuid4())
        data = (
            unseal(self.protected_data, self.user_id, "goal", self.crypto_id)
            if self.protected_data
            else {}
        )
        data[name] = value
        self.protected_data = seal(data, self.user_id, "goal", self.crypto_id)

    return property(get, set_value)
