from flask import Flask, render_template, request, Response
import os
import io
import subprocess
import pythoncom
import mss
import pyautogui
import win32gui
import win32con
import win32api
import win32com.client
from PIL import Image
import pygetwindow as gw
from ctypes import cast, POINTER, windll

# --- THE MISSING AUDIO IMPORTS ---
import comtypes
import comtypes.client
from comtypes import CLSCTX_ALL
from pycaw.constants import CLSID_MMDeviceEnumerator
from pycaw.pycaw import IMMDeviceEnumerator, IAudioEndpointVolume
import threading
import queue
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # <--- ADD THIS IMPORT

app = Flask(__name__)
CORS(app)  # <--- ADD THIS LINE RIGHT AFTER 'app = Flask'

# --- DPI AWARENESS ---
try:
    windll.user32.SetProcessDpiAwarenessContext(-4)
except Exception:
    try:
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        windll.user32.SetProcessDPIAware()

pyautogui.FAILSAFE = False


# --- MONITOR CONFIG ---
MONITOR_MAP = { 1: 2, 2: 1 }

# --- HELPERS ---

# 1. This route simply opens the new power page
@app.route('/power')
def power_page():
    return render_template('power.html')

# 2. This route is the "trigger" that actually turns off the PC
@app.route('/turnoff', methods=['POST'])
def shutdown():
    import os
    os.system("shutdown /s /t 1")
    return "OK", 200

@app.route('/audio')
def audio_menu():
    output_devices = []
    try:
        # Use -ExpandProperty Name to get a clean list of strings from PowerShell
        cmd = 'powershell -Command "Get-AudioDevice -List | Where-Object { $_.Type -eq \'Playback\' } | Select-Object -ExpandProperty Name"'
        
        # We use capture_output so we can see exactly what PowerShell is complaining about
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Split the output into lines and remove empty ones
            names = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            for name in names:
                output_devices.append({"name": name})
        else:
            # This will print the actual PowerShell error to your VS Code terminal
            print(f"PS Error: {result.stderr}")
            
    except Exception as e:
        print(f"Python Error: {e}")
        
    print(f"Found via PowerShell: {output_devices}")
    return render_template('audio.html', devices=output_devices)

@app.route('/set_audio', methods=['POST'])
def set_audio():
    device_name = request.form.get('device_name')
    # PowerShell command to set the default audio device by name
    # Using the wildcard * helps match the name more reliably
    cmd = f'powershell -Command "Get-AudioDevice -List | Where-Object {{ $_.Name -like \'{device_name}*\' }} | Set-AudioDevice"'
    subprocess.run(cmd, shell=True)
    return "OK"

# Create the traffic light to prevent simultaneous hardware access
audio_lock = threading.Lock()

# Creates a thread-safe "bucket" where Flask can drop volume numbers
volume_queue = queue.Queue()

def audio_worker():
    # Grants this permanent background thread permission to use Windows COM
    pythoncom.CoInitialize()
    
    try:
        # Connects to the raw Windows hardware enumerator
        enumerator = comtypes.client.CreateObject(
            CLSID_MMDeviceEnumerator, 
            interface=IMMDeviceEnumerator
        )
        
        # Grabs the specific endpoint for your main speakers
        endpoint = enumerator.GetDefaultAudioEndpoint(0, 1)
        
        # Activates the API connection to those speakers
        interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        
        # Casts the connection into a usable Python pointer
        volume_control = cast(interface, POINTER(IAudioEndpointVolume))
        
        print("DEBUG: Dedicated Audio Worker is online and holding the connection.")
        
        # Starts an infinite loop that keeps this thread alive forever
        while True:
            # Pauses the loop and waits peacefully until a number is dropped in the bucket
            # 'block=True' ensures it uses 0% CPU while waiting
            val = volume_queue.get(block=True)
            
            # Instantly changes the hardware volume using the permanently open connection
            volume_control.SetMasterVolumeLevelScalar(val, None)
            
            print(f"DEBUG: Worker applied volume: {val}")
            
    except Exception as e:
        # Catches any catastrophic hardware disconnects (like unplugging your speakers)
        print(f"DEBUG CRITICAL: Worker thread died: {e}")
        
    finally:
        # Closes the connection only if the script is completely shut down
        pythoncom.CoUninitialize()

# Spawns the permanent worker thread in the background the moment the script starts
# 'daemon=True' ensures this thread dies cleanly when you close the main Flask app
worker_thread = threading.Thread(target=audio_worker, daemon=True)
worker_thread.start()


