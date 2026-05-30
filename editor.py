#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import shutil
import sys
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

# Validity options mapping (human-readable option -> hours)
VALIDITY_OPTIONS = {
    "1 Saat": 1,
    "12 Saat": 12,
    "24 Saat (1 Gün)": 24,
    "48 Saat (2 Gün)": 48,
    "1 Hafta": 168,
    "Sınırsız": 0
}
VALIDITY_REVERSE = {v: k for k, v in VALIDITY_OPTIONS.items()}

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.delay = 400  # delay in ms
        self.after_id = None
        self.widget.bind("<Enter>", self.schedule_tip)
        self.widget.bind("<Leave>", self.hide_tip)
        self.widget.bind("<ButtonPress>", self.hide_tip)

    def schedule_tip(self, event=None):
        self.cancel_scheduled()
        self.after_id = self.widget.after(self.delay, self.show_tip)

    def cancel_scheduled(self):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def show_tip(self, event=None):
        self.cancel_scheduled()
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            tw, 
            text=self.text, 
            justify=tk.LEFT,
            background="#1f2937", 
            foreground="#f3f4f6", 
            relief=tk.SOLID, 
            borderwidth=1,
            highlightthickness=0,
            font=("Inter", 9),
            padx=6,
            pady=3
        )
        label.pack()

    def hide_tip(self, event=None):
        self.cancel_scheduled()
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class StoryEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Yaparız Başarırız - Hikaye Akışı İçerik Editörü")
        self.root.geometry("1100x700")
        self.root.minsize(1000, 600)
        
        # Paths configuration
        self.workspace_dir = os.path.dirname(os.path.abspath(__file__))
        self.json_path = os.path.join(self.workspace_dir, "kaynak.json")
        self.resimler_dir = os.path.join(self.workspace_dir, "resimler")
        self.assets_dir = os.path.join(self.workspace_dir, "assets")
        
        # Ensure directories exist
        os.makedirs(self.resimler_dir, exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)
        
        # State variables
        self.stories = []
        self.selected_index = None
        self.is_loading_item = False
        
        # Setup modern style
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()
        
        # Main layout container
        self.main_container = ttk.Frame(self.root, padding=20)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Status Bar at the bottom
        self.status_label = ttk.Label(self.root, text="Hazır", font=("Inter", 9), background="#e5e7eb", anchor=tk.W, padding=(10, 4))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Left Panel (Treeview List & Quick Buttons) - Fixed width 550px
        self.left_panel = ttk.Frame(self.main_container, width=550)
        self.left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 15))
        self.left_panel.pack_propagate(False)
        
        # Right Panel (Details Form & Preview) - Expands with window
        self.right_panel = ttk.LabelFrame(self.main_container, text=" İÇERİK DETAYLARI ", padding=20)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.build_left_panel()
        self.build_right_panel()
        
        # Load JSON data
        self.load_json_data()
        
    def configure_styles(self):
        # Configure colors and styles for a modern look
        bg_dark = "#111827"
        accent_color = "#10b981"
        self.style.configure(".", background="#f3f4f6", foreground="#1f2937", font=("Inter", 10))
        self.style.configure("TLabelframe", background="#ffffff", relief="flat", borderwidth=1)
        self.style.configure("TLabelframe.Label", background="#ffffff", foreground="#374151", font=("Outfit", 11, "bold"))
        self.style.configure("Form.TLabel", background="#ffffff", foreground="#374151", font=("Inter", 9, "bold"))
        self.style.configure("FormText.TLabel", background="#ffffff", foreground="#4b5563", font=("Inter", 9))
        self.style.configure("FormItalic.TLabel", background="#ffffff", foreground="#4b5563", font=("Inter", 9, "italic"))
        self.style.configure("TButton", font=("Inter", 10, "bold"), padding=8, background="#e5e7eb", borderwidth=0)
        self.style.configure("TButton", font=("Inter", 10, "bold"), padding=8, background="#e5e7eb", borderwidth=0)
        self.style.map("TButton",
                       background=[('active', '#d1d5db'), ('pressed', '#9ca3af')])
        
        # Save & Accent Buttons
        self.style.configure("Accent.TButton", background=accent_color, foreground="white")
        self.style.map("Accent.TButton",
                       background=[('active', '#059669'), ('pressed', '#047857')])
        
        # Danger / Delete Button
        self.style.configure("Danger.TButton", background="#ef4444", foreground="white")
        self.style.map("Danger.TButton",
                       background=[('active', '#dc2626'), ('pressed', '#b91c1c')])
        
        # Treeview styling
        self.style.configure("Treeview", font=("Inter", 10), rowheight=28, background="#ffffff", fieldbackground="#ffffff")
        self.style.configure("Treeview.Heading", font=("Outfit", 10, "bold"), background="#e5e7eb", foreground="#374151")
        
        # Entry styling (padding 5px)
        self.style.configure("TEntry", padding=5)
        
    def set_status(self, message):
        self.status_label.config(text=message)
        self.root.after(5000, lambda: self.clear_status(message))
        
    def clear_status(self, old_message):
        try:
            if self.status_label.cget("text") == old_message:
                self.status_label.config(text="Hazır")
        except Exception:
            pass

    def validate_numeric(self, P):
        if P == "":
            return True
        return P.isdigit()

    def build_left_panel(self):
        # Header Label
        header = ttk.Label(self.left_panel, text="Hikaye Akışı Listesi", font=("Outfit", 16, "bold"), background="#f3f4f6")
        header.pack(anchor=tk.W, pady=(0, 10))
        
        # Dedicated container for the Treeview list and its scrollbar
        list_frame = ttk.Frame(self.left_panel)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview Scrollbar
        scroll_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        
        # Treeview Table
        cols = ("Tür", "Başlık", "Süre")
        self.tree = ttk.Treeview(list_frame, columns=cols, yscrollcommand=scroll_y.set, selectmode="browse")
        scroll_y.config(command=self.tree.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.heading("#0", text="Sıra")
        self.tree.heading("Tür", text="İçerik Türü")
        self.tree.heading("Başlık", text="Başlık")
        self.tree.heading("Süre", text="Süre (sn)")
        
        self.tree.column("#0", width=50, minwidth=50, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column("Tür", width=100, minwidth=80, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column("Başlık", width=250, minwidth=180, stretch=tk.YES)
        self.tree.column("Süre", width=80, minwidth=70, stretch=tk.NO, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        
        # Configure tags (color expired items red)
        self.tree.tag_configure("expired", foreground="#ef4444")
        
        # Toolbar Container under the list (rescued from scrollbar alignment)
        toolbar_container = ttk.LabelFrame(self.left_panel, text=" ARAÇLAR ", padding=12)
        toolbar_container.pack(fill=tk.X, pady=(15, 0))
        
        # Single Row Frame for all Actions
        row_frame = ttk.Frame(toolbar_container)
        row_frame.pack(fill=tk.X)
        
        # Left-side buttons: List operations
        self.btn_add_new = ttk.Button(row_frame, text="➕ Yeni Hikaye Ekle", command=self.add_new_story_automatically)
        self.btn_add_new.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_delete = ttk.Button(row_frame, text="🗑️", width=4, style="Danger.TButton", command=self.delete_item)
        self.btn_delete.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_up = ttk.Button(row_frame, text="▲", width=4, command=self.move_up)
        self.btn_up.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_down = ttk.Button(row_frame, text="▼", width=4, command=self.move_down)
        self.btn_down.pack(side=tk.LEFT, padx=(0, 10))
        
        # Right-side buttons: Project / File operations
        self.btn_save_all = ttk.Button(row_frame, text="💾", width=4, style="Accent.TButton", command=self.save_to_json)
        self.btn_save_all.pack(side=tk.RIGHT)
        
        # Tooltips for list actions
        ToolTip(self.btn_add_new, "Listeye otomatik olarak yeni bir hikaye ekler")
        ToolTip(self.btn_delete, "Seçili hikayeyi listeden siler")
        ToolTip(self.btn_up, "Seçili hikayeyi listede yukarı taşır")
        ToolTip(self.btn_down, "Seçili hikayeyi listede aşağı taşır")
        
        # Tooltips for save actions
        ToolTip(self.btn_save_all, "Tüm değişiklikleri kaynak.json dosyasına kaydeder ve kaynak.zip oluşturur")
        
    def build_right_panel(self):
        # We need a scrollable form inside the right panel in case it grows
        canvas = tk.Canvas(self.right_panel, borderwidth=0, highlightthickness=0, background="#ffffff")
        scrollbar = ttk.Scrollbar(self.right_panel, orient="vertical", command=canvas.yview)
        self.form_container = ttk.Frame(canvas, padding=(0, 0, 10, 0))
        self.form_container.configure(style="TLabelframe")
        
        # Scroll setup
        canvas_window = canvas.create_window((0, 0), window=self.form_container, anchor="nw")
        
        # Stretches form_container to canvas width dynamically
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=max(400, event.width - 15))
            
        canvas.bind("<Configure>", on_canvas_configure)
        
        self.form_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Allow form columns to expand horizontally
        self.form_container.columnconfigure(0, weight=1)
        self.form_container.columnconfigure(1, weight=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Form Variables
        self.var_turu = tk.StringVar(value="Duyuru")
        self.var_baslik = tk.StringVar()
        self.var_resim = tk.StringVar()
        self.var_süre = tk.StringVar(value="5")
        self.var_olusturma_tarihi = tk.StringVar(value="Yeni içerik kaydedildiğinde oluşturulacak")
        self.var_gecerlilik_suresi = tk.StringVar(value="24")
        
        # Validation command for numeric inputs
        vcmd = (self.root.register(self.validate_numeric), '%P')
        
        grid_config = {"sticky": tk.W, "pady": 8}
        
        # Row 0: Content Type
        ttk.Label(self.form_container, text="İçerik Türü:", style="Form.TLabel").grid(row=0, column=0, **grid_config)
        self.combo_turu = ttk.Combobox(self.form_container, textvariable=self.var_turu, values=["Duyuru", "Haber", "Başarı"], state="readonly")
        self.combo_turu.grid(row=1, column=0, columnspan=2, sticky=tk.W+tk.E)
        
        # Row 1: Title
        ttk.Label(self.form_container, text="Başlık:", style="Form.TLabel").grid(row=2, column=0, **grid_config)
        self.entry_baslik = ttk.Entry(self.form_container, textvariable=self.var_baslik)
        self.entry_baslik.grid(row=3, column=0, columnspan=2, sticky=tk.W+tk.E)
        
        # Row 2: Text (Description) with height 250px and padding 5px
        ttk.Label(self.form_container, text="Metin / Açıklama:", style="Form.TLabel").grid(row=4, column=0, **grid_config)
        text_frame = ttk.Frame(self.form_container, height=250)
        text_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W+tk.E)
        text_frame.pack_propagate(False)
        self.text_metin = tk.Text(text_frame, font=("Inter", 10), wrap=tk.WORD, borderwidth=1, relief="solid", padx=5, pady=5)
        self.text_metin.pack(fill=tk.BOTH, expand=True)
        self.text_metin.bind("<<Modified>>", self.on_text_modified)
        
        # Traces for auto-update
        self.var_turu.trace_add("write", lambda *args: self.auto_update_current_story())
        self.var_baslik.trace_add("write", lambda *args: self.auto_update_current_story())
        self.var_resim.trace_add("write", lambda *args: self.auto_update_current_story())
        self.var_süre.trace_add("write", lambda *args: self.auto_update_current_story())
        self.var_gecerlilik_suresi.trace_add("write", lambda *args: self.auto_update_current_story())
        
        # Row 3: Duration Entry (Right-aligned, digit-only)
        ttk.Label(self.form_container, text="Gösterim Süresi (Saniye):", style="Form.TLabel").grid(row=6, column=0, **grid_config)
        self.entry_süre = ttk.Entry(self.form_container, textvariable=self.var_süre, justify=tk.RIGHT, width=12, validate="key", validatecommand=vcmd)
        self.entry_süre.grid(row=6, column=1, sticky=tk.E, pady=8)
        
        # Row 4: Validity Duration Entry (Right-aligned, digit-only)
        ttk.Label(self.form_container, text="Geçerlilik Süresi (Saat):", style="Form.TLabel").grid(row=7, column=0, **grid_config)
        self.entry_gecerlilik = ttk.Entry(self.form_container, textvariable=self.var_gecerlilik_suresi, justify=tk.RIGHT, width=12, validate="key", validatecommand=vcmd)
        self.entry_gecerlilik.grid(row=7, column=1, sticky=tk.E, pady=8)
        
        # Row 5: Creation DateTime
        ttk.Label(self.form_container, text="Oluşturulma Tarihi:", style="Form.TLabel").grid(row=8, column=0, **grid_config)
        self.lbl_olusturma_val = ttk.Label(self.form_container, textvariable=self.var_olusturma_tarihi, style="FormText.TLabel")
        self.lbl_olusturma_val.grid(row=9, column=0, columnspan=2, sticky=tk.W+tk.E)
        
        # Row 6: Image Picker
        ttk.Label(self.form_container, text="Hikaye Görseli:", style="Form.TLabel").grid(row=10, column=0, **grid_config)
        img_frame = ttk.Frame(self.form_container)
        img_frame.configure(style="TLabelframe")
        img_frame.grid(row=11, column=0, columnspan=2, sticky=tk.W+tk.E)
        
        btn_select_img = ttk.Button(img_frame, text="🖼️", width=4, command=self.select_image)
        btn_select_img.pack(side=tk.RIGHT, padx=(5, 0))
        ToolTip(btn_select_img, "Bilgisayarınızdan hikaye için bir görsel dosya seçin")
        
        self.lbl_img_path = ttk.Label(img_frame, textvariable=self.var_resim, style="FormItalic.TLabel")
        self.lbl_img_path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Row 7: Visual Thumbnail Preview
        ttk.Label(self.form_container, text="Görsel Önizleme:", style="Form.TLabel").grid(row=12, column=0, **grid_config)
        self.lbl_thumbnail = ttk.Label(self.form_container, text="[Önizleme Yok]", borderwidth=1, relief="solid", background="#f3f4f6")
        self.lbl_thumbnail.grid(row=13, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Actions frame moved to the bottom of right_panel (outside the scrollable canvas)
        pass
        
    def load_json_data(self):
        # Load sources from kaynak.json
        if not os.path.exists(self.json_path):
            messagebox.showwarning("Uyarı", "kaynak.json dosyası bulunamadı! Yeni bir tane oluşturulacak.")
            self.stories = []
            self.update_move_buttons_state()
            return
            
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.stories = data.get("icerikler", [])
            self.refresh_treeview()
            if self.stories:
                # Select first item by default
                self.tree.selection_set(self.tree.get_children()[0])
            else:
                self.update_move_buttons_state()
        except Exception as e:
            messagebox.showerror("Hata", f"JSON dosyası okunurken hata oluştu:\n{str(e)}")
            self.stories = []
            self.update_move_buttons_state()
            
    def is_story_expired(self, story):
        olusturma = story.get("olusturma_tarihi")
        if not olusturma:
            return False
            
        try:
            dt_str = olusturma.replace("T", " ")
            creation_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
            
        validity = story.get("gecerlilik_suresi_saat")
        if validity is None or validity == 0:
            return False
            
        expiration_time = creation_time + timedelta(hours=validity)
        return datetime.now() > expiration_time

    def refresh_treeview(self):
        # Clear and reload Treeview rows
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for idx, story in enumerate(self.stories):
            is_expired = self.is_story_expired(story)
            tags = ("expired",) if is_expired else ()
            self.tree.insert(
                "", 
                tk.END, 
                iid=str(idx), 
                text=str(idx + 1),
                values=(
                    story.get("icerik_turu", "Bilinmeyen"),
                    story.get("baslik", ""),
                    story.get("gosterim_suresi_sn", 5)
                ),
                tags=tags
            )
            
    def on_item_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
            
        new_index = int(selected[0])
        
        # Check if the PREVIOUSLY selected item has no image
        if self.selected_index is not None and self.selected_index != new_index:
            if self.selected_index < len(self.stories):
                prev_story = self.stories[self.selected_index]
                if not prev_story.get("resim_url") or not prev_story.get("resim_url").strip():
                    self.is_loading_item = True
                    self.tree.selection_set(str(self.selected_index))
                    self.is_loading_item = False
                    messagebox.showwarning("Eksik Bilgi", "Hikayeye resim eklenmedi, bir resim eklemelisiniz!")
                    return
            
        self.is_loading_item = True
        
        self.selected_index = new_index
        story = self.stories[self.selected_index]
        
        # Populate Form
        self.var_turu.set(story.get("icerik_turu", "Duyuru"))
        self.var_baslik.set(story.get("baslik", ""))
        
        # Reset modified state so programmatic edits don't trigger traces
        self.text_metin.edit_modified(False)
        self.text_metin.delete("1.0", tk.END)
        self.text_metin.insert("1.0", story.get("metin", ""))
        self.text_metin.edit_modified(False)
        
        self.var_süre.set(story.get("gosterim_suresi_sn", 5))
        
        olusturma = story.get("olusturma_tarihi", "")
        if olusturma:
            self.var_olusturma_tarihi.set(olusturma.replace("T", " "))
        else:
            self.var_olusturma_tarihi.set("Belirtilmemiş (Sınırsız)")
            
        validity = story.get("gecerlilik_suresi_saat", 0)
        self.var_gecerlilik_suresi.set(str(validity))
        
        # Process and show image thumbnail
        img_name = story.get("resim_url", "")
        self.var_resim.set(img_name)
        
        img_path = self.format_image_path(img_name)
        self.update_thumbnail_preview(img_path)
        
        # Update Move Buttons State
        self.update_move_buttons_state()
        
        self.is_loading_item = False

    def format_image_path(self, filename):
        if not filename:
            return ""
        # Check if already a full path
        if os.path.isabs(filename):
            return filename
            
        # The browser maps image_url dynamically.
        # Let's map it similarly for python to load it:
        clean_name = filename
        if not clean_name.startswith("resimler/"):
            # Check if it exists in root or needs resimler/ prefix
            clean_name = os.path.join("resimler", clean_name)
            
        # If ends with .jpg, also check for .jpg.png file on disk
        if clean_name.endswith(".jpg"):
            png_version = clean_name + ".png"
            if os.path.exists(os.path.join(self.workspace_dir, png_version)):
                clean_name = png_version
                
        return os.path.join(self.workspace_dir, clean_name)

    def update_thumbnail_preview(self, path):
        # Renders small thumbnail image
        if not path or not os.path.exists(path):
            self.lbl_thumbnail.config(image='', text="[Önizleme Yok]\n" + os.path.basename(path))
            return
            
        if PIL_AVAILABLE:
            try:
                img = Image.open(path)
                img.thumbnail((160, 90)) # 16:9 box
                photo = ImageTk.PhotoImage(img)
                self.lbl_thumbnail.config(image=photo, text="")
                self.lbl_thumbnail.image = photo # Keep reference
                return
            except Exception as e:
                print(f"PIL Thumbnail yükleme hatası: {e}")
                
        # Fallback to tk PhotoImage if file is png
        if path.lower().endswith('.png'):
            try:
                photo = tk.PhotoImage(file=path)
                width = photo.width()
                factor = max(1, width // 160)
                photo_small = photo.subsample(factor, factor)
                self.lbl_thumbnail.config(image=photo_small, text="")
                self.lbl_thumbnail.image = photo_small
                return
            except Exception:
                pass
                
        self.lbl_thumbnail.config(image='', text="[Önizleme Yok]")

    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="Görsel Seç",
            filetypes=[
                ("Resim Dosyaları", ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.PNG", "*.JPG", "*.JPEG", "*.WEBP")),
                ("Tüm Dosyalar", "*.*")
            ]
        )
        if not file_path:
            return
            
        abs_selected = os.path.abspath(file_path)
        abs_resimler = os.path.abspath(self.resimler_dir)
        
        # Check if the file is already inside the workspace resimler directory
        if abs_selected.startswith(abs_resimler):
            rel_name = os.path.relpath(abs_selected, abs_resimler)
            # Remove .png helper extension for JSON if it conforms to XX.jpg.png
            if rel_name.endswith('.jpg.png'):
                json_name = rel_name[:-4]
            else:
                json_name = rel_name
                
            self.var_resim.set(json_name)
            self.update_thumbnail_preview(abs_selected)
        else:
            # File is outside the directory, copy and rename it!
            try:
                # Scan directory for numerical filenames
                existing_files = os.listdir(self.resimler_dir)
                nums = []
                for f in existing_files:
                    name_parts = f.split('.')
                    if name_parts[0].isdigit():
                        nums.append(int(name_parts[0]))
                
                next_num = max(nums) + 1 if nums else 1
                new_json_name = f"{next_num:02d}.jpg"
                new_disk_name = f"{next_num:02d}.jpg.png"
                dest_path = os.path.join(self.resimler_dir, new_disk_name)
                
                # Copy file to resimler directory and convert to PNG if PIL is available
                if PIL_AVAILABLE:
                    try:
                        img = Image.open(abs_selected)
                        img.save(dest_path, "PNG")
                    except Exception as img_err:
                        print(f"Görsel PNG formatına dönüştürülemedi, ham kopya alınıyor: {img_err}")
                        shutil.copy2(abs_selected, dest_path)
                else:
                    shutil.copy2(abs_selected, dest_path)
                
                self.var_resim.set(new_json_name)
                self.update_thumbnail_preview(dest_path)
                messagebox.showinfo("Başarılı", f"Resim kopyalandı ve adlandırıldı:\n{new_disk_name}")
            except Exception as e:
                messagebox.showerror("Hata", f"Resim kopyalanırken bir hata oluştu:\n{str(e)}")

    def clear_form_for_new(self):
        # Reset form fields
        self.is_loading_item = True
        self.selected_index = None
        self.tree.selection_remove(self.tree.selection())
        
        self.var_turu.set("Duyuru")
        self.var_baslik.set("")
        self.text_metin.edit_modified(False)
        self.text_metin.delete("1.0", tk.END)
        self.text_metin.edit_modified(False)
        self.var_süre.set("5")
        self.var_resim.set("")
        self.var_olusturma_tarihi.set("Yeni içerik kaydedildiğinde oluşturulacak")
        self.var_gecerlilik_suresi.set("24")
        self.lbl_thumbnail.config(image='', text="[Görsel Seçilmedi]")
        
        # Disable Move Buttons
        self.update_move_buttons_state()
        self.is_loading_item = False
        
    def get_default_image(self):
        # Scan resimler directory for any available image file
        try:
            files = sorted(os.listdir(self.resimler_dir))
            for f in files:
                # e.g., '01.jpg.png' -> '01.jpg'
                if f.endswith('.jpg.png'):
                    return f[:-4]
                elif f.endswith('.jpg') or f.endswith('.png') or f.endswith('.jpeg'):
                    return f
        except Exception:
            pass
        return "01.jpg"  # fallback

    def add_new_story_automatically(self):
        # Check if currently selected item is missing an image
        if self.selected_index is not None:
            curr_story = self.stories[self.selected_index]
            if not curr_story.get("resim_url") or not curr_story.get("resim_url").strip():
                messagebox.showwarning("Eksik Bilgi", "Hikayeye resim eklenmedi, bir resim eklemelisiniz!")
                return
                
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        new_story = {
            "icerik_turu": "Duyuru",
            "resim_url": "",
            "video_url": "",
            "baslik": "Başlık Ekleyin",
            "metin": "İçerik Metnini buraya yazın ",
            "gosterim_suresi_sn": 5,
            "olusturma_tarihi": now_str,
            "gecerlilik_suresi_saat": 24
        }
        
        self.stories.append(new_story)
        self.refresh_treeview()
        
        # Select the newly added item
        new_idx = len(self.stories) - 1
        self.tree.selection_set(str(new_idx))
        
        # Auto-save changes
        self.save_to_json(silent=True)
        
        # Show warning
        messagebox.showwarning("Eksik Bilgi", "Hikayeye resim eklenmedi, bir resim eklemelisiniz!")

    def on_text_modified(self, event=None):
        if self.text_metin.edit_modified():
            self.auto_update_current_story()
            self.text_metin.edit_modified(False)

    def auto_update_current_story(self):
        if self.is_loading_item or self.selected_index is None:
            return
            
        baslik = self.var_baslik.get()
        metin = self.text_metin.get("1.0", "end-1c")
        resim = self.var_resim.get().strip()
        
        try:
            validity_hours = int(self.var_gecerlilik_suresi.get().strip())
        except ValueError:
            validity_hours = 0
            
        try:
            gosterim_suresi = int(self.var_süre.get().strip())
        except ValueError:
            gosterim_suresi = 5
            
        existing_story = self.stories[self.selected_index]
        olusturma_tarihi = existing_story.get("olusturma_tarihi")
        if not olusturma_tarihi:
            olusturma_tarihi = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
        self.stories[self.selected_index].update({
            "icerik_turu": self.var_turu.get(),
            "resim_url": resim,
            "baslik": baslik,
            "metin": metin,
            "gosterim_suresi_sn": gosterim_suresi,
            "olusturma_tarihi": olusturma_tarihi,
            "gecerlilik_suresi_saat": validity_hours
        })
        
        # Update Treeview row
        is_expired = self.is_story_expired(self.stories[self.selected_index])
        tags = ("expired",) if is_expired else ()
        self.tree.item(
            str(self.selected_index),
            values=(
                self.var_turu.get(),
                baslik,
                gosterim_suresi
            ),
            tags=tags
        )
        
        self.save_to_json(silent=True)

    def delete_story_image_file(self, story_to_delete):
        resim_url = story_to_delete.get("resim_url")
        if not resim_url:
            return
            
        # Check if the same image URL is used by any other story in self.stories
        is_used_elsewhere = any(
            other != story_to_delete and other.get("resim_url") == resim_url
            for other in self.stories
        )
        
        if is_used_elsewhere:
            return
            
        # Find paths to check/delete
        paths_to_delete = []
        
        # 1. Direct resolved path
        resolved_path = self.format_image_path(resim_url)
        if resolved_path:
            paths_to_delete.append(resolved_path)
            
        # 2. Raw path under resimler folder
        clean_name = resim_url
        if not clean_name.startswith("resimler/"):
            clean_name = os.path.join("resimler", clean_name)
            
        full_raw_path = os.path.join(self.workspace_dir, clean_name)
        paths_to_delete.append(full_raw_path)
        
        # 3. PNG version helper path
        if clean_name.endswith(".jpg"):
            paths_to_delete.append(os.path.join(self.workspace_dir, clean_name + ".png"))
            
        # De-duplicate paths
        paths_to_delete = list(set(paths_to_delete))
        
        for path in paths_to_delete:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Dosya silinirken hata ({path}): {e}")

    def delete_item(self):
        if self.selected_index is None:
            messagebox.showwarning("Seçim Yok", "Lütfen silmek istediğiniz hikayeyi listeden seçin!")
            return
            
        if messagebox.askyesno("Onay", "Seçili hikayeyi listeden silmek istediğinize emin misiniz?"):
            story_to_delete = self.stories[self.selected_index]
            self.delete_story_image_file(story_to_delete)
            
            self.stories.pop(self.selected_index)
            self.refresh_treeview()
            self.clear_form_for_new()
            
            # Auto-save changes
            self.save_to_json(silent=True)
            messagebox.showinfo("Başarılı", "Hikaye listeden kaldırıldı ve kaydedildi!")

    def save_to_json(self, silent=False):
        # Prevent manual saving if any story is missing an image
        if not silent:
            for idx, story in enumerate(self.stories):
                if not story.get("resim_url") or not story.get("resim_url").strip():
                    messagebox.showwarning("Eksik Bilgi", f"{idx+1}. sıradaki hikayeye resim eklenmedi, bir resim eklemelisiniz!")
                    self.tree.selection_set(str(idx))
                    return
                    
        # Save memory state back to disk
        try:
            # Save a backup file first
            if os.path.exists(self.json_path):
                shutil.copy2(self.json_path, self.json_path + ".bak")
                
            data = {"icerikler": self.stories}
            
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            # Update fallback data inside index.html to prevent local CORS errors
            self.update_index_html_fallback()
            
            if not silent:
                self.compress_project(silent=True)
                messagebox.showinfo("Başarılı", "Kaydedildi")
            else:
                self.set_status("Değişiklikler otomatik olarak kaydedildi.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Hata", f"Kaydedilirken bir hata oluştu:\n{str(e)}")
            else:
                self.set_status(f"Hata: Değişiklikler kaydedilemedi! ({str(e)})")

    def move_up(self):
        if self.selected_index is None or self.selected_index == 0:
            return
        
        idx = self.selected_index
        # Swap in list
        self.stories[idx], self.stories[idx - 1] = self.stories[idx - 1], self.stories[idx]
        self.selected_index = idx - 1
        self.refresh_treeview()
        self.tree.selection_set(str(self.selected_index))
        # Auto-save changes silently
        self.save_to_json(silent=True)
        
    def move_down(self):
        if self.selected_index is None or self.selected_index == len(self.stories) - 1:
            return
        
        idx = self.selected_index
        # Swap in list
        self.stories[idx], self.stories[idx + 1] = self.stories[idx + 1], self.stories[idx]
        self.selected_index = idx + 1
        self.refresh_treeview()
        self.tree.selection_set(str(self.selected_index))
        # Auto-save changes silently
        self.save_to_json(silent=True)
        
    def update_move_buttons_state(self):
        if self.selected_index is None:
            self.btn_up.state(['disabled'])
            self.btn_down.state(['disabled'])
        else:
            if self.selected_index == 0:
                self.btn_up.state(['disabled'])
            else:
                self.btn_up.state(['!disabled'])
                
            if self.selected_index == len(self.stories) - 1:
                self.btn_down.state(['disabled'])
            else:
                self.btn_down.state(['!disabled'])

    def update_index_html_fallback(self):
        index_path = os.path.join(self.workspace_dir, "index.html")
        if not os.path.exists(index_path):
            return
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Serialize self.stories to formatting JSON block
            stories_json = json.dumps({"icerikler": self.stories}, ensure_ascii=False, indent=6)
            
            # Realign indentation to match Javascript formatting
            lines = stories_json.splitlines()
            indented_lines = [lines[0]] + ["    " + line for line in lines[1:]]
            formatted_json_str = "\n".join(indented_lines)
            
            pattern = r'(const\s+fallbackData\s*=\s*)\{.*?\};'
            new_content = re.sub(
                pattern, 
                lambda m: m.group(1) + formatted_json_str + ';', 
                content, 
                flags=re.DOTALL
            )
            
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            print(f"index.html yedek verisi güncellenirken hata: {e}")

    def compress_project(self, silent=False):
        import zipfile
        zip_path = os.path.join(self.workspace_dir, "kaynak.zip")
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 1. Add index.html
                index_file = os.path.join(self.workspace_dir, "index.html")
                if os.path.exists(index_file):
                    zipf.write(index_file, "index.html")
                
                # 2. Add kaynak.json
                json_file = os.path.join(self.workspace_dir, "kaynak.json")
                if os.path.exists(json_file):
                    zipf.write(json_file, "kaynak.json")
                
                # 3. Add resimler directory recursively
                resimler_dir = os.path.join(self.workspace_dir, "resimler")
                if os.path.exists(resimler_dir):
                    for root_dir, _, files in os.walk(resimler_dir):
                        for file in files:
                            file_path = os.path.join(root_dir, file)
                            rel_path = os.path.relpath(file_path, self.workspace_dir)
                            zipf.write(file_path, rel_path)
                            
                # 4. Add assets directory recursively
                assets_dir = os.path.join(self.workspace_dir, "assets")
                if os.path.exists(assets_dir):
                    for root_dir, _, files in os.walk(assets_dir):
                        for file in files:
                            file_path = os.path.join(root_dir, file)
                            rel_path = os.path.relpath(file_path, self.workspace_dir)
                            zipf.write(file_path, rel_path)
                            
            if not silent:
                messagebox.showinfo("Başarılı", f"Dosyalar başarıyla kaynak.zip adıyla sıkıştırıldı:\n{zip_path}")
            self.set_status("Proje kaynak.zip olarak sıkıştırıldı.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Hata", f"Sıkıştırma işlemi sırasında hata oluştu:\n{str(e)}")
            else:
                self.set_status(f"Hata: kaynak.zip oluşturulamadı! ({str(e)})")

def main():
    root = tk.Tk()
    app = StoryEditorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
