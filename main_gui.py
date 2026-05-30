import sys
import os
import traceback
from datetime import datetime
import asyncio
import json
import struct
import socket
import threading
from hashlib import sha1

#
# ---------------- LOGGING SETUP ----------------
#
LOG_FILE_PATH = "kiwi_crash_log.txt"
if "ANDROID_ARGUMENT" in os.environ:
    LOG_FILE_PATH = "/storage/emulated/0/Download/kiwi_crash_log.txt"

def log_lifecycle(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"!!! COULD NOT WRITE TO LOG FILE: {e}")

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_lifecycle("\n" + "="*30)
    log_lifecycle("FATAL CRASH DETECTED")
    log_lifecycle(error_msg)
    log_lifecycle("="*30 + "\n")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = handle_exception

#
# ---------------- IMPORTS ----------------
#
try:
    log_lifecycle("Importing Kivy Config...")
    from kivy.config import Config
    Config.set('graphics', 'width', '400') # Mobile width simulation
    Config.set('graphics', 'height', '700')
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

    log_lifecycle("Importing Kivy UI Elements...")
    from kivy.app import App
    from kivy.lang import Builder
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.recycleview import RecycleView
    from kivy.uix.recycleview.views import RecycleDataViewBehavior
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.progressbar import ProgressBar
    from kivy.properties import StringProperty, NumericProperty, ObjectProperty, ListProperty, BooleanProperty
    from kivy.clock import Clock, mainthread
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput
    from kivy.utils import get_color_from_hex, platform
    log_lifecycle("Kivy Imported Successfully")

except Exception as e:
    log_lifecycle(f"❌ CRASH DURING IMPORTS: {e}")
    raise e

#
# ---------------- ASYNCIO PATCHES ----------------
#
if not getattr(asyncio.gather, "_is_patched", False):
    _original_gather = asyncio.gather
    def _patched_gather(*args, **kwargs):
        kwargs.pop('loop', None)
        return _original_gather(*args, **kwargs)
    _patched_gather._is_patched = True
    asyncio.gather = _patched_gather

if not getattr(asyncio.wait_for, "_is_patched", False):
    _original_wait_for = asyncio.wait_for
    def _patched_wait_for(fut, timeout, **kwargs):
        kwargs.pop('loop', None)
        return _original_wait_for(fut, timeout, **kwargs)
    _patched_wait_for._is_patched = True
    asyncio.wait_for = _patched_wait_for

class SafeQueue(asyncio.Queue):
    def __init__(self, *args, **kwargs):
        kwargs.pop('loop', None)
        super().__init__(*args, **kwargs)
asyncio.Queue = SafeQueue

#
# ---------------- DHT IMPORT ----------------
#
try:
    from aiobtdht import DHT
except ImportError as e:
    log_lifecycle("⚠️ aiobtdht not found. DHT features will be disabled.")
    DHT = None

