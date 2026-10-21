"""Full desktop controls on top of the existing Codex/quota integration."""
import copy
import ctypes
import json
import math
import os
import random
import shutil
import sys
import time
from collections import deque
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint,QRectF,QUrl,QEvent,Signal
from PySide6.QtGui import QPainter,QCursor,QDesktopServices
from PySide6.QtWidgets import QApplication,QMenu,QSystemTrayIcon,QFileDialog,QMessageBox
from enhanced import EnhancedPet,STATE_DIR,CONFIG
from pet import ROOT,ASSETS,clamp_position
from enhanced_core import motion_step,clean_text
from performance_metrics import measured
from desktop_core import (VERSION,DEFAULTS,normalized,atomic_json,ActionGate,physics_step,
    relative_position,restore_position)
from desktop_services import all_items,validate_character,open_codex,autostart_enabled,set_autostart
from stream_player import StreamPlayer
from status_reactions import StatusReactions

class DesktopPet(EnhancedPet):
    LAZY=True
    settingsChanged=Signal(dict)
    connectionHealthChanged=Signal(dict)
    def __init__(self,monitor=True):
        self._video_yielded=False;self.video_yield=None
        self.settings_revision=0
        from codex_connection import data_home,saved_paths
        from connection_health import CapabilityHealth
        saved_paths()
        try:previous=json.loads((STATE_DIR/'runtime.json').read_text(encoding='utf-8')).get('connection_health')
        except (OSError,ValueError):previous=None
        self.connection_health=CapabilityHealth(data_home(),previous)
        self.player=None;self.gate=ActionGate();self.asset_root=ASSETS
        self._interactive_action=False;self._manual_action=False;self._priority=0
        self._hit_image=None;self.throwing=False;self.velocity=(0.,0.)
        self.drag_samples=deque(maxlen=12);self.press_feedback=0;self.buffer_until=0
        self.pending_completion=None;self.settings_dialog=None;self.chat_window=None
        self.reactions=StatusReactions(time.monotonic());self.last_reaction=None
        self.character_dir=STATE_DIR/'characters';self.character_dir.mkdir(exist_ok=True)
        self.created_at=time.monotonic();self.decode_error=None
        super().__init__(monitor)
        from codex_navigation import CodexNavigation
        self.codex_navigation=CodexNavigation(lambda session:open_codex(session),self)
        self.codex_navigation.error.connect(lambda text:self.say(text,6000))
        from update_controller import UpdateController
        self.updates=UpdateController(VERSION,STATE_DIR/'updates',self,allow_auto=monitor)
        self.updates.installerReady.connect(self.install_app_update)
        self.updates.changed.connect(self.app_update_state)
        self._update_exit_pending=False
        self.reactions.set_actions(item['id'] for item in all_items(self.manifest))
        self.bubble.reportRequested.connect(self.open_report)
        self.bubble.settingsRequested.connect(self.open_settings)
        self.bubble.chatRequested.connect(self.open_chat)
        self.bubble.codexRequested.connect(self.open_assistant)
        self.bubble.conversationRequested.connect(self.open_conversation)
        self.bubble.optionRequested.connect(self.set_option)
        self.bubble.modeChanged.connect(self.save_bubble_mode)
        if self.settings.get('schema')!=2 and CONFIG.exists():
            shutil.copy2(CONFIG,STATE_DIR/'settings-before-0.5.0.json')
        self.settings=normalized(self.settings)
        self.walk_direction=self.settings['facing']
        self.apply_settings({},save=False)
        chosen=self.settings.get('character','builtin')
        if chosen!='builtin':
            try:self.switch_character(chosen)
            except (OSError,ValueError,KeyError):
                self.settings['character']='builtin';self.say('角色包不可用，已恢复白龙默认素材。',6000)
        self.restore_saved_position()
        self.next_chain=time.monotonic()+self.settings['random_interval']
        self.next_talk=time.monotonic()+random.uniform(self.settings['talk_min'],self.settings['talk_max'])
        self.motion_clock=time.monotonic()
        self.tray.setToolTip('白龙桌宠 '+VERSION+' · 点击恢复 / 右键设置')
        self.tray.activated.disconnect()
        self.tray.activated.connect(lambda reason:self.recover() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray_menu=QMenu();self.tray_menu.aboutToShow.connect(self.populate_tray);self.tray.setContextMenu(self.tray_menu)
        if monitor and sys.platform=='win32':
            from video_yield import VideoYield
            self.video_yield=VideoYield(self)
        self.save_settings()

    def asset_path(self,item):
        name=item.get('playbackFile') or item['file'].replace('.webm','.webp')
        path=(self.asset_root/name).resolve()
        if not path.is_relative_to(self.asset_root.resolve()):raise ValueError('素材路径不在角色目录内')
        return path

    def play(self,item,mode):
        if self._interactive_action and mode=='variant':mode='click'
        if not self.gate.request(mode,item,force=self._interactive_action or self._manual_action):return False
        if self.player is None:self.player=StreamPlayer()
        try:
            frame=self.player.start(self.asset_path(item),self.frame_size,item.get('durationMs',4000)/1000,cache_loop=mode=='idle')
        except (OSError,ValueError,KeyError) as error:
            self.decode_error=type(error).__name__;self.gate.state='idle'
            if self.current and self.current is not item:
                fallback=self.idles[0]
                if item is not fallback:self.play(fallback,'idle')
                return False
            raise
        self.frames=[frame];self._hit_image=frame.toImage();self.current=item;self.mode=mode;self.index=0
        self.started=time.monotonic();self.transition=None;self.update_frame()
        return True

    def idle(self):
        self.gate.state='idle'
        self.play(random.choice(self.idles),'idle')

    @measured('pet_animation_event')
    def animate(self):
        if self.player is None or not self.current:return
        frame,ended=self.player.advance(self.frame_size,getattr(self,'settings',{}).get('playback_speed',1))
        if frame is not None:
            self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame()
        if self.press_feedback and time.monotonic()-self.press_feedback<.5:self.update()
        if ended:
            if self.player.error:
                self.decode_error=self.player.error
                if self.enhanced_ready:self.say('这段素材读取失败，已回到待机。',5000)
            if self.mode in ('drag','throw') or (self.mode=='walk' and self.walking):
                mode=self.mode;self.gate.state=mode;self.play(self.current,mode);return
            previous=self.mode;self.gate.finish();now=time.monotonic()
            if previous!='idle':
                dedicated=previous=='reaction' and str(self.current.get('id','')).startswith('work')
                self.reactions.finished(now,max(2 if dedicated else 8,self.settings.get('action_gap',2)))
                self.buffer_until=now+max(.8,self.settings.get('action_gap',2))
            if previous in ('click','landing','task','quota','reaction'):self.next_chain=self.buffer_until+self.settings.get('random_interval',25)
            if self.play_status_reaction(now):return
            if previous=='idle' and self.autonomous_boundary(now):return
            self.idle()

    def play_status_reaction(self,now):
        allowed=self.isVisible() and self.settings.get('status_actions',True) and not (self.dragging or self.throwing or self.walking)
        if self.gate.state!='idle':return False
        selected=self.reactions.poll(now,boundary=bool(self.player and self.player.ended),allowed=allowed)
        if selected is None:return False
        items={item['id']:item for item in all_items(self.manifest)}
        item=items.get(selected.action_id)
        # Imported characters need an actual corresponding action. Do not
        # substitute an unrelated random animation when a mapping is absent.
        if item is None:return False
        if selected.kind=='complete':self.pending_completion=None
        mode='task' if selected.kind=='complete' else 'reaction'
        if not self.play(item,mode):return False
        self.last_reaction=selected
        return True

    def autonomous_boundary(self,now):
        if not self.isVisible() or self.dragging or self.throwing or self.walking:return False
        if now<max(self.next_chain,self.buffer_until,self.status_hold):return False
        if self.settings.get('status_actions',True) and self.reactions.busy(now):return False
        self.next_chain=now+self.settings['random_interval']+self.settings['action_gap']
        choices=['idle'];weights=[30]
        if self.random_actions:choices+=['turn','variant'];weights+=[10,40]
        if self.wandering and not self.settings['no_move']:choices+=['walk'];weights+=[20]
        selected=random.choices(choices,weights)[0]
        if selected=='walk':self.start_walk();return self.walking
        if selected=='turn':
            self.walk_direction*=-1;self.settings['facing']=self.walk_direction
            return self.play(random.choice(self.manifest.get('turnAnimations') or self.idles),'turn')
        if selected=='variant' and self.variants:self.choose(random.choice(self.variants));return True
        return False

    def draw_frame(self,painter,canvas):
        painter.save()
        elapsed=time.monotonic()-self.press_feedback if self.press_feedback else 99
        if elapsed<.5:
            squash=math.sin(elapsed/.5*math.pi*2)*.075*math.exp(-elapsed*5)
            painter.translate(canvas.center().x(),canvas.bottom())
            painter.scale(1+squash,1-squash);painter.translate(-canvas.center().x(),-canvas.bottom())
        if getattr(self,'walk_direction',1)<0:
            painter.translate(canvas.x()*2+canvas.width(),0);painter.scale(-1,1)
        # The base EnhancedPet mirrors only during walking; call Pet directly.
        from pet import Pet
        Pet.draw_frame(self,painter,canvas);painter.restore()

    def nativeEvent(self,event_type,message):
        if sys.platform=='win32' and self.enhanced_ready and not self.dragging:
            from ctypes import wintypes
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x84: # WM_NCHITTEST. Preserve soft alpha in the layered window.
                x=ctypes.c_short(msg.lParam&0xffff).value;y=ctypes.c_short((msg.lParam>>16)&0xffff).value
                pos=self.mapFromGlobal(QPoint(x,y))
                if not self.alpha_hit(pos.x(),pos.y()):return True,-1
        return super().nativeEvent(event_type,message)

    def alpha_hit(self,x,y):
        if self.settings.get('mouse_through'):return False
        if not self.frames or not self.current:return False
        scale=self.current.get('renderScale',1);offset=self.current.get('renderOffset',[0,0])
        if self.walk_direction<0:x=self.width()-1-x
        w=self.width()*scale;h=self.height()*scale
        fx=int((x-(self.width()-w)/2-self.width()*offset[0])/w*self.frames[0].width())
        fy=int((y-(self.height()-h)-self.height()*offset[1])/h*self.frames[0].height())
        image=self._hit_image or self.frames[0].toImage()
        return 0<=fx<image.width() and 0<=fy<image.height() and image.pixelColor(fx,fy).alpha()>=12

    def choose(self,item,interactive=False,manual=False):
        if not interactive and not manual and self.gate.state not in ('idle','turn','walk','variant'):return
        if interactive and self.gate.state=='task':return
        self.stop_walk();self.throwing=False
        self._interactive_action=interactive;self._manual_action=manual
        old=self._priority;self._priority=5 if interactive or manual else 1
        try:super().choose(item,interactive)
        finally:self._interactive_action=False;self._manual_action=False;self._priority=old

    def single_click(self):
        self.last_click=None;self.press_feedback=time.monotonic()
        pool=self.manifest.get('clickAnimations') or [v for v in self.variants if v['id'] in ('01','08','09','10','11','17','20','26') ] or self.variants or self.idles
        self.choose(random.choice(pool),interactive=True)

    def say(self,text,ms=4000):
        if self.enhanced_ready:
            now=time.monotonic();priority=self._priority or 3
            if now<self.status_hold and priority<getattr(self,'message_priority',0):return
            # Automatic action lines never obscure an active Codex task.
            if priority<=1 and not getattr(self,'_allow_talk_busy',False) and (self.last_activity.get('active',0)>0 or self.last_activity.get('state') in ('working','thinking','responding')):return
            self.message_priority=priority
        super().say(text,ms)

    def stop_walk(self):
        self.walking=False;self.walk_target=None
        if self.mode=='walk':self.gate.state='idle';self.idle()

    def start_walk(self):
        if (self.bubble.report and self.bubble.report.requested) or self.bubble.panel_page!='status' or self.settings.get('no_move') or self.dragging or self.throwing or self.gate.state not in ('idle','walk'):return
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        radius=self.settings['move_range'];spanx=max(0,area.width()-self.width()-16);spany=max(0,area.height()-self.height()-16)
        left=area.left()+8+spanx*(1-radius)/2;right=left+spanx*radius
        top=area.top()+8+spany*(1-radius)/2;bottom=top+spany*radius
        tx=random.uniform(left,right);ty=random.uniform(top,bottom)
        self.walk_direction=1 if tx>=self.x() else -1;self.settings['facing']=self.walk_direction
        self._fx,self._fy=float(self.x()),float(self.y());self.walk_target=(tx,ty,(area.left(),area.top(),area.right()-self.width()+1,area.bottom()-self.height()+1))
        pool=self.manifest.get('moveAnimations') or [self.manifest.get('dragAnimation') or self.idles[0]]
        self.walking=True;self.gate.state='idle';self.play(random.choice(pool),'walk');self.gesture_until=time.monotonic()+15

    def motion_tick(self):
        if not self.enhanced_ready:return
        now=time.monotonic();dt=now-self.motion_clock;self.motion_clock=now
        if not self.isVisible():return
        if self.throwing:
            a=(QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()).availableGeometry()
            bounds=(a.left(),a.top(),max(a.left(),a.right()-self.width()+1),max(a.top(),a.bottom()-self.height()+1))
            self._fx,self._fy,vx,vy,done=physics_step(self._fx,self._fy,*self.velocity,dt,bounds);self.velocity=(vx,vy)
            self.move(round(self._fx),round(self._fy));self.position_bubble()
            if done:self.throwing=False;self.gate.state='idle';self.play(self.manifest.get('landingAnimation') or self.idles[0],'landing');self.save_settings()
            return
        if self.walking and self.walk_target and not self.dragging:
            tx,ty,bounds=self.walk_target
            self._fx,self._fy,done=motion_step(self._fx,self._fy,tx,ty,self.settings['move_speed'],dt,bounds)
            self.move(round(self._fx),round(self._fy));self.position_bubble()
            if done or now>self.gesture_until:
                self.stop_walk();self.buffer_until=now+self.settings['action_gap'];self.next_chain=now+self.settings['random_interval'];self.save_settings()
        # Automatic gestures are dispatched in animate(), only after the
        # current clip has ended. This timer only moves the desktop window.
        if now>=self.next_talk:
            self.next_talk=now+random.uniform(self.settings['talk_min'],self.settings['talk_max'])
            busy=self.last_activity.get('active',0)>0 or self.last_activity.get('state') in ('working','thinking','responding')
            if self.settings['self_talk'] and self.settings['talk_lines'] and now>=self.status_hold and (not self.settings['talk_quiet'] or not busy):
                self._priority=1
                self._allow_talk_busy=not self.settings['talk_quiet']
                try:self.say(random.choice(self.settings['talk_lines']),5000)
                finally:self._priority=0;self._allow_talk_busy=False

    def mousePressEvent(self,event):
        self.throwing=False
        if self.mode=='throw':self.gate.state='idle';self.idle()
        self.press_feedback=time.monotonic();self.drag_samples.clear();self.drag_samples.append((time.monotonic(),self.x(),self.y()))
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.settings.get('no_move'):return
        # User dragging is the highest priority; it can interrupt a task gesture.
        if event.buttons()&Qt.MouseButton.LeftButton and not self.dragging and hasattr(self,'press_pos'):
            if (event.globalPosition().toPoint()-self.press_pos).manhattanLength()>8:self.gate.state='idle'
        super().mouseMoveEvent(event)
        if self.dragging:self.gate.state='drag';self.drag_samples.append((time.monotonic(),self.x(),self.y()))
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self.dragging:
            self.dragging=False;self.last_click=None;self.click_timer.stop();self.gate.state='idle'
            samples=[s for s in self.drag_samples if time.monotonic()-s[0]<.15]
            vx=vy=0
            if len(samples)>1:
                a,b=samples[0],samples[-1];dt=max(.01,b[0]-a[0]);vx=(b[1]-a[1])/dt;vy=(b[2]-a[2])/dt
            length=math.hypot(vx,vy)
            if self.settings['drag_physics'] and length>120 and not self.settings['no_move']:
                factor=min(1,1800/max(1,length));self.velocity=(vx*factor,vy*factor)
                self._fx,self._fy=float(self.x()),float(self.y());self.throwing=True
                self.play(self.manifest.get('dragAnimation') or self.idles[0],'throw')
            else:self.play(self.manifest.get('landingAnimation') or self.idles[0],'landing')
            self.bubble.redraw();self.position_bubble();self.save_settings();return
        super().mouseReleaseEvent(event)

    @measured('ui_activity')
    def on_activity(self,event):
        if event.get('kind')=='animation_lifecycle':
            self.reactions.confirm(event.get('session',''),event.get('turn',''),event.get('active',False),time.monotonic());return
        if event.get('kind')=='connection_health':
            self.update_connection_health(event.get('capabilities',{}));return
        if event.get('kind')=='conversation_names':
            if self.bubble.roster.update_names(event.get('names',{})):self.bubble.refresh_status()
            return
        if event.get('kind')=='read_receipts':
            if self.bubble.status_indicator.acknowledge_seen(event.get('seen',[])):self.bubble.refresh_status()
            return
        if event.get('kind')=='complete' and not self.bubble.status_indicator.notify_complete(event):return
        if event.get('kind') in ('status','complete'):
            self.bubble.roster.observe(event)
        if event.get('kind') in ('status','complete'):self.bubble.task_updated(event)
        elif event.get('kind')=='codex_presence':
            self.reactions.present=event.get('open')
            self.bubble.codex_open=event.get('open');self.bubble.evaluate_mode();return
        if event.get('kind')=='complete':
            title=clean_text(event.get('title','Codex 任务'),70)
            self._priority=10
            try:self.say('Codex 任务完成啦！\n'+title,14000)
            finally:self._priority=0
            self.notify('Codex 任务已完成',title);self.refresh_quota()
            self.complete_animation(event)
        else:
            if event.get('kind')=='status':
                self.reactions.observe(event,time.monotonic())
                if self.reactions.completion is None:self.pending_completion=None
            elif event.get('kind')=='monitor_error':
                self.reactions.observe(dict(state='offline',text='监听异常',active=0),time.monotonic())
            super().on_activity(event)
    def complete_animation(self,event):
        if self.reactions.queue_completion(event,time.monotonic()):self.pending_completion=event
    def update_connection_health(self,values):
        self.connection_health.update(values);self.connectionHealthChanged.emit(self.connection_health.snapshot())
    def quota_ready(self,windows):
        super().quota_ready(windows)
        known=any(isinstance(w.get('remaining'),(int,float)) for w in windows)
        self.update_connection_health({'quota':dict(state='available' if known else 'degraded',code='ok' if known else 'quota_unknown' if windows else 'no_windows',success_at=time.time())})
    def quota_failed(self,error):
        super().quota_failed(error)
        from quota import classify_error
        code=getattr(error,'code',None) or classify_error(str(error)).code
        if str(error) in ('服务器暂未提供额度窗口。','当前账户没有可读取的 Codex 额度。'):code='no_windows'
        self.update_connection_health({'quota':dict(state='degraded' if code=='no_windows' else 'unavailable',code=code)})
    def on_reset_feed(self,snapshot,alerts,fresh):
        self._priority=10
        try:super().on_reset_feed(snapshot,alerts,fresh)
        finally:self._priority=0

    def apply_settings(self,values,save=True):
        previous=copy.deepcopy(self.settings)
        old_size=self.height();foot=self.geometry().bottom()+1;center=self.geometry().center().x()
        self.settings.update(values);self.settings=normalized(self.settings)
        self.reactions.configure(self.settings['status_action_interval'],time.monotonic())
        if hasattr(self,'updates'):self.updates.configure(self.settings['update_checks'])
        for attr in ('wandering','random_actions','commentary','sound'):setattr(self,attr,self.settings[attr])
        self.bubble.enabled=self.settings['bubble'];self.bubble.show_quota=self.settings['quota_visible']
        self.bubble.bubble_mode=self.settings['bubble_mode']
        self.bubble.token_range=self.settings['token_chart_range']
        self.bubble.pinned=self.settings['on_top'];self.bubble.wandering=self.settings['wandering'];self.bubble.movement_locked=self.settings['no_move']
        size=round(256*self.settings['scale']);self.setFixedSize(size,size)
        if size!=old_size:self.move(self.constrained_position(QPoint(center-size//2,foot-size)))
        # All states use one physical-pixel decode policy. Refresh the current
        # frame immediately rather than changing clarity on the next action.
        self.sync_decode_size()
        if self.settings['no_move'] or not self.wandering:self.stop_walk()
        if self.settings['no_move']:self.throwing=False
        for widget in (self,self.bubble):
            visible=widget.isVisible()
            widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.settings['on_top'])
            if widget is self:widget.setWindowFlag(Qt.WindowType.WindowTransparentForInput,self.settings['mouse_through'])
            if visible:widget.show()
        self.sync_panel_flags()
        self.bubble.redraw();self.position_bubble()
        if self.video_yield:self.video_yield.reconcile()
        self.next_chain=time.monotonic()+self.settings['random_interval'];self.next_talk=time.monotonic()+self.settings['talk_min']
        if save:
            try:self.save_settings()
            except (OSError,ValueError):
                self.settings=previous;self.apply_settings({},save=False);raise
        changed={key:copy.deepcopy(value) for key,value in self.settings.items() if previous.get(key)!=value}
        if changed:
            self.settings_revision+=1;self.settingsChanged.emit(changed)

    def save_bubble_mode(self,mode):
        self.settings['bubble_mode']=mode;self.save_settings()

    def flush_status(self):
        super().flush_status();self.bubble.evaluate_mode()

    def sync_decode_size(self):
        self.frame_size=min(720,max(128,round(self.height()*(self.screen().devicePixelRatio() if self.screen() else 1))))
        if self.player is not None:
            frame=self.player.resize(self.frame_size)
            if frame is not None:
                self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame()

    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.Type.DevicePixelRatioChange and getattr(self,'enhanced_ready',False):
            QTimer.singleShot(0,self.sync_decode_size)
        return result

    def save_settings(self):
        if not self.enhanced_ready:return
        super().save_settings()
        self.settings['facing']=self.walk_direction
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();a=screen.availableGeometry()
        self.settings['screen_position']=relative_position(self.x(),self.y(),self.width(),self.height(),(a.x(),a.y(),a.width(),a.height()),screen.name())
        atomic_json(CONFIG,self.settings)
    def restore_saved_position(self):
        saved=self.settings.get('screen_position')
        if isinstance(saved,dict):
            screen=next((s for s in QApplication.screens() if s.name()==saved.get('screen')),QApplication.primaryScreen());a=screen.availableGeometry()
            try:x,y=restore_position(saved,self.width(),self.height(),(a.x(),a.y(),a.width(),a.height()));self.move(x,y)
            except (ValueError,TypeError):self.ensure_on_screen()
        self.position_bubble()
    def reset_position(self):
        self.stop_walk();self.throwing=False
        screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen();a=screen.availableGeometry()
        self.move(clamp_position(QPoint(a.right()-self.width()-20,a.bottom()-self.height()-20),self.size(),a));self.position_bubble();self.save_settings()
    def recover(self):
        self.apply_settings({'mouse_through':False});self.show();self.bubble.redraw();self.position_bubble()
    def toggle_pet(self):
        if self.isVisible():self.stop_walk();self.hide();self.bubble.hide()
        else:self.show();self.bubble.redraw();self.position_bubble()
    def position_bubble(self):
        if self.enhanced_ready and (self.bubble.size_transition.running or self.bubble.size_transition.preparing or self.bubble.size_transition.landing.image is not None):return
        if self.enhanced_ready and self.bubble.panel_page!='status' and self.bubble._editor_positioned:
            if not self.isVisible():self.bubble.hide()
            return
        super().position_bubble()
        if self.enhanced_ready and self.bubble.panel_page!='status':self.bubble._editor_positioned=True
        if self.enhanced_ready and not self.isVisible():self.bubble.hide()
    def can_raise_bubble(self):
        if self._video_yielded:return False
        # Owned panels stay above the pet. Periodic bubble updates must not
        # reorder its sibling windows over an open settings/chat panel.
        if QApplication.activePopupWidget() is not None or self.bubble.panel_page!='status':return False
        return not any(panel and panel.isVisible() and not panel.isMinimized()
                       for panel in (self.settings_dialog,self.chat_window))
    def sync_panel_flags(self):
        self.bubble._editing_flags(self.bubble.panel_page!='status')
        for panel in (self.settings_dialog,self.chat_window):
            if panel is None or not panel.isWindow():continue
            target=self.settings['on_top']
            if bool(panel.windowFlags()&Qt.WindowType.WindowStaysOnTopHint)!=target:
                visible=panel.isVisible();state=panel.windowState();active=panel.isActiveWindow()
                panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,target)
                if visible:
                    panel.setWindowState(state);panel.show()
                    if active:panel.raise_();panel.activateWindow()
    def show_panel(self,panel):
        if not panel.isWindow():
            self.stop_walk();self.throwing=False;self.show()
            self.bubble.show_page('settings' if panel is self.settings_dialog else 'chat',panel)
            self.bubble.raise_();self.bubble.activateWindow()
            if self.bubble.windowHandle():self.bubble.windowHandle().requestActivate()
            QApplication.setActiveWindow(self.bubble)
            if panel is self.chat_window and panel.pages.currentWidget() is panel.chat_body:panel.input.setFocus()
            elif panel is self.settings_dialog:panel.tabs.tabBar().setFocus()
            return
        self.sync_panel_flags();panel.showNormal();panel.raise_();panel.activateWindow()
    def set_option(self,attr,value):
        try:self.apply_settings({attr:value})
        except (OSError,ValueError) as error:
            message='设置保存失败，已恢复原值：'+str(error)
            if self.settings_dialog:self.settings_dialog.status.setText(message)
            previous=self._priority;self._priority=10
            try:self.say(message,6500)
            finally:self._priority=previous
    def toggle_bubble(self):self.set_option('bubble',not self.bubble.enabled)
    def toggle_quota(self,value):self.set_option('quota_visible',value)
    def quota(self):
        self.refresh_quota()

    def action_groups(self):
        return {'待机':self.idles,'转向':self.manifest.get('turnAnimations',[]),'移动':self.manifest.get('moveAnimations',[]),
            '点击回应':self.manifest.get('clickAnimations') or [v for v in self.variants if v['id'] in ('01','08','09','10','11')],
            '互动动作':self.variants,'工作动作':[v for v in self.manifest.get('workAnimations',[]) if v], '额度回应（不刷新数据）':[self.manifest['quotaAnimation']] if self.manifest.get('quotaAnimation') else [],
            '拖拽':[self.manifest['dragAnimation']] if self.manifest.get('dragAnimation') else [],
            '落地':[self.manifest['landingAnimation']] if self.manifest.get('landingAnimation') else []}
    def populate_tray(self):self.build_menu(self.tray_menu,tray=True)
    def execute_command(self,command,checked=False):
        toggles={'pin':'on_top','lock':'no_move','through':'mouse_through','bubble':'bubble'}
        if command in toggles:self.set_option(toggles[command],checked);return
        commands={'status':self.open_status,'settings':self.open_settings,'chat':self.open_chat,
            'visible':self.toggle_pet,'recover':self.recover,'position':self.reset_position,
            'walk':lambda:self.set_option('wandering',not self.settings['wandering']),'quit':self.close}
        commands[command]()
    def menu_command(self,menu,command):
        labels={'status':'查看状态','settings':'桌宠设置…','chat':'和白龙聊天…',
            'visible':'隐藏桌宠' if self.isVisible() else '显示桌宠','recover':'找回桌宠并关闭穿透',
            'position':'回到当前屏幕右下角','pin':'始终置顶','lock':'锁定人物位置（含拖动）',
            'through':'鼠标穿透（从托盘恢复）','bubble':'显示气泡','quit':'退出桌宠',
            'walk':('自主走动（位置已锁定）' if self.settings['no_move'] else '暂停自主走动' if self.settings['wandering'] else '恢复自主走动')}
        action=menu.addAction(labels[command]);action.setObjectName('command_'+command)
        key={'pin':'on_top','lock':'no_move','through':'mouse_through','bubble':'bubble'}.get(command)
        if key:action.setCheckable(True);action.setChecked(self.settings[key])
        if command=='walk':action.setEnabled(not self.settings['no_move'])
        action.triggered.connect(lambda value=False,c=command:QTimer.singleShot(0,self,lambda:self.execute_command(c,value)))
        return action
    def build_menu(self,menu,tray=False):
        menu.clear()
        if tray:
            for command in ('recover','visible','status','settings'):self.menu_command(menu,command)
            menu.addSeparator();self.menu_command(menu,'quit');return
        for command in ('status','chat','walk'):self.menu_command(menu,command)
        desktop=menu.addMenu('桌面操作')
        for command in ('pin','lock','through','bubble'):self.menu_command(desktop,command)
        desktop.addSeparator()
        for command in ('recover','position'):self.menu_command(desktop,command)
        groups=menu.addMenu('手动动作')
        for group,items in self.action_groups().items():
            sub=groups.addMenu(group)
            if not items:sub.addAction('专用素材待制作，暂用现有动作').setEnabled(False)
            for item in items:sub.addAction(item.get('name',item['id']),lambda v=item:self.choose(v,interactive=True,manual=True))
        menu.addSeparator()
        for command in ('settings','visible','quit'):self.menu_command(menu,command)
    def context_menu(self,point):
        self.stop_walk();menu=QMenu(self);self.build_menu(menu);menu.exec(point)
    def toggle_startup(self,value):
        try:set_autostart(value)
        except OSError:self.say('启动设置保存失败，请打开设置检查。',5000)
        if self.settings_dialog:self.settings_dialog.sync_from_pet(read_startup=True)
    def open_report(self):
        if self.bubble.report is None:
            from daily_report import DailyReport
            self.bubble.report=DailyReport(self.bubble)
            self.bubble.report.refreshRequested.connect(self.refresh_report)
        self.throwing=False
        self.bubble.report.set_snapshot(self.bubble.token_snapshot)
        self.bubble.report.toggle()

    def open_settings(self):
        if not self.settings_dialog:
            from desktop_settings import SettingsDialog
            self.settings_dialog=SettingsDialog(self,embedded=True)
        self.settings_dialog.sync_from_pet(read_startup=True)
        self.show_panel(self.settings_dialog)
    def open_status(self):
        self.show()
        if not self.bubble.enabled:self.set_option('bubble',True)
        self.bubble.set_mode('auto')
    def open_chat(self):
        if not self.chat_window:
            from chat_window import ChatWindow
            self.chat_window=ChatWindow(self,STATE_DIR,embedded=True)
        self.show_panel(self.chat_window)
    def open_chat_service(self):
        self.open_chat();self.chat_window.provider()
    def open_assistant(self):
        try:self.codex_navigation.open()
        except OSError as error:self.say(str(error),6000)
    def open_conversation(self,session):
        self.recently_visited=getattr(self,'recently_visited',{});self.recently_visited[session]=time.monotonic()
        try:self.codex_navigation.open(session)
        except OSError as error:self.say(str(error),6000)
    def open_data(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(STATE_DIR)))
    def app_update_state(self,state):
        text='白龙桌宠 '+VERSION+(' · 有更新 '+state['latest'] if state['phase']=='available' else ' · 点击恢复 / 右键设置')
        if self.tray.toolTip()!=text:self.tray.setToolTip(text)
    def install_app_update(self,path):
        import subprocess
        from app_updates import cache_paths,UpdateError
        try:
            release=self.updates.release
            if release is None:raise OSError('更新信息已失效，请重新检查')
            expected=cache_paths(self.updates.cache,release.version)['installer']
            if Path(path).resolve()!=expected.resolve() or not expected.is_file():raise OSError('安装程序尚未就绪，请重新下载')
            subprocess.Popen([str(expected),'--quick'],cwd=str(expected.parent),creationflags=0x08000000 if sys.platform=='win32' else 0)
            self.updates.installing()
        except (OSError,ValueError,UpdateError) as error:self.updates.install_failed(str(error))
    def character_choices(self):
        choices=[('builtin','白龙娘 · 内置')]
        for folder in sorted(self.character_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith('import-'):continue
            try:
                m=json.loads((folder/'素材清单.json').read_text(encoding='utf-8'));choices.append((folder.name,m.get('character',folder.name)))
            except (ValueError,OSError):pass
        return choices
    def switch_character(self,key):
        if not key:return
        if key=='builtin':root=ASSETS
        else:
            root=(self.character_dir/key).resolve()
            if root.parent!=self.character_dir.resolve():raise ValueError('角色目录无效')
        # Import performs full decoding. Switching checks structure and first frame only.
        m=json.loads((root/'素材清单.json').read_text(encoding='utf-8'))
        if not isinstance(m,dict) or not isinstance(m.get('idle'),dict) or not isinstance(m.get('variants',[]),list):raise ValueError('角色清单结构无效')
        for item in all_items(m):
            path=(root/(item.get('playbackFile') or item['file'])).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('角色包缺少素材或路径无效')
        old=(self.asset_root,self.manifest,self.idles,self.variants,self.settings.get('character','builtin'))
        preference_keys=('scale','playback_speed','talk_lines')
        self.settings['character_preferences'][old[4]]={k:copy.deepcopy(self.settings[k]) for k in preference_keys}
        self.stop_walk();self.throwing=False;self.gate.state='idle'
        try:
            self.asset_root=root;self.manifest=m;self.idles=[m['idle']]+m.get('additionalIdleAnimations',[]);self.variants=m.get('variants',[])
            self.reactions.set_actions(item['id'] for item in all_items(m))
            self.idle()
        except Exception:
            self.asset_root,self.manifest,self.idles,self.variants,_=old
            self.reactions.set_actions(item['id'] for item in all_items(self.manifest))
            self.gate.state='idle';self.idle();raise
        self.settings['character']=key
        self.apply_settings(self.settings['character_preferences'].get(key,{}))
        self.codex_navigation.close()
        if self.bubble.report:self.bubble.report.animation.stop();self.bubble.report.hide()
        if self.chat_window:self.chat_window.shutdown();self.chat_window.deleteLater();self.chat_window=None
    def export_diagnostics(self):
        self.record_state();path=ROOT/('白龙诊断-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
        value=json.loads((STATE_DIR/'runtime.json').read_text(encoding='utf-8'))
        value['asset_count']=len(all_items(self.manifest));value['decode_error']=self.decode_error
        value['work_animation_count']=len([v for v in self.manifest.get('workAnimations',[]) if v]);value['semantic_work_actions']=True;value['explicit_task_arrival_animation']=True
        atomic_json(path,value);self.say('诊断已保存：'+path.name,6000)
    def backup_settings(self):
        path=STATE_DIR/('settings-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.json');self.save_settings();shutil.copy2(CONFIG,path)
        self.say('设置备份已保存到配置目录。',5000)
    def restore_settings(self):
        path,_=QFileDialog.getOpenFileName(self.settings_dialog,'选择设置备份',str(STATE_DIR),'JSON (*.json)')
        if not path:return
        try:
            raw=json.loads(Path(path).read_text(encoding='utf-8'));self.backup_settings();self.apply_settings(normalized(raw));self.restore_saved_position()
            if self.settings_dialog:self.settings_dialog.reload()
        except (OSError,ValueError) as error:QMessageBox.warning(self.settings_dialog,'恢复失败',str(error))
    def record_state(self):
        path=STATE_DIR/'runtime.json';value=super().runtime_state()
        value.update(asset_count=len(all_items(self.manifest)),work_animation_count=len([v for v in self.manifest.get('workAnimations',[]) if v]),
            semantic_work_actions=True,explicit_task_arrival_animation=True,current_animation=self.current.get('id') if self.current else None,
            sustained_work_response=True,status_action_interval=self.reactions.interval,animation_lifecycle_leases=len(self.reactions.leases),
            smoothed_token_curves=True,conversation_hover_contrast=True,asynchronous_codex_navigation=True,
            in_app_updates=True,update_phase=self.updates.state['phase'] if hasattr(self,'updates') else 'idle',update_checks_enabled=self.settings.get('update_checks',True),
            last_reaction_kind=self.last_reaction.kind if self.last_reaction else None,
            pending_task_greetings=len(self.reactions.openings),animation_decoder_queue=self.player.frames.qsize() if self.player else 0)
        import psutil
        process=psutil.Process();mem=process.memory_info()
        snapshot=self.bubble.token_snapshot or {}
        idle_cache=self.player.loop_cache.stats() if self.player else dict(bytes=0,hits=0,limit=24*1048576)
        from typography import LATIN_FAMILY,register_font
        report=self.bubble.report
        report_data=snapshot.get('report') or {}
        value.update(ui_revision=62,hourly_token_entry='today_tokens',unified_refresh=True,icon_only_header_actions=True,refresh_icon_style='single_arc',icon_motion_speed=1.2,busy_icon_style='orbit_rings',status_icon_morph=True,status_waiting_live_flags=True,island_quota_segmented=False,island_quota_style='open_arc',island_quota_numeric_only=True,native_shrink_landing=True,shrink_preserves_chart_progress=True,native_landing_hold_ms=34,cached_chart_layers=True,stable_report_scrollbar=True,animated_deck_tabs=True,incremental_deck_switch=True,prewarmed_transition_landing=True,monotone_container_motion=True,status_updates_preserve_surface=True,capsule_pixel_handoff=True,atomic_transition_handoff=True,clean_report_dismiss=True,stable_disclosure_gutter=True,unified_card_motion=True,report_continuous_shape=True,animated_disclosures=True,week_quota_palette=True,continuous_surface_morph=True,shared_status_glyph=True,apple_island_reference=True,panel_shrink_spring=True,panel_dismiss_spring=True,panel_shrink_ms=440,panel_dismiss_ms=360,lossless_asset_pack=True,lightweight_maintenance=True,optional_webm_converter=True,shared_version_assets=True,fair_activity_targets=True,persistent_completion_ledger=True,cached_log_discovery=True,chat_incremental_stream=True,installation_ready_receipt=True,semantic_controls=True,labeled_header_actions=False,editor_keyboard_save=True,capability_health=True,connection_path_picker=True,report_scope_groups=True,report_model_filter_explicit=True,settings_draft_merge=True,settings_dirty_fields_only=True,context_menu_root_items=8,tray_recovery_menu=True,editor_returns_to_origin=True,chat_destructive_confirmation=True,quota_query_silent=True,subagent_completion_filter=True,ring_persistent_legend=False,quota_display_layout='labeled_bars',quota_reset_per_window=True,today_tokens_direct_value=True,book_reference_count=27,island_click_opens_normal=True,conversation_name_pointer_feedback=True,context_compaction_tracking=True,conversation_name_navigation=True,codex_live_status_connected=bool(self.activity and self.activity.live_reader and self.activity.live_reader.connected),daily_report_incremental_updates=True,daily_report_chart_start_after_show=True,quota_source_header_visible=False,incremental_status_refresh=True,skip_unchanged_log_reads=True,single_runtime_write=True,read_acknowledgement_history=True,read_acknowledgement_settle_seconds=4,conversation_names_visible=True,completed_conversation_background=True,independent_conversation_scroll=True,operation_status_summary=True,session_read_tracking=True,conversation_status_limit=2,codex_connection_diagnostics=True,portable_codex_discovery=True,island_bubble=True,island_quota_priority=True,bubble_mode=self.bubble.bubble_mode,bubble_auto_compact=self.bubble.auto_compact,island_visible=self.bubble.is_island(),panel_transition_stable_canvas=True,panel_transition_content_blend=True,chart_entry_animation=True,daily_report=True,daily_report_stable_surface=True,token_scan_background=True,token_models=len({r['model'] for r in report_data.get('daily_models',[])}),token_report_hours=len(report_data.get('hours',[])),daily_report_visible=bool(report and report.isVisible()),daily_report_aligned=not report or not report.isVisible() or (report.content_geometry().width()==self.bubble.width() and report.content_geometry().x()==self.bubble.x() and report.content_geometry().bottom()+1==self.bubble.y()-6),ring_center_y=None,daily_report_open=bool(self.bubble.report and self.bubble.report.requested),inline_explanations_only=True,version=VERSION,status_icon_animated=True,status_icon_unread=len(self.bubble.status_indicator.unread),status_icon_acknowledgement=True,status_icon_state=self.bubble.status_indicator.visual(),status_icon_timer=self.bubble.status_indicator.timer.isActive(),panel_transition_no_fade=True,panel_transition_staged_layout=True,panel_transition_ms=480,idle_cache_mb=round(idle_cache['bytes']/1048576,2),idle_cache_limit_mb=idle_cache['limit']/1048576,idle_cache_hits=idle_cache['hits'],integrated_panels=True,panel_page=self.bubble.panel_page,separate_panel_windows=sum(bool(p and p.isWindow()) for p in (self.settings_dialog,self.chat_window)),expanded_details_grouped=True,latin_font=LATIN_FAMILY,latin_font_loaded=register_font(),status_height_transition_ms=300,status_transition_synchronized=True,token_chart_range=self.bubble.token_range,
            token_history_days=len(snapshot.get('history_days',{})),token_hour_slots=len(snapshot.get('hours',[])),
            mode=self.mode,action_state=self.gate.state,mouse_through=self.settings['mouse_through'],scale=self.settings['scale'],
            facing=self.walk_direction,decoder_queue=self.player.frames.qsize() if self.player else 0,first_frame_cache=len(self.player.first) if self.player else 0,
            decode_size=self.frame_size,source_frame=self.player.frame_index if self.player else 0,quality_revision=self.manifest.get('qualityRevision',0),
            status_reactions=self.settings['status_actions'],reaction_samples=self.reactions.sample_count,
            reaction_kind=self.last_reaction.kind if self.last_reaction else None,reaction_action=self.last_reaction.action_id if self.last_reaction else None,
            completion_animation_pending=self.reactions.completion is not None,
            rss_mb=round(mem.rss/1048576,1),uptime=round(time.monotonic()-self.created_at,1),throwing=self.throwing)
        if self.connection_health.records['quota']['state']=='available' and any(w.get('resetsAt') and w['resetsAt']<=time.time() for w in self.quota_windows):
            self.connection_health.record('quota',dict(state='degraded',code='quota_expired'))
        value['video_fullscreen_yield_enabled']=self.settings['video_fullscreen_yield']
        value['video_fullscreen_yielding']=self._video_yielded
        value['video_detector_running']=bool(self.video_yield and self.video_yield.worker and self.video_yield.worker.is_alive())
        value['video_detection_reason']=self.video_yield.reason if self.video_yield else 'disabled'
        value['video_detection_sample']=self.video_yield.last_sample if self.video_yield else {}
        value['video_native_yield_applied']=bool(self.video_yield and self.video_yield.native_applied)
        value['video_completion_priority']=True
        value['video_firefox_backend']='ia2_video_tag'
        value['video_completion_override']=bool(self.video_yield and self.video_yield.attention_override)
        value['connection_health']=self.connection_health.snapshot()
        from performance_metrics import METRICS
        if METRICS.enabled:value['performance']=METRICS.snapshot()
        if self.activity:
            self.recently_visited={sid:t for sid,t in getattr(self,'recently_visited',{}).items() if time.monotonic()-t<120}
            self.activity.set_context(self.bubble.roster.pinned,self.recently_visited)
        if self.settings_dialog and self.settings_dialog.isVisible():self.connectionHealthChanged.emit(value['connection_health'])
        atomic_json(path,value)
    def closeEvent(self,event):
        if self.settings_dialog and self.settings_dialog.path_job and self.settings_dialog.path_job.isRunning():
            if not self.settings_dialog.path_job.wait(6500):event.ignore();return
        if self.settings_dialog and self.settings_dialog.connection_job and self.settings_dialog.connection_job.isRunning():
            self.settings_dialog.connection_job.cancel.set()
            if not self.settings_dialog.connection_job.wait(8000):event.ignore();return
        if self.settings_dialog and self.settings_dialog.job and self.settings_dialog.job.isRunning():
            self.say('素材导入仍在进行，请完成后退出。',5000);event.ignore();return
        if hasattr(self,'updates') and not self.updates.shutdown():
            if not self._update_exit_pending:self._update_exit_pending=True;self.updates.idle.connect(self.close)
            event.ignore();return
        if self.bubble.report:self.bubble.report.animation.stop();self.bubble.report.hide()
        if self.chat_window:self.chat_window.shutdown()
        if self.settings_dialog:self.settings_dialog.hide()
        if self.player:self.player.close()
        if self.video_yield:self.video_yield.shutdown()
        super().closeEvent(event)
