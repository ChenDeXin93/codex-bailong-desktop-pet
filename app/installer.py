"""Per-user installer for our own release; version folders enable rollback."""
import json
import stat
import uuid
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from PySide6.QtCore import QThread,Signal,QTimer,QLockFile
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QPushButton,QCheckBox,QMessageBox

ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Programs/BailongEnhanced'
DATA=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'BailongEnhanced'
from desktop_core import VERSION
def read_manifest(root=ROOT):
    try:return json.loads((root/'installations.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return dict(current='',versions=[])
def write_manifest(value,root=ROOT):
    root.mkdir(parents=True,exist_ok=True);temp=root/'installations.tmp'
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,root/'installations.json')
def checked_version(root,name):
    path=(root/'versions'/name).resolve()
    if path.parent!=(root/'versions').resolve() or not (path/'BailongEnhanced.exe').is_file():raise ValueError('安装版本目录无效')
    return path
def ps_string(value):return "'"+str(value).replace("'","''")+"'"
def register(exe,maintenance,startup):
    import winreg
    root=exe.parent
    # New shortcuts supersede the old Python entry, preserving the visible names.
    script="$s=New-Object -ComObject WScript.Shell\n"
    script+="$paths=@((Join-Path ([Environment]::GetFolderPath('Desktop')) '白龙桌宠增强版.lnk'),(Join-Path ([Environment]::GetFolderPath('Desktop')) '白龙桌宠.lnk'),(Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\\白龙桌宠增强版.lnk'))\n"
    script+="foreach($p in $paths){$l=$s.CreateShortcut($p);$l.TargetPath="+ps_string(exe)+";$l.WorkingDirectory="+ps_string(root)+";$l.Description='白龙桌宠增强版';$l.Save()}"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,creationflags=0x08000000)
    if result.returncode:raise OSError('创建快捷方式失败')
    startup_dir=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'
    old=startup_dir/'白龙桌宠增强版.lnk'
    if old.exists():old.unlink()
    vbs=startup_dir/'BailongEnhanced.vbs'
    if startup:vbs.write_text('Set s=CreateObject("WScript.Shell")\ns.Run """'+str(exe)+'""",0,False\n',encoding='utf-16')
    elif vbs.exists():vbs.unlink()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall\BailongEnhanced') as key:
        for name,value in dict(DisplayName='白龙桌宠增强版',DisplayVersion=exe.parent.name.split('-')[0],Publisher='本地白龙桌宠项目',InstallLocation=str(ROOT),UninstallString='"'+str(maintenance)+'" --manage').items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
        winreg.SetValueEx(key,'NoModify',0,winreg.REG_DWORD,1)

def install(payload,root=ROOT,startup=True,copy_installer=True,before_commit=None,old_running=None):
    from deployment_state import capture_entries,restore_entries,owned_destination,atomic,recover,verify_payload,stop_version
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True);system=root==ROOT.resolve()
    recover(root,system)
    name=VERSION+'-'+time.strftime('%Y%m%d-%H%M%S')
    if (root/'versions'/name).exists():name+='-'+str(time.time_ns())
    dest=owned_destination(root,name);dest.mkdir(parents=True)
    snapshot=None;journal=None;committed=False
    try:
        snapshot=capture_entries(root,system)
        journal=dict(phase='extracting',new_version=name,snapshot=snapshot,old_running=Path(old_running).parent.name if old_running else '')
        atomic(root/'deployment-journal.json',journal)
        with zipfile.ZipFile(payload) as archive:
            for member in archive.infolist():
                target=(dest/member.filename).resolve()
                if not target.is_relative_to(dest) or stat.S_ISLNK(member.external_attr>>16):raise ValueError('安装包路径无效')
            archive.extractall(dest)
        exe=checked_version(root,name)/'BailongEnhanced.exe';verify_payload(dest,VERSION)
        manifest=read_manifest(root);manifest['versions'].insert(0,name);manifest['current']=name
        maintenance=dest/'白龙安装管理.exe'
        if copy_installer and getattr(sys,'frozen',False):shutil.copy2(exe,maintenance)
        from shared_assets import share
        def register_shared(sha):
            journal.setdefault('new_shared_objects',[]).append(sha);atomic(root/'deployment-journal.json',journal)
        shared=share(dest,root,register_shared)
        if shared:manifest.setdefault('sharedAssets',{})[name]=shared
        journal['phase']='prepared';atomic(root/'deployment-journal.json',journal)
        if before_commit:
            ready=before_commit(exe,journal)
            if ready:manifest['lastHealth']={key:ready[key] for key in ('version','pid','windowReady','serverReady')}
        if system:register(exe,maintenance,startup)
        write_manifest(manifest,root)
        journal['phase']='committed';atomic(root/'deployment-journal.json',journal);committed=True
        try:(root/'deployment-journal.json').unlink(missing_ok=True)
        except OSError:pass  # Committed journal is safely cleaned on next run.
        return exe
    except Exception as error:
        if committed:raise
        try:
            if before_commit and journal:stop_version(dest/'BailongEnhanced.exe')
            if snapshot:restore_entries(root,snapshot,system)
        except Exception as restore_error:
            raise OSError('安装未提交，入口恢复尚未完成；已保留恢复记录和程序，请重试安装。') from restore_error
        # Never remove old versions or user data, and recheck the absolute path.
        if owned_destination(root,name)==dest and dest.exists():shutil.rmtree(dest)
        from shared_assets import cleanup_new
        if journal:cleanup_new(root,journal.get('new_shared_objects',[]))
        (root/'deployment-journal.json').unlink(missing_ok=True)
        raise error

