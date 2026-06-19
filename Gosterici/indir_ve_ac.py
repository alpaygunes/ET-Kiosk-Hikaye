import os
import sys
import urllib.request
import zipfile
import tempfile
import webbrowser
import shutil
import subprocess
import time
import http.server
import socketserver
import threading
import tkinter as tk
import json

# Ayarlar
KAYNAK_URL = "http://localhost:8000/kaynak.zip"
SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".config", "YaparizBasaririz")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "kiosk_settings.json")

def check_mute_status():
    """
    Sessizlik ayarını kontrol eder.
    Sessiz mod aktifse (ve süresi dolmadıysa) programı çalıştırmadan kapatır.
    """
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                mute_until = data.get("mute_until", 0)
                current_time = time.time()
                if current_time < mute_until:
                    remaining_seconds = mute_until - current_time
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    print(f"Sessiz mod etkin: Sessizlik süresinin bitmesine {hours} saat {minutes} dakika var. Program çalışmadan sonlandırılıyor.")
                    sys.exit(0)
        except SystemExit:
            sys.exit(0)
        except Exception as e:
            print(f"Sessiz mod kontrolü sırasında hata oluştu: {e}", file=sys.stderr)

class ToggleSwitch(tk.Canvas):
    """
    Tkinter Canvas tabanlı modern, premium görünümlü bir açma/kapama (Toggle) anahtarı.
    """
    def __init__(self, parent, width=55, height=26, bg_color="#57606f", active_color="#2ed573", knob_color="#ffffff", initial_state=False, command=None, *args, **kwargs):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], bd=0, highlightthickness=0, *args, **kwargs)
        self.width = width
        self.height = height
        self.bg_color = bg_color
        self.active_color = active_color
        self.knob_color = knob_color
        self.state = initial_state
        self.command = command
        
        self.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        self.delete("all")
        radius = self.height / 2
        color = self.active_color if self.state else self.bg_color
        
        # Rounded rectangle background
        self.create_oval(0, 0, self.height, self.height, fill=color, outline="")
        self.create_oval(self.width - self.height, 0, self.width, self.height, fill=color, outline="")
        self.create_rectangle(radius, 0, self.width - radius, self.height, fill=color, outline="")
        
        # Knob
        padding = 3
        knob_radius = radius - padding
        if self.state:
            knob_x = self.width - radius
        else:
            knob_x = radius
            
        self.create_oval(
            knob_x - knob_radius,
            padding,
            knob_x + knob_radius,
            self.height - padding,
            fill=self.knob_color,
            outline=""
        )

    def toggle(self, event=None):
        self.state = not self.state
        self.draw()
        if self.command:
            self.command(self.state)

class ThreadedHTTPServer:
    """
    Belirtilen dizini arka planda (ayrı bir iş parçacığında)
    http://localhost:<dinamik_port> üzerinden sunan basit bir HTTP sunucusu.
    """
    def __init__(self, directory):
        self.directory = directory
        self.port = None
        self.server = None
        self.thread = None

    def start(self):
        server_dir = self.directory
        # Python 3.7+ SimpleHTTPRequestHandler dizin parametresini destekler
        class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=server_dir, **kwargs)
                
            def log_message(self, format, *args):
                # Sunucu istek loglarının konsolu kirletmemesi için devre dışı bırakıyoruz
                pass

        # 0 portunu atayarak işletim sisteminin boş bir port seçmesini sağlıyoruz
        self.server = socketserver.TCPServer(("127.0.0.1", 0), CustomHTTPRequestHandler)
        self.port = self.server.socket.getsockname()[1]
        
        # Ana işlem sonlandığında sunucunun da kapanması için daemon=True yapıyoruz
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"HTTP sunucusu arka planda başlatıldı: http://localhost:{self.port}")
        return self.port

    def stop(self):
        if self.server:
            print("HTTP sunucusu durduruluyor...")
            self.server.shutdown()
            self.server.server_close()

