import os
import threading
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import pillow_heif
from pypdf import PdfReader, PdfWriter
import webbrowser
import yt_dlp

# --- 1. CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
pillow_heif.register_heif_opener()

cancel_event = threading.Event()

# --- 2. LOGIC: CONVERTER (Unchanged) ---
def convert_image(input_path, output_path, output_format):
    try:
        img = Image.open(input_path)
        if output_format.lower() in ['jpg', 'jpeg']:
            img = img.convert('RGB')
        img.save(output_path, quality=95)
        return output_path
    except Exception as e:
        return f"Error: {str(e)}"

def convert_media(input_path, output_path, output_format):
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(input_path)
        
        if output_format.lower() in ['mp3', 'wav']:
            if clip.audio is None:
                clip.close()
                return "Error: This video file has no audio track!"
            clip.audio.write_audiofile(output_path, logger=None)
        else:
            audio_setting = True if clip.audio else False
            clip.write_videofile(output_path, codec="libx264", audio_codec="aac", audio=audio_setting, logger=None)
            
        clip.close()
        return output_path
    except Exception as e:
        return f"Error: {str(e)}"

# --- 3. LOGIC: REAL COMPRESSOR (UPDATED) ---

def compress_logic(input_path, output_path, compression_level):
    try:
        ext = os.path.splitext(input_path)[1].lower()
        
        # --- A. IMAGE COMPRESSION ---
        if ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.heic']:
            img = Image.open(input_path)
            
            # DEFAULT SETTINGS (Medium)
            max_width = 1920
            qual = 65
            
            # TUNING SETTINGS
            if compression_level == "High Compression":
                max_width = 1280  # Resize to 720p (Much smaller file)
                qual = 30         # Lower quality
            elif compression_level == "Extreme Compression":
                max_width = 1024  # Resize to roughly XGA
                qual = 15         # Very low quality (Maximum space saving)
            elif compression_level == "Low Compression (High Quality)":
                max_width = 2560
                qual = 85

            # 1. RESIZE IF NEEDED
            # We only shrink, never enlarge
            if img.width > max_width:
                ratio = max_width / float(img.width)
                new_height = int((float(img.height) * float(ratio)))
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # 2. SAVE
            if ext == '.png':
                # PNG optimization is harder. 
                # Converting to P mode (256 colors) saves massive space but loses some color depth.
                # If "Extreme", we force color reduction.
                if compression_level == "Extreme Compression":
                    img = img.convert("P", palette=Image.ADAPTIVE, colors=256)
                img.save(output_path, optimize=True)
            else:
                # JPG/WebP
                if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                img.save(output_path, optimize=True, quality=qual)
                
            return output_path

        # --- B. PDF COMPRESSION ---
        elif ext == '.pdf':
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            # For PDF, "High" removes more metadata and compresses streams harder
            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)
            
            # Strip all metadata
            writer.add_metadata({}) 
            
            with open(output_path, "wb") as f:
                writer.write(f)
            return output_path
            
        else:
            return "Error: Compression currently only supports Images and PDFs."

    except Exception as e:
        return f"Error: {str(e)}"
# --- 4. THREADING HANDLERS ---

def run_conversion():
    input_path = entry_conv.get()
    target_format = combo_format.get()
    if not input_path: return
    
    suggested = os.path.splitext(os.path.basename(input_path))[0] + "." + target_format
    output_path = filedialog.asksaveasfilename(defaultextension=f".{target_format}", initialfile=suggested)
    if not output_path: return

    btn_convert.configure(state="disabled", text="Working...")
    progress_bar.start()
    lbl_status.configure(text="Status: Converting...", text_color="white")
    
    threading.Thread(target=process_conversion, args=(input_path, output_path, target_format)).start()

