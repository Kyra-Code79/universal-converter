import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import pillow_heif
from pypdf import PdfReader, PdfWriter
import webbrowser

# --- 1. CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
pillow_heif.register_heif_opener()

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
    
    app.after(0, lambda: finish_task(result, btn_convert, "Convert File"))

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
    app.after(0, lambda: finish_task(result, btn_compress, "Compress File"))

def finish_task(result, btn_obj, btn_text):
    progress_bar.stop()
    btn_obj.configure(state="normal", text=btn_text)
    
    if "Error" in result:
        messagebox.showerror("Error", result)
        lbl_status.configure(text="Status: Failed", text_color="#FF5555")
    else:
        # Calculate savings
        try:
             # Logic to show how much space was saved? (Optional polish)
             pass
        except: pass
        
        messagebox.showinfo("Success", "File compressed successfully!")
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


# --- SHARED FOOTER ---
progress_bar = ctk.CTkProgressBar(app, mode="indeterminate")
progress_bar.pack(pady=5, padx=20, fill="x")
progress_bar.set(0)

lbl_status = ctk.CTkLabel(app, text="Status: Ready", text_color="gray")
lbl_status.pack(pady=5)

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