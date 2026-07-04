#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import uuid
import re
import csv
import subprocess
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import shutil

class ThreadSafeConsole:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, text):
        self.text_widget.after(0, self._write, text)

    def _write(self, text):
        self.text_widget.insert(tk.END, text)
        self.text_widget.see(tk.END)

class RfTestManagerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LoRa Avionic Link Test & Flashing Manager (GUI)")
        self.geometry("950x750")
        
        self.tx_serial = None
        self.rx_serial = None
        self.tx_running = False
        self.rx_running = False
        self.tx_last_settings = {}
        self.rx_last_settings = {}
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.tab_flash = ttk.Frame(self.notebook)
        self.tab_tx = ttk.Frame(self.notebook)
        self.tab_rx = ttk.Frame(self.notebook)
        self.tab_analysis = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_flash, text="Flasher")
        self.notebook.add(self.tab_tx, text="Transmitter")
        self.notebook.add(self.tab_rx, text="Receiver Logger")
        self.notebook.add(self.tab_analysis, text="Log Analyzer")
        
        self.create_flash_tab()
        self.create_tx_tab()
        self.create_rx_tab()
        self.create_analysis_tab()
        
        self.refresh_ports()
        
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["No devices found"]
            
        self.flash_port_cb['values'] = ports
        self.tx_port_cb['values'] = ports
        self.rx_port_cb['values'] = ports
        
        if ports and ports[0] != "No devices found":
            self.flash_port_cb.current(0)
            self.tx_port_cb.current(0)
            self.rx_port_cb.current(0)
            
    # --- FLASHER TAB ---
    def create_flash_tab(self):
        frame = ttk.Frame(self.tab_flash, padding=10)
        frame.pack(fill='both', expand=True)
        
        # Controls
        ctrl_frame = ttk.LabelFrame(frame, text="Configuration", padding=10)
        ctrl_frame.pack(fill='x', pady=5)
        
        ttk.Label(ctrl_frame, text="Port:").grid(row=0, column=0, sticky='w', pady=2)
        self.flash_port_cb = ttk.Combobox(ctrl_frame, width=30)
        self.flash_port_cb.grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(ctrl_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5, pady=2)
        
        ttk.Label(ctrl_frame, text="Board Type:").grid(row=1, column=0, sticky='w', pady=2)
        self.flash_board_var = tk.StringVar(value="sender")
        ttk.Combobox(ctrl_frame, textvariable=self.flash_board_var, values=["sender", "receiver"], state="readonly").grid(row=1, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(ctrl_frame, text="Hardware Ver:").grid(row=2, column=0, sticky='w', pady=2)
        self.flash_ver_var = tk.StringVar(value="V6")
        ttk.Combobox(ctrl_frame, textvariable=self.flash_ver_var, values=["V5", "V6"], state="readonly").grid(row=2, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(ctrl_frame, text="Frequency:").grid(row=3, column=0, sticky='w', pady=2)
        self.flash_freq_var = tk.StringVar(value="915")
        ttk.Combobox(ctrl_frame, textvariable=self.flash_freq_var, values=["433", "915"], state="readonly").grid(row=3, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(ctrl_frame, text="Coding Rate (4/x):").grid(row=4, column=0, sticky='w', pady=2)
        self.flash_cr_var = tk.StringVar(value="6")
        ttk.Combobox(ctrl_frame, textvariable=self.flash_cr_var, values=["5", "6", "7", "8"], state="readonly").grid(row=4, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(ctrl_frame, text="Bandwidth:").grid(row=5, column=0, sticky='w', pady=2)
        self.flash_bw_var = tk.StringVar(value="125E3")
        ttk.Combobox(ctrl_frame, textvariable=self.flash_bw_var, values=["7.8E3", "10.4E3", "15.6E3", "20.8E3", "31.25E3", "41.7E3", "62.5E3", "125E3", "250E3", "500E3"], state="readonly").grid(row=5, column=1, padx=5, pady=2, sticky='w')

        self.btn_flash = ttk.Button(ctrl_frame, text="Flash Firmware", command=self.start_flash_thread)
        self.btn_flash.grid(row=6, column=0, columnspan=3, pady=10)
        
        # Console
        self.flash_console = scrolledtext.ScrolledText(frame, state='normal', height=20, bg='black', fg='lightgreen', font=('Consolas', 11))
        self.flash_console.pack(fill='both', expand=True, pady=5)
        self.flash_out = ThreadSafeConsole(self.flash_console)

    def set_cpp_parameters(self, filepath, freq_mhz, bw, cr):
        if not os.path.exists(filepath):
            self.flash_out.write(f"[ERROR] File not found: {filepath}\n")
            return False
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        lines = content.splitlines()
        new_lines = []
        
        for line in lines:
            if 'LORA_FREQ' in line and ('433E6' in line or '915E6' in line):
                if freq_mhz == "433":
                    if '433E6' in line:
                        new_lines.append("#define LORA_FREQ   433E6   // 433 MHz")
                    else:
                        new_lines.append("// #define LORA_FREQ      915E6   // 915 MHz")
                elif freq_mhz == "915":
                    if '433E6' in line:
                        new_lines.append("// #define LORA_FREQ   433E6   // 433 MHz")
                    else:
                        new_lines.append("#define LORA_FREQ      915E6   // 915 MHz")
            elif 'LoRa.setSignalBandwidth' in line:
                new_lines.append(f"  LoRa.setSignalBandwidth({bw});")
            elif 'LoRa.setCodingRate4' in line:
                new_lines.append(f"  LoRa.setCodingRate4({cr});")
            else:
                new_lines.append(line)
                
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')
        self.flash_out.write(f"[INFO] Configured: {freq_mhz}MHz, BW:{bw}, CR:4/{cr}\n")
        return True

    def start_flash_thread(self):
        self.btn_flash.config(state='disabled')
        self.flash_console.delete('1.0', tk.END)
        threading.Thread(target=self.run_flash, daemon=True).start()

    def run_flash(self):
        try:
            port = self.flash_port_cb.get()
            board = self.flash_board_var.get()
            ver = self.flash_ver_var.get()
            freq = self.flash_freq_var.get()
            bw = self.flash_bw_var.get()
            cr = self.flash_cr_var.get()
            
            if "No devices found" in port or not port:
                self.flash_out.write("[ERROR] Invalid port selected.\n")
                return
                
            src_dir = os.path.abspath('src')
            os.makedirs(src_dir, exist_ok=True)
            
            for filename in os.listdir(src_dir):
                if filename.endswith('.cpp'):
                    os.remove(os.path.join(src_dir, filename))
                    
            master_file = f"{board}{ver}.cpp"
            sandbox_file = os.path.join(src_dir, master_file)
            
            if not os.path.exists(master_file):
                self.flash_out.write(f"[ERROR] Master file {master_file} not found in root!\n")
                return
                
            shutil.copy2(master_file, sandbox_file)
            self.set_cpp_parameters(sandbox_file, freq, bw, cr)
            
            self.flash_out.write(f"[INFO] Uploading {board}{ver} to {port}...\n")
            
            cmd = ["pio", "run", "-t", "upload", "--upload-port", port]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            for line in process.stdout:
                self.flash_out.write(line)
            
            process.wait()
            if process.returncode == 0:
                self.flash_out.write(f"\n[SUCCESS] Flashing completed!\n")
            else:
                self.flash_out.write(f"\n[ERROR] Flashing failed with code {process.returncode}\n")
        except Exception as e:
            self.flash_out.write(f"[ERROR] {e}\n")
        finally:
            self.flash_console.after(0, lambda: self.btn_flash.config(state='normal'))

    # --- TRANSMITTER TAB ---
    def create_tx_tab(self):
        frame = ttk.Frame(self.tab_tx, padding=10)
        frame.pack(fill='both', expand=True)
        
        ctrl = ttk.LabelFrame(frame, text="Connection", padding=10)
        ctrl.pack(fill='x', pady=5)
        
        ttk.Label(ctrl, text="Port:").grid(row=0, column=0)
        self.tx_port_cb = ttk.Combobox(ctrl, width=30)
        self.tx_port_cb.grid(row=0, column=1, padx=5)
        
        self.btn_tx_conn = ttk.Button(ctrl, text="Connect", command=self.toggle_tx_connection)
        self.btn_tx_conn.grid(row=0, column=2, padx=5)
        
        test_frame = ttk.LabelFrame(frame, text="Test Controls", padding=10)
        test_frame.pack(fill='x', pady=5)
        
        ttk.Label(test_frame, text="SF (6-12):").grid(row=0, column=0)
        self.tx_sf_var = tk.StringVar(value="7")
        ttk.Entry(test_frame, textvariable=self.tx_sf_var, width=5).grid(row=0, column=1)
        
        ttk.Label(test_frame, text="Interval (ms):").grid(row=0, column=2, padx=(10,0))
        self.tx_int_var = tk.StringVar(value="150")
        ttk.Entry(test_frame, textvariable=self.tx_int_var, width=5).grid(row=0, column=3)
        
        ttk.Button(test_frame, text="1) Formal Test", command=lambda: self.send_tx_cmd("formal")).grid(row=1, column=0, pady=5)
        ttk.Button(test_frame, text="2) Stress Test", command=lambda: self.send_tx_cmd("stress")).grid(row=1, column=1, pady=5)
        ttk.Button(test_frame, text="3) Pre-Test", command=lambda: self.send_tx_cmd("pre")).grid(row=1, column=2, pady=5)
        ttk.Button(test_frame, text="Stop Transmission (x)", command=lambda: self.send_tx_cmd("stop")).grid(row=1, column=3, padx=10, pady=5)
        
        dyn_frame = ttk.LabelFrame(frame, text="Dynamic LoRa Settings", padding=10)
        dyn_frame.pack(fill='x', pady=5)
        
        ttk.Label(dyn_frame, text="Freq (MHz):").grid(row=0, column=0)
        self.tx_dyn_f = ttk.Combobox(dyn_frame, values=["433", "915"], width=5)
        self.tx_dyn_f.current(1)
        self.tx_dyn_f.grid(row=0, column=1, padx=2)

        ttk.Label(dyn_frame, text="BW (Hz):").grid(row=0, column=2, padx=(10,0))
        self.tx_dyn_b = ttk.Combobox(dyn_frame, values=["125000", "250000", "500000", "62500", "31250"], width=8)
        self.tx_dyn_b.current(0)
        self.tx_dyn_b.grid(row=0, column=3, padx=2)

        ttk.Label(dyn_frame, text="CR (4/x):").grid(row=0, column=4, padx=(10,0))
        self.tx_dyn_c = ttk.Combobox(dyn_frame, values=["5", "6", "7", "8"], width=3)
        self.tx_dyn_c.current(1)
        self.tx_dyn_c.grid(row=0, column=5, padx=2)

        ttk.Label(dyn_frame, text="SF:").grid(row=0, column=6, padx=(10,0))
        self.tx_dyn_s = ttk.Combobox(dyn_frame, values=["6", "7", "8", "9", "10", "11", "12"], width=3)
        self.tx_dyn_s.current(1)
        self.tx_dyn_s.grid(row=0, column=7, padx=2)
        
        ttk.Button(dyn_frame, text="Apply Settings", command=self.tx_apply_settings).grid(row=0, column=8, padx=10)
        
        self.tx_console = scrolledtext.ScrolledText(frame, height=15, bg='#1e1e1e', fg='#00ff00', font=('Consolas', 11))
        self.tx_console.pack(fill='both', expand=True, pady=5)
        self.tx_out = ThreadSafeConsole(self.tx_console)
        
    def toggle_tx_connection(self):
        if not self.tx_running:
            port = self.tx_port_cb.get()
            try:
                self.tx_serial = serial.Serial(port, 115200, timeout=0.1)
                self.tx_running = True
                self.btn_tx_conn.config(text="Disconnect")
                self.tx_out.write(f"[INFO] Connected to {port}\n")
                threading.Thread(target=self.tx_read_loop, daemon=True).start()
            except Exception as e:
                self.tx_out.write(f"[ERROR] {e}\n")
        else:
            self.tx_running = False
            if self.tx_serial:
                self.tx_serial.close()
            self.btn_tx_conn.config(text="Connect")
            self.tx_out.write("[INFO] Disconnected\n")
            
    def tx_read_loop(self):
        while self.tx_running and self.tx_serial and self.tx_serial.is_open:
            try:
                line = self.tx_serial.readline()
                if line:
                    self.tx_out.write(line.decode('utf-8', errors='ignore'))
            except:
                break

    def tx_send_raw(self, cmd):
        if self.tx_running and self.tx_serial:
            self.tx_out.write(f"[GUI] Sending Command: {cmd}\n")
            self.tx_serial.write((cmd + '\n').encode())

    def tx_apply_settings(self):
        f_val = self.tx_dyn_f.get()
        b_val = self.tx_dyn_b.get()
        c_val = self.tx_dyn_c.get()
        s_val = self.tx_dyn_s.get()

        if f_val != self.tx_last_settings.get("f"):
            self.tx_send_raw(f"f {int(float(f_val)*1E6)}")
            self.tx_last_settings["f"] = f_val
            time.sleep(0.05)
            
        if b_val != self.tx_last_settings.get("b"):
            self.tx_send_raw(f"b {b_val}")
            self.tx_last_settings["b"] = b_val
            time.sleep(0.05)
            
        if c_val != self.tx_last_settings.get("c"):
            self.tx_send_raw(f"c {c_val}")
            self.tx_last_settings["c"] = c_val
            time.sleep(0.05)
            
        if s_val != self.tx_last_settings.get("s"):
            self.tx_send_raw(f"v {s_val}")
            self.tx_last_settings["s"] = s_val
            time.sleep(0.05)

    def send_tx_cmd(self, mode):
        if not self.tx_running or not self.tx_serial:
            messagebox.showwarning("Warning", "Connect first!")
            return
            
        if mode == "stop":
            self.tx_serial.write(b"x\n")
            return
            
        test_uuid = str(uuid.uuid4())
        self.tx_out.write(f"\n[INFO] Setting UUID: {test_uuid}\n")
        self.tx_serial.write(f"u {test_uuid}\n".encode())
        time.sleep(0.3)
        
        sf = self.tx_sf_var.get()
        interval = self.tx_int_var.get()
        
        if mode == "formal":
            self.tx_serial.write(f"{sf}\n".encode())
        elif mode == "stress":
            self.tx_serial.write(f"s {sf} {interval}\n".encode())
        elif mode == "pre":
            self.tx_serial.write(f"p {sf}\n".encode())

    # --- RECEIVER TAB ---
    def create_rx_tab(self):
        frame = ttk.Frame(self.tab_rx, padding=10)
        frame.pack(fill='both', expand=True)
        
        ctrl = ttk.LabelFrame(frame, text="Connection", padding=10)
        ctrl.pack(fill='x', pady=5)
        
        ttk.Label(ctrl, text="Port:").grid(row=0, column=0)
        self.rx_port_cb = ttk.Combobox(ctrl, width=20)
        self.rx_port_cb.grid(row=0, column=1, padx=5)
        
        self.btn_rx_conn = ttk.Button(ctrl, text="Listen & Log", command=self.toggle_rx_connection)
        self.btn_rx_conn.grid(row=0, column=2, padx=5)
        
        ttk.Label(ctrl, text="Send Cmd:").grid(row=0, column=3, padx=(20,0))
        self.rx_cmd_entry = ttk.Entry(ctrl, width=10)
        self.rx_cmd_entry.grid(row=0, column=4, padx=5)
        self.rx_cmd_entry.bind("<Return>", self.send_rx_cmd)
        ttk.Button(ctrl, text="Send", command=self.send_rx_cmd).grid(row=0, column=5)
        
        dyn_frame = ttk.LabelFrame(frame, text="Dynamic LoRa Settings", padding=10)
        dyn_frame.pack(fill='x', pady=5)
        
        ttk.Label(dyn_frame, text="Freq (MHz):").grid(row=0, column=0)
        self.rx_dyn_f = ttk.Combobox(dyn_frame, values=["433", "915"], width=5)
        self.rx_dyn_f.current(1)
        self.rx_dyn_f.grid(row=0, column=1, padx=2)

        ttk.Label(dyn_frame, text="BW (Hz):").grid(row=0, column=2, padx=(10,0))
        self.rx_dyn_b = ttk.Combobox(dyn_frame, values=["125000", "250000", "500000", "62500", "31250"], width=8)
        self.rx_dyn_b.current(0)
        self.rx_dyn_b.grid(row=0, column=3, padx=2)

        ttk.Label(dyn_frame, text="CR (4/x):").grid(row=0, column=4, padx=(10,0))
        self.rx_dyn_c = ttk.Combobox(dyn_frame, values=["5", "6", "7", "8"], width=3)
        self.rx_dyn_c.current(1)
        self.rx_dyn_c.grid(row=0, column=5, padx=2)

        ttk.Label(dyn_frame, text="SF:").grid(row=0, column=6, padx=(10,0))
        self.rx_dyn_s = ttk.Combobox(dyn_frame, values=["6", "7", "8", "9", "10", "11", "12"], width=3)
        self.rx_dyn_s.current(1)
        self.rx_dyn_s.grid(row=0, column=7, padx=2)
        
        ttk.Button(dyn_frame, text="Apply Settings", command=self.rx_apply_settings).grid(row=0, column=8, padx=10)
        
        self.rx_console = scrolledtext.ScrolledText(frame, height=20, bg='#1e1e1e', fg='#00ffff', font=('Consolas', 11))
        self.rx_console.pack(fill='both', expand=True, pady=5)
        self.rx_out = ThreadSafeConsole(self.rx_console)
        
    def send_rx_cmd(self, event=None):
        if self.rx_running and self.rx_serial:
            cmd = self.rx_cmd_entry.get()
            if cmd:
                self.rx_serial.write((cmd + '\n').encode())
                self.rx_cmd_entry.delete(0, tk.END)

    def rx_send_raw(self, cmd):
        if self.rx_running and self.rx_serial:
            self.rx_out.write(f"[GUI] Sending Command: {cmd}\n")
            self.rx_serial.write((cmd + '\n').encode())

    def rx_apply_settings(self):
        f_val = self.rx_dyn_f.get()
        b_val = self.rx_dyn_b.get()
        c_val = self.rx_dyn_c.get()
        s_val = self.rx_dyn_s.get()

        if f_val != self.rx_last_settings.get("f"):
            self.rx_send_raw(f"f {int(float(f_val)*1E6)}")
            self.rx_last_settings["f"] = f_val
            time.sleep(0.05)
            
        if b_val != self.rx_last_settings.get("b"):
            self.rx_send_raw(f"b {b_val}")
            self.rx_last_settings["b"] = b_val
            time.sleep(0.05)
            
        if c_val != self.rx_last_settings.get("c"):
            self.rx_send_raw(f"c {c_val}")
            self.rx_last_settings["c"] = c_val
            time.sleep(0.05)
            
        if s_val != self.rx_last_settings.get("s"):
            self.rx_send_raw(f"v {s_val}")
            self.rx_last_settings["s"] = s_val
            time.sleep(0.05)

    def toggle_rx_connection(self):
        if not self.rx_running:
            port = self.rx_port_cb.get()
            try:
                self.rx_serial = serial.Serial(port, 115200, timeout=0.1)
                self.rx_running = True
                self.btn_rx_conn.config(text="Stop Listening")
                self.rx_out.write(f"[INFO] Connected. Listening on {port}...\n")
                threading.Thread(target=self.rx_read_loop, daemon=True).start()
            except Exception as e:
                self.rx_out.write(f"[ERROR] {e}\n")
        else:
            self.rx_running = False
            if self.rx_serial:
                self.rx_serial.close()
            self.btn_rx_conn.config(text="Listen & Log")
            self.rx_out.write("[INFO] Stopped.\n")

    def rx_read_loop(self):
        os.makedirs('logs', exist_ok=True)
        session_stats = {}
        current_uuid = None
        f = None
        csv_writer = None
        
        while self.rx_running and self.rx_serial and self.rx_serial.is_open:
            try:
                raw = self.rx_serial.readline()
                if not raw:
                    continue
                line = raw.decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                    
                if "RESET" in line or "同步至" in line or "[設定]" in line or "+SET_OK:" in line:
                    self.rx_out.write(f"[STATUS] {line}\n")
                    if "RESET" in line:
                        session_stats.clear()
                    continue
                    
                if line.startswith("+RCV:"):
                    parts = line.split(" | ")
                    rcv_part = parts[0]
                    snr = "N/A"
                    rssi = "N/A"
                    for p in parts[1:]:
                        if p.startswith("SNR:"): snr = p.split(":")[1].strip()
                        elif p.startswith("RSSI:"): rssi = p.split(":")[1].strip()
                            
                    payload = rcv_part[5:]
                    if payload.startswith("TST:") or payload.startswith("FRM:") or payload.startswith("STR:"):
                        tag_map = {"TST": "PRE-TEST", "FRM": "FORM", "STR": "STRESS"}
                        mode_tag = tag_map.get(payload[:3], "UNKNOWN")
                        
                        first_colon = payload.find(':')
                        second_colon = payload.find(':', first_colon + 1)
                        asterisk = payload.find('*')
                        if asterisk == -1: asterisk = len(payload)
                            
                        uuid_str = "N/A"
                        if second_colon != -1 and second_colon < asterisk:
                            id_str = payload[first_colon + 1:second_colon]
                            uuid_str = payload[second_colon + 1:asterisk]
                        else:
                            id_str = payload[first_colon + 1:asterisk]
                            
                        try:
                            pkt_id = int(id_str)
                        except ValueError:
                            self.rx_out.write(f"[RAW] {line}\n")
                            continue
                            
                        if uuid_str not in session_stats:
                            session_stats[uuid_str] = {"received": set(), "max": -1}
                        
                        stats = session_stats[uuid_str]
                        if pkt_id < stats["max"] - 5 or (pkt_id == 0 and stats["max"] > 0):
                            stats["received"].clear()
                            stats["max"] = -1
                            
                        stats["received"].add(pkt_id)
                        if pkt_id > stats["max"]: stats["max"] = pkt_id
                            
                        tot = stats["max"] + 1
                        loss = ((tot - len(stats["received"])) / tot * 100.0) if tot > 0 else 0.0
                        
                        if uuid_str != current_uuid:
                            if f: f.close()
                            current_uuid = uuid_str
                            log_path = f"logs/rx_GUI_session_{current_uuid}.csv"
                            exists = os.path.exists(log_path)
                            f = open(log_path, 'a', newline='', encoding='utf-8')
                            csv_writer = csv.writer(f)
                            if not exists:
                                csv_writer.writerow(["Timestamp", "Mode", "PacketID", "UUID", "SNR_dB", "RSSI_dBm", "LossRate"])
                                f.flush()
                            self.rx_out.write(f"\n[INFO] Logging to: {log_path}\n")
                            
                        iso = datetime.datetime.now().isoformat()
                        if mode_tag in ["FORM", "STRESS"] and csv_writer:
                            csv_writer.writerow([iso, mode_tag, pkt_id, uuid_str, snr, rssi, f"{loss:.2f}"])
                            f.flush()
                            
                        now = datetime.datetime.now().strftime("%H:%M:%S")
                        self.rx_out.write(f"{now} | {mode_tag} | ID:{pkt_id} | SNR:{snr} | RSSI:{rssi} | Loss:{loss:.2f}%\n")
                elif "+RCV_ERR: CRC Error!" in line:
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    self.rx_out.write(f"{now} | [WARNING] CRC Error detected!\n")
                    if f and csv_writer and current_uuid:
                        iso = datetime.datetime.now().isoformat()
                        csv_writer.writerow([iso, "CRC_ERR", "N/A", current_uuid, "N/A", "N/A", "N/A"])
                        f.flush()
                else:
                    self.rx_out.write(f"{line}\n")
            except Exception as e:
                break
        if f:
            f.close()

    # --- ANALYSIS TAB ---
    def create_analysis_tab(self):
        frame = ttk.Frame(self.tab_analysis, padding=10)
        frame.pack(fill='both', expand=True)
        
        ctrl = ttk.LabelFrame(frame, text="Log Selection", padding=10)
        ctrl.pack(fill='x', pady=5)
        
        self.log_cb = ttk.Combobox(ctrl, width=50)
        self.log_cb.grid(row=0, column=0, padx=5)
        ttk.Button(ctrl, text="Refresh Logs", command=self.refresh_logs).grid(row=0, column=1, padx=5)
        ttk.Button(ctrl, text="Analyze", command=self.analyze_selected_log).grid(row=0, column=2, padx=5)
        
        self.analysis_console = scrolledtext.ScrolledText(frame, height=20, bg='white', fg='black', font=('Consolas', 11))
        self.analysis_console.pack(fill='both', expand=True, pady=5)
        
        self.refresh_logs()

    def refresh_logs(self):
        if not os.path.exists('logs'):
            os.makedirs('logs')
        files = [f for f in os.listdir('logs') if f.endswith('.csv')]
        self.log_cb['values'] = files
        if files:
            self.log_cb.current(0)

    def analyze_selected_log(self):
        sel = self.log_cb.get()
        if not sel:
            return
        
        filepath = os.path.join('logs', sel)
        self.analysis_console.delete('1.0', tk.END)
        self.analysis_console.insert(tk.END, f"Analyzing {sel}...\n\n")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                packet_ids = set()
                snr_list = []
                rssi_list = []
                crc_errors = 0
                
                for row in reader:
                    if row.get('Mode') == 'CRC_ERR':
                        crc_errors += 1
                        continue
                    if 'PacketID' in row:
                        try: packet_ids.add(int(row['PacketID']))
                        except: pass
                    if 'SNR_dB' in row and row['SNR_dB'] != 'N/A':
                        try: snr_list.append(float(row['SNR_dB']))
                        except: pass
                    if 'RSSI_dBm' in row and row['RSSI_dBm'] != 'N/A':
                        try: rssi_list.append(float(row['RSSI_dBm']))
                        except: pass
                        
                if not packet_ids:
                    self.analysis_console.insert(tk.END, "No valid Packet IDs found.\n")
                    return
                    
                max_id = max(packet_ids)
                total_expected = max_id + 1
                total_received = len(packet_ids)
                lost_count = total_expected - total_received
                missed = lost_count - crc_errors if lost_count >= crc_errors else 0
                loss_rate = (lost_count / total_expected * 100) if total_expected > 0 else 0
                
                avg_snr = sum(snr_list)/len(snr_list) if snr_list else 0
                avg_rssi = sum(rssi_list)/len(rssi_list) if rssi_list else 0
                
                rep = (
                    "========================================\n"
                    "          ANALYSIS REPORT\n"
                    "========================================\n"
                    f"  Total Expected Packets : {total_expected}\n"
                    f"  Valid Received Packets : {total_received}\n"
                    f"  CRC Error Packets      : {crc_errors}\n"
                    f"  Completely Missed      : {missed}\n"
                    f"  Total Lost Packets     : {lost_count}\n"
                    f"  Packet Loss Rate       : {loss_rate:.2f} %\n"
                    "----------------------------------------\n"
                    f"  Average SNR            : {avg_snr:.2f} dB\n"
                    f"  Average RSSI           : {avg_rssi:.2f} dBm\n"
                    "========================================\n"
                )
                self.analysis_console.insert(tk.END, rep)
        except Exception as e:
            self.analysis_console.insert(tk.END, f"Error: {e}\n")

if __name__ == "__main__":
    app = RfTestManagerGUI()
    app.mainloop()
