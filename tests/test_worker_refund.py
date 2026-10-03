import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import worker
from app.db import Base, Document, Ledger, User, decrypt, encrypt, now


class WorkerRefundTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.blocks = [{"id": "b0000", "type": "paragraph", "text": "A personal plan for 30 minutes."}]
        with self.sessions() as db:
            user = User(email="worker-test@example.com", name="Test", password_hash="unused", credits=1)
            db.add(user); db.flush(); self.user_id = user.id
            doc = Document(user_id=user.id, title="Test", source_type="text", source=encrypt(self.blocks),
                           options=json.dumps({"detector": True, "detector_provider": "local"}), word_count=7,
                           price_cents=499, detector_cents=100, quote_breakdown="{}", quote_expires_at=now()+3600,
                           status="processing", charged=True, lease_token="lease", lease_until=now()+600, expires_at=now()+3600)
            db.add(doc); db.commit(); self.doc_id = doc.id

    def tearDown(self):
        self.engine.dispose()

    def test_missing_assessment_refunds_exactly_the_detector_fee_once(self):
        missing = {"status": "not_assessed"}
        report = {"before_detector": missing, "after_detector": missing, "detector_comparison": {"assessment_unavailable": True}, "provider_usage": [], "flags": []}
        with patch("app.worker.SessionLocal", self.sessions), patch("app.worker.pipeline.run", return_value=(self.blocks, report)):
            worker.process_job(self.doc_id, "lease")
            worker.process_job(self.doc_id, "lease")
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.user_id).credits, 101)
            doc = db.get(Document, self.doc_id)
            self.assertEqual(doc.status, "completed")
            self.assertEqual(decrypt(doc.result), self.blocks)
            self.assertEqual(len(db.scalars(select(Ledger)).all()), 1)

    def test_edit_failure_refunds_whole_job(self):
        with patch("app.worker.SessionLocal", self.sessions), patch("app.worker.pipeline.run", side_effect=RuntimeError("test")):
            worker.process_job(self.doc_id, "lease")
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.user_id).credits, 500)
            self.assertEqual(db.get(Document, self.doc_id).status, "failed")

    def test_recomposed_result_counts_every_paragraph_without_positional_edit_count(self):
        revised = [
            {"id": "new-title", "type": "heading", "text": "A revised plan"},
            {"id": "new-1", "type": "paragraph", "text": "I will set aside 30 minutes."},
            {"id": "new-2", "type": "paragraph", "text": "The task can remain unfinished."},
            {"id": "new-3", "type": "paragraph", "text": "I will review the routine."},
        ]
        report = {"before_detector": {}, "after_detector": {}, "structure_recomposed": True,
                  "detector_comparison": {"assessment_unavailable": False}}
        with patch("app.worker.SessionLocal", self.sessions), patch("app.worker.pipeline.run", return_value=(revised, report)):
            worker.process_job(self.doc_id, "lease")
        with self.sessions() as db:
            doc = db.get(Document, self.doc_id)
            self.assertEqual(doc.status, "completed")
            self.assertEqual(decrypt(doc.result), revised)
            stored = decrypt(doc.report)
            self.assertEqual(stored["revised_paragraphs"], 3)
            self.assertIsNone(stored["changed_blocks"])
            self.assertEqual(db.get(User, self.user_id).credits, 1)

    def test_structure_preserving_result_keeps_edited_passage_count(self):
        revised = [{**self.blocks[0], "text": "For 30 minutes, I will work on my personal plan."}]
        report = {"before_detector": {}, "after_detector": {},
                  "detector_comparison": {"assessment_unavailable": False}}
        with patch("app.worker.SessionLocal", self.sessions), patch("app.worker.pipeline.run", return_value=(revised, report)):
            worker.process_job(self.doc_id, "lease")
        with self.sessions() as db:
            stored = decrypt(db.get(Document, self.doc_id).report)
            self.assertEqual(stored["changed_blocks"], 1)
