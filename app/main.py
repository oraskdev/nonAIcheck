import asyncio
import hmac
import io
import json
import re
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import stripe
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text as sql_text, update
from sqlalchemy.exc import IntegrityError

from . import billing
from .config import ROOT, settings
from .db import Audit, AuthSession, Document, Ledger, Payment, ResetToken, SessionLocal, User, decrypt, encrypt, init_db, now, uid
from .documents import DocumentError, EXPORTERS, block, export_body, extract_file, normalize_blocks
from .pricing import count_words, quote
from .security import DUMMY_HASH, admin_user, current_user, digest, hash_password, rate_limit, verify_password
from .worker import grant_weekly_credits, start_worker


@asynccontextmanager
async def lifespan(app):
    init_db()
    worker = start_worker() if settings.worker_enabled else None
    yield
    if worker:
        worker[0].set()
        await asyncio.to_thread(worker[1].join, 5)


app = FastAPI(title="txtzi API", version="1.0.0", lifespan=lifespan, docs_url=None if settings.production else "/api/docs", redoc_url=None)


@app.middleware("http")
async def secure_requests(request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and path != "/api/billing/webhook":
        if request.headers.get("x-txtzi-request") != "1":
            return JSONResponse({"detail": "Request verification failed. Reload the page and try again."}, 403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != settings.app_url:
            return JSONResponse({"detail": "This request came from an unrecognized origin."}, 403)
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Invalid request length."}, 400)
    if length > settings.max_file_bytes + 500000:
        return JSONResponse({"detail": "Files must be 20 MB or smaller."}, 413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if settings.production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def public_user(user):
    return {"id": user.id, "name": user.name, "email": user.email, "credits": user.credits, "is_admin": user.is_admin}


def document_json(doc, detail=False):
    result = {"id": doc.id, "title": doc.title, "source_type": doc.source_type, "word_count": doc.word_count, "price_cents": doc.price_cents, "status": doc.status, "progress": doc.progress, "stage": doc.stage, "created_at": doc.created_at, "expires_at": doc.expires_at, "quote_expires_at": doc.quote_expires_at, "error": doc.error, "refunded": doc.refunded}
    if detail:
        result.update({"original": decrypt(doc.source), "revised": decrypt(doc.result), "report": decrypt(doc.report), "options": json.loads(doc.options), "warnings": json.loads(doc.warnings), "quote": json.loads(doc.quote_breakdown)})
    return result


def owned_doc(db, doc_id, user):
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(404, "Document not found.")
    return doc


@app.get("/healthz")
def health():
    with SessionLocal() as db:
        db.execute(sql_text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"name": "txtzi", "ai_ready": settings.ai_ready, "payments_ready": settings.payments_ready, "detector_ready": settings.detector_ready, "detector_provider": settings.detector_provider, "detector_name": settings.detector_name, "recovery_ready": bool(settings.resend_key and settings.email_from), "ocr_ready": bool(shutil.which("pdftoppm") and shutil.which("tesseract")), "max_words": settings.max_words, "max_file_mb": 20, "retention_hours": settings.retention_hours, "base_price": settings.base_price, "extra_price": settings.extra_price, "detector_price": settings.detector_price, "ocr_price": settings.ocr_price, "slide_price": settings.slide_price, "credit_packs": billing.PACKS, "weekly_free_credits": settings.weekly_free_credits, "support_email": settings.support_email}


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default="", max_length=80)
    bootstrap_token: str = Field(default="", max_length=150)


def create_session(db, response, user_id):
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(token), user_id=user_id, expires_at=now() + 30 * 86400))
    response.set_cookie("txtzi_session", token, httponly=True, secure=settings.production, samesite="lax", max_age=30 * 86400, path="/")


