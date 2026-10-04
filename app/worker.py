import json
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from . import providers, pipeline
from .billing import credit_detector_fee, process_refunds, refund_document
from .config import settings
from .db import AuthSession, Document, Ledger, ResetToken, SessionLocal, User, WeeklyGrant, decrypt, encrypt, now, uid
from .pricing import count_words

log = logging.getLogger(__name__)


def renew_lease(job_id, token, **values):
    """Only the current, unexpired owner may extend or update a running job."""
    with SessionLocal() as db:
        instant = now()
        result = db.execute(update(Document).where(
            Document.id == job_id, Document.status == "processing",
            Document.lease_token == token, Document.lease_until >= instant,
        ).values(lease_until=instant + 600, updated_at=instant, **values))
        db.commit()
        return bool(result.rowcount)


@contextmanager
def lease_heartbeat(job_id, token):
    """Renew during blocking provider/model work; never revive a lost lease."""
    stop, lost = threading.Event(), threading.Event()

    def beat():
        while not stop.wait(30):
            try:
                if not renew_lease(job_id, token):
                    lost.set()
                    return
            except Exception:
                # Stop admitting further stages when ownership cannot be verified.
                lost.set()
                return

    thread = threading.Thread(target=beat, daemon=True, name="txtzi-lease")
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=5)


def claim_job():
    with SessionLocal() as db:
        job_id = db.scalar(select(Document.id).where(Document.status == "queued").order_by(Document.created_at).limit(1))
        if not job_id:
            return None
        token = uid()
        claimed = db.execute(update(Document).where(Document.id == job_id, Document.status == "queued").values(status="processing", lease_token=token, lease_until=now() + 600, progress=5, stage="Preparing your document", updated_at=now()))
        db.commit()
        return (job_id, token) if claimed.rowcount else None


def process_job(job_id, token):
    try:
        with SessionLocal() as db:
            doc = db.get(Document, job_id)
            if (not doc or doc.status != "processing" or doc.lease_token != token
                    or not doc.lease_until or doc.lease_until < now()):
                return
            blocks = decrypt(doc.source)
            options = json.loads(doc.options)
        with lease_heartbeat(job_id, token) as lost:
            def progress(percent, stage):
                if lost.is_set() or not renew_lease(job_id, token, progress=percent, stage=stage):
                    raise RuntimeError("Job ownership changed")
            revised, report = pipeline.run(blocks, options, progress)
            if lost.is_set() or not renew_lease(job_id, token):
                raise RuntimeError("Job ownership changed")
        before, after = report["before_detector"], report["after_detector"]
        # Recomposed paragraphs have new identities and cannot be compared by position.
        # A null edit count deliberately avoids presenting an inaccurate zip-based count.
        changed_blocks = (None if report.get("structure_recomposed") else
                          sum(a["text"] != b["text"] for a, b in zip(blocks, revised)))
        report.update({"before_detector": before, "after_detector": after, "original_words": count_words("\n".join(b["text"] for b in blocks)), "revised_words": count_words("\n".join(b["text"] for b in revised)), "changed_blocks": changed_blocks, "revised_paragraphs": sum(b.get("type") == "paragraph" for b in revised), "completed_at": now(), "metadata": "Fresh exports omit original author fields, comments and revision history. This is not a watermark-removal or human-authorship certification."})
        with SessionLocal() as db:
            changed = db.execute(update(Document).where(Document.id == job_id, Document.status == "processing", Document.lease_token == token).values(result=encrypt(revised), report=encrypt(report), status="completed", progress=100, stage="Your refined document is ready", lease_until=None, updated_at=now()))
            if changed.rowcount and options.get("detector") and report["detector_comparison"]["assessment_unavailable"]:
                credit_detector_fee(db, db.get(Document, job_id))
            db.commit()
    except Exception as exc:
        # Log only job and exception class. Documents, provider responses and keys stay out of logs.
        log.warning("Document %s failed (%s)", job_id, type(exc).__name__)
        message = str(exc) if isinstance(exc, providers.ProviderError) else "We couldn't complete this document. Your payment is being returned. Please try a new quote."
        with SessionLocal() as db:
            changed = db.execute(update(Document).where(Document.id == job_id, Document.status == "processing", Document.lease_token == token).values(status="failed", stage="Processing unsuccessful", error=message, lease_until=None, updated_at=now()))
            if changed.rowcount:
                refund_document(db, db.get(Document, job_id))
            db.commit()


def grant_weekly_credits(db, user):
    """Grant once per ISO week, including immediately after registration."""
    if not settings.weekly_free_credits:
        return
    period = datetime.now(timezone.utc).strftime("%G-W%V")
    reference = f"weekly:{period}:{user.id}"
    if db.scalar(select(Ledger.id).where(Ledger.reference == reference)):
        return
    try:
        with db.begin_nested():
            db.add(WeeklyGrant(user_id=user.id, period_key=period, amount=settings.weekly_free_credits))
            db.add(Ledger(user_id=user.id, delta=settings.weekly_free_credits, kind="weekly_grant", description="Weekly free credits", reference=reference))
            db.flush()
            db.execute(update(User).where(User.id == user.id).values(credits=User.credits + settings.weekly_free_credits))
    except IntegrityError:
        # Another worker or login request already granted this period.
        pass


def housekeeping():
    with SessionLocal() as db:
        if settings.weekly_free_credits:
            for user in db.scalars(select(User)).all():
                grant_weekly_credits(db, user)
        stale = db.scalars(select(Document.id).where(Document.status == "processing", Document.lease_until < now())).all()
        for doc_id in stale:
            changed = db.execute(update(Document).where(Document.id == doc_id, Document.status == "processing", Document.lease_until < now()).values(status="failed", error="Processing was interrupted. Your payment is being returned.", stage="Interrupted · refunded", lease_until=None, updated_at=now()))
            if changed.rowcount:
                refund_document(db, db.get(Document, doc_id))
        expired = db.scalars(select(Document).where(Document.expires_at < now(), Document.status.not_in(["queued", "processing", "expired", "deleted"]))).all()
        for doc in expired:
            if doc.status == "funded":
                doc.charged = True
                refund_document(db, doc)
            doc.source = doc.result = doc.report = None
            doc.title = "Expired document"
            doc.status = "expired"
            doc.stage = "Content deleted after retention period"
        db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
        db.execute(delete(ResetToken).where(ResetToken.expires_at < now()))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    process_refunds()


def worker_loop(stop):
    last_sweep = 0
    while not stop.is_set():
        try:
            if time.monotonic() - last_sweep > 45:
                housekeeping()
                last_sweep = time.monotonic()
            claim = claim_job()
            if claim:
                process_job(*claim)
            else:
                stop.wait(1.5)
        except Exception as exc:
            log.warning("Worker temporarily unavailable (%s)", type(exc).__name__)
            stop.wait(4)


def start_worker():
    stop = threading.Event()
    thread = threading.Thread(target=worker_loop, args=(stop,), daemon=True, name="txtzi-worker")
    thread.start()
    return stop, thread


if __name__ == "__main__":
    import signal
    from .db import init_db
    init_db()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker_loop(stop)