def startup_preference(root=ROOT):
    """New installations opt in; upgrades retain the actual Startup setting."""
    manifest=read_manifest(root)
    if not manifest.get('current'):return True
    folder=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'
    try:
        text=(folder/'BailongEnhanced.vbs').read_text(encoding='utf-16')
        return str(checked_version(root,manifest['current'])/'BailongEnhanced.exe').casefold() in text.casefold()
    except FileNotFoundError:return (folder/'白龙桌宠增强版.lnk').is_file()
    except (OSError,UnicodeError,ValueError):return (folder/'BailongEnhanced.vbs').is_file()

def stop_existing(root=ROOT):
    """Close only running binaries inside this user's registered versions."""
    import psutil
    root=Path(root).resolve();manifest=read_manifest(root);known=set()
    for name in manifest.get('versions',[]):
        try:known.add((checked_version(root,name)/'BailongEnhanced.exe').resolve())
        except (OSError,ValueError):continue
    running=[]
    for process in psutil.process_iter(['exe']):
        try:
            if process.info['exe'] and Path(process.info['exe']).resolve() in known:running.append(process)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    if not running:return None
    old=Path(running[0].info['exe'])
    subprocess.run([str(old),'--quit'],timeout=20,creationflags=0x08000000,check=True)
    _,alive=psutil.wait_procs(running,timeout=25)
    if alive:raise OSError('旧桌宠尚未退出，请退出后重试；已有文件和设置未改动。')
    return old

def deploy(payload,startup,root=ROOT,progress=lambda text:None):
    from deployment_state import recover,atomic,wait_ready
    root=Path(root).resolve();recover(root,root==ROOT.resolve())
    progress('正在关闭旧桌宠…');old=stop_existing(root)
    ready_receipt=None
    def launch_and_confirm(exe,journal):
        nonlocal ready_receipt
        token=uuid.uuid4().hex;ready_receipt=exe.parent/('.ready-'+token+'.json')
        env=os.environ.copy();env.update(BAILONG_DEPLOY_TOKEN=token,BAILONG_DEPLOY_RECEIPT=str(ready_receipt))
        progress('正在确认新版窗口与本地服务就绪…')
        process=subprocess.Popen([str(exe)],cwd=str(exe.parent),env=env,creationflags=0x08000000)
        journal['pid']=process.pid;atomic(root/'deployment-journal.json',journal)
        ready=wait_ready(process,exe,ready_receipt,token,VERSION)
        ready_receipt.unlink(missing_ok=True)
        progress('启动检查通过，正在更新入口…')
        return ready
    progress('正在解压与校验程序及素材…')
    try:return install(payload,root=root,startup=startup,before_commit=launch_and_confirm,old_running=old)
    except Exception as error:
        if old:
            try:subprocess.Popen([str(old)],cwd=str(old.parent),creationflags=0x08000000)
            except OSError:raise OSError(str(error)+'；旧版未能自动恢复，请从安装目录启动旧版。') from error
        raise

