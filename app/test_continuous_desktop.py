import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import copy,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from desktop import DesktopPet
from continuous_work import ContinuousWork
from status_reactions import StatusReactions

APP=QApplication.instance() or QApplication([])

class DesktopContinuousTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.patches=[patch(module+'.'+key,root/('settings.json' if key=='CONFIG' else '')) for module in ('enhanced','desktop') for key in ('CONFIG','STATE_DIR')]
        for p in self.patches:p.start()
        self.pet=DesktopPet(monitor=False);self.pet.show();self.pet.tick.stop();self.pet.motion_timer.stop()
        self.pet.apply_settings(dict(wandering=False,random_actions=False));APP.processEvents()
        self.pet.manifest=copy.deepcopy(self.pet.manifest)
    def tearDown(self):
        self.pet.close();APP.processEvents()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def begin(self):
        p=self.pet;now=time.monotonic();p.reactions=StatusReactions(now,available=[i['id'] for i in p.manifest['workAnimations']])
        p.reactions.observe(dict(state='thinking',session='test',turn='one'),now-3)
        p.continuous=ContinuousWork();p.continuous.target(p.reactions,now-2)
        p.player.ended=True;p.gate.state='idle'
        self.assertTrue(p.play_status_reaction(now));self.assertTrue(p.sustained.active)
        self.assertTrue(p.sustained.tail.ready.wait(5))
    def end_segment(self):
        self.pet.player.ended=True
        with patch.object(self.pet.player,'advance',return_value=(None,True)):self.pet.animate()
    def test_completion_icon_immediate_and_character_finishes_original_tail(self):
        self.begin();p=self.pet
        with patch.object(p,'notify'),patch.object(p,'refresh_quota'):
            p.on_activity(dict(kind='complete',session='test',turn='one',title='测试完成'))
        self.assertTrue(p.bubble.status_indicator.unread);self.assertEqual(p.sustained.phase,'enter')
        tail_start=p.sustained.profile['end']+1
        self.end_segment();self.assertEqual(p.sustained.phase,'exit');self.assertEqual(p.player.frame_index,tail_start)
        self.end_segment();self.assertFalse(p.sustained.active);self.assertEqual(p.mode,'task');self.assertEqual(p.current['id'],'18')
    def test_manual_action_and_hide_cancel_workers_recover_cleanly(self):
        self.begin();p=self.pet;p.choose(p.variants[0],manual=True)
        self.assertFalse(p.sustained.active);self.assertIsNone(p.sustained.warmer)
        self.begin();p.hide();APP.processEvents();self.assertFalse(p.sustained.active)
        self.assertIsNone(p.player.thread);self.assertTrue(p._resume_idle)
        p.show();APP.processEvents();self.assertFalse(p._resume_idle);self.assertEqual(p.mode,'idle')
    def test_disable_requests_natural_tail_and_custom_without_profile_is_one_shot(self):
        self.begin();p=self.pet;p.apply_settings(dict(status_actions=False));self.end_segment()
        self.assertEqual(p.sustained.phase,'exit');self.end_segment();self.assertEqual(p.mode,'idle')
        p.apply_settings(dict(status_actions=True))
        for item in p.manifest['workAnimations']:item.pop('sustained',None)
        now=time.monotonic();p.reactions.earliest=now-5;p.reactions.played.clear();p.player.ended=True;p.gate.state='idle'
        p.continuous.target(p.reactions,now)
        self.assertTrue(p.play_status_reaction(now+2));self.assertFalse(p.sustained.active);self.assertEqual(p.current['id'],'work04')

if __name__=='__main__':unittest.main()
