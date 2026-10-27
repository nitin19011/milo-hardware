"""Simple sequential voice recording UI. Flash MicVoiceFast first."""
import os,queue,threading,time,tkinter as tk
from tkinter import ttk,messagebox,filedialog
from pathlib import Path
from voice_core import VoiceLink,Dataset,ROOT,COMMANDS,COUNT

class App:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.link=None;self.data=None
        self.state='connecting';self.take=None;self.window=None;self.closed=False
        root.title('Milo - Fast voice collection');root.geometry('820x650');root.minsize(760,600)
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',font=('Segoe UI',11),padding=9)
        style.configure('TLabel',font=('Segoe UI',11));style.configure('Title.TLabel',font=('Segoe UI',22,'bold'))
        outer=ttk.Frame(root,padding=24);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Milo fast voice collection',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='10 good takes per command. Same command until all 10 are saved.').pack(anchor='w',pady=(4,14))
        self.connection=tk.StringVar(value='Connecting to your laptop broker...');ttk.Label(outer,textvariable=self.connection).pack(anchor='w')
        self.mic=tk.StringVar(value='Mic: waiting');ttk.Label(outer,textvariable=self.mic).pack(anchor='w',pady=(3,12))
        self.progress=ttk.Progressbar(outer,maximum=60);self.progress.pack(fill='x')
        self.count=tk.StringVar(value='');ttk.Label(outer,textvariable=self.count).pack(anchor='w',pady=(5,14))
        self.phrase=tk.StringVar(value='Please wait');ttk.Label(outer,textvariable=self.phrase,font=('Segoe UI',28,'bold')).pack(pady=(6,10))
        self.cue=tk.Label(outer,text='Getting ready',font=('Segoe UI',26,'bold'),bg='#e9edf2',fg='#243448',pady=12);self.cue.pack(fill='x')
        self.info=tk.StringVar(value='Press Record and speak immediately. No countdown or automatic playback.\nThe recording window is 3 seconds. No glove or USB connection is required.')
        ttk.Label(outer,textvariable=self.info,wraplength=740,justify='left').pack(anchor='w',pady=14)
        row=ttk.Frame(outer);row.pack(fill='x',pady=8)
        self.record=ttk.Button(row,text='Record take  [Space]',command=self.start_capture);self.record.pack(side='left',padx=(0,8))
        self.keep=ttk.Button(row,text='Keep and next  [Enter]',command=self.accept);self.keep.pack(side='left',padx=(0,8))
        self.retry=ttk.Button(row,text='Retry',command=self.discard);self.retry.pack(side='left',padx=(0,8))
        bottom=ttk.Frame(outer);bottom.pack(fill='x',pady=(12,0))
        self.resume=ttk.Button(bottom,text='Resume saved session',command=self.resume_session);self.resume.pack(side='left',padx=(0,8))
        ttk.Button(bottom,text='Open dataset folder',command=self.open_folder).pack(side='left')
        self.path_text=tk.StringVar(value='');ttk.Label(outer,textvariable=self.path_text,wraplength=740,font=('Segoe UI',9)).pack(anchor='w',pady=(12,0))
        root.bind('<space>',lambda e:self.start_capture());root.bind('<Return>',lambda e:self.accept())
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.buttons();self.worker(self.connect);self.tick()
    def emit(self,kind,value):
        if not self.closed:self.events.put((kind,value))
    def worker(self,fn):threading.Thread(target=fn,daemon=True).start()
    def connect(self):
        try:
            link=VoiceLink(self.emit);self.link=link;link.start();self.emit('initialised',None)
        except Exception as e:self.emit('connect_error',str(e))
    def buttons(self):
        for button,enabled in [(self.record,self.state=='idle' and self.data is not None and self.data.pending() is not None),
          (self.keep,self.state=='review'),(self.retry,self.state=='review'),
          (self.resume,self.state in ('idle','done'))]:button.configure(state='normal' if enabled else 'disabled')
    def show_progress(self):
        pending=self.data.pending();self.progress['value']=len(self.data.entries)
        counts='   '.join(f'{c}: {sum(e["label"]==c for e in self.data.entries)}/10' for c in COMMANDS)
        self.count.set(f'{len(self.data.entries)}/60 accepted   |   '+counts)
        self.path_text.set('Share this ZIP: '+str(self.data.zip_path))
        if pending:self.phrase.set(f'Say "Milo {pending[0]}"');self.record.configure(text=f'Record take {pending[1]}/10  [Space]')
        else:
            self.state='done';self.phrase.set('All 60 takes saved');self.cue.configure(text='COMPLETE',bg='#d8f0df',fg='#174b2a')
            self.info.set('Your ZIP is ready for the AI teammate. It contains only accepted WAVs, labels and recording metadata.')
        self.buttons()
    def start_capture(self):
        if self.state!='idle' or self.data.pending() is None:return
        self.state='capturing';self.take=None;self.window=None;self.buttons()
        self.cue.configure(text='RECORDING - speak now',bg='#c8efd4',fg='#164c2a')
        self.info.set('Say the whole phrase once now. Then Keep or Retry; there is no playback delay.')
        def run():
            try:self.emit('take',self.link.capture())
            except Exception as e:self.emit('capture_error',str(e))
        self.worker(run)
    def accept(self):
        if self.state!='review':return
        self.state='saving';self.buttons();self.cue.configure(text='Saving WAV and ZIP...',bg='#e9edf2',fg='#243448')
        label,number=self.data.pending();doc,wav,stats=self.take
        def run():
            try:self.data.accept(label,number,doc,wav,stats);self.emit('saved',None)
            except Exception as e:self.emit('save_error',str(e))
        self.worker(run)
    def discard(self):
        if self.state!='review':return
        self.state='idle';self.take=None;self.cue.configure(text='Ready to retry',bg='#e9edf2',fg='#243448')
        self.info.set('The rejected take was not saved. Press Record when ready.');self.buttons()
    def resume_session(self):
        if self.state not in ('idle','done'):return
        path=filedialog.askdirectory(title='Choose a session folder containing session.json',initialdir=ROOT/'datasets')
        if not path:return
        try:
            if not (Path(path)/'session.json').is_file():raise ValueError('Select a session folder containing session.json.')
            self.data=Dataset(path);self.state='idle';self.take=None;self.show_progress()
            if self.state=='idle':self.cue.configure(text='Resumed - ready',bg='#e9edf2',fg='#243448')
        except Exception as e:messagebox.showerror('Cannot resume',str(e))
    def open_folder(self):
        if self.data:os.startfile(str(self.data.path.parent))
    def tick(self):
        if self.closed:return
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind in ('connected','connection'):self.connection.set(value)
                elif kind=='mic':self.mic.set(value)
                elif kind=='initialised':
                    self.data=Dataset();self.state='idle';self.cue.configure(text='Ready when mic is ready');self.show_progress()
                elif kind=='scheduled':self.window=value
                elif kind=='upload':self.window=None;self.cue.configure(text=value,bg='#e9edf2',fg='#243448')
                elif kind=='take':
                    self.window=None;self.take=value;self.state='review';stats=value[2]
                    self.info.set(f'Peak {stats["peak"]}  |  level {stats["rms_dbfs"]} dBFS  |  clipped {stats["clipped_fraction"]:.2%}\n'+
                      (' '.join(stats['warnings']) if stats['warnings'] else 'Keep if you said the correct phrase clearly. Retry if you misspoke or were interrupted.'))
                    self.cue.configure(text='Keep this take or retry?',bg='#e4e8fb',fg='#27335b');self.buttons()
                elif kind=='saved':
                    self.state='idle';self.take=None;self.cue.configure(text='Saved - ready for next take',bg='#e9edf2',fg='#243448')
                    self.info.set('Press Record when ready. Each accepted take updates the dataset ZIP.');self.show_progress()
                elif kind in ('connect_error','capture_error','save_error'):
                    self.window=None
                    if kind=='connect_error':
                        self.state='error';self.connection.set('Connection failed. Close this window, check local network/settings and relaunch.')
                        if self.link:self.worker(self.link.close)
                    elif kind=='save_error':self.state='error'
                    else:self.state='idle'
                    self.cue.configure(text='Could not complete - see details',bg='#fbe1df',fg='#7c2018');self.info.set(value);self.buttons()
                    if kind=='save_error':messagebox.showerror('Save failed',value+'\nClose and resume this session to recover accepted takes.')
        except queue.Empty:pass
        if self.window:
            start,end=self.window;now=time.monotonic()
            if now<end:self.cue.configure(text='RECORDING - speak now',bg='#c8efd4',fg='#164c2a')
            else:self.cue.configure(text='Recording finished - preparing upload',bg='#e9edf2',fg='#243448')
        self.root.after(50,self.tick)
    def close(self):
        if self.state in ('capturing','saving'):
            messagebox.showinfo('Please wait','Wait for this recording or save to finish before closing.');return
        if self.state=='review' and not messagebox.askyesno('Discard unsaved take?','This take has not been accepted. Close and discard it?'):return
        self.closed=True
        if self.link:self.worker(self.link.close)
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