def quick_mode(arguments,executable):
    return '--manage' not in arguments and ('--quick' in arguments or '一键部署' in Path(executable).stem)

class InstallJob(QThread):
    done=Signal(str);failed=Signal(str);progress=Signal(str)
    def __init__(self,payload,startup,parent=None,quick=False):super().__init__(parent);self.payload=payload;self.startup=startup;self.quick=quick
    def run(self):
        lock=None
        try:
            DATA.mkdir(parents=True,exist_ok=True);lock=QLockFile(str(DATA/'deployment.lock'))
            if not lock.tryLock(0):raise OSError('另一个安装程序正在运行，请等待完成后再试。')
            self.done.emit(str(deploy(self.payload,self.startup,progress=self.progress.emit)))
        except Exception as error:self.failed.emit(str(error))
        finally:
            if lock and lock.isLocked():lock.unlock()

class Installer(QWidget):
    def __init__(self,quick=False,maintenance=False):
        super().__init__();self.quick=quick;self.maintenance=maintenance;self.setWindowTitle('白龙桌宠增强版 · '+('一键部署' if quick else '安装与维护'));self.resize(510,220 if quick else 340);layout=QVBoxLayout(self)
        self.status=QLabel('安装版本 '+VERSION+'\n安装到当前用户，无需管理员权限。\n每次升级保留上一版本；设置和聊天记录放在独立用户目录。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.startup=QCheckBox('登录 Windows 时自动启动');self.startup.setChecked(startup_preference());layout.addWidget(self.startup);self.startup.setVisible(not quick)
        self.install_button=QPushButton('安装 / 升级');self.install_button.clicked.connect(self.start);layout.addWidget(self.install_button)
        b=QPushButton('回退到上一安装版本');b.clicked.connect(self.rollback);layout.addWidget(b);b.setVisible(not quick)
        b=QPushButton('卸载程序（保留配置与聊天记录）');b.clicked.connect(self.uninstall);layout.addWidget(b);b.setVisible(not quick)
        self.job=None;self.exe=None
        if maintenance:
            self.install_button.hide();self.status.setText('白龙桌宠 '+VERSION+' · 轻量维护\n可回退或卸载；升级请运行下载的一键部署程序。\n设置、聊天记录与账号数据保存在独立用户目录。')
        if quick:
            self.status.setText('正在准备一键部署 '+VERSION+'…\n将自动安装或升级并启动桌宠，已有设置和记录保留。')
            self.install_button.setEnabled(False);QTimer.singleShot(0,self.start)
    def start(self):
        if self.job and self.job.isRunning():return
        payload=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'payload.zip'
        if not payload.exists():self.status.setText('缺少安装载荷，请使用完整安装程序。');return
        self.install_button.setEnabled(False);self.status.setText('正在解压程序与素材，请稍等…')
        self.job=InstallJob(payload,self.startup.isChecked(),self,quick=self.quick);self.job.progress.connect(self.status.setText);self.job.done.connect(self.finished);self.job.failed.connect(self.failed);self.job.start()
    def finished(self,exe):
        if self.quick:
            self.exe=exe;self.status.setText('部署完成，桌宠已启动。\nCodex 将由桌宠自动识别，无需重启 Codex。\n本窗口即将自动关闭；维护入口为安装目录中的“白龙安装管理.exe”。')
            self.install_button.setText('关闭');self.install_button.setEnabled(True);self.install_button.clicked.disconnect();self.install_button.clicked.connect(self.close)
            QTimer.singleShot(4000,self.close);return
        self.exe=exe;self.status.setText('安装完成，已确认桌宠窗口与本地服务就绪。\n程序：'+exe)
        self.install_button.setText('显示桌宠');self.install_button.setEnabled(True);self.install_button.clicked.disconnect();self.install_button.clicked.connect(lambda:os.startfile(self.exe))
    def failed(self,message):self.install_button.setEnabled(True);self.install_button.setText('重试部署' if self.quick else '安装 / 升级');self.status.setText('安装失败：'+message)
    def rollback(self):
        try:
            m=read_manifest();others=[v for v in m['versions'] if v!=m['current']]
            if not others:self.status.setText('当前没有上一安装版本。工作目录中的源码版仍保留。');return
            folder=checked_version(ROOT,others[0])
            from shared_assets import verify_version
            from deployment_state import verify_payload
            verify_version(folder,m.get('sharedAssets',{}).get(others[0]));verify_payload(folder,others[0].split('-')[0])
            register(folder/'BailongEnhanced.exe',folder/'白龙安装管理.exe',self.startup.isChecked())
            m['current']=others[0];write_manifest(m);self.status.setText('已回退快捷方式到 '+others[0]+'。退出正在运行的桌宠后重新打开。')
        except (OSError,ValueError) as error:self.status.setText('回退失败：'+str(error))
    def uninstall(self):
        if QMessageBox.question(self,'卸载白龙','卸载所有已安装的白龙版本？配置、角色包和聊天记录会保留。')!=QMessageBox.StandardButton.Yes:return
        try:
            m=read_manifest()
            # Close the app through its local control socket, never unrelated Python/Codex processes.
            active=checked_version(ROOT,m['current']) if m['current'] else None
            if active:
                subprocess.run([str(active/'BailongEnhanced.exe'),'--quit'],timeout=20,creationflags=0x08000000)
            # Keep our running maintenance version until process exit; other versions can be removed.
            current_exe=Path(sys.executable).resolve()
            for version in m['versions']:
                folder=checked_version(ROOT,version)
                if not current_exe.is_relative_to(folder):shutil.rmtree(folder)
            startup=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'
            for name in ('BailongEnhanced.vbs','白龙桌宠增强版.lnk'):
                path=startup/name
                if path.exists():path.unlink()
            script="$s=New-Object -ComObject WScript.Shell\n$paths=@((Join-Path ([Environment]::GetFolderPath('Desktop')) '白龙桌宠增强版.lnk'),(Join-Path ([Environment]::GetFolderPath('Desktop')) '白龙桌宠.lnk'),(Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\\白龙桌宠增强版.lnk'))\nforeach($p in $paths){if(Test-Path -LiteralPath $p){$l=$s.CreateShortcut($p);if($l.TargetPath.StartsWith("+ps_string(ROOT)+",[StringComparison]::OrdinalIgnoreCase)){Remove-Item -LiteralPath $p}}}"
            subprocess.run(['powershell.exe','-NoProfile','-Command',script],creationflags=0x08000000,capture_output=True)
            import winreg
            try:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall\BailongEnhanced')
            except FileNotFoundError:pass
            # Cleanup waits for this maintenance process to exit. Its target is the
            # exact per-user install root, with the config directory outside it.
            expected=Path(os.environ['LOCALAPPDATA'])/'Programs/BailongEnhanced'
            if ROOT.resolve()!=expected.resolve() or ROOT.is_symlink():raise OSError('安装目录校验失败')
            script='$ErrorActionPreference="Stop"; Wait-Process -Id '+str(os.getpid())+' -ErrorAction SilentlyContinue; $target='+ps_string(ROOT.resolve())+'; if([IO.Path]::GetFullPath($target) -eq '+ps_string(expected.resolve())+'){Remove-Item -LiteralPath $target -Recurse -Force}'
            encoded=__import__('base64').b64encode(script.encode('utf-16-le')).decode()
            subprocess.Popen(['powershell.exe','-NoProfile','-WindowStyle','Hidden','-EncodedCommand',encoded],creationflags=0x08000000)
            self.status.setText('卸载完成。关闭此窗口后清理剩余安装文件；设置、角色包和对话已保留。')
        except OSError:self.status.setText('部分程序文件仍被占用。请先退出桌宠后再次卸载。')
    def closeEvent(self,event):
        if self.job and self.job.isRunning():event.ignore()
        else:event.accept()

def maintenance_main():
    app=QApplication.instance() or QApplication(sys.argv);app.setQuitOnLastWindowClosed(True)
    window=Installer(maintenance=True);window.show()
    if '--maintenance-smoke' in sys.argv:
        index=sys.argv.index('--maintenance-smoke')
        def record():
            output=Path(sys.argv[index+1]);output.write_text(json.dumps(dict(passed=window.isVisible(),version=VERSION,maintenance=True,installButtonHidden=not window.install_button.isVisible(),payloadPresent=(Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'payload.zip').exists())),encoding='utf-8');window.close()
        QTimer.singleShot(300,record)
    return app.exec()

if __name__=='__main__':
    app=QApplication(sys.argv);window=Installer(quick_mode(sys.argv[1:],sys.executable));window.show();sys.exit(app.exec())
