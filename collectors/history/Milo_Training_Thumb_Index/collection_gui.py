"""Desktop collection window. All sensor/file work runs off the Tk UI thread."""
import copy,json,os,queue,threading,traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import collect_training as backend

NAMES={'come':'Come','sit':'Sit','paw':'Paw','spin':'Spin','bang':'Bang',
       'throw_overhand':'Overhand throw','throw_underhand':'Underhand throw'}
INSTRUCTIONS={
    'come':'Beckon towards yourself once with your index finger. Keep your wrist reasonably steady.',
    'sit':'Point down with your index finger. Keep thumb and middle bent. Hold briefly, then relax.',
    'paw':'Present an open palm facing up. Hold briefly, then relax.',
    'spin':'Point with your index finger, then turn your hand clockwise once, from your view.',
    'bang':'Point a finger gun forward: index and thumb extended, middle bent. Hold briefly.',
    'throw_overhand':'Loosely grip an imaginary ball. Swing overhand and open your fingers during the throw. Follow through naturally.',
    'throw_underhand':'Loosely grip an imaginary ball near your hip. Swing underhand and open your fingers during the throw. Follow through naturally.'}
BG='#eef2f6';INK='#183143';MUTED='#637688';BLUE='#1769aa'

class Bridge:
    def __init__(self):self.events=queue.Queue();self.cancelled=threading.Event()
    def update(self,event_type,**data):self.events.put((event_type,data))
    def message(self,text):self.update('log',text=text)
    def check_cancel(self):
        if self.cancelled.is_set():raise KeyboardInterrupt
    def ask(self,prompt,kind='ready'):
        self.check_cancel();reply=queue.Queue(maxsize=1)
        self.update('question',prompt=prompt,kind=kind,reply=reply)
        while True:
            self.check_cancel()
            try:return reply.get(timeout=.1)
            except queue.Empty:pass

