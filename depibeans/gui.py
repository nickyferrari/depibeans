"""Native Python desktop preview. Only the simulator and calibration files are used."""
from pathlib import Path
import datetime as dt
import logging
from logging.handlers import RotatingFileHandler
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
from .core import Engine
from .calibration import load_points, dump_points, quadratic_fit
from .lighting import finite, integer, intensity_packet, calibration_packet


class Preview:
    def __init__(self, root, data):
        self.root=root
        self.data=data
        self.points=[]
        self.engine=Engine(str(data/'preview-v2.sqlite'))
        if not self.engine.status('local-preview'):
            self.engine.add_simulator('testbed-sim','Testbed preview',{'light_intensity':[0,1000]})
            self.engine.grant('local-preview','testbed-sim','operator',granted_by='local-preview-setup')
        root.title('DepiBeans - Testbed preview')
        root.geometry('960x720')
        root.minsize(760,600)
        root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame',background='#f5f6f2')
        style.configure('TLabel',background='#f5f6f2',foreground='#233f35',font=('Segoe UI',11))
        style.configure('TButton',font=('Segoe UI',10),padding=(12,7))
        style.configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        style.configure('Header.TLabel',font=('Segoe UI',14,'bold'))
        style.configure('Sim.TLabel',background='#fbead8',foreground='#875016',padding=8)
        style.configure('TNotebook',background='#f5f6f2')
        shell=ttk.Frame(root,padding=24);shell.pack(fill='both',expand=True)
        head=ttk.Frame(shell);head.pack(fill='x',pady=(0,18))
        ttk.Label(head,text='DepiBeans',style='Title.TLabel').pack(side='left')
        ttk.Label(head,text='SIMULATION',style='Sim.TLabel').pack(side='right')
        ttk.Label(shell,text='Python testbed preview. Physical controls are not enabled.').pack(anchor='w',pady=(0,14))
        tabs=ttk.Notebook(shell);tabs.pack(fill='both',expand=True)
        self.controls=ttk.Frame(tabs,padding=18)
        self.calibration=ttk.Frame(tabs,padding=18)
        self.schedule_tab=ttk.Frame(tabs,padding=18)
        self.readiness=ttk.Frame(tabs,padding=18)
        for frame,title in [(self.controls,'Controls'),(self.calibration,'Calibration'),(self.schedule_tab,'Schedules'),(self.readiness,'Readiness')]:tabs.add(frame,text=title)
        self.message=tk.StringVar(value='Ready to preview. No hardware connection is opened.')
        ttk.Label(shell,textvariable=self.message,wraplength=860).pack(fill='x',pady=(12,0))
        self.build_controls();self.build_calibration();self.build_schedules();self.build_readiness()
        self.refresh();self.tick()

    def run(self, action):
        try:action()
        except Exception as exc:
            logging.exception('Preview operation failed')
            self.message.set(str(exc))
            messagebox.showerror('DepiBeans',str(exc),parent=self.root)

    def build_controls(self):
        f=self.controls
        ttk.Label(f,text='Simulated chamber',style='Header.TLabel').pack(anchor='w')
        self.state=tk.StringVar()
        ttk.Label(f,textvariable=self.state,font=('Segoe UI',19)).pack(anchor='w',pady=20)
        row=ttk.Frame(f);row.pack(anchor='w')
        ttk.Label(row,text='Light intensity').pack(side='left',padx=(0,12))
        self.intensity=tk.StringVar(value='134')
        ttk.Entry(row,textvariable=self.intensity,width=14,font=('Segoe UI',13)).pack(side='left',padx=(0,12))
        ttk.Button(row,text='Apply to simulation',command=lambda:self.run(self.apply)).pack(side='left')
        ttk.Label(f,text='Preview range: 0-1000. This is not a commissioned hardware limit.').pack(anchor='w',pady=(12,4))
        ttk.Label(f,text='Manual changes pause this simulated chamber’s schedules.').pack(anchor='w')
        self.packet=tk.StringVar(value='')
        ttk.Label(f,textvariable=self.packet,font=('Consolas',11)).pack(anchor='w',pady=20)
        ttk.Separator(f).pack(fill='x',pady=12)
        ttk.Label(f,text='Current Java application',style='Header.TLabel').pack(anchor='w')
        ttk.Label(f,text='Lighting Calibratron remains the physical controller.\nUse its existing window for real equipment changes.',wraplength=800).pack(anchor='w',pady=12)

    def apply(self):
        value=finite(float(self.intensity.get()))
        row=self.engine.status('local-preview')[0]
        result=self.engine.command('local-preview',str(uuid.uuid4()),'testbed-sim',row['revision'],{'light_intensity':value})
        packet=intensity_packet(value)
        self.packet.set('Offline packet preview: '+packet.wire_bytes.hex(' '))
        self.message.set('Simulated setting applied.'+(' Schedules paused.' if result['paused_schedule_ids'] else ''))
        self.refresh()

    def build_calibration(self):
        f=self.calibration
        row=ttk.Frame(f);row.pack(fill='x')
        ttk.Button(row,text='Open calibration JSON',command=lambda:self.run(self.open_calibration)).pack(side='left')
        ttk.Button(row,text='Save JSON as…',command=lambda:self.run(self.save_calibration)).pack(side='left',padx=8)
        ttk.Button(row,text='Clear working copy',command=lambda:self.run(self.clear_points)).pack(side='left')
        ttk.Label(f,text='Work with measured data and fitted coefficients. No board writes.',wraplength=800).pack(anchor='w',pady=10)
        self.point_tree=ttk.Treeview(f,columns=('intensity','rail','zones'),show='headings',height=6)
        for col,title in [('intensity','Measured intensity'),('rail','Rail address'),('zones','Raw zone values')]:
            self.point_tree.heading(col,text=title);self.point_tree.column(col,width=160)
        self.point_tree.pack(fill='x')
        inputs=ttk.Frame(f);inputs.pack(fill='x',pady=12)
        self.measured=tk.StringVar(value='0');self.rail=tk.StringVar(value='1')
        self.zones=[tk.StringVar(value='0') for _ in range(3)]
        fields=[('Measured intensity',self.measured),('Rail',self.rail)]+[(f'Zone {i+1} raw',v) for i,v in enumerate(self.zones)]
        for i,(label,var) in enumerate(fields):
            ttk.Label(inputs,text=label).grid(row=0,column=i,sticky='w',padx=(0,10))
            ttk.Entry(inputs,textvariable=var,width=15).grid(row=1,column=i,sticky='w',padx=(0,10),pady=6)
        buttons=ttk.Frame(f);buttons.pack(fill='x')
        ttk.Button(buttons,text='Add measured point',command=lambda:self.run(self.add_point)).pack(side='left')
        ttk.Button(buttons,text='Fit selected rail',command=lambda:self.run(self.fit)).pack(side='left',padx=8)
        self.fit_output=tk.Text(f,height=7,wrap='word',font=('Consolas',10),state='disabled')
        self.fit_output.pack(fill='both',expand=True,pady=(12,0))

    def open_calibration(self):
        name=filedialog.askopenfilename(parent=self.root,filetypes=[('Calibration JSON','*.json')])
        if not name:return
        p=Path(name)
        if p.stat().st_size>5*1024*1024:raise ValueError('Calibration file exceeds the 5 MB preview limit')
        self.points=load_points(p.read_text(encoding='utf-8-sig'))
        self.refresh_points();self.message.set('Loaded a working copy of '+p.name)

    def save_calibration(self):
        if not self.points:raise ValueError('Add or open calibration points first')
        name=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',initialfile='depibeans-calibration.json',filetypes=[('Calibration JSON','*.json')])
        if name:
            Path(name).write_text(dump_points(self.points),encoding='utf-8')
            self.message.set('Calibration JSON saved. No coefficients uploaded to hardware.')

    def clear_points(self):
        if self.points and not messagebox.askyesno('Clear working copy','Clear these unsaved working points?',parent=self.root):return
        self.points=[];self.refresh_points()

    def add_point(self):
        measured=finite(float(self.measured.get()))
        address=integer(int(self.rail.get()),1,127,'rail address')
        zones=tuple(integer(int(v.get()),0,65535,'raw zone value') for v in self.zones)
        candidate=self.points+[(measured,{address:zones})]
        self.points=load_points(dump_points(candidate));self.refresh_points()
        self.message.set('Measured point added to the working copy.')

    def refresh_points(self):
        self.point_tree.delete(*self.point_tree.get_children())
        for intensity,rails in self.points:
            for rail,zones in rails.items():self.point_tree.insert('', 'end', values=(intensity,rail,', '.join(map(str,zones))))

    def fit(self):
        rail=integer(int(self.rail.get()),1,127,'rail address')
        points=[(i,r[rail]) for i,r in self.points if rail in r]
        if not points:raise ValueError('No measured points for that rail')
        n=len(points[0][1])
        if any(len(z)!=n for _,z in points):raise ValueError('Zone count differs between calibration points')
        lines=[]
        for zone in range(n):
            result=quadratic_fit([(i,z[zone]) for i,z in points])
            packet=calibration_packet(rail,zone,result['coefficients'])
            lines.append(f"Zone {zone+1}: c0, c1, c2 = "+', '.join(f'{v:.8g}' for v in result['coefficients']))
            lines.append(f"  RMSE {result['rmse']:.6g}; measured range {result['domain']}")
            lines.append('  Offline packet: '+packet.wire_bytes.hex(' '))
        self.fit_output.configure(state='normal');self.fit_output.delete('1.0','end');self.fit_output.insert('1.0','\n'.join(lines));self.fit_output.configure(state='disabled')
        self.message.set('Fit calculated. Verify physical calibration before any future board upload.')

    def build_schedules(self):
        f=self.schedule_tab
        ttk.Label(f,text='One-time simulated schedules',style='Header.TLabel').pack(anchor='w')
        row=ttk.Frame(f);row.pack(anchor='w',pady=14)
        self.minutes=tk.StringVar(value='1');self.scheduled_intensity=tk.StringVar(value='134')
        ttk.Label(row,text='Run in minutes').pack(side='left')
        ttk.Entry(row,textvariable=self.minutes,width=8).pack(side='left',padx=8)
        ttk.Label(row,text='Light intensity').pack(side='left')
        ttk.Entry(row,textvariable=self.scheduled_intensity,width=10).pack(side='left',padx=8)
        ttk.Button(row,text='New schedule',command=lambda:self.run(self.add_schedule)).pack(side='left')
        self.schedules_tree=ttk.Treeview(f,columns=('time','setting','state'),show='headings',height=10)
        for col,title in [('time','Next event (PC time)'),('setting','Intensity'),('state','Status')]:self.schedules_tree.heading(col,text=title)
        self.schedules_tree.pack(fill='both',expand=True)
        actions=ttk.Frame(f);actions.pack(anchor='w',pady=12)
        for title,state in [('Pause','paused'),('Resume','active'),('Delete','deleted')]:
            ttk.Button(actions,text=title,command=lambda state=state:self.run(lambda:self.change_schedule(state))).pack(side='left',padx=(0,8))
        ttk.Label(f,text='Preview events run while this application is open. Production automation is not connected.',wraplength=800).pack(anchor='w')

    def add_schedule(self):
        minutes=finite(float(self.minutes.get()))
        if not 0<minutes<=1440:raise ValueError('Choose a delay greater than zero and at most 1440 minutes')
        self.engine.schedule('local-preview',str(uuid.uuid4()),'testbed-sim',self.engine.clock()+minutes*60,{'light_intensity':finite(float(self.scheduled_intensity.get()))})
        self.message.set('Simulated schedule created.');self.refresh()

    def change_schedule(self,state):
        selected=self.schedules_tree.selection()
        if not selected:raise ValueError('Select a schedule first')
        self.engine.set_schedule_state('local-preview','testbed-sim',selected[0],state)
        self.message.set('Schedule '+state+'.');self.refresh()

    def build_readiness(self):
        f=self.readiness
        ttk.Label(f,text='Testbed migration',style='Header.TLabel').pack(anchor='w')
        text=('Verified: original source backup; Python on Windows; x64 ChrisBlaster native interface; offline protocol comparison.\n\n'
              'Available here: simulated intensity, one-time simulated schedules, calibration JSON and offline curve fitting.\n\n'
              'Next: commission one Python lighting function with an on-site observer and a controlled handover from Java.\n\n'
              'Then: inspect the fleet computer, register the 24 real chambers and connect authenticated Walker website access.\n\n'
              'Not enabled: physical controls, EEPROM uploads, camera acquisition, environmental control or cloud scheduling.')
        ttk.Label(f,text=text,wraplength=800,justify='left').pack(anchor='w',pady=18)
        ttk.Label(f,text='Local preview data: '+str(self.data),wraplength=800).pack(anchor='w')

    def refresh(self):
        row=self.engine.status('local-preview')[0]
        value=row['settings'].get('light_intensity')
        self.state.set('Simulated intensity: '+('not set' if value is None else f'{value:g}'))
        selected=self.schedules_tree.selection()
        self.schedules_tree.delete(*self.schedules_tree.get_children())
        for row in self.engine.schedules('local-preview'):
            self.schedules_tree.insert('','end',iid=row['id'],values=(dt.datetime.fromtimestamp(row['due']).strftime('%b %d %H:%M:%S'),row['settings']['light_intensity'],row['state']))
        for item in selected:
            if self.schedules_tree.exists(item):self.schedules_tree.selection_add(item)

    def tick(self):
        try:
            if self.engine.tick():self.refresh();self.message.set('Simulated schedule result recorded.')
        except Exception:
            logging.exception('Preview scheduler stopped')
            self.message.set('Preview scheduler stopped after an error. Close and reopen after reviewing the log.')
            return
        self.timer=self.root.after(1000,self.tick)

    def close(self):
        if getattr(self,'timer',None):self.root.after_cancel(self.timer)
        self.engine.close();self.root.destroy()


def main():
    data=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'DepiBeans'
    data.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(data/'preview.log',maxBytes=1024*1024,backupCount=1,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    root=tk.Tk()
    Preview(root,data)
    root.mainloop()

if __name__=='__main__':main()