@app.post("/api/auth/register")
def register(data: Credentials, request: Request, response: Response):
    rate_limit(request, "register", 8, 3600)
    email = data.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not data.name.strip():
        raise HTTPException(400, "Enter your name and a valid email address.")
    is_admin = bool(settings.bootstrap_token and data.bootstrap_token and hmac.compare_digest(settings.bootstrap_token, data.bootstrap_token))
    if data.bootstrap_token and not is_admin:
        raise HTTPException(400, "The administrator setup code is incorrect.")
    with SessionLocal() as db:
        user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password), is_admin=is_admin)
        db.add(user)
        try:
            db.flush()
            grant_weekly_credits(db, user)
            create_session(db, response, user.id)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "An account already uses this email. Please sign in.")
        return public_user(user)


@app.post("/api/auth/login")
def login(data: Credentials, request: Request, response: Response):
    rate_limit(request, "login", 15, 300)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
        valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
        if not user or not valid:
            raise HTTPException(401, "The email or password is incorrect.")
        create_session(db, response, user.id)
        db.commit()
        return public_user(user)


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return public_user(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    with SessionLocal() as db:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(request.cookies.get("txtzi_session", ""))))
        db.commit()
    response.delete_cookie("txtzi_session", path="/")
    return {"ok": True}


class PasswordChange(BaseModel):
    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


@app.post("/api/auth/password")
def change_password(data: PasswordChange, request: Request, response: Response, user=Depends(current_user)):
    rate_limit(request, "password", 10, 300)
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == user.id).values(password_hash=hash_password(data.new_password)))
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        create_session(db, response, user.id)
        db.commit()
    return {"ok": True}


class Recovery(BaseModel):
    email: str = Field(default="", max_length=254)
    token: str = Field(default="", max_length=128)
    password: str = Field(default="", max_length=128)


