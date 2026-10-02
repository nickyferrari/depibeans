"""Real Windows testbed lighting/calibration application. No simulator imports."""
import concurrent.futures
import ctypes
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import time
import tkinter as tk
from tkinter import ttk, messagebox
import uuid
from .gui import Preview
from .calibration import quadratic_fit,dump_points
from .hardware import Native,LightingBoard
from .lighting import zone_packet,all_zones_packet,intensity_packet,calibration_packet,integer,finite,Pulse

class Desktop(Preview):
    def __init__(self,root,data):
        self.root=root;self.data=data;self.points=[];self.board=None;self.future=None;self.uncertain=False;self.sent_raw={}
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.db=sqlite3.connect(data/'hardware-history.sqlite')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, created TEXT, description TEXT, state TEXT, result TEXT)')
        pending=self.db.execute("SELECT count(*) FROM actions WHERE state IN ('started','uncertain')").fetchone()[0]
        self.uncertain=bool(pending)
        root.title('DepiBeans - Testbed lighting');root.geometry('1160x820');root.minsize(1040,720)
        root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame',background='#f5f6f2');style.configure('TLabel',background='#f5f6f2',font=('Segoe UI',11))
        style.configure('TButton',font=('Segoe UI',10),padding=(10,6));style.configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        shell=ttk.Frame(root,padding=20);shell.pack(fill='both',expand=True)
        head=ttk.Frame(shell);head.pack(fill='x')
        ttk.Label(head,text='DepiBeans',style='Title.TLabel').pack(side='left')
        self.connection=tk.StringVar(value='DISCONNECTED')
        ttk.Label(head,textvariable=self.connection).pack(side='right')
        row=ttk.Frame(shell);row.pack(fill='x',pady=12)
        ttk.Button(row,text='Connect testbed',command=self.connect).pack(side='left')
        ttk.Button(row,text='Disconnect',command=self.disconnect).pack(side='left',padx=8)
        ttk.Button(row,text='ALL LIGHTS OFF',command=lambda:self.launch('All lights off',lambda:self.board.set_all_raw(0),self.zero_display)).pack(side='right')
        ttk.Label(shell,text='Real hardware controls • Close Calibratron before connecting. Changes take effect when you press Apply.').pack(anchor='w',pady=(0,12))
        tabs=ttk.Notebook(shell);tabs.pack(fill='both',expand=True)
        self.controls=ttk.Frame(tabs,padding=12);self.calibration=ttk.Frame(tabs,padding=12)
        for frame,title in [(self.controls,'Lighting'),(self.calibration,'Calibration')]:tabs.add(frame,text=title)
        self.message=tk.StringVar(value='Ready. Connecting does not change the lights.' if not pending else 'Previous action ended without confirmation. Inspect the lights before reconnecting.')
        ttk.Label(shell,textvariable=self.message,wraplength=1100).pack(fill='x',pady=(12,0))
        self.build_controls();self.build_calibration()
        # Replace the inherited offline explanation; point/file helpers remain reusable.
        for child in self.calibration.winfo_children():
            if isinstance(child,ttk.Label) and 'No board writes' in str(child.cget('text')):child.configure(text='Record measured values, fit each rail, then explicitly upload its coefficients.')
        ttk.Button(self.calibration,text='Upload fitted calibration for selected rail…',command=lambda:self.run(self.upload_calibration)).pack(anchor='w',pady=8)
        self.timer=root.after(100,self.poll)
    def build_controls(self):
        f=self.controls
        self.raw={}
        ttk.Label(f,text='Raw zone output (0–4095)').pack(anchor='w')
        grid=ttk.Frame(f);grid.pack(fill='both',expand=True,pady=8)
        for address in range(1,17):
            box=ttk.LabelFrame(grid,text=f'Rail {address}',padding=7);box.grid(row=(address-1)//8,column=(address-1)%8,sticky='nsew',padx=3,pady=5)
            grid.columnconfigure((address-1)%8,weight=1)
            for zone in range(3):
                v=tk.StringVar(value='0');self.raw[address,zone]=v
                ttk.Label(box,text=f'{zone+1}').grid(row=zone,column=0,padx=(0,3))
                ttk.Entry(box,textvariable=v,width=5).grid(row=zone,column=1,pady=6)
                ttk.Button(box,text='Set',width=3,command=lambda a=address,z=zone:self.run(lambda:self.apply_zone(a,z))).grid(row=zone,column=2,padx=(3,0))
        row=ttk.Frame(f);row.pack(fill='x',pady=8)
        self.all_raw=tk.StringVar(value='0')
        ttk.Label(row,text='All rails raw').pack(side='left');ttk.Entry(row,textvariable=self.all_raw,width=8).pack(side='left',padx=8)
        ttk.Button(row,text='Apply to all…',command=lambda:self.run(self.apply_all)).pack(side='left')
        self.intensity=tk.StringVar(value='0')
        ttk.Label(row,text='Calibrated intensity').pack(side='left',padx=(22,5));ttk.Entry(row,textvariable=self.intensity,width=9).pack(side='left')
        ttk.Button(row,text='Apply intensity…',command=lambda:self.run(self.apply_intensity)).pack(side='left',padx=8)
        ttk.Label(f,text='Fields are requested values, not sensor readings. Calibrated intensity uses coefficients already stored on the rails.').pack(anchor='w')
    def connect(self):
        if self.board or self.future:return
        if self.uncertain:
            if not messagebox.askyesno('Inspect testbed','An earlier output is uncertain. Have you inspected the lights and confirmed that reconnecting is appropriate?',parent=self.root):return
        self.launch('Connect',self.open_board,self.connected,hardware=False)
    def open_board(self):
        path=Path(os.environ['USERPROFILE'])/'Desktop/run225611898/lib/ChrisBlasterAdvanced_x64.dll'
        b=LightingBoard(Native(path),'Nexys2');info=b.connect();return b,info
    def connected(self,result):
        self.board,info=result;self.uncertain=False
        self.db.execute("UPDATE actions SET state='reviewed' WHERE state IN ('started','uncertain')");self.db.commit()
        self.connection.set('CONNECTED • Nexys2');self.message.set(f"Connected to real FPGA ({info['clock_hz']:,} Hz). No lighting output changed.")
    def disconnect(self):
        if self.future:return
        if self.board:self.launch('Disconnect',self.board.disconnect,self.disconnected,hardware=False)
    def disconnected(self,result):
        self.board=None;self.connection.set('DISCONNECTED');self.message.set('Disconnected. Last lighting output remains in place.')
    def launch(self,description,action,done=lambda result:None,hardware=True):
        if self.future:
            self.message.set('Wait for the current operation to finish.');return
        if hardware and (not self.board or self.uncertain):
            messagebox.showerror('DepiBeans','Connect the testbed first. Inspect and reconnect after any uncertain output.',parent=self.root);return
        action_id=str(uuid.uuid4())
        self.db.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(action_id,datetime.datetime.now(datetime.timezone.utc).isoformat(),description,'started',''));self.db.commit()
        self.future=self.pool.submit(action);self.pending=(action_id,description,done,hardware)
        self.message.set(description+'…')
    def poll(self):
        if self.future and self.future.done():
            future=self.future;self.future=None
            action_id,description,done,hardware=self.pending
            try:
                result=future.result()
                self.db.execute('UPDATE actions SET state=?,result=? WHERE id=?',('completed',str(result),action_id));self.db.commit()
                self.message.set(description+': FPGA completed.');done(result)
            except Exception as exc:
                logging.exception('Hardware operation failed')
                self.db.execute('UPDATE actions SET state=?,result=? WHERE id=?',('uncertain' if hardware else 'failed',str(exc),action_id));self.db.commit()
                if hardware:self.uncertain=True;self.connection.set('OUTPUT UNCERTAIN')
                self.message.set(str(exc));messagebox.showerror('DepiBeans',str(exc),parent=self.root)
        self.timer=self.root.after(100,self.poll)
    def submit_packet(self,description,packet,done=lambda result:None):
        self.launch(description,lambda:self.board.send_packet(packet),done)
    def apply_zone(self,address,zone):
        value=integer(int(self.raw[address,zone].get()),0,4095,'Raw output')
        self.submit_packet(f'Rail {address}, zone {zone+1}: {value}',zone_packet(address,zone,value),lambda result:self.sent_raw.update({(address,zone):value}))
    def apply_all(self):
        value=integer(int(self.all_raw.get()),0,4095,'Raw output')
        if messagebox.askyesno('All rails',f'Set every lighting rail to raw output {value}?',parent=self.root):
            self.launch(f'All rails raw {value}',lambda:self.board.set_all_raw(value),lambda r:self.set_display(value))
    def apply_intensity(self):
        value=finite(float(self.intensity.get()))
        if not 0<=value<=1000:raise ValueError('Commissioning intensity range is 0–1000')
        if messagebox.askyesno('Calibrated intensity',f'Set all rails to calibrated intensity {value:g}, using their existing calibration?',parent=self.root):
            self.submit_packet(f'Calibrated intensity {value:g}',intensity_packet(value),lambda result:self.sent_raw.clear())
    def set_display(self,value):
        for key,var in self.raw.items():var.set(str(value));self.sent_raw[key]=value
    def zero_display(self,result):self.set_display(0);self.all_raw.set('0');self.intensity.set('0')
    def add_point(self):
        address=integer(int(self.rail.get()),1,16,'rail')
        if any((address,z) not in self.sent_raw for z in range(3)):raise ValueError('Apply all three raw zone settings before recording this rail. Current raw outputs cannot be read back.')
        for zone,v in enumerate(self.zones):v.set(str(self.sent_raw[address,zone]))
        super().add_point()
    def fit(self):
        super().fit()
        self.message.set('Coefficients calculated. Review the fit before uploading to the selected rail.')
    def upload_calibration(self):
        rail=integer(int(self.rail.get()),1,16,'rail')
        points=[(i,r[rail]) for i,r in self.points if rail in r]
        if not points or any(len(z)!=3 for _,z in points):raise ValueError('Need measured points with three zones for this rail')
        fits=[quadratic_fit([(i,z[zone]) for i,z in points]) for zone in range(3)]
        for fit in fits:
            c=fit['coefficients'];low,high=fit['domain']
            # Verify the entire fitted interval, including any turning point.
            xs=[low,high]
            if c[2] and low< -c[1]/(2*c[2]) <high:xs.append(-c[1]/(2*c[2]))
            if any(not -.001<=c[0]+c[1]*x+c[2]*x*x<=4095.001 for x in xs):raise ValueError('Fitted output leaves the DAC range within the measured interval')
        packets=[calibration_packet(rail,z,fit['coefficients']) for z,fit in enumerate(fits)]
        if not messagebox.askyesno('Write rail calibration',f'Replace EEPROM calibration for rail {rail}, zones 1–3? This cannot read back or restore the previous coefficients. Save the existing calibration file first.',parent=self.root):return
        backup=self.data/('calibration-upload-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
        backup.write_text(json.dumps({'rail':rail,'fits':fits,'measurement_data':json.loads(dump_points(self.points))},indent=2))
        def upload():
            for packet in packets:self.board.send_packet(packet);time.sleep(.064)
            return {'fpga_completed':True,'rail_readback_available':False}
        self.launch(f'Upload rail {rail} calibration',upload)
    def close(self):
        if self.future:
            messagebox.showinfo('Operation in progress','Wait for the current operation to finish before closing.',parent=self.root);return
        if self.board:
            if not messagebox.askyesno('Close DepiBeans','Close and leave the current lighting output in place? Use ALL LIGHTS OFF first if you want darkness.',parent=self.root):return
            try:self.board.disconnect()
            except Exception as exc:messagebox.showerror('Disconnect failed',str(exc),parent=self.root);return
        self.root.after_cancel(self.timer);self.pool.shutdown(wait=False);self.db.close();self.root.destroy()

def main():
    if os.name!='nt':raise RuntimeError('This desktop controller requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\DepiBeans-Testbed-Lighting')
    if not mutex:raise OSError('Cannot acquire application mutex')
    if ctypes.get_last_error()==183:
        root=tk.Tk();root.withdraw();messagebox.showinfo('DepiBeans','DepiBeans is already open.');root.destroy();return
    data=Path(os.environ['LOCALAPPDATA'])/'DepiBeans';data.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,handlers=[RotatingFileHandler(data/'hardware.log',maxBytes=1048576,backupCount=2)])
    root=tk.Tk();app=Desktop(root,data);root.after(200,app.connect);root.mainloop()

if __name__=='__main__':main()
