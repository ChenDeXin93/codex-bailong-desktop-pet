"""Autonomous motion must respect manual placement and the horizontal limit."""
import random
import unittest
from desktop_core import DEFAULTS,normalized,local_roam_bounds,local_roam_target


class WanderingTests(unittest.TestCase):
    def test_upgraded_settings_default_to_horizontal_and_reject_invalid_home(self):
        current=normalized({'move_range':.75})
        self.assertTrue(current['wander_horizontal_only'])
        self.assertIsNone(current['wander_home'])
        self.assertFalse(normalized({'wander_horizontal_only':False})['wander_horizontal_only'])
        self.assertIsNone(normalized({'wander_home':{'screen':'one','rx':float('nan'),'ry':.5}})['wander_home'])

    def test_right_bottom_manual_home_never_selects_screen_center(self):
        area=(0,0,1920,1080);size=(256,256);home=(1620,800)
        bounds=local_roam_bounds(home,size,area,DEFAULTS['move_range'],True)
        self.assertGreater(bounds[0],area[2]*.66)
        self.assertEqual(bounds[1],bounds[3])
        rng=random.Random(13);current=home
        for _ in range(1000):
            target=local_roam_target(current,bounds,55,True,rng.uniform)
            self.assertIsNotNone(target)
            x,y=target
            self.assertGreaterEqual(x,bounds[0]);self.assertLessEqual(x,bounds[2])
            self.assertEqual(y,home[1])
            self.assertLessEqual(abs(x-current[0]),220)
            current=target

    def test_free_mode_stays_local_on_offset_monitor(self):
        area=(-1600,80,1600,900);size=(256,256);home=(-1450,680)
        bounds=local_roam_bounds(home,size,area,.75,False)
        self.assertLess(bounds[2],-1100)
        rng=random.Random(91);current=home;changed_height=False
        for _ in range(200):
            target=local_roam_target(current,bounds,55,False,rng.uniform)
            self.assertIsNotNone(target)
            x,y=target
            self.assertLessEqual(bounds[0],x);self.assertLessEqual(x,bounds[2])
            self.assertLessEqual(bounds[1],y);self.assertLessEqual(y,bounds[3])
            changed_height|=abs(y-current[1])>1
            current=target
        self.assertTrue(changed_height)


if __name__=='__main__':unittest.main()
