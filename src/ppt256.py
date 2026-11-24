import tkinter as tk
import os, sys, math, copy, colorsys
from tkinter import Listbox, filedialog, messagebox, scrolledtext, colorchooser
from PIL import Image
from dataclasses import dataclass
from enum import Enum

rows, cols = 16, 16
cell_grid = []
palette = []
file_path = None
g_shift_down = False

# Stubbed here, gets initialized along with tk
ICON_IMG = object()

class ColorMode(Enum):
    HSV = 1
    RGB = 2
    OKLAB = 3

@dataclass
class Selection:
    start: int
    end: int

g_sel = Selection(-1, -1)

@dataclass
class TintColor:
    "Interpreted based off of colormode"
    x: float
    y: float
    z: float

@dataclass
class TintRamp:
    start: int
    end: int

    type: ColorMode
    startcolor: TintColor
    endcolor: TintColor
    step: int

    # kinda rough conversion of skip value
    skipstart: bool
    skipend: bool

ramps: dict[int, TintRamp] = dict()
# Initialized later along with tk

#### COLOR OPERATIONS
def normalize_rgb(r: int, g: int, b: int):
    return (r / 255.0, g / 255.0, b / 255.0)

# Based off of colorsys's H range (0-170)
def normalize_hsv(h: int, s: int, v: int):
    return (h / 170.0, s / 255.0, v / 255.0)

# Previous conversion method implemented based off of: https://lettier.github.io/3d-game-shaders-for-beginners/gamma-correction.html
# Improved conversion implemented from: https://bottosson.github.io/posts/colorwrong/#what-can-we-do%3F
def linear_rgb_to_srgb(r: float, g: float, b: float):
    if r >= 0.0031308:
        r = (1.055) * r ** (1.0/2.4) - 0.055
    else:
        r = 12.92 * r

    if g >= 0.0031308:
        g = (1.055) * g ** (1.0/2.4) - 0.055
    else:
        g = 12.92 * g

    if b >= 0.0031308:
        b = (1.055) * b ** (1.0/2.4) - 0.055
    else:
        b = 12.92 * b

    return (r, g, b)

def srgb_to_linear_rgb(r: float, g: float, b: float):
    if r >= 0.04045:
        r = ((r + 0.055)/(1 + 0.055))**2.4
    else:
        r = r / 12.92

    if g >= 0.04045:
        g = ((g + 0.055)/(1 + 0.055))**2.4
    else:
        g = g / 12.92

    if b >= 0.04045:
        b = ((b + 0.055)/(1 + 0.055))**2.4
    else:
        b = b / 12.92

    return (r, g, b)

# Implementation based off of:
# https://bottosson.github.io/posts/oklab/
def linear_rgb_to_oklab(r: float, g: float, b: float):
    l = 4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = math.cbrt(l)
    m_ = math.cbrt(m)
    s_ = math.cbrt(s)

    labl = 0.2104542553*l_ + 0.7936177850*m_ - 0.0040720468*s_
    laba = 1.9779984951*l_ - 2.4285922050*m_ + 0.4505937099*s_
    labb = 0.0259040371*l_ + 0.7827717662*m_ - 0.8086757660*s_

    return (labl, laba, labb)

def oklab_to_linear_rgb(l: float, a: float, b: float):
    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3.0
    m = m_ ** 3.0
    s = s_ ** 3.0

    return (+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
		    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
		    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)

# Implemented from: https://en.wikipedia.org/wiki/Linear_interpolation#Programming_language_support
# To hopefully ensure starting and ending colors fully match
def mylerp(a: float, b: float, t: float) -> float:
    return (1.0 - t) * a + t * b

