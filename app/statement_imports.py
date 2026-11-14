"""Bounded authenticated upload -> encrypted preview -> atomic user confirmation."""

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import anyio
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.balance import lock_wallet
from app.config import settings
from app.crypto import cipher
from app.db import SessionLocal, get_db
from app.ingestion import make_entry
from app.models import Entry, ImportLease, StatementImport
from app.schemas import Strict
from app.security import current_user, limit
from app.statement_parser import MAX_BYTES, MAX_ROWS
from app.statement_parsers import REGISTRY

router = APIRouter(prefix="/imports", tags=["Extratos"])
FORMATS = {"csv", "pdf", "xml", "ofx", "docx"}
MIMES = {
    "csv": {"text/csv", "text/plain", "application/vnd.ms-excel"},
    "pdf": {"application/pdf"},
    "xml": {"application/xml", "text/xml"},
    "ofx": {"application/x-ofx", "application/ofx", "text/plain"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}


class MemoryMultipartParser(MultiPartParser):
    # Total body is capped before parsing. Never spill a bank statement to /tmp.
    spool_max_size = MAX_BYTES + 65536


def fingerprint(data, uid):
    return hmac.new(
        settings.statement_encryption_key.encode(), str(uid).encode() + b":" + data, hashlib.sha256
    ).hexdigest()


def acquire_slot():
    """Two concurrent uploads/parsers across all API workers; leases survive crashes."""
    now, token = int(time.time()), secrets.token_hex(16)
    with SessionLocal() as db:
        for slot in (1, 2):
            try:
                db.add(ImportLease(id=slot, token="", expires_at=0))
                db.commit()
            except IntegrityError:
                db.rollback()
            changed = db.execute(
                update(ImportLease)
                .where(ImportLease.id == slot, ImportLease.expires_at <= now)
                .values(token=token, expires_at=now + 60)
            )
            db.commit()
            if changed.rowcount:
                return token
    raise HTTPException(
        429, "Importador ocupado. Tente novamente em instantes.", headers={"Retry-After": "15"}
    )


def release_slot(token):
    with SessionLocal() as db:
        db.execute(
            update(ImportLease).where(ImportLease.token == token).values(expires_at=0, token="")
        )
        db.commit()


def parse_isolated(data, fmt, institution=None):
    windows_dev = (
        os.name == "nt"
        and settings.environment == "development"
        and settings.allow_windows_import_dev
    )

    if os.name != "posix" and not windows_dev:
        raise HTTPException(
            503, "Importação requer Linux ou ambiente Windows de desenvolvimento autorizado."
        )
    try:
        worker_env = {
            "LANG": "C.UTF-8",
            "PATH": os.defpath,
        }

        if os.name == "nt":
            for key, value in os.environ.items():
                if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}:
                    worker_env[key] = value

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).with_name("statement_worker.py")),
                fmt,
                *([institution] if institution else []),
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=12,
            cwd=(os.environ.get("TEMP", os.environ.get("TMP")) if os.name == "nt" else "/tmp"),
            env=worker_env,
            check=False,
        )
        if len(result.stdout) > 512 * 1024:
            raise ValueError()
        rows = json.loads(result.stdout)
        if result.returncode or isinstance(rows, dict):
            code = rows.get("error") if isinstance(rows, dict) else None
            messages = {
                "worker_unavailable": "O processador de extratos está indisponível. Verifique a instalação do servidor e tente novamente.",
                "institution_mismatch": "O arquivo pertence a outra instituição. Confira o banco selecionado.",
                "invalid_institution": "Selecione uma instituição financeira válida.",
                "unsupported_layout": "Layout não reconhecido, arquivo corrompido ou protegido. Confira o banco e exporte CSV/OFX. Nenhum lançamento foi salvo.",
            }
            raise HTTPException(
                503 if code == "worker_unavailable" else 422,
                messages.get(code, messages["unsupported_layout"]),
                headers={"X-Error-Code": code if code in messages else "unsupported_layout"},
            )
        if not 1 <= len(rows) <= MAX_ROWS:
            raise ValueError()
        return rows
    except subprocess.TimeoutExpired:
        raise HTTPException(
            504,
            "O processamento excedeu o tempo limite. Envie um período menor.",
            headers={"X-Error-Code": "processing_timeout"},
        ) from None
    except (subprocess.SubprocessError, ValueError, OSError):
        raise HTTPException(
            503,
            "O processador de extratos está indisponível. Tente novamente.",
            headers={"X-Error-Code": "worker_unavailable"},
        ) from None


