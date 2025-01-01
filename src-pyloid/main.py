from pyloid import (
    Pyloid,
    PyloidAPI,
    Bridge,
    TrayEvent,
    is_production,
    get_production_path,
)
import os
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QThread, Signal
import uuid
from pathlib import Path

app = Pyloid(app_name="ASSNP", single_instance=True)

if is_production():
    app.set_icon(os.path.join(get_production_path(), "icons/icon.png"))
    app.set_tray_icon(os.path.join(get_production_path(), "icons/icon.png"))
else:
    app.set_icon("src-pyloid/icons/icon.png")
    app.set_tray_icon("src-pyloid/icons/icon.png")

############################## Tray ################################
def on_double_click():
    print("Tray icon was double-clicked.")


app.set_tray_actions(
    {
        TrayEvent.DoubleClick: on_double_click,
    }
)
app.set_tray_menu_items(
    [
        {"label": "Show Window", "callback": app.show_and_focus_main_window},
        {"label": "Exit", "callback": app.quit},
    ]
)
####################################################################

############################## Bridge ##############################

def get_font_path():
    """Get the path to the font file, falling back to system fonts if needed"""
    font_paths = [
        "src-pyloid/assets/SpaceMono-Regular.ttf",  # Local development path
    ]
    
    # Only add production path if we're in production mode
    if is_production():
        font_paths.append(os.path.join(get_production_path(), "assets/SpaceMono-Regular.ttf"))
    
    # System font fallbacks
    font_paths.extend([
        "/System/Library/Fonts/Helvetica.ttc",  # macOS fallback
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux fallback
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows fallback
    ])
    
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    raise OSError("No suitable font found. Please install Space Mono or ensure system fonts are available.")

class PrinterThread(QThread):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, image_path, length_cm, printer_url):
        super().__init__()
        self.image_path = image_path
        self.length_cm = length_cm
        self.printer_url = printer_url

    def run(self):
        try:
            if not self.printer_url:
                raise Exception("No printer selected")

            self.progress.emit("Sending to printer...")
            
            # Clean up the printer URL - ensure it's in the correct format
            printer_url = None
            if "ipp://" in self.printer_url:
                printer_url = self.printer_url
            elif "dnssd://" in self.printer_url:
                # Convert dnssd URL to IPP URL format
                name = self.printer_url.split("(")[1].split(")")[0]
                printer_url = f"ipp://{name}.local:631/ipp/print"
            
            if not printer_url:
                raise Exception("Invalid printer URL")
                
            # Use the full IPP URL with the image path directly
            os.system(f'ipptool -tv -f {self.image_path} "{printer_url}" -d fileType=image/reverse-encoding-bmp print-job.test')
            
            # Cleanup
            try:
                if os.path.exists(self.image_path):
                    os.remove(self.image_path)
            except:
                pass
            
            self.finished.emit(f"Print job completed successfully ({self.length_cm:.1f}cm)")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")
            # Cleanup on error
            try:
                if os.path.exists(self.image_path):
                    os.remove(self.image_path)
            except:
                pass

class PreviewThread(QThread):
    progress = Signal(str)
    finished = Signal(tuple)  # (preview_path, length_cm)
    error = Signal(str)

    def __init__(self, api_instance, text, width_inches, dpi, font_size, margin_cm):
        super().__init__()
        self.api = api_instance
        self.text = text
        self.width_inches = width_inches
        self.dpi = dpi
        self.font_size = font_size
        self.margin_cm = margin_cm

    def run(self):
        try:
            image, length_cm = self.api._generate_image(
                self.text,
                self.width_inches,
                self.dpi,
                self.font_size,
                self.margin_cm,
                self.progress.emit
            )
            
            # Use a unique filename for each preview
            preview_path = f"preview_{uuid.uuid4()}.png"
            image.save(preview_path, optimize=True, quality=85)
            
            self.finished.emit((preview_path, length_cm))
        except Exception as e:
            self.error.emit(f"Error generating preview: {str(e)}")