def color_convert(from_: ColorMode, to: ColorMode, color: TintColor) -> TintColor:
    """
    Extremely ugly monolithic function, but it's best to have the whole thing in a single
    place. I really don't want to keep scouring tiny functions for mistakes
    """
    if from_ == to:
        return color

    if from_ == ColorMode.RGB and to == ColorMode.HSV:
        r, g, b = normalize_rgb(int(color.x), int(color.y), int(color.z))
        r, g, b = colorsys.rgb_to_hsv(r, g, b)
        return TintColor(int(r * 170.0), int(g * 255.0), int(b * 255.0))
    if from_ == ColorMode.HSV and to == ColorMode.RGB:
        h, s, v = normalize_hsv(int(color.x), int(color.y), int(color.z))
        h, s, v = colorsys.hsv_to_rgb(h, s, v)
        return TintColor(int(h * 255.0), int(s * 255.0), int(v * 255.0))

    if from_ == ColorMode.RGB and to == ColorMode.OKLAB:
        l, a, b = linear_rgb_to_oklab(*srgb_to_linear_rgb(*normalize_rgb(int(color.x), int(color.y), int(color.z))))
        return TintColor(l, a, b)
    if from_ == ColorMode.OKLAB and to == ColorMode.RGB:
        r, g, b = linear_rgb_to_srgb(*oklab_to_linear_rgb(color.x, color.y, color.z))
        return TintColor(int(r * 255.0), int(g * 255.0), int(b * 255.0))
    if from_ == ColorMode.HSV and to == ColorMode.OKLAB:
        return color_convert(ColorMode.RGB, ColorMode.OKLAB,
                                color_convert(ColorMode.HSV,
                                                 ColorMode.RGB, color))
    if from_ == ColorMode.OKLAB and to == ColorMode.HSV:
        return color_convert(ColorMode.RGB, ColorMode.HSV,
                                color_convert(ColorMode.OKLAB,
                                                 ColorMode.RGB, color))

    # Fallback
    # TODO: Something like pink missing texture but account
    # for every colormode/colorspace
    return TintColor(0,0,0)

def color_to_hex(mode: ColorMode, color: TintColor) -> str:
    res = color_convert(mode, ColorMode.RGB, color)

    r = int(res.x) & 0xFF
    g = int(res.y) & 0xFF
    b = int(res.z) & 0xFF

    return f"#{r:02x}{g:02x}{b:02x}"

def handle_key(event, down: bool):
    global g_shift_down
    #print(event.keysym)

    if event.keysym == "Shift_L" or event.keysym == "Shift_R":
        g_shift_down = down

def resource_path(relative_path):
  if hasattr(sys, '_MEIPASS'):
      base_path = sys._MEIPASS
  else:
      base_path = os.path.abspath(".")

  return os.path.join(base_path, relative_path)

def open_file():
  global palette, file_path
  file_paths = filedialog.askopenfilenames(title="Select a Palette File", filetypes=[
    ("PNG Files", "*.png"),
    ("Palette Lump", "*.lmp"),
    ("JASC Palette", "*.pal"),
    ("Microsoft Palette", "*.pal"),
    ("Build Engine Palette", "*.DAT"),
    ("Photoshop Palette", "*.act"),
    ("GIMP Palette", "*.gpl"),
    ])
  if not file_paths: return

  # Backup palette just in case our load fails
  palette_backup = []
  if len(palette) != 0:
      palette_backup = copy.deepcopy(palette)

  palette = []
  for file_path in file_paths:
    if file_path.endswith(".png"):
      open_png(file_path)
    elif file_path.endswith(".lmp"):
      open_lmp(file_path)
    elif file_path.endswith(".pal"):
      with open(file_path, "rb") as f:
        header = f.read(12)
        if header.startswith(b"JASC-PAL"):
          open_jasc_pal(file_path)
        else:
          open_ms_pal(file_path)
    elif file_path.endswith(".DAT"):
      open_dat(file_path)
    elif file_path.endswith(".act"):
      open_act(file_path)
    elif file_path.endswith(".gpl"):
      open_gpl(file_path)

  # Restore from aborted load
  if len(palette) == 0 and len(palette_backup) != 0:
      palette = palette_backup

