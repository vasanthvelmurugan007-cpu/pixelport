import customtkinter as ctk
import socket
import psutil
import threading
from werkzeug.serving import make_server
from flask import Flask, Response, render_template_string
import mss
import cv2
import numpy as np
import time
import os

app = Flask(__name__)
is_sharing = False
flask_server = None

def get_ips():
    ips = []
    primary_ip = None
    try:
        # Connect to a dummy external IP to find the primary routable interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Doesn't have to be reachable
        s.connect(('10.254.254.254', 1)) 
        primary_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    try:
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                    if snic.address == primary_ip:
                        ips.insert(0, (f"{interface} (⭐ Primary)", snic.address))
                    else:
                        ips.append((interface, snic.address))
    except Exception as e:
        if primary_ip:
            ips.append(("Primary Network", primary_ip))
            
    # Remove duplicates while preserving order
    seen = set()
    return [(iface, ip) for iface, ip in ips if not (ip in seen or seen.add(ip))]

def generate_frames():
    with mss.mss() as sct:
        try:
            # Use the primary monitor or explicitly check available monitors
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        except Exception:
            monitor = {"top": 0, "left": 0, "width": 1920, "height": 1080} # Fallback

        while is_sharing:
            try:
                img = sct.grab(monitor)
                frame = np.array(img)[:, :, :3]
                # Dynamic quality for speed
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(0.04) # approx 25fps logic limit
            except Exception as e:
                time.sleep(1)

