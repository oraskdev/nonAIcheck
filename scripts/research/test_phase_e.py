"""Offline isolated configuration, authorization and real response-cap checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

from scripts.research import recovery as r
from scripts.research import phase_d as d
from scripts.research import phase_e as e


class PhaseESafety(unittest.TestCase):
    def test_isolated_configuration_preserves_phase_d(self):
        self.assertEqual((d.PHASE,d.ID_PREFIX,d.REQUEST_PREFIX,d.OUTPUT_LIMIT,d.MAX_BANKS,d.MAX_CALLS,d.MAX_TEXTS),
                         ('D','d','phase-d-',7000,3,9,450))
        self.assertEqual((e.core.PHASE,e.core.ID_PREFIX,e.core.REQUEST_PREFIX,e.core.OUTPUT_LIMIT,e.core.MAX_BANKS,e.core.MAX_CALLS,e.core.MAX_TEXTS),
                         ('E','e','phase-e-',4500,2,6,300))
        self.assertEqual(e.core.PARENT_PHASES,('A','B','D','E'))

    def test_unapproved_e_cannot_call_provider(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(e,'E',Path(folder)), patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'not been authorized'):e.core.call('anthropic',1,{},True)
            invoke.assert_not_called()

    def test_e_request_namespace_and_cap(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'RUN',Path(folder)), \
             patch.object(e.core,'admitted'), patch.object(r,'ledger',return_value={'requests':{}}), patch.object(r,'call') as invoke:
            e.core.call('openai',2,{},True)
            self.assertEqual(invoke.call_args.args[1],'phase-e-r02-openai')
            self.assertEqual(invoke.call_args.kwargs['max_output_tokens'],4500)
        requests={f'phase-e-old{i}':{} for i in range(6)}
        with patch.object(e.core,'admitted'), patch.object(r,'ledger',return_value={'requests':requests}), patch.object(r,'call') as invoke:
            with self.assertRaises(RuntimeError):e.core.call('anthropic',1,{},True)
            invoke.assert_not_called()

    def test_response_cap_is_sent_and_reserved(self):
        import httpx
        for provider in ('anthropic','openai','xai'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as folder:
                fake=MagicMock();fake.status_code=200
                body=({'stop_reason':'end_turn','content':[{'type':'text','text':'{}'}]} if provider=='anthropic' else
                      {'status':'completed','output':[{'content':[{'type':'output_text','text':'{}'}]}]})
                body['usage']={'input_tokens':1,'output_tokens':1};fake.json.return_value=body
                client=MagicMock();client.__enter__.return_value.post.return_value=fake
                with patch.object(r,'RUN',Path(folder)), patch.object(r,'load_keys',return_value={provider:'test-placeholder'}), \
                     patch.object(httpx,'Client',return_value=client):
                    self.assertEqual(r.call(provider,'bounded-test','sys','{}',True,max_output_tokens=4500),{})
                    payload=client.__enter__.return_value.post.call_args.kwargs['json']
                    self.assertEqual(payload['max_tokens' if provider=='anthropic' else 'max_output_tokens'],4500)
                    record=r.ledger()['requests']['bounded-test']
                    expected=((3+2+8192)*2+4500*(6 if provider=='xai' else 10))/1e6
                    self.assertAlmostEqual(record['reserved_usd'],expected)
                    self.assertEqual(r.read(Path(folder)/'rounds/bounded-test.request.json')['max_output_tokens'],4500)

    def test_cannot_raise_shared_output_limit(self):
        with self.assertRaises(ValueError):r.call('openai','invalid','s','{}',True,max_output_tokens=7001)


if __name__=='__main__':unittest.main()