def process_conversion(input_path, output_path, target_format):
    ext = os.path.splitext(input_path)[1].lower()
    img_exts = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.heic']
    vid_exts = ['.mp4', '.mkv', '.avi', '.mov', '.flv']
    
    result = ""
    if ext in img_exts:
        if target_format in ['mp3', 'wav', 'mp4', 'mkv']:
             result = "Error: Cannot convert Image to Audio/Video."
        else:
             result = convert_image(input_path, output_path, target_format)
    elif ext in vid_exts:
        result = convert_media(input_path, output_path, target_format)
    else:
        result = "Error: Unsupported file type."
    
    app.after(0, lambda: finish_task(result, btn_convert, "Convert File", "Conversion Completed Successfully!"))

def run_compression():
    input_path = entry_comp.get()
    level = combo_comp.get() # Get High/Medium/Low selection
    if not input_path: return

    ext = os.path.splitext(input_path)[1].lower()
    suggested = os.path.splitext(os.path.basename(input_path))[0] + "_compressed" + ext
    
    output_path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=suggested)
    if not output_path: return

    btn_compress.configure(state="disabled", text="Working...")
    progress_bar.start()
    lbl_status.configure(text="Status: Compressing...", text_color="white")
    
    threading.Thread(target=process_compression, args=(input_path, output_path, level)).start()

def process_compression(input_path, output_path, level):
    result = compress_logic(input_path, output_path, level)
    result = compress_logic(input_path, output_path, level)
    app.after(0, lambda: finish_task(result, btn_compress, "Compress File", "Compression Completed Successfully!"))

# --- 4.5 LOGIC: YOUTUBE DOWNLOADER ---

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)

def youtube_hook(d):
    if cancel_event.is_set():
        raise Exception("CancelledByUser")

    if d['status'] == 'downloading':
        p = clean_ansi(d.get('_percent_str', '0%'))
        s = clean_ansi(d.get('_speed_str', 'N/A'))
        e = clean_ansi(d.get('_eta_str', 'N/A')) 
        # Note: _eta_str might be missing in some versions, check keys if needed
        # Fallback for ETA if key differs
        if not e: e = "..."
        
        msg = f"Downloading: {p} | Speed: {s} | ETA: {e}"
        app.after(0, lambda: lbl_status.configure(text=msg, text_color="white"))
        
    elif d['status'] == 'finished':
        app.after(0, lambda: lbl_status.configure(text="Download Complete. Processing...", text_color="#55FF55"))

def download_youtube_logic(url, output_folder, video_format, resolution):
    try:
        # Map resolution string to height
        res_map = {
            "Best": 2160,
            "4K": 2160,
            "1080p": 1080,
            "720p": 720,
            "480p": 480,
            "360p": 360
        }
        
        ydl_opts = {
            'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
            'progress_hooks': [youtube_hook],
            # 'ffmpeg_location': 'C:/ffmpeg/bin/ffmpeg.exe' # Optional if not in PATH
        }

        if video_format == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            # Video Mode (mp4/mkv)
            target_height = res_map.get(resolution, 2160)
            
            # Format selection:
            # "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]"
            # We try to match resolution. Extension is handled by merge_output_format
            
            if resolution == "Best":
                ydl_opts['format'] = f"bestvideo+bestaudio/best"
            else:
                ydl_opts['format'] = f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]"
            
            ydl_opts['merge_output_format'] = video_format

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        return "Download Successful!"

    except Exception as e:
        if "CancelledByUser" in str(e):
            return "Download Cancelled"
        return f"Error: {str(e)}"

def run_youtube():
    url = entry_yt_url.get()
    folder = entry_yt_folder.get()
    fmt = combo_yt_format.get()
    res = combo_yt_res.get()
    
    if not url or not folder:
        messagebox.showerror("Error", "Please fill in URL and Save Folder")
        return

    cancel_event.clear()
    
    btn_yt.configure(state="disabled", text="Downloading...")
    btn_cancel_yt.configure(state="normal", fg_color="#FF5555")
    
    progress_bar.start()
    
    threading.Thread(target=process_youtube, args=(url, folder, fmt, res)).start()

def process_youtube(url, folder, fmt, res):
    result = download_youtube_logic(url, folder, fmt, res)
    app.after(0, lambda: finish_youtube(result))