def load_palette():
  for x in range(rows):
    for y in range(cols):
      color_index = x * cols + y
      r, g, b = palette[color_index]
      hex_color = f"#{r:02x}{g:02x}{b:02x}"
      cell_grid[x][y].config(bg=hex_color)

def export_file():
  global file_path
  file_path = filedialog.asksaveasfilename(title="Select a Palette File", filetypes=[
    ("PNG Files", "*.png"),
    ("Palette Lump", "*.lmp"),
    ("JASC Palette", "*.pal"),
    ("Microsoft Palette", "*.mspal"),
    # This is not implemented
    # Requires narrowing conversion from 8 to 6 bit RGB
    #("Build Engine Palette", "*.DAT"),
    ("Photoshop Palette", "*.act"),
    ("GIMP Palette", "*.gpl"),
    ],
    defaultextension="*.*")
  if not file_path: return

  print(file_path)
  if file_path.endswith(".png"):
    export_png()
  elif file_path.endswith(".lmp"):
    export_lmp()
  elif file_path.endswith(".pal"):
    export_jasc_pal()
  elif file_path.endswith(".mspal"):
    export_ms_pal()
  elif file_path.endswith(".act"):
    export_act()
  elif file_path.endswith(".gpl"):
    export_gpl()

def edit_color(row, col):
    """
    Opens a color chooser when a cell is double-clicked and updates the color.
    """
    if not palette:
        return
    # Calculate index of color in flat palette list.
    color_index = row * cols + col
    # Get current color to set as init in colorchooser
    current_rgb = palette[color_index]
    current_hex = f"#{current_rgb[0]:02x}{current_rgb[1]:02x}{current_rgb[2]:02x}"
    # open colorchooser. returns new color or none if canceled
    new_color = colorchooser.askcolor(color=current_hex, title="Select a New Color")
    
    # result is a tuple: ((R, G, B), '#RRGGBB')
    if new_color and new_color[0] is not None:
        # convert new rgb-values (can be floats) into integer tuple
        new_rgb = tuple(map(int, new_color[0]))
        new_hex = new_color[1]
        
        #1. update color in global palette data
        palette[color_index] = new_rgb
        #2. redraw bckgnd color of clicked cell in UI
        cell_grid[row][col].config(bg=new_hex)

def _grid():
  
  for x in range(rows):
    row = []
    for y in range(cols):
      cell = tk.Label(frame, width=4, height=2, bg="white", relief=tk.SUNKEN, bd=2 )
      cell.grid(row=x, column=y)
      cell.bind("<Button-1>", lambda event, ind = (x * cols + y): edit_selection(ind))
      cell.bind("<Double-1>", lambda event, r=x, c=y: edit_color(r, c))
      row.append(cell)
    cell_grid.append(row)

def apply_ramps():
    global ramps
    for ramp in ramps.values():
        ramp_len = float(abs(ramp.start - ramp.end))
        for i in range(ramp.start, ramp.end+1):
            if ramp.skipstart and i == ramp.start:
                continue
            if ramp.skipend and i == ramp.end:
                continue
            factor = (i - ramp.start) / ramp_len

            out = color_convert(ramp.type, ColorMode.RGB, TintColor((mylerp(ramp.startcolor.x, ramp.endcolor.x, factor)),
                          (mylerp(ramp.startcolor.y, ramp.endcolor.y, factor)),
                          (mylerp(ramp.startcolor.z, ramp.endcolor.z, factor))))

            palette[i] = (int(out.x) & 0xFF,
                          int(out.y) & 0xFF,
                          int(out.z) & 0xFF)

    load_palette()

def update_selection():
    for y in range(cols):
        for x in range(rows):
            color_index = x * cols + y
            r, g, b = palette[color_index]

            if g_sel.start != -1:
                if ((g_sel.start <= color_index <= g_sel.end or g_sel.start >= color_index >= g_sel.end) and g_sel.end != -1) or (g_sel.end == -1 and color_index == g_sel.start):
                    r = abs(r - 60)
                    b = 255
                    g = abs(g - 60)

            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            cell_grid[x][y].config(bg=hex_color)