def decrypt(row, uid):
    try:
        data = json.loads(cipher().decrypt(row.payload, ttl=3600))
        if data["user_id"] != uid or data["id"] != row.id:
            raise ValueError()
        return data["rows"]
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(410, "Prévia expirada ou indisponível. Envie o extrato novamente.")


def preview(row, db, uid):
    rows = decrypt(row, uid)
    existing = Counter(
        db.execute(
            select(Entry.on_date, Entry.kind, Entry.amount_cents).where(
                Entry.user_id == uid,
                Entry.on_date >= date.fromisoformat(min(r["on_date"] for r in rows)),
                Entry.on_date <= date.fromisoformat(max(r["on_date"] for r in rows)),
            )
        ).all()
    )
    output = []
    for index, r in enumerate(rows):
        key = (date.fromisoformat(r["on_date"]), r["kind"], r["amount_cents"])
        duplicate = existing[key] > 0
        if duplicate:
            existing[key] -= 1
        output.append(dict(r, index=index, possible_duplicate=duplicate))
    return {
        "id": row.id,
        "expires_at": row.expires_at,
        "rows": output,
        "income_cents": sum(r["amount_cents"] for r in rows if r["kind"] == "income"),
        "expense_cents": sum(r["amount_cents"] for r in rows if r["kind"] == "expense"),
    }


def store_preview(data, fmt, uid, institution=None):
    rows = parse_isolated(data, fmt, institution)
    digest = fingerprint(data, uid)
    now = int(time.time())
    with SessionLocal() as db:
        lock_wallet(db, uid)
        db.execute(
            delete(StatementImport).where(
                StatementImport.user_id == uid,
                StatementImport.status == "pending",
                StatementImport.expires_at <= now,
            )
        )
        existing = db.scalar(
            select(StatementImport)
            .where(StatementImport.user_id == uid, StatementImport.fingerprint == digest)
            .with_for_update()
        )
        if existing:
            if existing.status == "confirmed":
                raise HTTPException(409, "Este arquivo já foi confirmado. Consulte os lançamentos.")
            return preview(existing, db, uid)
        pending = db.scalars(
            select(StatementImport)
            .where(StatementImport.user_id == uid, StatementImport.status == "pending")
            .with_for_update()
        ).all()
        if len(pending) >= 3:
            raise HTTPException(
                409, "Confirme ou descarte as prévias pendentes antes de enviar outro extrato."
            )
        identifier = str(uuid4())
        payload = cipher().encrypt(
            json.dumps({"id": identifier, "user_id": uid, "rows": rows}).encode()
        )
        row = StatementImport(
            id=identifier,
            user_id=uid,
            fingerprint=digest,
            payload=payload,
            expires_at=now + 3600,
            status="pending",
            imported_count=0,
        )
        db.add(row)
        db.flush()
        response = preview(row, db, uid)
        db.commit()
        return response


