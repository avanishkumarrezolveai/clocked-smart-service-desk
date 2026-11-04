"""Run with: python -m unittest discover -s tests -v
Uses local synthetic demo mode; live Clocked API verification remains a separate requirement.
"""
import os
import unittest
os.environ.pop('CLOCKED_API_KEY', None)
import app as service


class QAFixes(unittest.TestCase):
    def setUp(self):
        self.client = service.app.test_client()

    def send(self, text, user='DEMO001', previous=None):
        payload = {'text': text, 'user_id': user}
        if previous:
            payload.update({'state': previous['state'], 'state_token': previous['state_token']})
        response = self.client.post('/api/chat', json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def action(self, previous, action, user='DEMO001'):
        return self.client.post('/api/action', json={'user_id': user, 'state': previous['state'], 'state_token': previous['state_token'], 'action': action})

    def test_incident_remains_incident_after_knowledge_escalation(self):
        for query,user,offering in [('My laptop won\'t turn on','DEMO001','INC001'),('The VPN is no longer connecting','DEMO002','INC004'),('The printer has a paper jam','DEMO001','INC007')]:
            with self.subTest(query=query):
                r=self.send(query,user)
                if r['state']['phase']=='knowledge':
                    r=self.action(r,'escalate',user).get_json()
                self.assertEqual(r['state'].get('ticket_type'), 'INC')
                self.assertNotEqual(r['state'].get('offering_id',''), 'REQ001')

    def test_known_requests(self):
        data=[('I need a new laptop','REQ001'),('I need Microsoft Visio installed','REQ011'),('Install Adobe Acrobat on my laptop','REQ012'),('Please help me with request vpn access','REQ031'),('Please help me with request guest wifi','REQ036'),('Please help me with request sso application access','REQ028'),('I need my MFA re-enrolled','REQ027')]
        for query,offering in data:
            with self.subTest(query=query):
                r=self.send(query)
                self.assertEqual(r['state'].get('offering_id'), offering)

    def test_vague_outlook_and_unknown_application(self):
        r=self.send('Create a ticket about Outlook')
        self.assertEqual(r['state'].get('phase'), 'clarify_intent')
        r=self.send('I need access to Zorblax Quantum Ledger')
        self.assertEqual(r['state'].get('phase'), 'clarify_offering')
        self.assertNotIn('offering_id',r['state'])

    def test_unknown_asset_is_not_dead_end(self):
        r=self.send('My Dell computer is broken')
        self.assertEqual(r['state']['phase'], 'asset_type')
        r=self.action(r,'device:laptop').get_json()
        r=self.action(r,'symptom:power').get_json()
        self.assertEqual(r['state']['phase'], 'asset_choice')
        self.assertTrue(any(c['value']=='unknown_asset' for c in r['choices']))
        r=self.send("I don't know the model",previous=r)
        self.assertNotEqual(r['state']['phase'],'asset_choice')

    def test_irrelevant_knowledge_not_answer(self):
        r=self.send('How do I fix my laptop screen?')
        self.assertNotEqual((r.get('card') or {}).get('id'), 'KB010')

    def test_forged_review_rejected(self):
        fake={'phase':'review','ticket_type':'REQ','offering_id':'REQ001','original_text':'new laptop'}
        r=self.client.post('/api/action',json={'user_id':'DEMO001','state':fake,'action':'confirm_ticket'})
        self.assertEqual(r.status_code,400)
        self.assertNotIn('reference',(r.get_json() or {}))

    def test_modified_state_rejected(self):
        r=self.send('I need Microsoft Visio installed')
        state=dict(r['state']);state['offering_id']='REQ029'
        resp=self.client.post('/api/action',json={'user_id':'DEMO001','state':state,'state_token':r['state_token'],'action':'confirm_ticket'})
        self.assertEqual(resp.status_code,400)

    def test_simulated_ticket_succeeds_once(self):
        r=self.send('I need Microsoft Visio installed')
        result=self.action(r,'confirm_ticket')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.get_json()['card']['type'],'complete')

    def test_correction(self):
        r=self.send('I need Microsoft Visio installed')
        changed=self.send('Sorry I meant Microsoft Project',previous=r)
        self.assertNotEqual(changed['state'].get('offering_id'),r['state'].get('offering_id'))

    def test_bad_state_returns_json(self):
        r=self.client.post('/api/chat',json={'text':'hello','user_id':'DEMO001','state':{'phase':[]}})
        self.assertEqual(r.status_code,400)
        self.assertTrue(r.is_json)


if __name__=='__main__':
    unittest.main()