def edit_selection(val):
    global g_sel, g_shift_down
    """
    Selection manager
    Val will set the currently empty point of the selection
    or reset selection if val is -1
    """

    if g_sel.start != -1 and g_shift_down == True:
        g_sel.end = val
    else:
        g_sel.end = -1

    if g_sel.start == -1 or g_shift_down == False:
        g_sel.start = val

    if val == -1:
        g_sel.start = -1
        g_sel.end = -1

    update_selection()


class RampEditorFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.ramp_cnt = 1
        self.ramps_tk = tk.Variable()
        self.curselection = -1
        # Frame + Listbox
        listbox = Listbox(self, width=20, height=10, listvariable=self.ramps_tk, selectmode=tk.SINGLE, exportselection=False)
        listbox_scroll = tk.Scrollbar(self)
        listbox.config(yscrollcommand=listbox_scroll.set)
        listbox_scroll.config(command=listbox.yview)
        add_button = tk.Button(self, text="+", command=self.add_ramp, pady=2)
        trash_button = tk.Button(self, text="trash", pady=2,
                                 command=lambda: self.del_ramp(listbox.curselection()))

        listbox.bind("<<ListboxSelect>>", self.lb_callback)


        listbox.grid(column=0, row=0, rowspan=9, sticky='nw')
        listbox_scroll.grid(column=0, row=0, rowspan=9, sticky='nse')
        self.grid(column=0, row=16, columnspan=16, rowspan=10, sticky='w')
        add_button.grid(column=0, row= 9, padx= 5, sticky='nw')
        trash_button.grid(column=0, row= 9, padx=50, sticky='nw')

        # First column of editor
        colorframe = tk.LabelFrame(self, text="Color Mode")
        colorframe.grid(column=1, row=0, padx=5)
        color_row = 1
        self.colors_var = tk.StringVar()
        colors = ('HSV', 'RGB', 'OKLAB')
        for color in colors:
            colorradio = tk.Radiobutton(colorframe, text=color, value=color, variable=self.colors_var)
            colorradio.grid(column=1, row=color_row, sticky='w')
            color_row += 1

        skipframe = tk.LabelFrame(self, text="Skip")
        self.skipstart_var = tk.IntVar()
        self.skipend_var = tk.IntVar()
        skipstart_btn = tk.Checkbutton(skipframe, text="Start", variable=self.skipstart_var, onvalue=1, offvalue=0)
        skipend_btn = tk.Checkbutton(skipframe, text="End", variable=self.skipend_var, onvalue=1, offvalue=0)
        skipframe.grid(column=1, row=color_row + 1, padx=5, sticky='w')
        skipstart_btn.grid(column=1, row=color_row + 2, sticky='w')
        skipend_btn.grid(column=1, row=color_row + 3, sticky='w')

        # Second column of editor
        startcolor_frame = tk.LabelFrame(self, text="Start Color")
        self.startcolor_color_frame = tk.Frame(startcolor_frame, bg="black", width=50, height=60)

        startcolor_frame.grid(column=2, row= 0, columnspan=3, rowspan=3, padx=5, sticky='nw')
        self.startcolor_color_frame.grid(column=2, row=1, rowspan=3, padx=5, pady=5)

        self.startcolor_x = tk.StringVar()
        self.startcolor_x_label = tk.Label(startcolor_frame, text="R")
        self.startcolor_x_sb = tk.Spinbox(startcolor_frame, from_=0, to=255, textvariable=self.startcolor_x, wrap=False, width=5)
        self.startcolor_x_label.grid(column=3, row=1, padx=5, sticky='w')
        self.startcolor_x_sb.grid(column=4, row = 1, padx=5, sticky='w')

        self.startcolor_y = tk.StringVar()
        self.startcolor_y_label = tk.Label(startcolor_frame, text="G")
        self.startcolor_y_sb = tk.Spinbox(startcolor_frame, from_=0, to=255, textvariable=self.startcolor_y, wrap=False, width=5)
        self.startcolor_y_label.grid(column=3, row=2, padx=5, sticky='w')
        self.startcolor_y_sb.grid(column=4, row = 2, padx=5, sticky='w')

        self.startcolor_z = tk.StringVar()
        self.startcolor_z_label = tk.Label(startcolor_frame, text="B")
        self.startcolor_z_sb = tk.Spinbox(startcolor_frame, from_=0, to=255, textvariable=self.startcolor_z, wrap=False, width=5)
        self.startcolor_z_label.grid(column=3, row=3, padx=5, sticky='w')
        self.startcolor_z_sb.grid(column=4, row = 3, padx=5, sticky='w')


        endcolor_frame = tk.LabelFrame(self, text="End Color")
        self.endcolor_color_frame = tk.Frame(endcolor_frame, bg="black", width=50, height=60)

        endcolor_frame.grid(column=2, row=4, columnspan=3, rowspan=3, padx=5, sticky='nw')
        self.endcolor_color_frame.grid(column=2, row=5, rowspan=3, padx=5, pady=5)

        self.endcolor_x = tk.StringVar()
        self.endcolor_x_label = tk.Label(endcolor_frame, text="R")
        self.endcolor_x_sb = tk.Spinbox(endcolor_frame, from_=0, to=255, textvariable=self.endcolor_x, wrap=False, width=5)
        self.endcolor_x_label.grid(column=3, row=5, padx=5, sticky='w')
        self.endcolor_x_sb.grid(column=4, row = 5, padx=5, sticky='w')

        self.endcolor_y = tk.StringVar()
        self.endcolor_y_label = tk.Label(endcolor_frame, text="G")
        self.endcolor_y_sb = tk.Spinbox(endcolor_frame, from_=0, to=255, textvariable=self.endcolor_y, wrap=False, width=5)
        self.endcolor_y_label.grid(column=3, row=6, padx=5, sticky='w')
        self.endcolor_y_sb.grid(column=4, row = 6, padx=5, sticky='w')

        self.endcolor_z = tk.StringVar()
        self.endcolor_z_label = tk.Label(endcolor_frame, text="B")
        self.endcolor_z_sb = tk.Spinbox(endcolor_frame, from_=0, to=255, textvariable=self.endcolor_z, wrap=False, width=5)
        self.endcolor_z_label.grid(column=3, row=7, padx=5, sticky='w')
        self.endcolor_z_sb.grid(column=4, row = 7, padx=5, sticky='w')

        apply_btn = tk.Button(self, text='Apply', height=2, width=5, command=self.apply_settings)
        apply_btn.grid(column=7, row=5, padx=5, pady=5)

    def update_editor_colors(self, mode: ColorMode, startcolor: TintColor, endcolor: TintColor):
        self.colors_var.set(mode.name)
        self.startcolor_x.set(str(startcolor.x))
        self.startcolor_y.set(str(startcolor.y))
        self.startcolor_z.set(str(startcolor.z))
        self.endcolor_x.set(str(endcolor.x))
        self.endcolor_y.set(str(endcolor.y))
        self.endcolor_z.set(str(endcolor.z))

        self.startcolor_color_frame.config(bg=color_to_hex(mode, startcolor))
        self.endcolor_color_frame.config(bg=color_to_hex(mode, endcolor))

    def apply_settings(self):
        global ramps
        if not self.curselection in ramps.keys():
            return

        ramps[self.curselection].type = ColorMode[self.colors_var.get()]
        ramps[self.curselection].startcolor.x = float(self.startcolor_x.get())
        ramps[self.curselection].startcolor.y = float(self.startcolor_y.get())
        ramps[self.curselection].startcolor.z = float(self.startcolor_z.get())
        ramps[self.curselection].endcolor.x = float(self.endcolor_x.get())
        ramps[self.curselection].endcolor.y = float(self.endcolor_y.get())
        ramps[self.curselection].endcolor.z = float(self.endcolor_z.get())
        ramps[self.curselection].skipstart = bool(self.skipstart_var.get())
        ramps[self.curselection].skipend = bool(self.skipend_var.get())
        apply_ramps()


    def lb_callback(self, event):
        global ramps
        sel = event.widget.curselection()
        idx = 0
        try:
            idx = self.ramps_tk.get()[sel[0]]
        except IndexError:
            return
        self.curselection = idx
        self.update_editor_colors(ramps[idx].type, ramps[idx].startcolor, ramps[idx].endcolor)
        self.skipstart_var.set(int(ramps[idx].skipstart))
        self.skipend_var.set(int(ramps[idx].skipend))

    def add_ramp(self):
        global ramps
        """
        Creates a ramp based off of selection
        """

        if g_sel.end == -1:
            return

        ramps[self.ramp_cnt] = (TintRamp(g_sel.start,
                              g_sel.end,
                              ColorMode.HSV,
                              TintColor(0,0,0),
                              TintColor(0,0,0),
                              1,
                              False,
                              False)
                     )
        self.ramp_cnt += 1
        self.ramps_tk.set(value=tuple(ramps.keys()))
        print("Added ramp!")

    def del_ramp(self, list_sel):
        global ramps
        # Real ugly lazy solution to avoid checking whether
        # we have anything selected in the listbox
        try:
            idx = self.ramps_tk.get()[list_sel[0]]
            del ramps[idx]
            self.ramps_tk.set(value=tuple(ramps.keys()))
        except IndexError:
            pass


