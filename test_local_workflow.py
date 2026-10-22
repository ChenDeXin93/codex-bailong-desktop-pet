"""Exercise the actual local orchestrator without launching or stopping any pet."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import build_local as local

class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'app').mkdir();(self.root/'app/example.py').write_text('answer=42')
        self.stage=self.root/'release/BailongEnhanced';self.stage.mkdir(parents=True);(self.stage/'BailongEnhanced.exe').write_bytes(b'compiled-placeholder')
        self.proof=dict(version=local.VERSION,executableSha256=local.sha(self.stage/'BailongEnhanced.exe'))
        self.patch=patch.object(local,'ROOT',self.root);self.patch.start()
        receipt=self.root/'本地实装/回归验收/current-regressions.json';receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps(dict(passed=True,modules=1,tests=1,sourceHashes=local.source_hashes())),encoding='utf-8')
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_verified_local_deploy_has_lock_ready_validation_and_no_package_command(self):
        lock=Mock();lock.tryLock.return_value=True
        result=dict(current='new',previous='old',backup='backup',executable='new.exe')
        with patch('PySide6.QtCore.QLockFile',return_value=lock),patch('installer.DATA',self.root/'user-data'),patch('installer.startup_preference',return_value=False),patch('directory_deploy.deploy_directory',return_value=result) as deploy,patch.object(local,'verify_installed',return_value=dict(passed=True)) as verify:
            self.assertEqual(local.install_verified(self.proof,self.stage),0)
        deploy.assert_called_once_with(self.stage,False);verify.assert_called_once_with(result);lock.unlock.assert_called_once()
        report=local.read(self.root/'本地实装/最终验收.json');self.assertEqual(report['regression']['tests'],1)
    def test_changed_source_or_lock_collision_prevents_deploy(self):
        (self.root/'app/example.py').write_text('answer=43')
        with patch('directory_deploy.deploy_directory') as deploy,self.assertRaises(ValueError):local.install_verified(self.proof,self.stage)
        deploy.assert_not_called()
    def test_deploy_verified_rejects_changed_executable_before_stop_or_build(self):
        path=self.root/'本地实装/构建验收.json';path.write_text(json.dumps(self.proof))
        (self.stage/'BailongEnhanced.exe').write_bytes(b'changed')
        lock=Mock();lock.tryLock.return_value=True
        with patch('PySide6.QtCore.QLockFile',return_value=lock),patch.object(local,'verify_code'),patch.object(local,'install_verified') as install,patch.object(local.subprocess,'run') as build,self.assertRaises(ValueError):local.main(['--deploy-verified'])
        build.assert_not_called();install.assert_not_called()
    def test_default_build_calls_application_only_and_preserves_verified_handoff(self):
        with patch.object(local.subprocess,'run') as run,patch.object(local,'verify_code',return_value=dict(passed=True)),patch.object(local,'native_matrix',return_value=[]),patch.object(local,'snapshot_source',return_value=self.root/'snapshot'),patch.object(local,'install_verified',return_value=0) as deploy:
            self.assertEqual(local.build_and_deploy(SimpleNamespace(build_only=False)),0)
        command=run.call_args.args[0];self.assertEqual(Path(command[1]).name,'build_release.py');self.assertNotIn('--package',command)
        self.assertEqual(deploy.call_args.args[0]['executableSha256'],local.sha(self.stage/'BailongEnhanced.exe'))
        self.assertFalse(deploy.call_args.args[0]['fullInstallerGenerated'])

if __name__=='__main__':unittest.main()