@app.post("/api/auth/forgot")
def forgot(data: Recovery, request: Request):
    rate_limit(request, "forgot", 5, 3600)
    if not settings.resend_key or not settings.email_from:
        raise HTTPException(503, "Email recovery is not configured. Contact the site administrator.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
        if user:
            token = secrets.token_urlsafe(32)
            db.add(ResetToken(token_hash=digest(token), user_id=user.id, expires_at=now() + 1800))
            db.commit()
            link = settings.app_url + "/?reset=" + token + "#account"
            try:
                with httpx.Client(timeout=15) as client:
                    result = client.post("https://api.resend.com/emails", headers={"Authorization": "Bearer " + settings.resend_key}, json={"from": settings.email_from, "to": [user.email], "subject": "Reset your txtzi password", "text": "Use this link within 30 minutes to reset your password:\n" + link + "\n\nIf you didn't request this, ignore this email."})
                    result.raise_for_status()
            except Exception:
                pass  # Uniform response avoids disclosing account existence.
    return {"message": "If this email has an account, a reset link will be sent shortly."}


@app.post("/api/auth/reset")
def reset_password(data: Recovery, request: Request):
    rate_limit(request, "reset", 10, 300)
    if len(data.password) < 10:
        raise HTTPException(400, "Use at least 10 characters.")
    with SessionLocal() as db:
        token = db.get(ResetToken, digest(data.token))
        if not token or token.expires_at < now():
            raise HTTPException(400, "This reset link has expired or was already used.")
        result = db.execute(delete(ResetToken).where(ResetToken.token_hash == token.token_hash, ResetToken.expires_at >= now()))
        if not result.rowcount:
            raise HTTPException(400, "This reset link was already used.")
        db.execute(update(User).where(User.id == token.user_id).values(password_hash=hash_password(data.password)))
        db.execute(delete(AuthSession).where(AuthSession.user_id == token.user_id))
        db.execute(delete(ResetToken).where(ResetToken.user_id == token.user_id))
        db.commit()
    return {"ok": True}


class EditOptions(BaseModel):
    tone: str = "natural"
    depth: str = "light"
    language: str = "English"
    clean_metadata: bool = True
    clean_hidden: bool = True
    detector: bool = False
    detector_provider: str | None = Field(default=None, pattern="^(local|gptzero)$")
    consent: bool = False
    provider_consent: bool = False


@app.post("/api/documents/quote")
def quote_document(request: Request, text: str = Form(""), title: str = Form("Untitled document"), options: str = Form("{}"), file: UploadFile | None = File(None), user=Depends(current_user)):
    rate_limit(request, "upload", 12, 600)
    try:
        prefs = EditOptions.model_validate_json(options)
    except ValueError:
        raise HTTPException(400, "The editing preferences were invalid.")
    if not prefs.consent or not prefs.provider_consent:
        raise HTTPException(400, "Accept the personal-use declaration and AI processing notice before continuing.")
    if prefs.tone not in ("natural", "professional", "conversational") or prefs.depth not in ("light", "thorough"):
        raise HTTPException(400, "Choose a valid writing tone and editing depth.")
    if prefs.language not in ("English", "Hebrew", "Arabic", "Spanish", "French", "German", "Other"):
        raise HTTPException(400, "Choose a valid language.")
    if len(text) > settings.max_chars or len(title) > 160:
        raise HTTPException(400, "This document is too long. Please split it into smaller parts.")
    with SessionLocal() as db:
        active = db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user.id, Document.status.in_(["quoted", "funded", "queued", "processing"])))
        if active >= 30:
            raise HTTPException(400, "You have 30 unfinished documents. Delete an old quote or finish a document first.")
    if file and text.strip():
        raise HTTPException(400, "Choose either a file or pasted text.")
    if file:
        data = file.file.read(settings.max_file_bytes + 1)
        file.file.close()
        if len(data) > settings.max_file_bytes:
            raise HTTPException(413, "Files must be 20 MB or smaller.")
        try:
            extracted = extract_file(file.filename or "", data, prefs.language)
        except DocumentError as exc:
            raise HTTPException(400, str(exc))
    else:
        blocks = normalize_blocks([block("paragraph", t) for t in text.split("\n\n")])
        extracted = {"blocks": blocks, "word_count": count_words(text), "source_type": "text", "ocr_pages": 0, "slides": 0, "warnings": []}
    total_chars = sum(len(b["text"]) for b in extracted["blocks"])
    if extracted["word_count"] < 15:
        raise HTTPException(400, "Add at least 15 words so there is enough text to refine.")
    if extracted["word_count"] > settings.max_words or total_chars > settings.max_chars:
        raise HTTPException(400, f"Please limit each document to {settings.max_words:,} words and {settings.max_chars:,} characters.")
    if prefs.detector:
        if not settings.detector_ready:
            raise HTTPException(400, "AI-detector assessment is not available yet.")
        if prefs.detector_provider != settings.detector_provider:
            raise HTTPException(409, "The detector selection changed. Reload the studio and review the processing notice.")
        if prefs.language != "English" or extracted["word_count"] < 300 or extracted["source_type"] == "pptx":
            raise HTTPException(400, "Detector assessment is available for English prose of at least 300 words, excluding presentations.")
    price = quote(extracted["word_count"], extracted["ocr_pages"], extracted["slides"], prefs.detector)
    with SessionLocal() as db:
        doc = Document(user_id=user.id, title=title.strip() or "Untitled document", source_type=extracted["source_type"], source=encrypt(extracted["blocks"]), options=json.dumps({**prefs.model_dump(), "consent_version": "2026-10-02", "consented_at": now()}), warnings=json.dumps(extracted["warnings"]), word_count=extracted["word_count"], price_cents=price["total_cents"], detector_cents=price["detector_cents"], quote_breakdown=json.dumps(price), quote_expires_at=now() + 3600, expires_at=now() + settings.retention_hours * 3600)
        db.add(doc)
        db.commit()
        return document_json(doc, True)


@app.get("/api/documents")
def list_documents(user=Depends(current_user)):
    with SessionLocal() as db:
        docs = db.scalars(select(Document).where(Document.user_id == user.id, Document.status != "deleted").order_by(Document.created_at.desc()).limit(100)).all()
        return [document_json(d) for d in docs]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        return document_json(owned_doc(db, doc_id, user), True)