def open_png(file_path):
  image = Image.open(file_path)
  image = image.convert("RGB")
  width, height = image.size

  if (width, height) != (16, 16):
    messagebox.showerror("Error", f"Invalid image size. Select an image with a size of 16x16.")
    return
  
  for x in range(rows):
    for y in range(cols):
      color = image.getpixel((y,x))
      palette.append(color)
      hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
      cell_grid[x][y].config(bg=hex_color)

def open_lmp(file_path):
    """
    Reads a Quake-format .lmp file and loads it into the palette grid.
    """
    try:
        with open(file_path, "rb") as f:
            pal_data = f.read()
    except IOError as e:
        messagebox.showerror("Error", f"Could not read file {file_path}: {e}")
        return

    if len(pal_data) != 768:
        messagebox.showerror("Error", f"Invalid Quake Palette file. Expected 768 bytes, got {len(pal_data)}.")
        return

    for i in range(0, 768, 3):
        r, g, b = pal_data[i:i+3]
        palette.append((r, g, b))

    load_palette()

def open_jasc_pal(file_path):
  with open(file_path, "r") as f:
    data = f.readlines()

  if data[0].strip() != "JASC-PAL" or data[1].strip() != "0100":
    messagebox.showerror("Error", "Invalid JASC Palette file.")

  for line in data[3:]:
    line = line.strip()
    parts = line.split()
    if len(parts) == 1 and parts[0].startswith("#"):
      hex_color = line.lstrip("#")
      r = int(hex_color[0:2], 16)
      g = int(hex_color[2:4], 16)
      b = int(hex_color[4:6], 16)
    elif len(parts) == 3 and all(part.isdigit() for part in parts):
      r, g, b = map(int, parts)
    elif len(parts) == 4 and all(parts[i].isdigit() for i in [0, 1, 2]) and parts[3].startswith("#"):
      r, g, b = map(int, parts[:3])
      
    palette.append((r, g, b))
  
  load_palette()

