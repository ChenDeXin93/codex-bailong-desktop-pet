"""Categorised expanded details; live data, explanations and sources stay separate."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QTabWidget,QScrollArea,QFrame
from compact_bubble import font,FONT_CSS,source_button
from reset_watch import pending_reset,schedule_text,account_reset_text
from ring_widgets import draw_metric_icon
from quota_summary_data import quota_items,today_tokens


class MetricIcon(QWidget):
    def __init__(self,kind,parent=None):
        super().__init__(parent);self.kind=kind;self.setFixedSize(24,24)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#e9e0f1'));p.drawEllipse(QRectF(1,1,22,22))
        draw_metric_icon(p,QPointF(12,12),self.kind,14)


class DetailCard(QWidget):
    def __init__(self,title,warning=False,parent=None):
        super().__init__(parent);self.warning=warning
        self.body=QVBoxLayout(self);self.body.setContentsMargins(10,9,10,10);self.body.setSpacing(6)
        label=self.text(title,size=12,strong=True)
        label.setObjectName('detail_section_title')
    def text(self,text,size=12,strong=False,muted=False,warning=False):
        if muted and not warning:size=min(size,10)
        label=QLabel(str(text));label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
        color='#915e74' if warning else '#706879' if muted else '#393343'
        label.setStyleSheet(FONT_CSS+f'font-size:{size}px;font-weight:{600 if strong else 500};color:{color};background:transparent;')
        self.body.addWidget(label);return label
    def add_metric(self,name,value,icon):
        row=QHBoxLayout();row.setSpacing(7);row.addWidget(MetricIcon(icon))
        title=QLabel(name);title.setStyleSheet(FONT_CSS+'font-size:12px;color:#706879;');row.addWidget(title,1)
        number=QLabel(value);number.setStyleSheet(FONT_CSS+'font-size:20px;color:#514360;');row.addWidget(number)
        self.body.addLayout(row)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#fbf4f7' if self.warning else '#f5f1f7'))
        p.setPen(QPen(QColor('#e9dce5' if self.warning else '#e9e0f0'),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),9,9)


class DetailsTabs(QTabWidget):
    def __init__(self,bubble,parent=None):
        super().__init__(parent);self.setObjectName('detail_tabs');self.setFixedHeight(244)
        self.setFont(font(12,True));self.areas={};self.keys=['quota','tokens','reset','legend']
        self.setStyleSheet('QTabWidget::pane{border:1px solid #e7deed;border-radius:10px;background:#fcfafc;top:-1px;}'
            'QTabBar::tab{'+FONT_CSS+'font-size:12px;color:#706879;background:transparent;border:0;padding:7px 15px;margin-bottom:3px;}'
            'QTabBar::tab:selected{color:#514360;background:#eae2f2;border-radius:7px;}'
            'QTabBar::tab:hover{background:#f2edf6;border-radius:7px;}'
            'QScrollArea{border:0;background:transparent;}QScrollBar:vertical{background:transparent;width:8px;margin:2px 0;}'
            'QScrollBar::handle:vertical{background:#cfc0de;border-radius:4px;min-height:24px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}'
            'QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}')
        quota=self.page('quota','额度');tokens=self.page('tokens','Token');reset=self.page('reset','重置');legend=self.page('legend','说明')
        card=self.card(quota,'账户额度')
        if not bubble.windows:card.text('账户额度尚未提供，空轨道不代表 0%。',muted=True)
        for item in quota_items(bubble.windows):
            card.add_metric(item['name']+'剩余',item['display'],'bolt' if item['name']=='5小时' else 'calendar')
            card.text(item['reset_text']+' · '+account_reset_text(item['reset_at'])+'（北京时间）',size=11,muted=True)
        card.text(bubble.quota_caption,size=11,warning=any(s in bubble.quota_caption for s in ('上次','不可用','待刷新')),muted=True)
        card=self.card(quota,'额度与重置')
        card.text('每条进度条表示该周期的剩余额度；下方时间是该周期自己的重置倒计时。悬停额度卡可查看精确重置时刻。',size=10,muted=True)
        card=self.card(tokens,'本机 Token 用量')
        snapshot=bubble.token_snapshot
        if not snapshot:card.text('Token 用量正在统计中…',muted=True)
        elif snapshot.get('unavailable'):card.text('Token 用量统计暂不可用，请点击顶部刷新重试。',warning=True)
        else:
            card.add_metric(snapshot.get('month','')+' 累计',f"{snapshot.get('total',0):,}",'tokens')
            card.text(today_tokens(snapshot)['description'],size=11,muted=True)
            if snapshot.get('partial'):card.text('部分日志暂不可读，当前用量统计可能不完整。',size=11,warning=True)
        card=self.card(tokens,'图表与统计范围')
        card.text('全部 / 近30天 / 近7天：用量柱状图。\n今日00–24时：每小时消耗曲线，非累计值。\n悬停图表可查看精确日期与用量。',size=11,muted=True)
        card.text('按本地日期统计，仅包含本机已记录历史。输入含缓存，输出含推理，不重复相加；长时段自动合并日期。',size=11,muted=True)
        pending=pending_reset(bubble.reset_snapshot)
        card=self.card(reset,'待落实的额外重置' if pending else '额外重置安排',warning=bool(pending))
        card.text(schedule_text(bubble.reset_snapshot),strong=True)
        if pending and pending.get('text'):card.text(pending['text'])
        if bubble.reset_feed_error:card.text('重置消息连接失败 · 显示上次记录' if bubble.reset_snapshot else '重置消息暂不可用，稍后自动重试',size=11,warning=True)
        card=self.card(reset,'公告来源')
        card.text('Codex Resets（第三方）\n预计安排不等于账户额度已到账。',size=11,muted=True)
        card.body.addWidget(source_button(),0,Qt.AlignmentFlag.AlignLeft)
        card=self.card(legend,'数据怎么看')
        for icon,title,note in [('calendar','周额度','该账户一周窗口的剩余额度，重置时间独立显示。'),('bolt','5小时额度','仅在账户提供这个限制时显示，耗尽后需等对应窗口重置。'),('clock','重置倒计时','到期显示待刷新；取得新数据后才更新余额。'),('tokens','今日 Token','本机今日实际记录的消耗量，点击可查看24小时曲线。')]:
            row=QHBoxLayout();row.setSpacing(8);row.addWidget(MetricIcon(icon),0,Qt.AlignmentFlag.AlignTop)
            labels=QVBoxLayout();labels.setSpacing(2)
            for value,size,color in [(title,11,'#514360'),(note,9,'#706879')]:
                text=QLabel(value);text.setWordWrap(True);text.setStyleSheet(FONT_CSS+f'font-size:{size}px;color:{color};');labels.addWidget(text)
            row.addLayout(labels,1);card.body.addLayout(row)
        for layout in (quota,tokens,reset,legend):layout.addStretch()
        self.setCurrentIndex(self.keys.index(bubble.detail_tab) if bubble.detail_tab in self.keys else 0)
        self.currentChanged.connect(lambda i:setattr(bubble,'detail_tab',self.keys[i]))
    def page(self,key,title):
        area=QScrollArea();area.setObjectName('detail_'+key);area.setWidgetResizable(True);area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget();content.setStyleSheet('background:transparent;');layout=QVBoxLayout(content)
        layout.setContentsMargins(7,8,7,8);layout.setSpacing(8);area.setWidget(content)
        self.areas[key]=area;self.addTab(area,title);return layout
    def card(self,layout,title,warning=False):
        card=DetailCard(title,warning);layout.addWidget(card);return card
    def restore_scroll(self,positions):
        for key,area in self.areas.items():area.verticalScrollBar().setValue(positions.get(key,0))