@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PixelPort - Live Screen View</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700&display=swap" rel="stylesheet">
        <style>
          body { margin: 0; background: linear-gradient(135deg, #0f172a, #1e1b4b); display: flex; justify-content: center; align-items: center; height: 100vh; font-family: 'Outfit', sans-serif; color: white; overflow: hidden; }
          .container { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; height: 100%; }
          .video-container { width: 95%; max-width: 1600px; height: 85vh; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 50px rgba(0,0,0,0.6); border: 2px solid rgba(255, 255, 255, 0.1); background: #000; display: flex; justify-content: center; align-items: center; position: relative;}
          img { max-width: 100%; max-height: 100%; object-fit: contain; }
          .header { height: 10vh; display: flex; justify-content: space-between; align-items: center; width: 95%; max-width: 1600px; }
          .title { font-size: 2rem; font-weight: 700; background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
          .status { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #10b981; padding: 8px 16px; border-radius: 30px; font-weight: 600; display: flex; align-items: center; gap: 8px; box-shadow: 0 0 15px rgba(16,185,129,0.3);}
          .dot { width: 10px; height: 10px; background-color: #10b981; border-radius: 50%; box-shadow: 0 0 10px #10b981; animation: blink 1.5s infinite;}
          @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; }}
          #errorMsg { position: absolute; font-size: 1.5rem; color: #94a3b8; display: none; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <div class="title">PixelPort.</div>
            <div class="status"><div class="dot"></div>Live Stream</div>
          </div>
          <div class="video-container">
            <div id="errorMsg">Waiting for stream...</div>
            <img src="/video_feed" id="vid" onerror="document.getElementById('errorMsg').style.display='block'; this.style.display='none';" onload="document.getElementById('errorMsg').style.display='none'; this.style.display='block';" alt=""/>
          </div>
        </div>
        <script>
            // Auto reconnect on drop
            setInterval(() => {
                let vid = document.getElementById('vid');
                if (vid.style.display === 'none') {
                    vid.src = "/video_feed?" + new Date().getTime();
                }
            }, 5000);
        </script>
      </body>
    </html>
    ''')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

class ServerThread(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        try:
             # Using port 5001 to avoid conflict with previous script
             self.server = make_server('0.0.0.0', 5001, app, threaded=True)
        except OSError:
             self.server = make_server('0.0.0.0', 5002, app, threaded=True)
        self.port = self.server.port
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

class PixelPortApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("PixelPort - Premium Screen Share")
        self.geometry("700x550")
        
        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # UI layout
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(40, 10), fill="x", padx=40)
        
        self.title_label = ctk.CTkLabel(self.header_frame, text="PixelPort", font=ctk.CTkFont(family="Outfit", size=36, weight="bold"), text_color="#38bdf8")
        self.title_label.pack(side="left")
        
        self.status_frame = ctk.CTkFrame(self.header_frame, fg_color="#1e293b", corner_radius=20, border_width=1, border_color="#334155")
        self.status_frame.pack(side="right", ipady=5, ipadx=10)
        
        self.status_indicator = ctk.CTkLabel(self.status_frame, text="●", text_color="#ef4444", font=ctk.CTkFont(size=20))
        self.status_indicator.pack(side="left", padx=(10, 5))
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="STOPPED", text_color="#e2e8f0", font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.pack(side="left", padx=(0, 10))
        
        # Tagline
        self.tagline = ctk.CTkLabel(self, text="Real-time screen casting over mobile hotspot.", text_color="#94a3b8", font=ctk.CTkFont(size=14))
        self.tagline.pack(pady=(0, 20), anchor="w", padx=40)
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=20, fill="x", padx=40)
        
        self.start_btn = ctk.CTkButton(self.btn_frame, text="▶ Start Casting", command=self.start_sharing, 
                                       fg_color="#38bdf8", hover_color="#0284c7", text_color="white",
                                       font=ctk.CTkFont(size=16, weight="bold"), height=50, corner_radius=25)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        self.stop_btn = ctk.CTkButton(self.btn_frame, text="◼ Stop", command=self.stop_sharing, 
                                      fg_color="#334155", hover_color="#1e293b", text_color="#94a3b8", state="disabled",
                                      font=ctk.CTkFont(size=16, weight="bold"), height=50, corner_radius=25, border_width=1, border_color="#475569")
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(10, 0))
        
        # Instructions
        self.info_frame = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=15)
        self.info_frame.pack(pady=20, fill="both", expand=True, padx=40)
        
        self.info_label = ctk.CTkLabel(self.info_frame, text="Viewer Access Links:", text_color="#cbd5e1", font=ctk.CTkFont(size=16, weight="bold"))
        self.info_label.pack(pady=(15, 5), anchor="w", padx=20)
        
        self.urls_textbox = ctk.CTkTextbox(self.info_frame, fg_color="#0f172a", text_color="#a5b4fc", font=ctk.CTkFont(family="Consolas", size=14), corner_radius=10, border_width=1, border_color="#312e81")
        self.urls_textbox.pack(pady=(5, 15), padx=20, fill="both", expand=True)
        
        self.populate_ips(5001)
        
        # Handlers
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def populate_ips(self, port=5001):
        ips = get_ips()
        self.urls_textbox.configure(state="normal")
        self.urls_textbox.delete("1.0", ctk.END)
        current_text = ""
        if not ips:
            current_text = "⚠️ No network connections found.\nPlease connect to Wi-Fi or turn on Mobile Hotspot.\n"
        else:
            current_text += "❗ Important: Ensure both devices are on the same Wi-Fi.\n"
            current_text += "If viewer can't connect, set Wi-Fi network profile to 'Private'.\n\n"
            for interface, ip in ips:
                if "Loopback" not in interface and "Virtual" not in interface:
                    current_text += f"> {interface}\n  http://{ip}:{port}\n\n"
        
        self.urls_textbox.insert(ctk.END, current_text)
        self.urls_textbox.configure(state="disabled")

    def start_sharing(self):
        global is_sharing, flask_server
        is_sharing = True
        
        flask_server = ServerThread(app)
        flask_server.start()
        
        self.status_indicator.configure(text_color="#10b981") # Green
        self.status_label.configure(text="LIVE NOW")
        self.status_frame.configure(border_color="#10b981")
        
        self.start_btn.configure(state="disabled", fg_color="#334155", text_color="#94a3b8")
        self.stop_btn.configure(state="normal", fg_color="#ef4444", text_color="white", hover_color="#b91c1c", border_color="#ef4444")
        self.populate_ips(flask_server.port)

    def stop_sharing(self):
        global is_sharing, flask_server
        is_sharing = False
        if flask_server is not None:
            flask_server.shutdown()
            flask_server = None
            
        self.status_indicator.configure(text_color="#ef4444") # Red
        self.status_label.configure(text="STOPPED")
        self.status_frame.configure(border_color="#334155")
        
        self.start_btn.configure(state="normal", fg_color="#38bdf8", text_color="white")
        self.stop_btn.configure(state="disabled", fg_color="#334155", text_color="#94a3b8", border_color="#475569")

    def on_closing(self):
        self.stop_sharing()
        self.destroy()
        os._exit(0)

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app_ui = PixelPortApp()
    app_ui.mainloop()