def open_dat(file_path):
  with open(file_path, "rb") as f:
    data = f.read()

  for i in range(256):
    r = data[i * 3] * 4
    g = data[i * 3 + 1] * 4
    b = data[i * 3 + 2] * 4
    palette.append((r, g, b))

  load_palette()

def open_act(file_path):
  with open(file_path, "rb") as f:
    data = f.read()

  for i in range(0, 768, 3):
    r, g, b = data[i:i+3]
    palette.append((r, g, b))

  load_palette()

def open_ms_pal(file_path):
  with open(file_path, "rb") as f:
    data = f.read()
  
  if data[:4] != b"RIFF":
    messagebox.showerror("Error", "Invalid Microsoft PAL file.")
    return

  offset = 24
  for _ in range(256):
    r = data[offset]
    g = data[offset + 1]
    b = data[offset + 2]
    palette.append((r, g, b))
    offset += 4
  
  load_palette()

def open_gpl(file_path):
  with open(file_path, "r") as f:
    data = f.readlines()

  if data[0].strip() != "GIMP Palette":
    messagebox.showerror("Error", "Invalid GIMP Palette file.")

  for line in data[4:]:
    line = line.strip()
    parts = line.split()
    r = int(parts[0])
    g = int(parts[1])
    b = int(parts[2])
    palette.append((r, g, b))
  
  load_palette()

