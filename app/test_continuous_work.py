import unittest
from continuous_work import ContinuousWork
from status_reactions import StatusReactions,Reaction

class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.r=StatusReactions(0,available=('work01','work02','work03','work04','work05'));self.c=ContinuousWork()
    def status(self,now,state='thinking',activity='',session='a',turn='1'):
        self.r.observe(dict(session=session,turn=turn,state=state,activity=activity),now)
    def test_burst_does_not_reset_semantic_stability(self):
        for i in range(100):
            self.status(i/50);target=self.c.target(self.r,i/50)
        self.assertEqual(target.action_id,'work04');self.assertEqual(self.c.since,0)
        self.assertEqual(len(self.r.sessions),1)
    def test_short_alternations_keep_current_loop_until_stable(self):
        self.status(0);self.c.target(self.r,0);owner=self.c.target(self.r,2);self.c.commit(owner)
        self.status(3,'working','execute');self.assertEqual(self.c.target(self.r,3),owner)
        self.status(4);self.assertEqual(self.c.target(self.r,4),owner)
        self.status(5,'working','execute');self.c.target(self.r,5)
        self.assertEqual(self.c.target(self.r,7).action_id,'work02')
    def test_owner_sticks_across_other_sessions_but_new_turn_does_not_inherit(self):
        self.status(0);self.c.target(self.r,0);owner=self.c.target(self.r,2);self.c.commit(owner)
        self.status(3,'working','execute',session='b');self.assertEqual(self.c.target(self.r,3),owner)
        self.status(4,turn='2');self.assertIsNone(self.c.target(self.r,4))
        self.assertEqual(self.c.target(self.r,6).turn,'2')
    def test_explicit_waiting_completion_offline_and_disable_stop(self):
        for reason in ('waiting_input','complete','offline','disabled','presence'):
            with self.subTest(reason=reason):
                self.setUp();self.status(0);self.c.target(self.r,0);self.c.commit(self.c.target(self.r,2))
                if reason=='complete':self.r.queue_completion(dict(session='a',turn='1'),3)
                elif reason=='presence':self.r.present=False
                elif reason!='disabled':self.status(3,reason)
                self.assertIsNone(self.c.target(self.r,3,enabled=reason!='disabled'))
    def test_live_turn_lease_keeps_thinking_but_not_old_tool_semantics(self):
        for state,expected in (('thinking','work04'),('working',None)):
            self.setUp();self.status(0,state,'execute');self.c.target(self.r,0)
            self.r.confirm('a','1',True,99)
            result=self.c.target(self.r,100)
            self.assertEqual(result.action_id if result else None,expected)
        self.r.confirm('a','1',False,101);self.assertIsNone(self.c.target(self.r,102))
    def test_opening_and_completion_are_once_and_completion_avoids_fixed_interval(self):
        self.r.observe(dict(session='a',turn='1',state='thinking',turn_started=True),0)
        self.assertEqual(self.r.take_opening(1).kind,'received');self.assertIsNone(self.r.take_opening(2))
        self.r.queue_completion(dict(session='a',turn='1'),3)
        self.assertEqual(self.r.take_completion(4).kind,'complete');self.assertIsNone(self.r.take_completion(5))

if __name__=='__main__':unittest.main()
