"""Stable semantic selection from existing snapshots, never a FIFO of messages."""
from status_reactions import ACTIVE,classify,Reaction

class ContinuousWork:
    def __init__(self,stable_seconds=1.5):
        self.stable_seconds=stable_seconds;self.owner=None;self.candidate=None;self.since=0.;self.next_check=0.;self.current=None
    def clear(self):
        self.owner=None;self.candidate=None;self.current=None;self.next_check=0.
    def commit(self,reaction):self.owner=reaction
    def target(self,reactions,now,enabled=True):
        if not enabled or reactions.present is False or reactions.completion:
            self.current=None;self.candidate=None;self.next_check=0.;return None
        if now<self.next_check:return self.current
        self.next_check=now+.15
        def eligible(e):
            return (e and e['state'] in ACTIVE and reactions.fresh(e,now) and
                    (e['state']=='thinking' or now-e['received']<=90))
        held=reactions.sessions.get(self.owner.session) if self.owner else None
        if not eligible(held) or self.owner and held.get('turn')!=self.owner.turn:held=None
        event=held or next((e for e in reversed(reactions.sessions.values()) if eligible(e)),None)
        if event is None:self.candidate=None;self.current=None;return None
        selected=classify(event,reactions.action_ids)
        result=Reaction(selected.kind,selected.action_id,str(event['session']),str(event['turn'])) if selected else None
        key=(result.session,result.turn,result.action_id) if result else None
        if key!=self.candidate:self.candidate=key;self.since=now
        if now-self.since>=self.stable_seconds:self.current=result
        elif self.owner and held and self.current and self.current.session==self.owner.session and self.current.turn==self.owner.turn:
            pass  # Keep the current pose through transient semantic changes.
        else:self.current=None
        return self.current