def cancel_youtube():
    cancel_event.set()
    lbl_status.configure(text="Status: Cancelling...", text_color="orange")
    btn_cancel_yt.configure(state="disabled")

def finish_youtube(result):
    btn_cancel_yt.configure(state="disabled", fg_color="gray")
    finish_task(result, btn_yt, "Download Video", "Download Completed Successfully!")

def select_folder(entry_widget):
    path = filedialog.askdirectory()
    if path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)


def finish_task(result, btn_obj, btn_text, success_msg="Task Done!"):
    progress_bar.stop()
    btn_obj.configure(state="normal", text=btn_text)
    
    if "Error" in result:
        messagebox.showerror("Error", result)
        lbl_status.configure(text="Status: Failed", text_color="#FF5555")
    elif "Cancelled" in result:
        lbl_status.configure(text="Status: Cancelled", text_color="orange")
    else:
        messagebox.showinfo("Success", success_msg)
        lbl_status.configure(text="Status: Done!", text_color="#55FF55")

def select_file(entry_widget):
    path = filedialog.askopenfilename()
    if path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)

# --- 5. UI LAYOUT ---

app = ctk.CTk()
app.title("Universal Converter Pro")
app.geometry("500x520")

lbl_title = ctk.CTkLabel(app, text="Universal Tool Suite", font=("Roboto", 24, "bold"))
lbl_title.pack(pady=10)

# --- 6. FOOTER WITH LINK ---

def open_link(event):
    # Change this to your actual LinkedIn or GitHub URL
    webbrowser.open_new("https://github.com/Kyra-Code79") 

frame_footer = ctk.CTkFrame(app, fg_color="transparent")
frame_footer.pack(side="bottom", pady=10)

# CREATE TABS
tabview = ctk.CTkTabview(app)
tabview.pack(padx=20, pady=10, fill="both", expand=True)

tab_conv = tabview.add("Converter")
tab_comp = tabview.add("Compressor")
tab_yt = tabview.add("Youtube")

# --- TAB 1: CONVERTER UI ---
lbl_conv_in = ctk.CTkLabel(tab_conv, text="Select File to Convert:")
lbl_conv_in.pack(pady=5)
frame_conv_in = ctk.CTkFrame(tab_conv, fg_color="transparent")
frame_conv_in.pack(fill="x", padx=10)
entry_conv = ctk.CTkEntry(frame_conv_in, placeholder_text="Select file...")
entry_conv.pack(side="left", fill="x", expand=True, padx=(0,10))
ctk.CTkButton(frame_conv_in, text="Browse", width=60, command=lambda: select_file(entry_conv)).pack(side="right")

lbl_conv_to = ctk.CTkLabel(tab_conv, text="Convert To:")
lbl_conv_to.pack(pady=5)
combo_format = ctk.CTkComboBox(tab_conv, values=["jpg", "png", "webp", "mp4", "mkv", "mp3", "wav"])
combo_format.pack(pady=5)

btn_convert = ctk.CTkButton(tab_conv, text="Convert File", command=run_conversion)
btn_convert.pack(pady=20, fill="x", padx=20)


# --- TAB 2: COMPRESSOR UI (UPDATED) ---
lbl_comp_in = ctk.CTkLabel(tab_comp, text="Select File (Image or PDF):")
lbl_comp_in.pack(pady=5)

frame_comp_in = ctk.CTkFrame(tab_comp, fg_color="transparent")
frame_comp_in.pack(fill="x", padx=10)
entry_comp = ctk.CTkEntry(frame_comp_in, placeholder_text="Select file...")
entry_comp.pack(side="left", fill="x", expand=True, padx=(0,10))
ctk.CTkButton(frame_comp_in, text="Browse", width=60, command=lambda: select_file(entry_comp)).pack(side="right")

lbl_comp_method = ctk.CTkLabel(tab_comp, text="Compression Level:")
lbl_comp_method.pack(pady=5)

# New Options for compression strength
combo_comp = ctk.CTkComboBox(tab_comp, values=[
    "Medium Compression (Balanced)", 
    "High Compression (Low Quality)", 
    "Extreme Compression",
    "Low Compression (High Quality)"
])
combo_comp.set("High Compression") # Set default to High
combo_comp.pack(pady=5)