#
# ---------------- KV LAYOUT ----------------
#
KV_CODE = '''
#:import get_color_from_hex kivy.utils.get_color_from_hex

<CommonButton@Button>:
    background_normal: ''
    background_color: get_color_from_hex('#444488')
    font_size: dp(14)
    bold: True

<TorrentRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(60)
    padding: dp(5)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: get_color_from_hex('#2b2b2b') if self.index % 2 == 0 else get_color_from_hex('#333333')
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        size_hint_x: 0.6
        Label:
            text: root.name
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            bold: True
            font_size: dp(14)
            shorten: True
        Label:
            text: root.status
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            color: get_color_from_hex('#aaaaaa')
            font_size: dp(12)

    BoxLayout:
        size_hint_x: 0.4
        orientation: 'vertical'
        valign: 'center'
        Label:
            text: "{:.1f}%".format(root.progress)
            font_size: dp(12)
            size_hint_y: 0.4
        ProgressBar:
            value: root.progress
            max: 100
            size_hint_y: 0.2

<NearbyPeerRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(60)
    padding: dp(10)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: get_color_from_hex('#252525')
        Rectangle:
            pos: self.pos
            size: self.size
    
    BoxLayout:
        orientation: 'vertical'
        Label:
            text: root.peer_name
            bold: True
            font_size: dp(16)
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        Label:
            text: root.ip_addr
            color: get_color_from_hex('#888888')
            font_size: dp(12)
            text_size: self.size
            halign: 'left'
            valign: 'middle'
    
    CommonButton:
        text: "Connect"
        size_hint_x: None
        width: dp(80)
        on_release: root.connect_callback(root.ip_addr)

<PeerFileRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(50)
    padding: dp(5)
    
    # We add these properties to track where the file comes from
    peer_host: ""
    peer_port: 0
    
    CommonButton:
        text: root.text
        # Pass host and port to the callback so we know who to download from
        on_release: root.select_callback(root.torrent_id, root.text, root.peer_host, root.peer_port)

# --- POPUPS ---

<PeerFileListPopup>:
    title: "Files Available at Peer"
    size_hint: 0.9, 0.8
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(10)
        
        TextInput:
            id: search_input
            hint_text: "Search files..."
            size_hint_y: None
            height: dp(40)
            multiline: False
            on_text: root.filter_data(self.text)

        RecycleView:
            id: rv_peer_files
            viewclass: 'PeerFileRow'
            RecycleBoxLayout:
                default_size: None, dp(50)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                spacing: dp(5)
        
        CommonButton:
            text: "Close"
            size_hint_y: None
            height: dp(48)
            background_color: get_color_from_hex('#aa4444')
            on_release: root.dismiss()

<NearbyPopup>:
    title: "Nearby Network Files"
    size_hint: 0.9, 0.8
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(10)
        
        Label:
            id: status_label
            text: "Scanning nearby peers for files..."
            size_hint_y: None
            height: dp(30)
            color: get_color_from_hex('#00ffff')
        
        # SEARCH BAR FOR NEARBY FILES
        TextInput:
            id: nearby_search
            hint_text: "Search network files..."
            size_hint_y: None
            height: dp(40)
            multiline: False
            background_color: get_color_from_hex('#333333')
            foreground_color: get_color_from_hex('#ffffff')
            on_text: root.filter_data(self.text)

        RecycleView:
            id: rv_nearby_files
            viewclass: 'PeerFileRow'
            RecycleBoxLayout:
                default_size: None, dp(50)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                spacing: dp(5)
        
        CommonButton:
            text: "Close"
            size_hint_y: None
            height: dp(48)
            background_color: get_color_from_hex('#aa4444')
            on_release: root.dismiss()

<DirectConnectPopup>:
    title: "Direct Connect"
    size_hint: 0.85, 0.35
    BoxLayout:
        orientation: 'vertical'
        padding: dp(15)
        spacing: dp(15)
        TextInput:
            id: manual_ip
            hint_text: "Enter IP:PORT (e.g., 192.168.1.5:6881)"
            multiline: False
            size_hint_y: None
            height: dp(48)
        BoxLayout:
            spacing: dp(10)
            CommonButton:
                text: "Cancel"
                background_color: get_color_from_hex('#555555')
                on_release: root.dismiss()
            CommonButton:
                text: "Connect"
                background_color: get_color_from_hex('#44aa44')
                on_release: root.do_connect(manual_ip.text)

<AddTorrentPopup>:
    title: "Download from DHT ID"
    size_hint: 0.85, 0.35
    BoxLayout:
        orientation: 'vertical'
        padding: dp(15)
        spacing: dp(15)
        TextInput:
            id: t_id_input
            hint_text: "Paste Torrent ID Hash"
            multiline: False
            size_hint_y: None
            height: dp(48)
        BoxLayout:
            spacing: dp(10)
            CommonButton:
                text: "Cancel"
                background_color: get_color_from_hex('#555555')
                on_release: root.dismiss()
            CommonButton:
                text: "Download"
                background_color: get_color_from_hex('#44aa44')
                on_release: root.download(t_id_input.text)

<FileLoadDialog>:
    title: "Select File to Seed"
    size_hint: 0.95, 0.95
    BoxLayout:
        orientation: "vertical"
        FileChooserListView:
            id: filechooser
            path: "/storage/emulated/0" if app.is_android() else "."
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(10)
            padding: dp(5)
            CommonButton:
                text: "Cancel"
                background_color: get_color_from_hex('#555555')
                on_release: root.dismiss()
            CommonButton:
                text: "Select"
                background_color: get_color_from_hex('#44aa44')
                on_release: root.load(filechooser.path, filechooser.selection)

<PieceSizePopup>:
    title: "Set Piece Size"
    size_hint: 0.8, 0.3
    BoxLayout:
        orientation: "vertical"
        padding: dp(10)
        spacing: dp(10)
        TextInput:
            id: p_size
            text: "262144"
            hint_text: "Bytes"
            multiline: False
            size_hint_y: None
            height: dp(40)
        BoxLayout:
            spacing: dp(10)
            CommonButton:
                text: "Cancel"
                background_color: get_color_from_hex('#555555')
                on_release: root.dismiss()
            CommonButton:
                text: "Create"
                on_release: root.confirm(p_size.text)

# --- MAIN WINDOW ---

<MainWindow>:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: get_color_from_hex('#1e1e1e')
        Rectangle:
            pos: self.pos
            size: self.size

    # HEADER / STATUS
    BoxLayout:
        size_hint_y: None
        height: dp(30)
        canvas.before:
            Color:
                rgba: get_color_from_hex('#003366') 
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            id: ip_status
            text: "Initializing..."
            color: get_color_from_hex('#00ffff')
            bold: True
            font_size: dp(12)

    # TOOLBAR (Scalable for Mobile)
    BoxLayout:
        size_hint_y: None
        height: dp(60) 
        padding: dp(5)
        spacing: dp(5)
        canvas.before:
            Color:
                rgba: get_color_from_hex('#3c3f41')
            Rectangle:
                pos: self.pos
                size: self.size
        
        Label:
            text: "🥝"
            font_size: dp(24)
            size_hint_x: None
            width: dp(40)

        # Action Buttons
        CommonButton:
            text: "DHT DL"
            on_release: root.show_add_popup()
        
        CommonButton:
            text: "Seed"
            background_color: get_color_from_hex('#8844aa') 
            on_release: app.show_file_chooser()

        CommonButton:
            text: "Direct"
            background_color: get_color_from_hex('#aa8844')
            on_release: root.show_direct_popup()

        CommonButton:
            text: "Nearby"
            background_color: get_color_from_hex('#44aa88')
            on_release: root.show_nearby_popup()

    # LIST HEADER
    BoxLayout:
        size_hint_y: None
        height: dp(30)
        padding: dp(5)
        canvas.before:
            Color:
                rgba: get_color_from_hex('#111111')
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            text: "Name / Status"
            size_hint_x: 0.6
            bold: True
            halign: 'left'
            text_size: self.size
        Label:
            text: "Progress"
            size_hint_x: 0.4
            bold: True

    # TORRENT LIST
    RecycleView:
        id: rv
        viewclass: 'TorrentRow'
        scroll_type: ['bars', 'content']
        bar_width: dp(10)
        RecycleBoxLayout:
            default_size: None, dp(60)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: 'vertical'
            spacing: dp(2)

    # LOG WINDOW
    BoxLayout:
        orientation: 'vertical'
        size_hint_y: 0.2
        canvas.before:
            Color:
                rgba: get_color_from_hex('#000000')
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            text: "System Log"
            size_hint_y: None
            height: dp(20)
            font_size: dp(10)
            color: get_color_from_hex('#888888')
        TextInput:
            id: console_log
            readonly: True
            foreground_color: get_color_from_hex('#00ff00')
            background_color: 0, 0, 0, 0
            font_size: dp(10)
'''