@app.route('/set_volume', methods=['POST'])
def set_volume():
    # Retrieves the incoming number from your phone
    vol_level = request.form.get('volume')
    
    # Checks to make sure the phone didn't send blank data
    if vol_level is not None:
        # Converts the 0-100 number into a 0.0-1.0 decimal
        val = float(vol_level) / 100.0
        
        # Drops the decimal into the bucket for the audio_worker to pick up instantly
        # This route now finishes in less than 1 millisecond, preventing all crashes
        volume_queue.put(val)
        
    # Sends a success signal back to the phone
    return "OK", 204

def force_focus(hwnd):
    pythoncom.CoInitialize()
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%') 
        win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Focus Error: {e}")
    finally:
        pythoncom.CoUninitialize()

def get_volume_control():
    pythoncom.CoInitialize()
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        devices = enumerator.GetDefaultAudioEndpoint(0, 1)
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        print(f"Audio Hardware Error: {e}")
        return None

def get_open_windows():
    # --- THE BLACKLIST ---
    BLACKLIST = [
        "program manager",
        "windows input experience",
        "nvidia geforce overlay",
        "app center",
        "microsoft text input application",
        "task scheduler"
    ]

    def callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            full_title = win32gui.GetWindowText(hwnd)
            if full_title:
                is_junk = any(bad_word in full_title.lower() for bad_word in BLACKLIST)
                if not is_junk:
                    # Clean the title: Split by " - " and grab the very last element
                    short_title = full_title.split(" - ")[-1].strip()
                    windows.append({"hwnd": hwnd, "title": short_title})
                    
    window_list = []
    win32gui.EnumWindows(callback, window_list)
    # Sort alphabetically by the clean name
    return sorted(window_list, key=lambda x: x['title'].lower())

# --- ROUTES ---

@app.route('/')
def home():
    current_vol = 50
    vc = get_volume_control()
    if vc:
        try:
            current_vol = int(vc.GetMasterVolumeLevelScalar() * 100)
        except: pass
        finally: pythoncom.CoUninitialize()
    return render_template('index.html', current_vol=current_vol)

@app.route('/windows')
def windows_menu():
    apps = get_open_windows()
    return render_template('windows.html', apps=apps)

@app.route('/move_window', methods=['POST'])
def move_window():
    hwnd = int(request.form.get('hwnd'))
    monitor_label = int(request.form.get('monitor_id'))
    layout = request.form.get('layout', 'move') 
    physical_id = MONITOR_MAP.get(monitor_label)

    with mss.mss() as sct:
        mon = sct.monitors[physical_id]
        m_left, m_top = mon["left"], mon["top"]
        m_width, m_height = mon["width"], mon["height"]

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        if layout == 'full':
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, m_left, m_top, m_width, m_height, 0)
        elif layout == 'left':
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, m_left, m_top, m_width // 2, m_height, 0)
        elif layout == 'right':
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, m_left + (m_width // 2), m_top, m_width // 2, m_height, 0)
        else:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, m_left, m_top, 0, 0, 0x0001)
        
        force_focus(hwnd)
    return '', 204

@app.route('/display/<int:monitor_id>')
def monitor_view(monitor_id):
    return render_template('display/monitor.html', monitor_id=monitor_id)

@app.route('/screenshot/<int:monitor_id>')
def screenshot(monitor_id):
    physical_id = MONITOR_MAP.get(monitor_id, monitor_id)
    with mss.mss() as sct:
        sct_img = sct.grab(sct.monitors[physical_id])
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=30) 
        return Response(img_byte_arr.getvalue(), mimetype='image/jpeg')

@app.route('/mouse_action', methods=['POST'])
def mouse_action():
    monitor_id = int(request.form.get('monitor_id'))
    physical_id = MONITOR_MAP.get(monitor_id, monitor_id)
    rx, ry = float(request.form.get('x')), float(request.form.get('y'))
    action = request.form.get('action', 'move')
    with mss.mss() as sct:
        mon = sct.monitors[physical_id]
        target_x = mon["left"] + int(rx * mon["width"])
        target_y = mon["top"] + int(ry * mon["height"])
        if action == 'click': pyautogui.click(target_x, target_y)
        else: pyautogui.moveTo(target_x, target_y, _pause=False)
    return '', 204

@app.route('/media_control', methods=['POST'])
def media_control():
    command = request.form.get('command')
    print(f"DEBUG: Media Command Received -> {command}")
    if command:
        pyautogui.press(command)
    return "OK", 204

@app.route('/type_text', methods=['POST'])
def type_text():
    text = request.form.get('text')
    print(f"DEBUG: Typing Text -> {text}")
    if text:
        pyautogui.write(text, interval=0.01)
    return "OK", 204

@app.route('/key_press', methods=['POST'])
def key_press():
    key = request.form.get('key')
    print(f"DEBUG: Key Pressed -> {key}")
    if key:
        pyautogui.press(key)
    return "OK", 204