def export_gpl():
  global file_path

  file_name = os.path.basename(file_path)
  file_name_ne, _ = os.path.splitext(file_name)
  flat_palette = [component for color in palette for component in color]

  with open(file_path, "w") as f:
    f.write("GIMP Palette\n")
    f.write(f"Name: {file_name_ne}\n")
    f.write("Columns: 16\n")
    f.write("#\n")
  
    for i in range(0, len(flat_palette), 3):
        r = flat_palette[i]
        g = flat_palette[i + 1]
        b = flat_palette[i + 2]
        f.write(f"{r}\t{g}\t{b}\n")
  
def export_jasc_pal():
  global file_path

  flat_palette = [component for color in palette for component in color]

  with open(file_path, "w") as f:
    f.write("JASC-PAL\n")
    f.write("0100\n")
    f.write("256\n")
  
    for i in range(0, len(flat_palette), 3):
      r = flat_palette[i]
      g = flat_palette[i + 1]
      b = flat_palette[i + 2]
      f.write(f"{r}\t{g}\t{b}\n")

def export_ms_pal():
  global file_path

  if file_path.endswith(".mspal"): 
    file_path = file_path[:-5] + "pal"

  with open(file_path, "wb") as f:
    f.write(b"RIFF")
    file_size = 20 + len(palette) * 4
    f.write((file_size - 8).to_bytes(4, "little"))
    f.write(b"PAL ")
    f.write(b"data")
    f.write((file_size - 20).to_bytes(4, "little"))
    f.write(b"\x03\x00")
    f.write(len(palette).to_bytes(2, "little"))
    
    for r, g, b in palette:
      f.write(bytes([r, g, b, 0]))

def export_act():
  global file_path

  flat_palette = [component for color in palette for component in color]

  with open(file_path, "wb") as f:
    f.write(bytes(flat_palette))

def export_lmp():
    """
    Writes the current palette data to a Quake-format .lmp file.
    """
    global file_path

    # Flatten the list of (r, g, b) tuples into a single bytes object.
    pal_data = bytes([component for color in palette for component in color])

    if len(pal_data) != 768:
        messagebox.showerror("Error", f"Palette data is incorrect size for .lmp file. Expected 768 bytes, got {len(pal_data)}.")
        return
        
    try:
        with open(file_path, "wb") as f_lmp:
            f_lmp.write(pal_data)
    except IOError as e:
        messagebox.showerror("Error", f"Error writing to {file_path}: {e}")

def export_png():
  global file_path

  image = Image.new("P", (16,16))

  flat_palette = [component for color in palette for component in color]

  image.putpalette(flat_palette)

  for x in range(rows):
    for y in range(cols):
      color_index = x * rows + y
      image.putpixel((y,x), color_index)

  image.save(file_path, format="PNG")