combo_comp.set("Medium Compression (Balanced)")
combo_comp.pack(pady=5)

btn_compress = ctk.CTkButton(tab_comp, text="Compress File", command=run_compression, fg_color="#E0a800", hover_color="#c29100")
btn_compress.pack(pady=20, fill="x", padx=20)


# --- TAB 3: YOUTUBE UI ---

lbl_yt_url = ctk.CTkLabel(tab_yt, text="Youtube URL:")
lbl_yt_url.pack(pady=5)
entry_yt_url = ctk.CTkEntry(tab_yt, placeholder_text="Paste Link Here...")
entry_yt_url.pack(fill="x", padx=10)

lbl_yt_folder = ctk.CTkLabel(tab_yt, text="Save To:")
lbl_yt_folder.pack(pady=5)
frame_yt_folder = ctk.CTkFrame(tab_yt, fg_color="transparent")
frame_yt_folder.pack(fill="x", padx=10)
entry_yt_folder = ctk.CTkEntry(frame_yt_folder, placeholder_text="Select Folder...")
entry_yt_folder.pack(side="left", fill="x", expand=True, padx=(0,10))
ctk.CTkButton(frame_yt_folder, text="Browse", width=60, command=lambda: select_folder(entry_yt_folder)).pack(side="right")

lbl_yt_opts = ctk.CTkLabel(tab_yt, text="Format & Resolution:")
lbl_yt_opts.pack(pady=5)

frame_yt_opts = ctk.CTkFrame(tab_yt, fg_color="transparent")
frame_yt_opts.pack(fill="x", padx=10)

combo_yt_format = ctk.CTkComboBox(frame_yt_opts, values=["mp4", "mkv", "mp3"])
combo_yt_format.set("mp4")
combo_yt_format.pack(side="left", expand=True, padx=5)

combo_yt_res = ctk.CTkComboBox(frame_yt_opts, values=["Best", "4K", "1080p", "720p", "480p", "360p"])
combo_yt_res.set("1080p")
combo_yt_res.pack(side="right", expand=True, padx=5)

def update_res_state(choice):
    if choice == "mp3":
        combo_yt_res.configure(state="disabled")
    else:
        combo_yt_res.configure(state="normal")

combo_yt_format.configure(command=update_res_state)

combo_yt_format.configure(command=update_res_state)

frame_yt_btns = ctk.CTkFrame(tab_yt, fg_color="transparent")
frame_yt_btns.pack(fill="x", padx=10, pady=20)

btn_yt = ctk.CTkButton(frame_yt_btns, text="Download Video", command=run_youtube, fg_color="#FF0000", hover_color="#CC0000")
btn_yt.pack(side="left", fill="x", expand=True, padx=(0, 10))

btn_cancel_yt = ctk.CTkButton(frame_yt_btns, text="Cancel", command=cancel_youtube, state="disabled", fg_color="gray")
btn_cancel_yt.pack(side="right", fill="x", expand=True, padx=(10, 0))


# --- SHARED FOOTER ---
progress_bar = ctk.CTkProgressBar(app, mode="indeterminate")
progress_bar.pack(pady=5, padx=20, fill="x")
progress_bar.set(0)

lbl_status = ctk.CTkLabel(app, text="Status: Ready", text_color="gray", wraplength=480)
lbl_status.pack(pady=5, fill="x", padx=10)

# 1. Create the label
lbl_footer = ctk.CTkLabel(
    frame_footer, 
    text="Created by Habibi", 
    font=("Arial", 12, "underline"), # Added underline to look like a link
    text_color="#1f6aa5",            # Standard "Link Blue" color
    cursor="hand2"                   # Changes mouse pointer to a Hand when hovering
)
lbl_footer.pack()

# 2. Bind the click event
# "<Button-1>" refers to the Left Mouse Click
lbl_footer.bind("<Button-1>", open_link)

app.mainloop()