def open_in_kiosk(url):
    """
    Belirtilen URL'i tarayıcıda kiosk modunda açmayı dener.
    Başarılı olursa Popen sürecini (process) döner, başarısız olursa None döner.
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "kaynak_gosterici_kiosk")
    chrome_profile = os.path.join(temp_dir, "chrome_profile")
    try:
        os.makedirs(chrome_profile, exist_ok=True)
    except Exception:
        pass

    browsers = [
        ("google-chrome", [f"--user-data-dir={chrome_profile}", "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required", "--kiosk", url]),
        ("chromium-browser", [f"--user-data-dir={chrome_profile}", "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required", "--kiosk", url]),
        ("chromium", [f"--user-data-dir={chrome_profile}", "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required", "--kiosk", url]),
        ("firefox", ["--kiosk", url])
    ]
    
    for browser_name, args in browsers:
        if shutil.which(browser_name):
            try:
                print(f"Tarayıcı kiosk modunda başlatılıyor: {browser_name}")
                proc = subprocess.Popen([browser_name] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return proc
            except Exception as e:
                print(f"{browser_name} ile kiosk modunda başlatma başarısız oldu: {e}", file=sys.stderr)
    return None

def show_control_panel(browser_proc):
    """
    Ekranın sağ üst köşesinde her zaman üstte duran çıkış ve ayarlar butonlarını oluşturur.
    Kullanıcının kiosk modundan kolayca çıkmasını veya ayarları yönetmesini sağlar.
    Dokunmatik ekranlar için:
    - Sürükleme (drag & drop) desteği sunar, böylece ekranın istenen yerine taşınabilir.
    - Sürükleme hareketi yaparken yanlışlıkla kapanmaması veya ayarların açılmaması için akıllı hareket algılaması vardır.
    - Tek dokunuşla (tıklama) eylemleri anında tetikler.
    """
    try:
        root = tk.Tk()
    except Exception as tk_err:
        print(f"Grafiksel arayüz başlatılamadı (Tkinter hatası: {tk_err}).", file=sys.stderr)
        print("Sunucuyu kapatmak ve çıkmak için terminalde Ctrl+C tuşlarına basın.")
        # Grafik arayüzü yoksa, terminal üzerinden süreci bekletelim
        if browser_proc:
            try:
                browser_proc.wait()
            except KeyboardInterrupt:
                print("\nKullanıcı tarafından sonlandırıldı.")
        else:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nKullanıcı tarafından sonlandırıldı.")
        return

    root.title("Kiosk Kontrol")
    
    # Pencere çerçevelerini kaldır (borderless)
    root.overrideredirect(True)
    # Her zaman en üstte tut
    root.attributes('-topmost', True)
    
    # Dokunmatik ekran için daha büyük hedef alanı (240x60)
    window_width = 240
    window_height = 60
    try:
        screen_width = root.winfo_screenwidth()
        x = screen_width - window_width - 25
        y = 25
    except Exception:
        # Hata durumunda varsayılan konumlar
        x, y = 1000, 25
        
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    # Sürükleme yapılıp yapılmadığını izlemek için bayrak (flag)
    root.was_dragged = False
    
    def on_exit():
        print("Çıkış gerçekleştiriliyor. Kapatılıyor...")
        if browser_proc:
            try:
                browser_proc.terminate()
                browser_proc.wait(timeout=2)
            except Exception:
                try:
                    browser_proc.kill()
                except Exception:
                    pass
        root.destroy()

    def open_settings_popup():
        popup = tk.Toplevel(root)
        popup.title("Ayarlar")
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.configure(bg="#1e272e")
        popup.config(highlightbackground="#57606f", highlightthickness=1)
        
        popup_width = 340
        popup_height = 200
        
        try:
            screen_width = popup.winfo_screenwidth()
            screen_height = popup.winfo_screenheight()
            px = (screen_width - popup_width) // 2
            py = (screen_height - popup_height) // 2
        except Exception:
            px, py = 500, 300
        popup.geometry(f"{popup_width}x{popup_height}+{px}+{py}")
        popup.grab_set()

        title_label = tk.Label(
            popup,
            text="Kiosk Ayarları",
            font=("Helvetica", 14, "bold"),
            bg="#1e272e",
            fg="#ffffff"
        )
        title_label.pack(pady=(15, 10))

        row_frame = tk.Frame(popup, bg="#1e272e")
        row_frame.pack(fill=tk.X, padx=25, pady=10)

        option_label = tk.Label(
            row_frame,
            text="12 Saat Sessize Al",
            font=("Helvetica", 12),
            bg="#1e272e",
            fg="#dfe4ea"
        )
        option_label.pack(side=tk.LEFT)

        initial_state = False
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mute_until = data.get("mute_until", 0)
                    if time.time() < mute_until:
                        initial_state = True
        except Exception:
            pass

        popup.shutdown_timer = None

        def on_toggle(state):
            if state:
                mute_duration = 12 * 3600
                mute_until = time.time() + mute_duration
                try:
                    os.makedirs(SETTINGS_DIR, exist_ok=True)
                    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
                        json.dump({"mute_until": mute_until}, f, ensure_ascii=False, indent=4)
                    
                    info_label.config(text="Sessiz mod etkinleştirildi.\nProgram 3 saniye içinde kapanacak...", fg="#2ed573")
                    
                    def delayed_exit():
                        on_exit()
                    
                    popup.shutdown_timer = popup.after(3000, delayed_exit)
                except Exception as err:
                    info_label.config(text=f"Hata: {err}", fg="#ff4757")
            else:
                if popup.shutdown_timer:
                    popup.after_cancel(popup.shutdown_timer)
                    popup.shutdown_timer = None
                try:
                    os.makedirs(SETTINGS_DIR, exist_ok=True)
                    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
                        json.dump({"mute_until": 0}, f, ensure_ascii=False, indent=4)
                    info_label.config(text="Sessiz mod iptal edildi.", fg="#ffffff")
                except Exception as err:
                    info_label.config(text=f"Hata: {err}", fg="#ff4757")

        toggle = ToggleSwitch(row_frame, width=55, height=26, initial_state=initial_state, command=on_toggle)
        toggle.pack(side=tk.RIGHT)

        info_label = tk.Label(
            popup,
            text="Programı sessiz moda alarak 12 saat kapanmasını sağlayabilirsiniz.",
            font=("Helvetica", 9),
            bg="#1e272e",
            fg="#a4b0be",
            justify=tk.CENTER,
            wraplength=300
        )
        info_label.pack(pady=(5, 10))

        def close_popup():
            if popup.shutdown_timer:
                popup.after_cancel(popup.shutdown_timer)
            popup.destroy()

        close_btn = tk.Button(
            popup,
            text="KAPAT",
            bg="#2f3542",
            fg="white",
            font=("Helvetica", 10, "bold"),
            bd=0,
            activebackground="#57606f",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=close_popup
        )
        close_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=25, pady=(0, 15))

        def on_close_btn_enter(e):
            close_btn.config(bg="#57606f")
        def on_close_btn_leave(e):
            close_btn.config(bg="#2f3542")
        close_btn.bind("<Enter>", on_close_btn_enter)
        close_btn.bind("<Leave>", on_close_btn_leave)

    # Modern buton tasarımları (Premium aesthetics)
    # Settings Button
    settings_btn = tk.Button(
        root,
        text="⚙",
        bg="#2f3542",
        fg="white",
        font=("Helvetica", 16),
        bd=0,
        activebackground="#57606f",
        activeforeground="white",
        relief=tk.FLAT,
        cursor="hand2"
    )
    settings_btn.place(x=0, y=0, width=60, height=60)

    # Close Button
    button = tk.Button(
        root,
        text="KAPAT",
        bg="#ff4757",       # Canlı mercan kırmızısı
        fg="white",
        font=("Helvetica", 11, "bold"),
        bd=0,
        activebackground="#ff6b81",
        activeforeground="white",
        relief=tk.FLAT,
        cursor="hand2"
    )
    button.place(x=60, y=0, width=180, height=60)

    # Hover (üzerine gelme) efektleri
    def on_enter(e):
        button.config(bg="#ff6b81")
    def on_leave(e):
        button.config(bg="#ff4757")
    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)

    def on_settings_enter(e):
        settings_btn.config(bg="#57606f")
    def on_settings_leave(e):
        settings_btn.config(bg="#2f3542")
    settings_btn.bind("<Enter>", on_settings_enter)
    settings_btn.bind("<Leave>", on_settings_leave)

    # Sürükleme (Drag & Drop) mekanizması
    def start_drag(event):
        root._drag_start_x = event.x_root
        root._drag_start_y = event.y_root
        root.was_dragged = False

    def drag(event):
        deltax = event.x_root - root._drag_start_x
        deltay = event.y_root - root._drag_start_y
        
        if abs(deltax) > 3 or abs(deltay) > 3:
            root.was_dragged = True
            x = root.winfo_x() + deltax
            y = root.winfo_y() + deltay
            root.geometry(f"+{x}+{y}")
            root._drag_start_x = event.x_root
            root._drag_start_y = event.y_root

    def on_close_release(event):
        if not root.was_dragged:
            on_exit()

    def on_settings_release(event):
        if not root.was_dragged:
            open_settings_popup()

    # Olayları butonlara bağlama
    button.bind("<Button-1>", start_drag)
    button.bind("<B1-Motion>", drag)
    button.bind("<ButtonRelease-1>", on_close_release)

    settings_btn.bind("<Button-1>", start_drag)
    settings_btn.bind("<B1-Motion>", drag)
    settings_btn.bind("<ButtonRelease-1>", on_settings_release)

    # Tarayıcının kendiliğinden kapanıp kapanmadığını izleyen döngü
    def check_browser():
        if browser_proc and browser_proc.poll() is not None:
            print("Tarayıcı süreci kapandı. Kontrol paneli kapatılıyor.")
            root.destroy()
        else:
            root.after(1000, check_browser)

    if browser_proc:
        root.after(1000, check_browser)

    # Tkinter ana döngüsü
    try:
        root.mainloop()
    except KeyboardInterrupt:
        on_exit()

def main():
    check_mute_status()
    server = None
    try:
        # Sabit geçici dizin ismi kullanarak önceki çalışmalardan kalan dosyaları temizleyebiliyoruz
        temp_dir = os.path.join(tempfile.gettempdir(), "kaynak_gosterici_kiosk")
        
        # 1. Önceki zip ve içeriğini sil (varsa)
        if os.path.exists(temp_dir):
            print(f"[1/4] Önceki zip dosyası ve çıkartılan içerikler siliniyor: {temp_dir}")
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as clean_error:
                print(f"Uyarı: Önceki dizin tam olarak silinemedi: {clean_error}", file=sys.stderr)
        else:
            print("[1/4] Önceki temizlenecek veri bulunamadı. Yeni dizin hazırlanıyor.")

        # Çalışma dizinlerini oluştur
        zip_path = os.path.join(temp_dir, "kaynak.zip")
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        # 2. kaynak.zip dosyasını önbelleğe almadan (no-cache) indir
        print(f"[2/4] '{KAYNAK_URL}' adresinden güncel dosya indiriliyor...")
        try:
            timestamp = int(time.time() * 1000)
            separator = "&" if "?" in KAYNAK_URL else "?"
            nocache_url = f"{KAYNAK_URL}{separator}_={timestamp}"
            
            req = urllib.request.Request(nocache_url)
            req.add_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            req.add_header('Pragma', 'no-cache')
            req.add_header('Expires', '0')
            
            with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            print("İndirme işlemi başarıyla tamamlandı (Önbellek aşılması zorlandı).")
        except Exception as download_error:
            print(f"Hata: Dosya indirilemedi. Lütfen sunucunun (http://localhost:8000) açık olduğundan emin olun.", file=sys.stderr)
            print(f"Detaylı hata: {download_error}", file=sys.stderr)
            return

        if not os.path.exists(zip_path):
            print("Hata: kaynak.zip dosyası indirilemedi (dosya bulunamadı). Kiosk başlatılmıyor.", file=sys.stderr)
            return

        # 3. Zip dosyasını yeni baştan çıkart
        print("[3/4] Zip dosyası çıkartılıyor...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            print(f"Dosyalar şuraya çıkartıldı: {extract_dir}")
        except zipfile.BadZipFile:
            print("Hata: İndirilen dosya geçerli bir zip dosyası değil.", file=sys.stderr)
            return
        except Exception as extract_error:
            print(f"Hata: Zip dosyası çıkartılamadı: {extract_error}", file=sys.stderr)
            return

        # 4. index.html dosyasını bul, sunucuyu başlat ve aç
        print("[4/4] index.html aranıyor...")
        index_path = None
        
        possible_index = os.path.join(extract_dir, "index.html")
        if os.path.exists(possible_index):
            index_path = possible_index
        else:
            for root, dirs, files in os.walk(extract_dir):
                if "index.html" in files:
                    index_path = os.path.join(root, "index.html")
                    break
        
        if index_path:
            # index.html dosyasının bulunduğu klasörü sunucu kök dizini yapıyoruz
            server_dir = os.path.dirname(os.path.abspath(index_path))
            
            # kaynak.json kontrolü
            json_path = os.path.join(server_dir, "kaynak.json")
            if not os.path.exists(json_path):
                print("Hata: 'kaynak.json' dosyası bulunamadı. Kiosk başlatılmıyor.", file=sys.stderr)
                return
                
            try:
                import json
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as json_err:
                print(f"Hata: 'kaynak.json' okunamadı veya geçersiz JSON formatı: {json_err}", file=sys.stderr)
                return
                
            stories = data.get("icerikler", [])
            if not stories:
                print("Hata: 'kaynak.json' içinde hiçbir haber/içerik bulunamadı. Kiosk başlatılmıyor.", file=sys.stderr)
                return
                
            # Güncel/aktif haber kontrolü
            from datetime import datetime, timedelta
            
            def is_story_expired(story):
                olusturma = story.get("olusturma_tarihi")
                if not olusturma:
                    return False
                    
                try:
                    dt_str = olusturma.replace("T", " ")
                    creation_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return False
                    
                validity = story.get("gecerlilik_suresi_saat")
                try:
                    validity = int(validity) if validity is not None else 0
                except (ValueError, TypeError):
                    validity = 0
                    
                if validity == 0:
                    return False
                    
                expiration_time = creation_time + timedelta(hours=validity)
                return datetime.now() > expiration_time

            active_stories = [s for s in stories if not is_story_expired(s)]
            if not active_stories:
                print("Hata: kaynak.json içindeki tüm haberlerin gösterim tarihi geçmiş (güncel haber yok). Kiosk başlatılmıyor.", file=sys.stderr)
                return

            # Lokal HTTP Sunucusunu başlat
            server = ThreadedHTTPServer(server_dir)
            port = server.start()
            
            # Sunucu üzerindeki URL'i oluştur
            server_url = f"http://localhost:{port}/index.html"
            print(f"Tarayıcıda açılıyor: {server_url}")
            
            # Kiosk modunda açmayı dene
            browser_process = open_in_kiosk(server_url)
            
            if browser_process:
                # Kiosk modunda açıldı, grafik arayüzlü kapatma butonunu göster
                show_control_panel(browser_process)
            else:
                # Kiosk modu çalışmazsa varsayılan tarayıcıda normal modda aç
                print("Kiosk modu başlatılamadı. Varsayılan tarayıcı normal modda açılıyor...")
                webbrowser.open(server_url)
                # Yine de sunucuyu kapatmak için küçük bir GUI kontrolü göster
                show_control_panel(None)
        else:
            print("Hata: Çıkartılan dosyalar arasında 'index.html' bulunamadı.", file=sys.stderr)
            print("Çıkartılan dosyalar listesi:")
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    print(f" - {os.path.relpath(os.path.join(root, file), extract_dir)}")

    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {e}", file=sys.stderr)
    finally:
        if server:
            server.stop()

if __name__ == "__main__":
    main()