@app.post("/api/documents/{doc_id}/generate")
def generate(doc_id: str, request: Request, user=Depends(current_user)):
    rate_limit(request, "generate", 10, 300)
    if not settings.ai_ready:
        raise HTTPException(503, "The three writing providers are not all connected yet. No credits were used.")
    with SessionLocal() as db:
        doc = owned_doc(db, doc_id, user)
        if doc.status in ("queued", "processing", "completed"):
            return document_json(doc)
        if doc.status not in ("quoted", "funded") or not doc.source:
            raise HTTPException(400, "Create a new quote to refine this document.")
        if doc.expires_at < now() or (doc.status == "quoted" and doc.quote_expires_at < now()):
            raise HTTPException(400, "This quote has expired. Create a new quote.")
        paid = doc.status == "funded"
        if not paid and doc.payment_id:
            raise HTTPException(409, "A one-time checkout is attached to this quote. Complete it or create a new quote to use credits.")
        claimed = db.execute(update(Document).where(Document.id == doc.id, Document.status == doc.status, Document.charged.is_(False)).values(status="queued", charged=True, stage="In the writing queue", updated_at=now()))
        if not claimed.rowcount:
            db.rollback()
            raise HTTPException(409, "This document has already been submitted. Refresh to see its progress.")
        if not paid:
            deducted = db.execute(update(User).where(User.id == user.id, User.credits >= doc.price_cents).values(credits=User.credits - doc.price_cents))
            if not deducted.rowcount:
                db.rollback()
                raise HTTPException(402, "Your balance is too low. Add credits or pay for this document once.")
            db.add(Ledger(user_id=user.id, delta=-doc.price_cents, kind="generation", description="Document refinement", reference="generation:" + doc.id))
        db.commit()
        db.refresh(doc)
        return document_json(doc)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        doc = owned_doc(db, doc_id, user)
        if doc.status in ("queued", "processing"):
            raise HTTPException(409, "Wait for the current job to finish before deleting it.")
        old_status = doc.status
        changed = db.execute(update(Document).where(Document.id == doc.id, Document.status == old_status).values(status="deleted", source=None, result=None, report=None, title="Deleted document", updated_at=now()))
        if not changed.rowcount:
            db.rollback()
            raise HTTPException(409, "This document changed. Refresh and try again.")
        db.refresh(doc)
        if old_status == "funded":
            doc.charged = True
            billing.refund_document(db, doc)
        db.commit()
    return {"ok": True}


@app.get("/api/documents/{doc_id}/export/{format}")
def export_document(doc_id: str, format: str, request: Request, user=Depends(current_user)):
    rate_limit(request, "export", 30, 300)
    if format not in (*EXPORTERS, "txt"):
        raise HTTPException(400, "Choose PDF, DOCX, PPTX or TXT.")
    with SessionLocal() as db:
        doc = owned_doc(db, doc_id, user)
        if doc.status != "completed" or not doc.result or doc.expires_at < now():
            raise HTTPException(400, "This document is not available for export.")
        blocks = decrypt(doc.result)
        prefs = json.loads(doc.options)
        title = doc.title
    if format == "txt":
        data = (title + "\n\n" + "\n\n".join(b["text"] for b in export_body(title, blocks))).encode("utf-8")
        mime = "text/plain; charset=utf-8"
    else:
        exporter, mime = EXPORTERS[format]
        data = exporter(title, blocks, prefs.get("clean_metadata", True))
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", title).strip("-")[:70] or "refined-document"
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}.{format}"'})


class CheckoutRequest(BaseModel):
    document_id: str | None = Field(default=None, max_length=32)
    amount: int = 0