#
# ---------------- NETWORK LOGIC ----------------
#

MSG_LEN = 4
DISCOVERY_PORT = 11223 # port for discovery

def pack_msg(msg_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(msg_type + payload)) + msg_type + payload

async def read_msg(reader):
    try:
        raw_len = await reader.readexactly(MSG_LEN)
    except asyncio.IncompleteReadError:
        return None, None
    (l,) = struct.unpack(">I", raw_len)
    data = await reader.readexactly(l)
    return data[:1], data[1:]

class UDPAdapter(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
        self.subscriber = None
        self.dht = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.subscriber:
            asyncio.create_task(self.subscriber(data, addr))

    def send(self, data, addr):
        if self.transport:
            self.transport.sendto(data, addr)
            
    def subscribe(self, callback):
        self.subscriber = callback

#
# ---------------- LOCAL DISCOVERY (BEACON) ----------------
#
class LocalDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, app_ref):
        self.app = app_ref
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        # Enable broadcast
        sock = transport.get_extra_info('socket')
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        log_lifecycle(f"📡 Discovery Listener STARTED. Listening on 0.0.0.0:{DISCOVERY_PORT}")

    def datagram_received(self, data, addr):
        # Ignore own messages
        local_ip = self.app.get_local_ip()
        if addr[0] == local_ip:
            return
            
        try:
            msg = json.loads(data.decode())
            if msg.get('type') == 'KIWI_BEACON':
                # Notify App to update Nearby List
                self.app.on_beacon_received(addr[0], msg)
        except Exception as e:
            pass