class CollectionWindow:
    def __init__(self,root,args,cfg):
        self.root=root;self.args=args;self.cfg=cfg;self.bridge=Bridge()
        self.running=False;self.pending=None;self.close_when_done=False;self.handoff=None;self.closed=False;self.poll_id=None
        self.classes=[c['id'] for c in cfg['classes']];self.counts={c:0 for c in self.classes};self.current=None
        self.root.title('Milo | Gesture collection');self.root.geometry('1060x760');self.root.minsize(940,720)
        self.root.configure(bg=BG);self.root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TButton',font=('Segoe UI',11),padding=(16,10))
        style.configure('Primary.TButton',foreground='white',background=BLUE)
        style.map('Primary.TButton',background=[('active','#12568c'),('disabled','#93abc0')])
        style.configure('TProgressbar',background='#27866b',troughcolor='#dce5ed',borderwidth=0)
        shell=tk.Frame(root,bg=BG);shell.pack(fill='both',expand=True,padx=24,pady=20)
        header=tk.Frame(shell,bg=BG);header.pack(fill='x',pady=(0,18))
        tk.Label(header,text='Milo',font=('Segoe UI',25,'bold'),fg=INK,bg=BG).pack(side='left')
        tk.Label(header,text='GESTURE COLLECTION',font=('Segoe UI',10,'bold'),fg=MUTED,bg=BG).pack(side='left',padx=18,pady=(10,0))
        self.total=tk.Label(header,text='0 / '+str(args.reps*len(self.classes))+' saved',font=('Segoe UI',14,'bold'),fg=INK,bg=BG);self.total.pack(side='right')
        self.overall=ttk.Progressbar(shell,maximum=args.reps*len(self.classes));self.overall.pack(fill='x',pady=(0,18))
        body=tk.Frame(shell,bg=BG);body.pack(fill='both',expand=True)
        sidebar=tk.Frame(body,bg='white',width=210);sidebar.pack(side='left',fill='y',padx=(0,18));sidebar.pack_propagate(False)
        tk.Label(sidebar,text='COMPLETE EACH GESTURE',font=('Segoe UI',9,'bold'),fg=MUTED,bg='white').pack(anchor='w',padx=16,pady=(18,10))
        self.rows={}
        for i,c in enumerate(self.classes,1):
            row=tk.Label(sidebar,text=f'{i}. {NAMES[c]}     0/{args.reps}',font=('Segoe UI',11),fg=INK,bg='white',anchor='w',padx=12,pady=13)
            row.pack(fill='x',padx=5,pady=2);self.rows[c]=row
        tk.Label(sidebar,text='Thumb + index + IMU\n2 seconds per sample\nMotor stays off while recording',justify='left',font=('Segoe UI',9),fg=MUTED,bg='white',wraplength=180).pack(side='bottom',anchor='w',padx=16,pady=20)
        card=tk.Frame(body,bg='white',padx=26,pady=22);card.pack(side='left',fill='both',expand=True)
        self.eyebrow=tk.Label(card,text='READY WHEN YOU ARE',font=('Segoe UI',10,'bold'),fg=MUTED,bg='white');self.eyebrow.pack(anchor='w')
        self.title=tk.Label(card,text='Collect one gesture at a time',font=('Segoe UI',24,'bold'),fg=INK,bg='white',anchor='w');self.title.pack(anchor='w',pady=(7,10))
        self.instruction=tk.Label(card,text='Finish 10 good samples of Come, then move to Sit, Paw and the remaining gestures.',font=('Segoe UI',11),fg=INK,bg='white',justify='left',wraplength=600,anchor='w');self.instruction.pack(fill='x',pady=(0,12))
        self.phrase=tk.Label(card,text='Say the matching command naturally around the movement.',font=('Segoe UI',12,'bold'),fg=BLUE,bg='white',anchor='w');self.phrase.pack(fill='x',pady=(0,15))
        self.cue=tk.Label(card,text='Ready',font=('Segoe UI',32,'bold'),fg=INK,bg='#f2f6fa',height=1,pady=12);self.cue.pack(fill='x')
        self.timeline=ttk.Progressbar(card,maximum=2000);self.timeline.pack(fill='x',pady=(8,10))
        self.status=tk.Label(card,text='1 second prepare  >  movement and follow-through  >  review',font=('Segoe UI',11),fg=MUTED,bg='white',justify='left',wraplength=650,anchor='w');self.status.pack(fill='x',pady=(0,10))
        self.buttons=tk.Frame(card,bg='white');self.buttons.pack(fill='x',pady=(3,12))
        self.host_area=tk.Frame(card,bg='white');self.host_area.pack(fill='x',pady=(4,5))
        tk.Label(self.host_area,text='Broker address',font=('Segoe UI',10),fg=MUTED,bg='white').pack(side='left')
        self.host=tk.StringVar(root,value=args.host);self.host_entry=ttk.Entry(self.host_area,textvariable=self.host,width=21);self.host_entry.pack(side='left',padx=12)
        self.hint=tk.Label(card,text='Continue only if the glove fit is unchanged. Start a new session after removing or refitting it.',font=('Segoe UI',9),fg=MUTED,bg='white',justify='left',wraplength=650,anchor='w');self.hint.pack(fill='x',pady=(4,8))
        self.details=tk.Text(card,height=3,font=('Consolas',8),bg='#f4f7fa',fg=MUTED,relief='flat',wrap='word',state='disabled')
        footer=tk.Frame(shell,bg=BG);footer.pack(fill='x',pady=(15,0))
        tk.Label(footer,text='Enter: record / keep     R: repeat     Q: save and stop',font=('Segoe UI',10),fg=MUTED,bg=BG).pack(side='left')
        ttk.Button(footer,text='Details',command=self.open_details).pack(side='left',padx=16)
        self.stop_button=ttk.Button(footer,text='Save and stop',command=self.stop,state='disabled');self.stop_button.pack(side='right')
        root.bind('<Return>',lambda e:self.default_action());root.bind('<space>',lambda e:self.default_action())
        root.bind('<r>',lambda e:self.reply('r') if self.pending and self.pending[1]=='review' else None)
        root.bind('<q>',lambda e:self.stop() if self.running else None)
        self.refresh_counts(self.counts,args.reps)
        self.welcome();self.poll_id=root.after(30,self.poll)
        if args.resume or args.resume_latest:root.after(120,lambda:self.begin(resume=True))

    def latest(self):
        pointer=self.args.output/'latest_session.txt'
        if not pointer.is_file():return None
        folder=self.args.output/pointer.read_text(encoding='utf-8').strip()
        return folder if (folder/'session.json').is_file() else None

    def welcome(self):
        latest=self.latest()
        if latest:
            try:
                counts=backend.counted(latest,self.classes);self.refresh_counts(counts,self.args.reps)
                self.status.config(text=f'{sum(counts.values())} good samples found. Continue to keep them and fill each gesture to 10.')
            except (OSError,ValueError,KeyError):latest=None
        choices=[]
        if latest:choices.append(('Continue saved session',lambda:self.begin(True),'Primary.TButton'))
        choices.append(('Start new session',lambda:self.begin(False),'TButton' if latest else 'Primary.TButton'))
        choices.append(('Choose saved session...',self.choose_session,'TButton'))
        self.set_buttons(choices)

    def set_buttons(self,choices):
        for child in self.buttons.winfo_children():child.destroy()
        self.default_button=None
        for text,command,style in choices:
            b=ttk.Button(self.buttons,text=text,command=command,style=style);b.pack(side='left',padx=(0,8),pady=3)
            if self.default_button is None:self.default_button=b

    def default_action(self):
        if self.root.focus_get() is self.host_entry:return
        if self.default_button is not None and str(self.default_button['state'])!='disabled':self.default_button.invoke()

    def choose_session(self):
        selected=filedialog.askopenfilename(parent=self.root,title='Select the saved session.json',filetypes=[('Session metadata','session.json')])
        if selected:self.args.resume=Path(selected).parent;self.args.resume_latest=False;self.begin(True)

    def begin(self,resume=False):
        if self.running:return
        host=self.host.get().strip()
        if not host:messagebox.showerror('Connection','Enter the laptop broker address.',parent=self.root);return
        args=copy.copy(self.args);args.host=host
        if not resume:args.resume=None;args.resume_latest=False
        elif not args.resume:args.resume_latest=True
        self.running=True;self.bridge=Bridge();self.pending=None;self.handoff=None
        self.host_area.pack_forget()
        self.set_buttons([]);self.stop_button.config(state='normal');self.host_entry.config(state='disabled')
        self.cue.config(text='Connecting...',fg=BLUE,bg='#edf4fb');self.status.config(text='Waiting for the glove. Keep the broker running and the glove powered on.')
        def worker():
            backend.VIEW=self.bridge
            try:code=backend.run(args,self.cfg)
            except (Exception,KeyboardInterrupt) as e:
                self.bridge.update('error',message=str(e) or 'Collection stopped.');code=1
                (backend.ROOT/'gui_error.log').write_text(traceback.format_exc(),encoding='utf-8')
            finally:backend.VIEW=None
            self.bridge.update('worker_done',code=code)
        threading.Thread(target=worker,name='Milo collector',daemon=False).start()

    def reply(self,value):
        if not self.pending:return
        target,_=self.pending;self.pending=None;self.set_buttons([]);target.put(value)

    def refresh_counts(self,counts,target):
        self.counts=counts.copy();self.total.config(text=f'{sum(counts.values())} / {target*len(self.classes)} saved')
        self.overall.config(maximum=target*len(self.classes),value=sum(counts.values()))
        for i,c in enumerate(self.classes,1):
            n=counts.get(c,0);self.rows[c].config(text=f'{i}. {NAMES[c]}   {n}/{target}',bg='#e6f3ed' if n>=target else '#eaf2fb' if c==self.current else 'white',fg='#247052' if n>=target else INK)

    def handle(self,kind,data):
        if kind=='log':
            self.details.config(state='normal');self.details.insert('end',data['text']+'\n')
            if int(self.details.index('end-1c').split('.')[0])>100:self.details.delete('1.0','30.0')
            self.details.see('end');self.details.config(state='disabled');return
        if kind=='connecting':self.refresh_counts(data['counts'],data['target'])
        elif kind=='calibration':
            label={'open':'Open hand','fist':'Comfortable fist','ball_grip':'Loose ball grip'}[data['pose']]
            self.current=None;self.eyebrow.config(text='ONE-TIME CALIBRATION');self.title.config(text=label)
            self.instruction.config(text=data['instruction']);self.phrase.config(text='Hold this pose for 2 seconds.');self.cue.config(text='Hold the pose',bg='#f2f6fa',fg=INK)
            self.hint.config(text='Calibration uses only thumb, index and the IMU. The motor stays off.')
        elif kind=='gesture':
            self.current=data['action'];self.eyebrow.config(text=f'GESTURE {data["index"]+1} OF {len(self.classes)}')
            self.title.config(text=NAMES[self.current]);self.instruction.config(text=INSTRUCTIONS[self.current]);self.phrase.config(text='Say "'+data['phrase']+'" near the movement.')
            self.hint.config(text='Finish all 10 accepted samples of this gesture before moving to the next.')
            self.refresh_counts(data['counts'],data['target'])
        elif kind=='sample':
            self.title.config(text=f'{NAMES[data["action"]]}  |  {data["number"]} / {data["target"]}')
            self.cue.config(text='Ready',fg=INK,bg='#f2f6fa');self.timeline['value']=0
            self.status.config(text='Record when ready. Prepare for 1 second, then perform one gesture at GO.')
            self.refresh_counts(data['counts'],data['target'])
        elif kind in ['prepare','hold','go','stop']:
            text,color,bg={'prepare':('Get ready','#9a6500','#fff4d5'),'hold':('Hold still',BLUE,'#edf4fb'),
                           'go':('GO - move now','#1d7753','#e3f5e9'),'stop':('Checking...',BLUE,'#edf4fb')}[kind]
            self.cue.config(text=text,fg=color,bg=bg)
            if kind=='stop':self.timeline['value']=2000
        elif kind=='recording_progress':self.timeline.config(value=data['elapsed_ms'])
        elif kind=='saved':self.refresh_counts(data['counts'],data['target'])
        elif kind=='fault':
            self.cue.config(text='Repeat this take',fg='#a43d34',bg='#fff0ed');self.status.config(text=data['message'])
        elif kind=='question':
            self.pending=(data['reply'],data['kind']);question=data['kind']
            if question=='review':
                self.cue.config(text='Keep this sample?',fg=BLUE,bg='#edf4fb')
                self.status.config(text='Keep only if you performed the full gesture correctly. For throws, include finger opening.')
                self.set_buttons([('Keep sample',lambda:self.reply(''),'Primary.TButton'),('Repeat',lambda:self.reply('r'),'TButton')])
            elif question=='motor':
                self.eyebrow.config(text='MOTOR CHECK');self.title.config(text='Did you feel three buzzes?')
                self.instruction.config(text='The motor pulses briefly at power-on/reset. If needed, press RST now and wait for the glove to reconnect.')
                self.phrase.config(text='It stays off during all recordings.');self.cue.config(text='Motor check',fg=INK,bg='#f2f6fa')
                self.set_buttons([('Yes, it vibrated',lambda:self.reply('y'),'Primary.TButton'),('No vibration',lambda:self.reply('n'),'TButton'),('Not checked',lambda:self.reply('u'),'TButton')])
            elif question=='retry':self.set_buttons([('Try again',lambda:self.reply(''),'Primary.TButton')])
            else:self.set_buttons([('Record 2 seconds',lambda:self.reply(''),'Primary.TButton')])
        elif kind=='saving':
            self.pending=None;self.set_buttons([]);self.cue.config(text='Saving ZIP...',fg=BLUE,bg='#edf4fb')
            self.status.config(text='Saving your accepted samples and preparing the handoff. Please wait.')
        elif kind=='finished':
            self.handoff=data.get('handoff');self.refresh_counts(data['counts'],data['target'])
            self.cue.config(text='Complete' if data['complete'] else 'Progress saved',fg='#1d7753',bg='#e3f5e9')
            self.title.config(text='Ready for your AI teammate' if data['complete'] else 'Continue later')
            self.instruction.config(text='Your ZIP contains the accepted recordings, labels, calibration and training arrays.' if data['complete'] else 'Your accepted samples are safe. Continue this session while the glove fit stays unchanged.')
            self.status.config(text=data.get('error') or (str(self.handoff) if self.handoff else 'Calibration was not completed; the local session is saved.'))
            self.phrase.config(text='70 clean samples' if data['complete'] else f'{sum(data["counts"].values())} good samples saved')
        elif kind=='error':
            self.cue.config(text='Could not continue',fg='#a43d34',bg='#fff0ed');self.status.config(text=data['message'])
        elif kind=='worker_done':
            self.running=False;self.pending=None;self.stop_button.config(state='disabled');self.host_entry.config(state='normal')
            choices=[]
            if self.handoff:choices.append(('Open ZIP folder',self.open_folder,'Primary.TButton'))
            choices.append(('Back to collection',self.reset_welcome,'TButton'));self.set_buttons(choices)
            if self.close_when_done:self.destroy()

    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,data=self.bridge.events.get_nowait();self.handle(kind,data)
                if self.closed:return
        except queue.Empty:pass
        if not self.closed:self.poll_id=self.root.after(30,self.poll)

    def reset_welcome(self):
        self.current=None;self.cue.config(text='Ready',fg=INK,bg='#f2f6fa');self.title.config(text='Collect one gesture at a time')
        self.instruction.config(text='Finish 10 good samples of one gesture, then move to the next.')
        self.phrase.config(text='Say the matching command naturally around the movement.')
        self.host_area.pack(fill='x',pady=(4,5),before=self.hint);self.welcome()

    def open_details(self):
        window=tk.Toplevel(self.root);window.title('Collection details');window.geometry('840x420')
        text=tk.Text(window,font=('Consolas',10),wrap='word');text.pack(fill='both',expand=True,padx=12,pady=12)
        text.insert('1.0',self.details.get('1.0','end'));text.config(state='disabled')

    def open_folder(self):
        if self.handoff:os.startfile(str(Path(self.handoff).parent))

    def stop(self):
        if not self.running:return
        self.bridge.cancelled.set();self.pending=None;self.set_buttons([]);self.stop_button.config(state='disabled')
        self.cue.config(text='Saving progress...',fg=BLUE,bg='#edf4fb');self.status.config(text='Stopping safely and preparing your partial ZIP.')

    def close(self):
        if self.running:self.close_when_done=True;self.stop()
        else:self.destroy()

    def destroy(self):
        self.closed=True
        if self.poll_id:
            try:self.root.after_cancel(self.poll_id)
            except tk.TclError:pass
        self.root.destroy()

def main():
    args,cfg=backend.parse_args();root=tk.Tk();CollectionWindow(root,args,cfg);root.mainloop()

if __name__=='__main__':main()