@router.post("/preview")
async def upload(
    request: Request,
    format: str | None = Query(None),
    institution: str | None = Query(None),
    user=Depends(current_user),
):
    cipher()
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    multipart = mime == "multipart/form-data"
    if not multipart:
        validate_upload_metadata(format, institution, mime)
    for scope, maximum, seconds in [("import-minute", 6, 60), ("import-day", 120, 86400)]:
        await run_in_threadpool(limit, scope, str(user.id), maximum, seconds)
    await run_in_threadpool(
        limit, "import-global", "all", settings.import_global_hourly_limit, 3600
    )
    token = await run_in_threadpool(acquire_slot)
    try:
        data = bytearray()
        try:
            with anyio.fail_after(20):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BYTES + (65536 if multipart else 0):
                        raise HTTPException(
                            413, "Limite de 5 MiB por arquivo. Divida o histórico por período."
                        )
                    data.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "Tempo limite de envio excedido.")
        if multipart:
            # Parse only AFTER authentication, rate limit and the total streamed size cap.
            async def stream():
                yield bytes(data)

            try:
                form = await MemoryMultipartParser(
                    request.headers, stream(), max_files=1, max_fields=2, max_part_size=256
                ).parse()
            except MultiPartException:
                raise HTTPException(
                    400, "Envio multipart inválido. Selecione o arquivo novamente."
                ) from None
            try:
                if len(form.multi_items()) != 2 or set(form.keys()) != {"file", "institution"}:
                    raise HTTPException(422, "Envie um arquivo e a instituição selecionada.")
                file, selected = form["file"], form["institution"]
                if not isinstance(file, UploadFile) or not isinstance(selected, str):
                    raise HTTPException(422, "Arquivo ou instituição inválidos.")
                file_format = (file.filename or "").rsplit(".", 1)[-1].lower()
                validate_upload_metadata(
                    file_format, selected, (file.content_type or "application/octet-stream").lower()
                )
                if file.size is None or not 0 < file.size <= MAX_BYTES:
                    raise HTTPException(413, "O arquivo precisa ter entre 1 byte e 5 MiB.")
                content = await file.read(MAX_BYTES + 1)
            finally:
                await form.close()
            return await run_in_threadpool(store_preview, content, file_format, user.id, selected)
        return await run_in_threadpool(store_preview, bytes(data), format, user.id, institution)
    finally:
        await run_in_threadpool(release_slot, token)


def validate_upload_metadata(fmt, institution, mime):
    if institution not in REGISTRY:
        raise HTTPException(422, "Selecione uma instituição financeira válida.")
    if fmt not in FORMATS:
        raise HTTPException(415, "Use CSV, OFX, XML, PDF textual ou DOCX sem macros.")
    if mime not in MIMES[fmt] | {"application/octet-stream"}:
        raise HTTPException(415, "Tipo de conteúdo incompatível com o formato informado.")


@router.get("")
def pending(user=Depends(current_user), db=Depends(get_db)):
    return [
        {"id": r.id, "expires_at": r.expires_at}
        for r in db.scalars(
            select(StatementImport).where(
                StatementImport.user_id == user.id,
                StatementImport.status == "pending",
                StatementImport.expires_at > int(time.time()),
            )
        ).all()
    ]


@router.get("/{item_id}")
def get_preview(item_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    row = db.scalar(
        select(StatementImport).where(
            StatementImport.id == str(item_id), StatementImport.user_id == user.id
        )
    )
    if row is None or row.status != "pending":
        raise HTTPException(404, "Prévia não encontrada.")
    return preview(row, db, user.id)


class ConfirmImport(Strict):
    selected: list[int] = Field(min_length=1, max_length=MAX_ROWS)


@router.post("/{item_id}/confirm")
def confirm(item_id: UUID, payload: ConfirmImport, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    row = db.scalar(
        select(StatementImport)
        .where(StatementImport.id == str(item_id), StatementImport.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Prévia não encontrada.")
    if row.status == "confirmed":
        return {"imported_count": row.imported_count, "already_confirmed": True}
    rows = decrypt(row, user.id)
    if len(set(payload.selected)) != len(payload.selected) or any(
        i < 0 or i >= len(rows) for i in payload.selected
    ):
        raise HTTPException(422, "Seleção inválida.")
    for i in payload.selected:
        r = rows[i]
        db.add(
            make_entry(
                user_id=user.id,
                source="statement",
                request_id=str(uuid4()),
                on_date=date.fromisoformat(r["on_date"]),
                amount_cents=r["amount_cents"],
                kind=r["kind"],
                category="outros" if r["kind"] == "expense" else "outras_receitas",
                description="",
                essential=False,
                payment_method="other",
                context=r.get("context"),
            )
        )
    row.status, row.imported_count, row.payload = "confirmed", len(payload.selected), b""
    db.commit()
    return {"imported_count": row.imported_count, "already_confirmed": False}


@router.delete("/{item_id}", status_code=204)
def discard(item_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    lock_wallet(db, user.id)
    result = db.execute(
        delete(StatementImport).where(
            StatementImport.id == str(item_id),
            StatementImport.user_id == user.id,
            StatementImport.status == "pending",
        )
    )
    if not result.rowcount:
        raise HTTPException(404, "Prévia não encontrada.")
    db.commit()