def is_alt_tab_window(hwnd):
    """Checks if a window is a 'real' app that should appear in Alt+Tab."""
    if not win32gui.IsWindowVisible(hwnd):
        return False
    
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return False
        
    # Corrected: win32con holds the GWL_EXSTYLE attribute
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    
    # 0x00000080 is WS_EX_TOOLWINDOW (hides it from taskbar/alt-tab)
    if ex_style & 0x00000080: 
        return False
        
    return True

pyautogui.PAUSE = 0
pyautogui.MINIMUM_DURATION = 0

@app.route('/remote_input')
def remote_input_page():
    return render_template('input.html')

@app.route('/mouse_move', methods=['POST'])
def remote_live_move():
    # dx/dy are sent as dampened parabolic floats from JS
    dx = int(float(request.form.get('x', 0)))
    dy = int(float(request.form.get('y', 0)))
    
    if dx != 0 or dy != 0:
        # Direct Windows API call for instant responses
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy, 0, 0)
    return "OK", 204

@app.route('/live_type', methods=['POST'])
def remote_live_type():
    key = request.form.get('key')
    if key == "BACKSPACE":
        pyautogui.press('backspace')
    elif key == "ENTER":
        pyautogui.press('enter')
    elif key:
        pyautogui.write(key)
    return "OK", 204

# 3. The button strike logic
@app.route('/input_command', methods=['POST'])
def input_command():
    cmd = request.form.get('command')
    # Executes the hardware key strike based on the button pressed
    if cmd == 'left_click': pyautogui.click()
    elif cmd == 'right_click': pyautogui.rightClick()
    elif cmd == 'backspace': pyautogui.press('backspace')
    elif cmd == 'enter': pyautogui.press('enter')
    return "OK", 204

# 1. Define your apps and their exact executable paths
# NOTE: Using the 'r' before the string handles the backslashes correctly in Windows paths
CONTROL_APPS = {
    "Chrome": {
        "path": r"C:\Users\blake\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk",
        "keyword": "chrome"
    },
    "YouTube": {
        "path": r"C:\Users\blake\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Chrome Apps\YouTube.lnk",
        "keyword": "youtube"
    },
    "Spotify": {
        "path": "spotify:",  # This tells Windows to just 'open Spotify'
        "keyword": "spotify"
    },
    "Overcooked": {
        "path": r"C:\Users\blake\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Steam\Overcooked! 2.url",
        "keyword": "overcooked"
    }
}

@app.route('/applications')
def applications_manager():
    all_windows = gw.getAllWindows()
    apps_to_display = []

    for name, config in CONTROL_APPS.items():
        app_data = {
            'name': name,
            'path': config['path'],
            'hwnd': None,
            'is_open': False
        }

        # Search for the window
        for w in all_windows:
            # We check if the keyword is in the title AND ensure the title isn't empty
            if config['keyword'].lower() in w.title.lower() and w.title.strip() != "":
                app_data['hwnd'] = w._hWnd
                app_data['is_open'] = True
                app_data['title'] = w.title
                break # Found it, move to the next app in CONTROL_APPS
        
        apps_to_display.append(app_data)

    return render_template('applications.html', apps=apps_to_display)

@app.route('/launch_app', methods=['POST'])
def launch_app():
    app_path = request.form.get('path')
    
    if app_path:
        try:
            # os.startfile is smart. 
            # If it's a path, it opens the file.
            # If it's 'spotify:', it launches the Store app.
            os.startfile(app_path)
            return "OK", 200
        except Exception as e:
            print(f"DEBUG CRITICAL: Launch error: {e}")
            return str(e), 500
            
    return "Invalid Path", 400

# Global memory bank
latest_youtube_data = {"title": "No Media", "channel": "", "url": ""}
sync_back_requested = False

@app.route('/youtube') 
def youtube_page(): 
    return render_template('youtube.html') 

# --- 1. THE CATCHER (Listens for PC data) ---
@app.route('/youtube/update', methods=['POST'])
def update_youtube():
    global latest_youtube_data
    latest_youtube_data = request.json 
    return {"status": "success"}, 200

# --- 2. THE DASHBOARD ROUTE (Sends data to phone) ---
@app.route('/youtube/pull', methods=['GET'])
def pull_youtube():
    return jsonify(latest_youtube_data), 200

# --- 3. THE SYNC TRIGGER (Called by the new button) ---
@app.route('/youtube/sync_back', methods=['POST'])
def sync_back_trigger():
    global sync_back_requested
    sync_back_requested = True
    return {"status": "triggered"}, 200

# --- 4. THE COMMAND CHECK (Called by Chrome Extension) ---
@app.route('/youtube/check_sync', methods=['GET'])
def check_sync():
    global sync_back_requested
    if sync_back_requested:
        sync_back_requested = False # Reset immediately
        return {"sync": True}, 200
    return {"sync": False}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)