def about():
    message = """
        Palpatine 256
        v1.15
        © 2025 voidsrc
        contact@voidsrc.com
    """
    about_window = tk.Toplevel()
    about_window.title("About Palpatine 256")
    about_window.geometry("350x100")
    about_window.resizable(False, False)

    # Proper cross platform window
    if sys.platform == "win32":
        about_window.attributes('-toolwindow', True)
  
    frame = tk.Frame(about_window)
    frame.pack(padx=5, pady=5)


    icon_label = tk.Label(frame, image=ICON_IMG)
    icon_label.image = ICON_IMG
    icon_label.grid(row=0, column=0)

    text_label = tk.Label(frame, text=message, justify="left", anchor="w")
    text_label.grid(row=0, column=1, sticky="w")

    ok_button = tk.Button(frame, text="Ok", padx=30, pady=2, command=about_window.destroy)
    ok_button.grid(row=0, column=2, padx=5)

def help():
  message = """
Palpatine 256 supports the conversion of PNG, Quake Palette,
Microsoft Palette, JASC Palette, Build Engine PALETTE.DAT,
GIMP GPL, and Photoshop ACT palettes to 8-bit PNG, 
Palette LMP, Microsoft Palette, JASC Palette, GIMP GPL, 
or Photoshop ACT, while preserving the original index order of 
the source file.

You can create a source image in any graphics editor and save it
as a 16×16 PNG file for use with Palpatine 256.

Importing a Palette
1. Go to File > Import File.
2. Choose the appropriate file extension to load as a source palette.

Exporting a Palette
1. Go to File > Export File.
2. Select the desired file extension to save the palette in.

Example
If you have a PNG palette file named my_palette.png (16×16), choose 
PNG as the extension when importing. To convert it into a GIMP .gpl 
file, select File > Export File and choose GIMP .gpl.

---------------------------------------------------------------------

Credits to Pup Luka for .lmp file support,
and color editing implementation.
 - aeroxsoftware@null.net -
"""
  help_window = tk.Toplevel()
  help_window.title("Help Palpatine 256")
  help_window.geometry("600x320")
  help_window.resizable(False, False)
  help_window.iconphoto(True, ICON_IMG)

  frame = tk.Frame(help_window)
  frame.pack(padx=5, pady=5)

  text = scrolledtext.ScrolledText(frame, wrap="none")
  text.pack()
  text.tag_configure("margin", lmargin1=10)
  text.insert("1.0", message, "margin")

root = tk.Tk()
root.title("Palpatine 256")
root.geometry("610x775")
root.resizable(0,0)

# ugly place to do this but it's gotta be after tk has been initialized
ICON_IMG = tk.PhotoImage(master=root, file=resource_path("icon.png"))
root.iconphoto(True, ICON_IMG)

frame = tk.Frame(root)
frame.pack(expand=True)

menu = tk.Menu(root)
file_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="File", menu=file_menu)
import_file = tk.Menu(file_menu, tearoff=0)
file_menu.add_command(label="Import File...", command=open_file, accelerator="Ctrl+O")
file_menu.add_separator()
file_menu.add_command(label="Export File...", command=export_file, accelerator="Ctrl+S")
file_menu.add_separator()
file_menu.add_command(label="Exit", command=lambda: root.destroy(), accelerator="Ctrl+Q")
help_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="Help", menu=help_menu)
help_menu.add_command(label="Help", command=help, accelerator="Ctrl+H")
help_menu.add_separator()
help_menu.add_command(label="About", command=about)

root.config(menu=menu)

# Fill up palette, so that we can have
# selections without loading a ready made one
for _ in range(256):
    palette.append((255, 255, 255))

_grid()
#_range_editor()
test = RampEditorFrame(frame)

root.bind("<Control-o>", lambda event: open_file())
root.bind("<Control-s>", lambda event: export_file())
root.bind("<Control-h>", lambda event: help())
root.bind("<Control-q>", lambda event: root.destroy())
root.bind("<Escape>", lambda event: edit_selection(-1))

# Used to implement alternative modes eg holding down shift
root.bind("<KeyPress>", lambda event: handle_key(event, True))
root.bind("<KeyRelease>", lambda event: handle_key(event, False))

root.mainloop()