#
# ---------------- UI CLASSES ----------------
# 

class TorrentRow(BoxLayout, RecycleDataViewBehavior):
    index = NumericProperty(0)
    name = StringProperty("Unknown")
    progress = NumericProperty(0.0)
    status = StringProperty("Idle")

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

class NearbyPeerRow(BoxLayout, RecycleDataViewBehavior):
    peer_name = StringProperty("")
    ip_addr = StringProperty("")
    connect_callback = ObjectProperty(None)

    def refresh_view_attrs(self, rv, index, data):
        return super().refresh_view_attrs(rv, index, data)

class PeerFileRow(BoxLayout, RecycleDataViewBehavior):
    text = StringProperty("")
    torrent_id = StringProperty("")
    peer_host = StringProperty("")
    peer_port = NumericProperty(0)
    select_callback = ObjectProperty(None)
    
    def refresh_view_attrs(self, rv, index, data):
        return super().refresh_view_attrs(rv, index, data)

class PeerFileListPopup(Popup):
    raw_files = []
    callback_ref = None

    def set_data(self, files, callback, host, port):
        # Flatten structure: Add host/port to every file dict
        self.raw_files = []
        for f in files:
            f_data = f.copy()
            f_data['peer_host'] = host
            f_data['peer_port'] = port
            self.raw_files.append(f_data)
            
        self.callback_ref = callback
        self.filter_data("")

    def filter_data(self, query):
        data = []
        q = query.lower()
        for f in self.raw_files:
            if q in f['name'].lower():
                data.append({
                    'text': f['name'],
                    'torrent_id': f['torrent_id'],
                    'peer_host': f['peer_host'],
                    'peer_port': f['peer_port'],
                    'select_callback': self.callback_ref
                })
        self.ids.rv_peer_files.data = data

class NearbyPopup(Popup):
    raw_files = []
    
    def set_status(self, text):
        self.ids.status_label.text = text

    def add_files(self, files_list, host, port):
        app = App.get_running_app()
        for f in files_list:
            # Avoid duplicates (simple check by ID)
            if not any(x['torrent_id'] == f['torrent_id'] for x in self.raw_files):
                self.raw_files.append({
                    'name': f['name'],
                    'torrent_id': f['torrent_id'],
                    'peer_host': host,
                    'peer_port': port
                })
        # Refresh view
        self.filter_data(self.ids.nearby_search.text)

    def filter_data(self, query):
        data = []
        q = query.lower()
        app = App.get_running_app()
        
        for f in self.raw_files:
            if q in f['name'].lower():
                data.append({
                    'text': f['name'],
                    'torrent_id': f['torrent_id'],
                    'peer_host': f['peer_host'],
                    'peer_port': int(f['peer_port']),
                    'select_callback': app.on_peer_file_selected
                })
        self.ids.rv_nearby_files.data = data

class DirectConnectPopup(Popup):
    def do_connect(self, ip_str):
        if not ip_str: return
        App.get_running_app().direct_connect_wrapper(ip_str)
        self.dismiss()

class AddTorrentPopup(Popup):
    def download(self, t_id):
        t_id = t_id.strip()
        if t_id:
            app = App.get_running_app()
            app.root.add_log(f"Requesting download for: {t_id}")
            app.add_download_task(t_id)
        self.dismiss()

class FileLoadDialog(Popup):
    load = ObjectProperty(None)

class PieceSizePopup(Popup):
    confirm = ObjectProperty(None)

class MainWindow(BoxLayout):
    def show_add_popup(self):
        AddTorrentPopup().open()
    
    def show_direct_popup(self):
        DirectConnectPopup().open()

    def show_nearby_popup(self):
        p = NearbyPopup()
        App.get_running_app().scan_and_show_nearby_files(p)
        p.open()
    
    def add_log(self, text):
        log_lifecycle(text)
        def _update(dt):
            ts = datetime.now().strftime("%H:%M:%S")
            self.ids.console_log.text += f"[{ts}] {text}\n"
            self.ids.console_log.cursor = (0, 0)
        Clock.schedule_once(_update)

#
# ---------------- MAIN APP ----------------
#