class TextPrinterAPI(PyloidAPI):
    def __init__(self):
        super().__init__()
        self.current_preview = None
        self.current_image = None
        self.current_length = None
        self.current_printer = None

    def split_long_word(self, word: str, usable_width: int, draw: ImageDraw, font: ImageFont) -> list:
        """Split a word that's too long to fit on one line"""
        parts = []
        while word:
            # Try to fit as many characters as possible
            for i in range(len(word)):
                part = word[:i+1]
                if draw.textlength(part, font=font) > usable_width:
                    # Found the breaking point, use previous length
                    if i > 0:
                        parts.append(word[:i])
                        word = word[i:]
                    else:
                        # If even one character is too wide, force split it
                        parts.append(word[0])
                        word = word[1:]
                    break
            else:
                # Remaining word fits entirely
                parts.append(word)
                word = ''
        return parts

    def _generate_image(self, text: str, width_inches: float, dpi: int, font_size: int, margin_cm: float = 0, progress_callback=None):
        """Common image generation code for both preview and print"""
        try:
            # Calculate pixel dimensions
            image_width_px = 576  # Fixed width for thermal printer
            margin_px = int((margin_cm / 2.54) * dpi)  # Convert cm to inches to pixels
            
            # Scale font size with DPI
            scaled_font_size = int(font_size * (dpi / 72))
            font = ImageFont.truetype(get_font_path(), scaled_font_size)
            
            if progress_callback:
                progress_callback("Processing text...")
                
            # Create a dummy image for dimension calculations
            dummy_image = Image.new("RGB", (1, 1))
            draw = ImageDraw.Draw(dummy_image)
            
            # Calculate line height and margins
            line_height = draw.textbbox((0, 0), "A", font=font)[3]
            side_margin_px = int(0.03 * dpi)  # Horizontal margin
            usable_width = image_width_px - (2 * side_margin_px)
            
            # Process text in chunks
            lines = []
            text_lines = text.split('\n')
            total_lines = len(text_lines)
            
            for i, line in enumerate(text_lines):
                if not line.strip():
                    lines.append('')
                    continue
                
                words = line.split()
                current_line = []
                current_width = 0
                
                for word in words:
                    word_width = draw.textlength(word, font=font)
                    space_width = draw.textlength(" ", font=font)
                    
                    total_width = current_width
                    if current_line:
                        total_width += space_width
                    total_width += word_width
                    
                    if total_width <= usable_width:
                        current_line.append(word)
                        current_width = total_width
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                            current_line = []
                            current_width = 0
                        
                        if word_width > usable_width:
                            word_parts = self.split_long_word(word, usable_width, draw, font)
                            lines.extend(word_parts[:-1])
                            if word_parts[-1]:
                                current_line = [word_parts[-1]]
                                current_width = draw.textlength(word_parts[-1], font=font)
                        else:
                            current_line = [word]
                            current_width = word_width
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                if progress_callback and i % 10 == 0:
                    progress = int((i / total_lines) * 50)
                    progress_callback(f"Processing text... {progress}%")
            
            if progress_callback:
                progress_callback("Creating image...")
            
            # Calculate dimensions with margins
            base_margin = int(0.05 * dpi)  # Default minimal margin
            top_margin = margin_px + base_margin  # Add user margin to base margin
            bottom_margin = margin_px + base_margin
            image_height_px = (line_height * len(lines)) + top_margin + bottom_margin
            
            # Create the final image
            image = Image.new("RGB", (image_width_px, image_height_px), "white")
            draw = ImageDraw.Draw(image)
            
            # Draw text with margins
            y = top_margin  # Start from top margin
            total_lines = len(lines)
            
            for i, line in enumerate(lines):
                draw.text((side_margin_px, y), line, fill="black", font=font)
                y += line_height
                
                if progress_callback and i % 10 == 0:
                    progress = 50 + int((i / total_lines) * 50)
                    progress_callback(f"Drawing text... {progress}%")
            
            # Calculate actual length including margins
            length_inches = image_height_px / dpi
            length_cm = length_inches * 2.54
            
            return image, length_cm
        except Exception as e:
            import traceback
            print(f"Error in _generate_image: {str(e)}")
            print(traceback.format_exc())
            raise

    @Bridge(str, float, int, int, float, result=str)
    def preview_text(self, text: str, width_inches: float, dpi: int, font_size: int, margin_cm: float):
        # Create and start the preview thread
        self.preview_thread = PreviewThread(self, text, width_inches, dpi, font_size, margin_cm)
        self.preview_thread.progress.connect(self.on_progress)
        self.preview_thread.finished.connect(self.on_preview_finished)
        self.preview_thread.error.connect(self.on_error)
        self.preview_thread.start()
        return "Generating preview..."

    @Bridge(tuple, result=None)
    def on_preview_finished(self, result: tuple):
        preview_path, length_cm = result  # The preview thread already saved the image
        try:
            # Load and encode the preview data
            with open(preview_path, 'rb') as image_file:
                import base64
                encoded_string = base64.b64encode(image_file.read()).decode()
                
                # Clean up old preview if it exists
                if self.current_preview and self.current_preview != preview_path:
                    try:
                        os.remove(self.current_preview)
                    except:
                        pass
                
                # Store current preview path and data
                self.current_preview = preview_path
                self.current_image = Image.open(preview_path)  # Load the image for later printing
                self.current_length = length_cm
                
                # Send preview data to frontend
                self.window.emit('preview_ready', {
                    "preview": f"data:image/png;base64,{encoded_string}",
                    "length": f"{length_cm:.1f}"
                })
        except Exception as e:
            self.window.emit('print_error', {"message": f"Error loading preview: {str(e)}"})
            if preview_path:
                try:
                    os.remove(preview_path)
                except:
                    pass

    @Bridge(result=str)
    def print_current(self):
        """Print the currently previewed image"""
        if not self.current_image:
            return "Error: No preview available"
        
        if hasattr(self, 'current_bmp_path') and os.path.exists(self.current_bmp_path):
            # For images, use the BMP file directly
            temp_path = self.current_bmp_path
        else:
            # For text/markdown, use the current image
            temp_path = f"temp_output_{uuid.uuid4()}.png"
            self.current_image.save(temp_path)
            
        # Create and start the printer thread with the file path
        self.printer_thread = PrinterThread(temp_path, self.current_length, self.current_printer)
        self.printer_thread.progress.connect(self.on_progress)
        self.printer_thread.finished.connect(self.on_finished)
        self.printer_thread.error.connect(self.on_error)
        self.printer_thread.start()
        return "Print job started..."

    @Bridge(str, result=None)
    def on_progress(self, message: str):
        # Send progress update to frontend
        self.window.emit('print_progress', {"message": message})

    @Bridge(str, result=None)
    def on_finished(self, message: str):
        # Send completion message to frontend
        self.window.emit('print_finished', {"message": message})

    @Bridge(str, result=None)
    def on_error(self, message: str):
        # Send error message to frontend
        self.window.emit('print_error', {"message": message})

    @Bridge(result=str)
    def get_printer_status(self):
        # You could implement printer status checking here
        return "Printer ready"

    @Bridge(result=list)
    def get_printers(self):
        """Get list of available IPP printers"""
        try:
            printers = []
            
            # Use lpstat to list all printers
            import subprocess
            result = subprocess.run(['lpstat', '-v'], capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                if ':' in line:  # Any printer entry
                    try:
                        # Extract printer name and URL/device
                        parts = line.split(':', 1)
                        name = parts[0].split()[-1]  # Get last word before colon
                        url = parts[1].strip()
                        printers.append({
                            "name": f"{name} ({url})",
                            "url": url
                        })
                    except:
                        continue
            
            return printers
        except Exception as e:
            print(f"Error getting printers: {str(e)}")
            return []

    @Bridge(str, result=None)
    def set_printer(self, printer_url: str):
        """Set the current printer"""
        self.current_printer = printer_url

    @Bridge(str, result=None)
    def store_canvas_data(self, canvas_data: str):
        """Store canvas data for printing"""
        try:
            # Remove the data URL prefix
            image_data = canvas_data.split(',')[1]
            
            import base64
            import io
            from PIL import Image
            
            # Load and convert image
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Ensure exact 576px width
            if image.width != 576:
                height = int((576 / image.width) * image.height)
                image = image.resize((576, height), Image.Resampling.LANCZOS)
            
            # Set the DPI metadata to match the printer's requirements
            image.info['dpi'] = (203, 203)  # ASSNP uses 203 DPI (8 dots/mm)
            
            # Convert to monochrome (1-bit)
            image = image.convert('1')
            
            # Store for printing
            self.current_image = image
            self.current_length = (image.height / 203) * 2.54  # Use 203 DPI for length calculation
            
        except Exception as e:
            print(f"Error storing canvas data: {str(e)}")

    @Bridge(str, result=str)
    def prepare_image_file(self, file_path: str):
        """Prepare an image file for printing"""
        try:
            # Validate file exists
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
            
            self.window.emit('preview_progress', {"message": "Converting to printer format..."})
            
            # Generate unique temp filenames
            temp_output = f"temp_output_{uuid.uuid4()}.png"
            output_bmp = f"output_{uuid.uuid4()}.bmp"
            
            # First resize to a narrower width (e.g., 500px) and save temporarily
            image = Image.open(file_path)
            target_width = 500  # Wider than before (was 400)
            height = int((target_width / image.width) * image.height)
            resized = image.resize((target_width, height), Image.Resampling.LANCZOS)
            
            # Create a new white image of exactly 576px width
            final_image = Image.new('RGB', (576, height), 'white')
            
            # Paste the resized image in the center (less padding)
            paste_x = (576 - target_width) // 2
            final_image.paste(resized, (paste_x, 0))
            
            final_image.save(temp_output)
            
            # Save a preview PNG (un-flipped version for display)
            preview_path = f"preview_{uuid.uuid4()}.png"
            
            # For preview, use the original processed image before flipping
            os.system(f'magick {temp_output} -modulate 120,100,100 -monochrome -colors 2 {preview_path}')
            
            # For printing, create the flipped BMP
            os.system(f'magick {temp_output} -modulate 120,100,100 -monochrome -colors 2 -flip BMP3:{output_bmp}')
            
            # Store both the BMP and its path for printing
            self.current_image = Image.open(output_bmp)
            self.current_bmp_path = output_bmp
            self.current_length = (self.current_image.height / 203) * 2.54
            
            # Clean up temp PNG
            try:
                os.remove(temp_output)
            except:
                pass
            
            # Clean up old preview
            if self.current_preview and self.current_preview != preview_path:
                try:
                    os.remove(self.current_preview)
                except:
                    pass
            
            self.current_preview = preview_path
            
            # Send preview to frontend
            with open(preview_path, 'rb') as image_file:
                import base64
                encoded_string = base64.b64encode(image_file.read()).decode()
                
                self.window.emit('preview_ready', {
                    "preview": f"data:image/png;base64,{encoded_string}",
                    "length": f"{self.current_length:.1f}"
                })
            
            return f"Image prepared successfully ({self.current_length:.1f}cm)"
            
        except Exception as e:
            return f"Error preparing image: {str(e)}"

    def __del__(self):
        # Clean up any remaining preview file
        if self.current_preview:
            try:
                os.remove(self.current_preview)
            except:
                pass

####################################################################

if is_production():
    window = app.create_window(
        title="ASSNP",
        js_apis=[TextPrinterAPI()],
    )
    window.load_file(os.path.join(get_production_path(), "build/index.html"))
else:
    window = app.create_window(
        title="ASSNP",
        js_apis=[TextPrinterAPI()],
        dev_tools=True,
    )
    window.load_url("http://localhost:5173")

window.show_and_focus()
app.run()
