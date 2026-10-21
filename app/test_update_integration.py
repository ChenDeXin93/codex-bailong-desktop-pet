"""Updater journeys through the real embedded settings and desktop close path."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_interaction_batch as journeys
from test_app_updates import payload
from app_updates import parse_release,cache_paths
APP=journeys.APP

class UpdateIntegration(unittest.TestCase):
    setUp=journeys.InteractionTests.setUp
    tearDown=journeys.InteractionTests.tearDown
    settings=journeys.InteractionTests.settings
    def wait(self,check):
        deadline=time.monotonic()+4
        while not check():APP.processEvents();time.sleep(.003);self.assertLess(time.monotonic(),deadline)
    def test_update_checkbox_uses_existing_draft_and_preserves_unrelated_external_changes(self):
        settings=self.settings();self.assertIs(settings.update_panel.controller,self.pet.updates)
        settings.fields['update_checks'].setChecked(False)
        self.assertTrue(self.pet.settings['update_checks'])
        self.pet.apply_settings(dict(wandering=False))
        with patch.object(self.pet,'apply_settings',wraps=self.pet.apply_settings) as apply:
            settings.apply();self.assertEqual(apply.call_args.args[0],dict(update_checks=False))
        self.assertFalse(self.pet.settings['update_checks']);self.assertFalse(self.pet.settings['wandering'])
        self.assertFalse(settings.draft.dirty)
    def test_only_the_expected_cache_installer_launches_and_launch_error_stays_in_panel(self):
        release=parse_release(payload());self.pet.updates.release=release;paths=cache_paths(self.pet.updates.cache,release.version)
        paths['installer'].write_bytes(b'MZtest')
        with patch('subprocess.Popen') as launch:
            self.pet.install_app_update(str(self.root/'wrong.exe'));launch.assert_not_called()
            self.assertEqual(self.pet.updates.state['phase'],'error')
            self.pet.install_app_update(str(paths['installer']))
            self.assertEqual(launch.call_args.args[0],[str(paths['installer']),'--quick'])
            self.assertEqual(self.pet.updates.state['phase'],'installing')
        with patch('subprocess.Popen',side_effect=OSError('启动失败')):
            self.pet.install_app_update(str(paths['installer']))
        self.assertEqual(self.pet.updates.state['phase'],'error');self.assertIn('启动失败',self.pet.updates.state['message'])
    def test_exit_waits_asynchronously_for_update_job_and_never_installs(self):
        gate=threading.Event()
        def slow(*args,**kwargs):gate.wait(3);return parse_release(payload())
        with patch('update_controller.check_release',side_effect=slow),patch('subprocess.Popen') as launch:
            self.pet.updates.check();started=time.monotonic();self.pet.close()
            self.assertLess(time.monotonic()-started,.4);self.assertTrue(self.pet.updates.closing)
            self.assertTrue(self.pet.isVisible());gate.set()
            self.wait(lambda:self.pet.updates.job is None and not self.pet.isVisible());launch.assert_not_called()

if __name__=='__main__':unittest.main()