@app.post("/api/billing/checkout")
def create_checkout(data: CheckoutRequest, request: Request, user=Depends(current_user)):
    rate_limit(request, "checkout", 10, 300)
    if not settings.payments_ready or not settings.ai_ready:
        raise HTTPException(503, "Checkout will open once payment and writing services are connected.")
    try:
        url = billing.checkout(user, data.amount, data.document_id)
        return {"url": url}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(502, "We couldn't open checkout. Please try again. Your card has not been charged by this request.")


@app.post("/api/billing/webhook")
async def webhook(request: Request):
    if not settings.stripe_webhook:
        raise HTTPException(503, "Webhook is not configured.")
    body = await request.body()
    if len(body) > 1000000:
        raise HTTPException(413, "Payload too large.")
    try:
        event = stripe.Webhook.construct_event(body, request.headers.get("stripe-signature", ""), settings.stripe_webhook)
        await asyncio.to_thread(billing.settle_payment, event)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook.")
    return {"received": True}


@app.get("/api/billing/wallet")
def wallet(user=Depends(current_user)):
    with SessionLocal() as db:
        ledger = db.scalars(select(Ledger).where(Ledger.user_id == user.id).order_by(Ledger.created_at.desc()).limit(100)).all()
        payments = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(30)).all()
        return {"credits": user.credits, "ledger": [{"id": r.id, "delta": r.delta, "kind": r.kind, "description": r.description, "created_at": r.created_at} for r in ledger], "payments": [{"id": p.id, "amount": p.amount, "kind": p.kind, "status": p.status, "created_at": p.created_at} for p in payments]}


@app.get("/api/admin/overview")
def admin_overview(user=Depends(admin_user)):
    with SessionLocal() as db:
        counts = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
        users = db.scalars(select(User).order_by(User.created_at.desc()).limit(100)).all()
        docs = db.scalars(select(Document).order_by(Document.created_at.desc()).limit(50)).all()
        audits = db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(50)).all()
        return {"users": [public_user(u) for u in users], "documents": [document_json(d) for d in docs], "counts": counts, "revenue_cents": db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid")), "providers": [{"name": "OpenAI", "connected": bool(settings.openai_key), "model": settings.openai_model}, {"name": "Anthropic", "connected": bool(settings.anthropic_key), "model": settings.anthropic_model}, {"name": "xAI", "connected": bool(settings.xai_key), "model": settings.xai_model}, {"name": settings.detector_name, "connected": settings.detector_ready, "model": "Desklib English beta · self-hosted" if settings.detector_provider == "local" else "Optional assessment"}, {"name": "Stripe", "connected": settings.payments_ready, "model": "Checkout + signed webhook"}], "audit": [{"action": a.action, "detail": a.detail, "created_at": a.created_at} for a in audits]}


class CreditGrant(BaseModel):
    user_id: str = Field(max_length=32)
    amount: int = Field(ge=1, le=100000)
    reason: str = Field(min_length=5, max_length=150)
    idempotency_key: str = Field(min_length=10, max_length=80)


@app.post("/api/admin/credits")
def grant_credits(data: CreditGrant, request: Request, admin=Depends(admin_user)):
    rate_limit(request, "grants", 20, 300)
    with SessionLocal() as db:
        if not db.get(User, data.user_id):
            raise HTTPException(404, "Account not found.")
        reference = "admin:" + data.idempotency_key
        if db.scalar(select(Ledger.id).where(Ledger.reference == reference)):
            return {"ok": True}
        db.execute(update(User).where(User.id == data.user_id).values(credits=User.credits + data.amount))
        db.add(Ledger(user_id=data.user_id, delta=data.amount, kind="admin_grant", description=data.reason, reference=reference))
        db.add(Audit(actor=admin.id, action="credit_grant", detail=json.dumps({"user_id": data.user_id, "cents": data.amount, "reason": data.reason})))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return {"name": "txtzi — Your words, refined", "short_name": "txtzi", "start_url": "/", "display": "standalone", "background_color": "#f4f6f8", "theme_color": "#121c31", "icons": [{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]}


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /api/\n", media_type="text/plain")
