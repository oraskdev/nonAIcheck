"""Integer-cent accounting, signed payment webhooks, idempotent settlement/refunds."""
import json

import stripe
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import Document, Ledger, Payment, SessionLocal, User, WebhookEvent, now, uid

PACKS = [1000, 2500, 5000]


def stripe_client():
    return stripe.StripeClient(settings.stripe_key, max_network_retries=2)


def checkout(user, amount, document_id=None):
    payment_id = uid()
    with SessionLocal() as db:
        if document_id:
            doc = db.get(Document, document_id)
            if not doc or doc.user_id != user.id:
                raise ValueError("Document not found.")
            if doc.status != "quoted" or doc.quote_expires_at < now():
                raise ValueError("This quote is no longer available. Create a new quote.")
            amount = doc.price_cents
            if doc.payment_id:
                payment_id = doc.payment_id
            else:
                changed = db.execute(update(Document).where(Document.id == doc.id, Document.payment_id.is_(None), Document.status == "quoted").values(payment_id=payment_id))
                if changed.rowcount != 1:
                    db.rollback()
                    raise ValueError("A checkout is already being prepared. Please try again.")
                db.add(Payment(id=payment_id, user_id=user.id, document_id=doc.id, amount=amount, kind="document"))
                db.commit()
        else:
            if amount not in PACKS:
                raise ValueError("Choose a valid credit pack.")
            db.add(Payment(id=payment_id, user_id=user.id, amount=amount, kind="credits"))
            db.commit()
        payment = db.get(Payment, payment_id)
        if payment.status != "pending":
            raise ValueError("This payment has already been processed.")
        if payment.stripe_session:
            session = stripe_client().v1.checkout.sessions.retrieve(payment.stripe_session)
            if session.status == "open":
                return session.url
            if session.status == "complete":
                raise ValueError("Payment is being confirmed. Please refresh your documents in a moment.")
            raise ValueError("This checkout has expired. Create a fresh document quote.")
        description = "Document refinement" if document_id else f"${amount / 100:.0f} in txtzi credits"
    session = stripe_client().v1.checkout.sessions.create({
        "mode": "payment", "payment_method_types": ["card"],
        "customer_email": user.email, "client_reference_id": payment_id,
        "metadata": {"txtzi_payment_id": payment_id},
        "line_items": [{"price_data": {"currency": "usd", "unit_amount": amount, "product_data": {"name": description}}, "quantity": 1}],
        "success_url": settings.app_url + "/?checkout=success#documents", "cancel_url": settings.app_url + "/?checkout=cancelled#documents",
        "expires_at": now() + 1800
    }, options={"idempotency_key": "txtzi-checkout-" + payment_id})
    with SessionLocal() as db:
        payment = db.get(Payment, payment_id)
        payment.stripe_session = session.id
        db.commit()
    return session.url


def settle_payment(event):
    event_type = event.get("type")
    event_id = event["id"]
    obj = event["data"]["object"]
    if event_type not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return
    if obj.get("payment_status") != "paid":
        return
    payment_id = obj.get("metadata", {}).get("txtzi_payment_id")
    if not payment_id:
        return
    with SessionLocal() as db:
        if db.get(WebhookEvent, event_id):
            return
        payment = db.get(Payment, payment_id)
        if not payment:
            return
        if obj.get("amount_total") != payment.amount or obj.get("currency") != "usd" or obj.get("client_reference_id") != payment.id:
            raise ValueError("Payment verification mismatch")
        if payment.stripe_session and payment.stripe_session != obj.get("id"):
            raise ValueError("Checkout session mismatch")
        changed = db.execute(update(Payment).where(Payment.id == payment.id, Payment.status == "pending").values(status="paid", stripe_session=obj["id"], stripe_intent=obj.get("payment_intent")))
        if changed.rowcount:
            if payment.kind == "credits":
                db.execute(update(User).where(User.id == payment.user_id).values(credits=User.credits + payment.amount))
                db.add(Ledger(user_id=payment.user_id, delta=payment.amount, kind="purchase", description="Purchased credit balance", reference="purchase:" + payment.id))
            else:
                updated = db.execute(update(Document).where(Document.id == payment.document_id, Document.status == "quoted", Document.source.is_not(None)).values(status="funded", stage="Paid · ready to generate", updated_at=now()))
                if not updated.rowcount:
                    db.execute(update(Payment).where(Payment.id == payment.id).values(status="refund_pending"))
        db.add(WebhookEvent(id=event_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def refund_document(db, doc):
    if not doc.charged or doc.refunded:
        return
    # Caller holds the job row or won a conditional state update within this transaction.
    doc.refunded = True
    if doc.payment_id:
        payment = db.get(Payment, doc.payment_id)
        if payment and payment.status == "paid":
            payment.status = "refund_pending"
    else:
        db.execute(update(User).where(User.id == doc.user_id).values(credits=User.credits + doc.price_cents))
        db.add(Ledger(user_id=doc.user_id, delta=doc.price_cents, kind="refund", description="Automatic refund for an unsuccessful document", reference="refund:" + doc.id))


def credit_detector_fee(db, doc):
    if not doc.detector_cents:
        return
    reference = "detector-refund:" + doc.id
    if db.scalar(select(Ledger.id).where(Ledger.reference == reference)):
        return
    db.execute(update(User).where(User.id == doc.user_id).values(credits=User.credits + doc.detector_cents))
    db.add(Ledger(user_id=doc.user_id, delta=doc.detector_cents, kind="refund", description="Detector unavailable · fee returned as credits", reference=reference))


def process_refunds():
    if not settings.stripe_key:
        return
    with SessionLocal() as db:
        payments = db.scalars(select(Payment).where(Payment.status == "refund_pending").limit(5)).all()
        for payment in payments:
            if not payment.stripe_intent:
                continue
            try:
                stripe_client().v1.refunds.create({"payment_intent": payment.stripe_intent}, options={"idempotency_key": "txtzi-refund-" + payment.id})
                db.execute(update(Payment).where(Payment.id == payment.id, Payment.status == "refund_pending").values(status="refunded"))
                db.commit()
            except Exception:
                db.rollback()
                # Leave pending so a later worker sweep retries with the same idempotency key.