class KiwiTorrentApp(App):
    data_items = ListProperty([])
    found_peers = {}

    def build(self):
        log_lifecycle("Building GUI...")
        Builder.load_string(KV_CODE)
        return MainWindow()

    def is_android(self):
        return platform == 'android'

    def on_start(self):
        log_lifecycle("App Started (on_start)")
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.INTERNET,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.ACCESS_NETWORK_STATE
            ])
            
        asyncio.create_task(self.setup_backend())

    # --- LIST MANAGEMENT ---
    @mainthread
    def update_row(self, t_id, **kwargs):
        new_data = []
        found = False
        for item in self.data_items:
            if item.get('id') == t_id:
                item.update(kwargs)
                found = True
            new_data.append(item)
        
        if not found and 'name' in kwargs:
            item = {'id': t_id}
            item.update(kwargs)
            new_data.append(item)
        
        self.data_items = new_data
        self.root.ids.rv.data = self.data_items
        self.root.ids.rv.refresh_from_data()

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    # --- DISCOVERY LOGIC ---
    def on_beacon_received(self, ip, msg):
        self.found_peers[ip] = {
            'name': msg.get('name', 'Unknown Kiwi'),
            'port': msg.get('port', 6881),
            'last_seen': datetime.now().timestamp()
        }

    async def broadcast_beacon_loop(self):
        log_lifecycle("Starting Beacon Broadcast Loop...")
        while True:
            if self.discovery_transport:
                msg = {
                    'type': 'KIWI_BEACON',
                    'name': f"KiwiUser-{str(self.port)[-2:]}",
                    'port': self.port
                }
                data = json.dumps(msg).encode()
                try:
                    self.discovery_transport.sendto(data, ('<broadcast>', DISCOVERY_PORT))
                except Exception as e:
                    pass
            await asyncio.sleep(3) 

    # --- NEARBY FILE SCAN LOGIC ---
    def scan_and_show_nearby_files(self, popup_instance):
        self._nearby_popup = popup_instance
        asyncio.create_task(self.scan_peers_worker(popup_instance))

    async def scan_peers_worker(self, popup):
        # 1. Get active peers
        current_time = datetime.now().timestamp()
        active_peers = []
        for ip, info in self.found_peers.items():
            if current_time - info['last_seen'] < 15: # 15s timeout
                active_peers.append((ip, info['port']))

        if not active_peers:
            popup.set_status("No nearby peers found.")
            return

        popup.set_status(f"Querying {len(active_peers)} peers...")
        
        # 2. Query all peers concurrently
        tasks = [self.fetch_file_list(ip, port) for ip, port in active_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Populate popup
        found_count = 0
        for res in results:
            if isinstance(res, tuple) and res[0] is not None:
                files, host, port = res
                if files:
                    popup.add_files(files, host, port)
                    found_count += len(files)
        
        popup.set_status(f"Found {found_count} files from {len(active_peers)} peers.")

    async def fetch_file_list(self, host, port):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
            writer.write(pack_msg(b'L', b''))
            await writer.drain()
            
            typ, payload = await read_msg(reader)
            writer.close()
            await writer.wait_closed()
            
            if typ == b'L':
                files = json.loads(payload.decode())
                return files, host, port
        except:
            return None

    # --- SEEDING LOGIC ---
    def show_file_chooser(self):
        FileLoadDialog(load=self.load_file).open()

    def load_file(self, path, selection):
        if hasattr(self.root, '_popup'): self.root._popup.dismiss()
        if selection:
            self.selected_file = selection[0]
            # Save reference to popup
            self._seed_popup = PieceSizePopup(confirm=self.process_seed_file)
            self._seed_popup.open()

    def process_seed_file(self, size_text):
        # Auto-close popup
        if hasattr(self, '_seed_popup') and self._seed_popup:
            self._seed_popup.dismiss()

        try:
            piece_size = int(size_text)
        except ValueError:
            piece_size = 262144 
        threading.Thread(target=self.make_pieces_worker, args=(self.selected_file, piece_size)).start()

    def make_pieces_worker(self, file_path, piece_size):
        try:
            self.root.add_log(f"Hashing: {os.path.basename(file_path)}...")
            base_name = os.path.basename(file_path)
            size = os.path.getsize(file_path)
            torent_id_hasher = sha1()
            pieces = []

            if platform == 'android':
                from android.storage import primary_external_storage_path
                base_dir = os.path.join(primary_external_storage_path(), "Download", "KiwiTorrent")
            else:
                base_dir = "torrents"

            out_dir = os.path.join(base_dir, f"torrent_{base_name}_{size}")
            pieces_dir = os.path.join(out_dir, "pieces")
            os.makedirs(pieces_dir, exist_ok=True)

            with open(file_path, "rb") as f:
                i = 0
                while True:
                    data = f.read(piece_size)
                    if not data: break
                    h = sha1(data).hexdigest()
                    pieces.append(h)
                    torent_id_hasher.update(bytes.fromhex(h))
                    piece_name = os.path.join(pieces_dir, f"piece_{i:06d}.bin")
                    with open(piece_name, "wb") as pf:
                        pf.write(data)
                    i += 1

            torrent_id = torent_id_hasher.hexdigest()
            metadata = {"name": base_name, "length": size, "piece_length": piece_size, "pieces": pieces, "torrent_id": torrent_id}
            
            meta_path = os.path.join(out_dir, "metadata.json")
            with open(meta_path, "w") as m:
                json.dump(metadata, m, indent=2)
            
            self.root.add_log(f"Seeding ID: {torrent_id}")
            self.update_row(torrent_id, name=base_name, progress=100, status="Seeding (Local)")
            if self.dht:
                asyncio.run_coroutine_threadsafe(self.dht.announce(bytes.fromhex(torrent_id), self.port), self.loop)

        except Exception as e:
            self.root.add_log(f"Seeding failed: {e}")

    # --- BACKEND SETUP ---
    async def setup_backend(self):
        log_lifecycle("⚙️ Setting up backend...")
        self.loop = asyncio.get_running_loop()
        self.port = 6881
        self.host = "0.0.0.0"
        
        # 1. TCP Server (File Transfer)
        self.udp_adapter = UDPAdapter()
        try:
            await self.loop.create_datagram_endpoint(lambda: self.udp_adapter, local_addr=(self.host, self.port))
            self.root.add_log(f"Bound to port {self.port}")
        except OSError:
            self.port = 0 
            await self.loop.create_datagram_endpoint(lambda: self.udp_adapter, local_addr=(self.host, self.port))
            if self.udp_adapter.transport:
                self.port = self.udp_adapter.transport.get_extra_info('sockname')[1]
            self.root.add_log(f"Port busy. Using random port {self.port}")

        my_ip = self.get_local_ip()
        self.root.ids.ip_status.text = f"My Address: {my_ip}:{self.port}"
        log_lifecycle(f"🔍 INTERNAL IP DETECTED: {my_ip}")

        # 2. DHT Setup
        if DHT:
            try:
                log_lifecycle("⚙️ Initializing DHT...")
                local_id = int.from_bytes(os.urandom(20), "big")
                self.dht = DHT(local_id, self.udp_adapter, self.loop)
                self.udp_adapter.dht = self.dht
                await self.dht.bootstrap([("router.utorrent.com", 6881)])
                self.root.add_log("DHT Bootstrapped.")
                asyncio.create_task(self.announce_loop())
            except Exception as e:
                log_lifecycle(f"❌ DHT INIT FAILED: {e}")
                self.dht = None
        else:
             self.root.add_log("DHT Disabled (Import Error)")

        # 3. Discovery Setup (Nearby)
        try:
            transport, protocol = await self.loop.create_datagram_endpoint(
                lambda: LocalDiscoveryProtocol(self),
                local_addr=('0.0.0.0', DISCOVERY_PORT),
                allow_broadcast=True
            )
            self.discovery_transport = transport
            asyncio.create_task(self.broadcast_beacon_loop())
            self.root.add_log("Discovery Beacon Active")
        except Exception as e:
            self.root.add_log(f"Discovery Failed: {e}")
            self.discovery_transport = None

        # 4. Start Loops
        asyncio.create_task(self.server_loop())

    async def announce_loop(self):
        while True:
            scan_dirs = ["torrents"]
            if platform == 'android':
                from android.storage import primary_external_storage_path
                scan_dirs.append(os.path.join(primary_external_storage_path(), "Download", "KiwiTorrent"))

            for base in scan_dirs:
                if os.path.exists(base):
                    for folder in os.listdir(base):
                        meta_path = os.path.join(base, folder, "metadata.json")
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, 'r') as rf: m = json.load(rf)
                                if "torrent_id" in m and self.dht:
                                    await self.dht.announce(bytes.fromhex(m["torrent_id"]), self.port)
                            except: pass
            await asyncio.sleep(60)

    async def server_loop(self):
        server = await asyncio.start_server(self.handle_peer_connection, host=self.host, port=self.port)
        self.root.add_log(f"TCP Server listening on {self.port}")
        async with server: await server.serve_forever()

    async def handle_peer_connection(self, reader, writer):
        try:
            typ, payload = await read_msg(reader=reader)
            if typ is None: return

            if typ == b'L': # LIST
                available = []
                scan_dirs = ["torrents"]
                if platform == 'android':
                    from android.storage import primary_external_storage_path
                    scan_dirs.append(os.path.join(primary_external_storage_path(), "Download", "KiwiTorrent"))

                for base in scan_dirs:
                    if os.path.exists(base):
                        for f in os.listdir(base):
                            mp = os.path.join(base, f, "metadata.json")
                            if os.path.exists(mp):
                                try:
                                    with open(mp) as rf: available.append(json.load(rf))
                                except: pass
                
                writer.write(pack_msg(b'L', json.dumps(available).encode()))
                await writer.drain()
                return

            if typ == b'M': # META
                req_id = payload.decode()
                metadata = {}
                found = False
                
                scan_dirs = ["torrents"]
                if platform == 'android':
                    from android.storage import primary_external_storage_path
                    scan_dirs.append(os.path.join(primary_external_storage_path(), "Download", "KiwiTorrent"))

                for base in scan_dirs:
                    if os.path.exists(base):
                        for f in os.listdir(base):
                            mp = os.path.join(base, f, "metadata.json")
                            if os.path.exists(mp):
                                try:
                                    with open(mp) as rf: temp = json.load(rf)
                                    if temp['torrent_id'] == req_id:
                                        metadata = temp
                                        found = True
                                        break
                                except: pass
                    if found: break

                if not found:
                    writer.close(); return
                writer.write(pack_msg(b'M', json.dumps(metadata).encode()))
                await writer.drain()

                # Handshake
                typ, payload = await read_msg(reader)
                if typ != b'H': return
                writer.write(pack_msg(b'H', metadata["torrent_id"].encode()))
                await writer.drain()

                # Bitfield
                n_pieces = len(metadata["pieces"])
                bitfield_bytes = bytearray((n_pieces + 7) // 8)
                for i in range(n_pieces):
                    bitfield_bytes[i // 8] |= (1 << (i % 8))
                
                writer.write(pack_msg(b'B', bytes(bitfield_bytes)))
                await writer.drain()

                # Pieces Logic
                p_dir = None
                folder_name = f"torrent_{metadata['name'].split('.')[0]}_{metadata['torrent_id'][:6]}"
                
                for base in scan_dirs:
                    check_path = os.path.join(base, folder_name, "pieces")
                    if os.path.exists(check_path):
                        p_dir = check_path
                        break
                    if os.path.exists(base):
                        for f in os.listdir(base):
                            mp = os.path.join(base, f, "metadata.json")
                            if os.path.exists(mp):
                                try:
                                    with open(mp) as rf:
                                        if json.load(rf)['torrent_id'] == metadata['torrent_id']:
                                            p_dir = os.path.join(base, f, "pieces")
                                            break
                                except: pass
                        if p_dir: break

                while True:
                    typ, payload = await read_msg(reader)
                    if typ != b'R': break
                    (piece_idx,) = struct.unpack(">I", payload[:4])
                    if p_dir:
                        p_path = os.path.join(p_dir, f"piece_{piece_idx:06d}.bin")
                        if os.path.exists(p_path):
                            with open(p_path, "rb") as pf: p_data = pf.read()
                            writer.write(pack_msg(b'P', struct.pack(">I", piece_idx) + p_data))
                            await writer.drain()
        except: pass
        finally: writer.close()

    # --- CLIENT ---
    def add_download_task(self, torrent_id):
        self.update_row(torrent_id, name=f"Finding peers...", progress=0, status="Searching DHT")
        asyncio.create_task(self.download_workflow(torrent_id))

    def direct_connect_wrapper(self, ip_port_str):
        if ":" not in ip_port_str:
            self.root.add_log("Invalid format. Use IP:PORT")
            return
        host, port = ip_port_str.split(":")
        try:
            port = int(port)
            asyncio.create_task(self.direct_list_and_download(host, port))
        except ValueError:
            self.root.add_log("Port must be a number")

    async def direct_list_and_download(self, host, port):
        self.root.add_log(f"Connecting to {host}:{port}...")
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
            
            # Request List
            writer.write(pack_msg(b'L', b''))
            await writer.drain()
            
            typ, payload = await read_msg(reader)
            if typ == b'L':
                files = json.loads(payload.decode())
                if not files:
                    self.root.add_log("Peer has no files.")
                else:
                    self._peer_list_popup = PeerFileListPopup()
    
                    self._peer_list_popup.set_data(files, self.on_peer_file_selected, host, port)
                    self._peer_list_popup.open()
            else:
                self.root.add_log("Peer sent unknown response.")
            
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            self.root.add_log(f"Connection failed: {e}")

    def on_peer_file_selected(self, torrent_id, file_name, host, port):
        # Now accepts host and port directly
        if hasattr(self, '_peer_list_popup'): self._peer_list_popup.dismiss()
        if hasattr(self, '_nearby_popup'): self._nearby_popup.dismiss()
        
        self.root.add_log(f"Selected: {file_name}. Starting...")
        self.update_row(torrent_id, name=file_name, progress=0, status="Direct Connect")
        asyncio.create_task(self.download_torrent(host, port, torrent_id))

    async def download_workflow(self, torrent_id):
        self.root.add_log(f"Searching DHT for {torrent_id}")
        peers = []
        if self.dht:
            for attempt in range(3): 
                shii_info = bytes.fromhex(torrent_id)
                peers = await self.dht[shii_info]
                if peers: break
                await asyncio.sleep(1)
        
        if not peers:
            self.update_row(torrent_id, status="Stalled (No Peers)")
            self.root.add_log("No peers found via DHT.")
            return

        host, port = peers[0]
        await self.download_torrent(host, port, torrent_id)

    async def download_torrent(self, peer_host, peer_port, torrent_id):
        self.update_row(torrent_id, status="Connecting...")
        try:
            reader, writer = await asyncio.open_connection(peer_host, peer_port)
        except:
            self.root.add_log(f"Connection failed to {peer_host}:{peer_port}")
            self.update_row(torrent_id, status="Conn Failed")
            return

        try:
            # Meta
            writer.write(pack_msg(b'M', torrent_id.encode()))
            await writer.drain()
            typ, payload = await read_msg(reader)
            if typ != b'M': return
            
            metadata = json.loads(payload.decode())
            name = metadata['name']
            self.update_row(torrent_id, name=name, status="Downloading")
            
            # Storage
            save_dir = os.path.join("downloads", name)
            if platform == 'android':
                from android.storage import primary_external_storage_path
                save_dir = os.path.join(primary_external_storage_path(), "Download", "KiwiTorrent", name)
            
            pieces_dir = os.path.join(save_dir, "pieces")
            os.makedirs(pieces_dir, exist_ok=True)

            # Handshake
            writer.write(pack_msg(b'H', metadata["torrent_id"].encode()))
            await writer.drain()
            typ, _ = await read_msg(reader) 
            
            # Bitfield
            typ, payload = await read_msg(reader) 
            
            # Download Loop
            n_pieces = len(metadata["pieces"])
            downloaded = 0
            
            for i in range(n_pieces):
                p_path = os.path.join(pieces_dir, f"piece_{i:06d}.bin")
                if os.path.exists(p_path): 
                    downloaded += 1
                    continue

                writer.write(pack_msg(b'R', struct.pack(">I", i)))
                await writer.drain()

                typ, payload = await read_msg(reader)
                if typ == b'P':
                    with open(p_path, "wb") as f: f.write(payload[4:])
                    downloaded += 1
                    pct = (downloaded / n_pieces) * 100
                    self.update_row(torrent_id, progress=pct)
                    await asyncio.sleep(0.01)

            self.update_row(torrent_id, progress=100, status="Seeding")
            self.root.add_log(f"Finished: {name}")
            
            # Assemble
            final_file = os.path.join(save_dir, name)
            with open(final_file, 'wb') as outfile:
                for i in range(n_pieces):
                    with open(os.path.join(pieces_dir, f"piece_{i:06d}.bin"), 'rb') as pf:
                        outfile.write(pf.read())
            self.root.add_log(f"File saved to: {final_file}")

        except Exception as e:
            self.root.add_log(f"Download Error: {e}")
            self.update_row(torrent_id, status="Error")
        finally:
            writer.close()

if __name__ == '__main__':
    log_lifecycle("App Main Entry Point Reached")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = KiwiTorrentApp()
        loop.run_until_complete(app.async_run(async_lib='asyncio'))
    except KeyboardInterrupt:
        log_lifecycle("App stopped by user")
    except Exception as e:
        log_lifecycle(f"FATAL: {e}")
