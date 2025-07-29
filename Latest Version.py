import tkinter as tk
from tkinter import ttk
import math
import json
import os
import sv_ttk
import numpy as np
from functools import lru_cache
import weakref
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL not available - textures will not be supported")


# Global texture cache to prevent memory leaks and improve performance
_texture_cache = {}
_max_cache_size = 1000  # Limit cache size

def clear_old_cache_entries():
    """Clear oldest cache entries when cache gets too large"""
    global _texture_cache
    if len(_texture_cache) > _max_cache_size:
        # Remove oldest 20% of entries
        items = list(_texture_cache.items())
        to_remove = len(items) // 5
        for i in range(to_remove):
            del _texture_cache[items[i][0]]


@lru_cache(maxsize=128)
def _find_perspective_coeffs_cached(src_pts_tuple, dst_pts_tuple):
    """Cached version of perspective coefficient calculation"""
    src_pts = [list(pt) for pt in src_pts_tuple]
    dst_pts = [list(pt) for pt in dst_pts_tuple]
    
    A = []
    b = []
    for (xs, ys), (xd, yd) in zip(src_pts, dst_pts):
        A.append([ xs, ys, 1,   0,   0, 0, -xd*xs, -xd*ys ])
        A.append([  0,   0, 0,  xs,  ys, 1, -yd*xs, -yd*ys ])
        b.extend([xd, yd])
    A = np.array(A, dtype=np.float64)
    b = np.array(b, dtype=np.float64)
    return tuple(np.linalg.solve(A, b))


def apply_shading_to_image(image, factor):
    """Apply darkening/lightening to an image"""
    if factor == 1.0:
        return image
    
    # Convert to numpy array for faster processing
    img_array = np.array(image)
    
    # Apply factor to RGB channels, keep alpha unchanged
    img_array[:, :, :3] = np.clip(img_array[:, :, :3] * factor, 0, 255).astype(np.uint8)
    
    return Image.fromarray(img_array)


def skew_to_trapezoid_optimized(path, direction, size, factor=0.2):
    """
    Optimized version with global caching, size parameter, and shading
    """
    global _texture_cache
    
    # Determine shading factor based on direction (matching fallback block shading)
    if direction == 'top':
        shade_factor = 1.2  # Brighten top face
    elif direction == 'left':
        shade_factor = 0.8  # Darken left face
    elif direction == 'right':
        shade_factor = 0.6  # Darken right face more
    else:
        shade_factor = 1.0
    
    # Create cache key including all parameters and shading
    cache_key = f"{path}_{direction}_{size}_{factor}_{shade_factor}"
    
    if cache_key in _texture_cache:
        return _texture_cache[cache_key]
    
    try:
        im = Image.open(path).convert("RGBA")
        original_size = im.size[0]
        
        # Resize image first if needed
        if original_size != size:
            im = im.resize((size, size), Image.LANCZOS)
        
        # Apply shading before transformation
        if shade_factor != 1.0:
            im = apply_shading_to_image(im, shade_factor)
        
        w, h = size, size
        height = size / 2

        # center‑top of diamond:
        x = size / 2
        y = 0

        # four corners of the target trapezoid
        if direction == 'top':
           dst = [
               ( x,              y               ),  # top
               ( x + size/2,     y + size/4      ),  # right
               ( x,              y + size/2      ),  # bottom
               ( x - size/2,     y + size/4      )   # left
           ]
        elif direction == 'left':
           dst = [
               ( x - size/2,     y + size/4          ),  # UL
               ( x,              y + size/2          ),  # UR
               ( x,              y + size/2 + height ),  # LR
               ( x - size/2,     y + size/4 + height )   # LL
           ]
        elif direction == 'right':
           dst = [
               ( x,              y + size/2          ),  # UL
               ( x + size/2,     y + size/4          ),  # UR
               ( x + size/2,     y + size/4 + height ),  # LR
               ( x,              y + size/2 + height )   # LL
           ]
        else:
            raise ValueError("direction must be 'left','right' or 'top'")
        
        src = [(0, 0), (size, 0), (size, size), (0, size)]

        # Use cached coefficient calculation
        src_tuple = tuple(tuple(pt) for pt in src)
        dst_tuple = tuple(tuple(pt) for pt in dst)
        coeffs = _find_perspective_coeffs_cached(dst_tuple, src_tuple)

        # warp
        out = im.transform(
            (w, h),
            Image.PERSPECTIVE,
            data=coeffs,
            resample=Image.BICUBIC,
            fillcolor=(0, 0, 0, 0)  # transparent
        )

        # Cache the result
        photo_image = ImageTk.PhotoImage(out)
        _texture_cache[cache_key] = photo_image
        
        # Clean old entries if cache is getting large
        clear_old_cache_entries()
        
        return photo_image
        
    except Exception as e:
        print(f"Texture generation error: {e}")
        return None


class MinecraftBlock:
    """Represents a Minecraft block with its properties"""
    def __init__(self, name, color, texture_path=None):
        self.name = name
        self.color = color
        self.texture_path = texture_path
        # Remove individual texture caching from blocks - use global cache instead


class MinecraftBuildPreview:
    # Constants
    BLOCK_SIZE_ISO = 16
    BLOCK_HEIGHT_ISO = 8
    BLOCK_HEIGHT_RATIO = 0.5

    DEFAULT_CANVAS_WIDTH = 400
    DEFAULT_CANVAS_HEIGHT = 400
    ISO_CANVAS_WIDTH = 500
    ISO_CANVAS_HEIGHT = 500
    MIN_ZOOM = 0.01
    MAX_ZOOM = 10.0
    ZOOM_FACTOR = 1.1
    
    # Performance constants
    REDRAW_DELAY = 16  # ~60 FPS limit
    ZOOM_CACHE_THRESHOLD = 0.1  # Only cache textures for zoom levels that differ by this much
    
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Build Preview")
        self.root.geometry("1920x1080")
        
        # Build data - 3D array [x][z][y]
        self.build_size = 16
        self.build_data = {}  # Dictionary with (x,z,y) as keys
        self.current_y = 0
        self.current_block = "stone"
        
        # Isometric view settings
        self.iso_rotation = 0  # 0, 90, 180, 270 degrees
        self.iso_zoom = 5.0
        self.iso_offset_x = 0
        self.iso_offset_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        
        # Performance optimization flags
        self._pending_grid_update = False
        self._pending_iso_update = False
        self._last_canvas_size = (0, 0)
        self._cached_canvas_dimensions = {}
        
        # Pre-calculate color variations
        self._color_cache = {}
        
        # Dark mode settings - Initialize before setup_ui
        self.dark_mode = False
        self.themes = {
            'light': {
                'bg': '#f0f0f0',
                'canvas_bg': 'white',
                'iso_canvas_bg': 'lightblue',
                'text': 'black',
                'grid_line': 'gray',
                'ghost_outline': 'lightgray'
            },
            'dark': {
                'bg': '#2d2d2d',
                'canvas_bg': '#404040',
                'iso_canvas_bg': '#1a1a2e',
                'text': 'white',
                'grid_line': '#666666',
                'ghost_outline': '#555555'
            }
        }
        
        # Initialize blocks
        self.init_blocks()
        
        # Setup UI
        self.setup_ui()
        
        # Bind window events
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Initial render (delayed to ensure proper canvas sizing)
        self.root.after(100, self.initial_render)
    
    def init_blocks(self):
        """Initialize available Minecraft blocks"""
        self.blocks = {
            "air": MinecraftBlock("Air", "#FFFFFF"),
            "stone": MinecraftBlock("Stone", "#7F7F7F"),
            "dirt": MinecraftBlock("Dirt", "#8B4513"),
            "grass": MinecraftBlock("Grass Block", "#228B22"),
            "cobblestone": MinecraftBlock("Cobblestone", "#696969"),
            "wood_planks": MinecraftBlock("Wood Planks", "#DEB887"),
            "wood_log": MinecraftBlock("Wood Log", "#8B4513"),
            "leaves": MinecraftBlock("Leaves", "#228B22"),
            "sand": MinecraftBlock("Sand", "#F4A460"),
            "gravel": MinecraftBlock("Gravel", "#808080"),
            "gold_ore": MinecraftBlock("Gold Ore", "#FFD700"),
            "iron_ore": MinecraftBlock("Iron Ore", "#CD853F"),
            "coal_ore": MinecraftBlock("Coal Ore", "#2F4F4F"),
            "diamond_ore": MinecraftBlock("Diamond Ore", "#4169E1"),
            "emerald_ore": MinecraftBlock("Emerald Ore", "#50C878"),
            "bedrock": MinecraftBlock("Bedrock", "#36454F"),
            "water": MinecraftBlock("Water", "#4682B4"),
            "lava": MinecraftBlock("Lava", "#FF4500"),
            "obsidian": MinecraftBlock("Obsidian", "#1C1C1C"),
            "glass": MinecraftBlock("Glass", "#E0FFFF"),
            "brick": MinecraftBlock("Bricks", "#B22222"),
            "tnt": MinecraftBlock("TNT", "#FF0000"),
            "bookshelf": MinecraftBlock("Bookshelf", "#8B4513"),
            "mossy_cobblestone": MinecraftBlock("Mossy Cobblestone", "#6B8E23"),
            "snow": MinecraftBlock("Snow Block", "#FFFAFA"),
            "ice": MinecraftBlock("Ice", "#B0E0E6"),
            "clay": MinecraftBlock("Clay", "#A0522D"),
            "pumpkin": MinecraftBlock("Pumpkin", "#FF8C00"),
            "netherrack": MinecraftBlock("Netherrack", "#8B0000"),
            "soul_sand": MinecraftBlock("Soul Sand", "#654321"),
            "glowstone": MinecraftBlock("Glowstone", "#FFFF99"),
            "wool_white": MinecraftBlock("White Wool", "#FFFFFF"),
            "wool_black": MinecraftBlock("Black Wool", "#000000"),
            "wool_red": MinecraftBlock("Red Wool", "#FF0000"),
            "wool_blue": MinecraftBlock("Blue Wool", "#0000FF"),
            "wool_green": MinecraftBlock("Green Wool", "#008000"),
            "wool_yellow": MinecraftBlock("Yellow Wool", "#FFFF00"),
            "wool_orange": MinecraftBlock("Orange Wool", "#FFA500"),
            "wool_purple": MinecraftBlock("Purple Wool", "#800080"),
            "wool_pink": MinecraftBlock("Pink Wool", "#FFC0CB"),
            "concrete_white": MinecraftBlock("White Concrete", "#F0F0F0"),
            "concrete_black": MinecraftBlock("Black Concrete", "#1A1A1A"),
            "concrete_red": MinecraftBlock("Red Concrete", "#CC0000"),
            "concrete_blue": MinecraftBlock("Blue Concrete", "#003399"),
            "concrete_green": MinecraftBlock("Green Concrete", "#006600"),
            "concrete_yellow": MinecraftBlock("Yellow Concrete", "#CCCC00"),
            "quartz": MinecraftBlock("Quartz Block", "#F5F5F5"),
            "prismarine": MinecraftBlock("Prismarine", "#5F9EA0"),
            "end_stone": MinecraftBlock("End Stone", "#E6E6B8"),
            "purpur": MinecraftBlock("Purpur Block", "#A569BD"),
            "magma": MinecraftBlock("Magma Block", "#8B0000"),
            "sea_lantern": MinecraftBlock("Sea Lantern", "#B0E0E6"),
            "terracotta": MinecraftBlock("Terracotta", "#A0522D"),
            "glazed_terracotta": MinecraftBlock("Glazed Terracotta", "#D2691E"),
            "sandstone": MinecraftBlock("Sandstone", "#F4A460"),
            "red_sandstone": MinecraftBlock("Red Sandstone", "#CD853F"),
            "granite": MinecraftBlock("Granite", "#A0522D"),
            "diorite": MinecraftBlock("Diorite", "#D3D3D3"),
            "andesite": MinecraftBlock("Andesite", "#696969"),
        }
        
        # Pre-calculate color variations for all blocks
        self._precalculate_colors()
    
    def _precalculate_colors(self):
        """Pre-calculate all color variations to avoid runtime computation"""
        factors = [0.6, 0.8, 1.2]  # right, left, top
        for block_name, block in self.blocks.items():
            self._color_cache[block_name] = {}
            for factor in factors:
                self._color_cache[block_name][factor] = self.lighten_color(block.color, factor)
    
    def setup_ui(self):
        """Setup the user interface"""

    
        
        # This is where the magic happens
        sv_ttk.set_theme("dark")
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side - Isometric view
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Isometric controls
        iso_controls = ttk.Frame(left_frame)
        iso_controls.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(iso_controls, text="3D Preview:").pack(side=tk.LEFT)
        
        ttk.Button(iso_controls, text="↺ 90°", 
                  command=self.rotate_left).pack(side=tk.LEFT, padx=5)
        ttk.Button(iso_controls, text="↻ 90°", 
                  command=self.rotate_right).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(iso_controls, text="Reset View", 
                  command=self.reset_view).pack(side=tk.LEFT, padx=5)
        
        # Add save/load buttons
        ttk.Button(iso_controls, text="Save Build", 
                  command=self.save_build).pack(side=tk.LEFT, padx=5)
        ttk.Button(iso_controls, text="Load Build", 
                  command=self.load_build).pack(side=tk.LEFT, padx=5)
        ttk.Button(iso_controls, text="Clear All", 
                  command=self.clear_build).pack(side=tk.LEFT, padx=5)
        
        # Dark mode toggle
        #ttk.Button(iso_controls, text="🌙 Dark Mode", 
        #          command=self.toggle_dark_mode).pack(side=tk.LEFT, padx=5)
        
        # Isometric canvas
        self.iso_canvas = tk.Canvas(left_frame, bg=self.get_theme_color('iso_canvas_bg'), 
                                   width=self.ISO_CANVAS_WIDTH, height=self.ISO_CANVAS_HEIGHT)
        self.iso_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind mouse events for panning
        self.iso_canvas.bind("<Button-1>", self.start_pan)
        self.iso_canvas.bind("<B1-Motion>", self.do_pan)
        self.iso_canvas.bind("<ButtonRelease-1>", self.end_pan)
        
        # Cross-platform mouse wheel binding
        self.iso_canvas.bind("<MouseWheel>", self.zoom_iso)  # Windows/Mac
        self.iso_canvas.bind("<Button-4>", self.zoom_iso)    # Linux
        self.iso_canvas.bind("<Button-5>", self.zoom_iso)    # Linux
        
        # Right side - Grid and controls
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH)
        
        # Y-layer control
        y_controls = ttk.Frame(right_frame)
        y_controls.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(y_controls, text="Y Layer:").pack(side=tk.LEFT)
        self.y_var = tk.IntVar(value=0)
        self.y_scale = ttk.Scale(y_controls, from_=0, to=15, 
                                orient=tk.HORIZONTAL, variable=self.y_var,
                                command=self.change_y_layer)
        self.y_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.y_label = ttk.Label(y_controls, text="0")
        self.y_label.pack(side=tk.RIGHT)
        
        # Block selector with preview
        block_frame = ttk.Frame(right_frame)
        block_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(block_frame, text="Block:").pack(side=tk.TOP, anchor=tk.W)
        
        block_selector_frame = ttk.Frame(block_frame)
        block_selector_frame.pack(fill=tk.X)
        
        self.block_var = tk.StringVar(value="stone")
        block_combo = ttk.Combobox(block_selector_frame, textvariable=self.block_var,
                                  values=list(self.blocks.keys()), state="readonly")
        block_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        block_combo.bind("<<ComboboxSelected>>", self.change_block)
        
        # Block color preview
        self.block_preview = tk.Canvas(block_selector_frame, width=30, height=20, 
                                      bg=self.blocks["stone"].color)
        self.block_preview.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Build info
        info_frame = ttk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.info_label = ttk.Label(info_frame, text="Blocks: 0")
        self.info_label.pack(side=tk.LEFT)
        
        # Grid canvas
        grid_frame = ttk.Frame(right_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        self.grid_canvas = tk.Canvas(grid_frame, bg=self.get_theme_color('canvas_bg'), 
                                    width=self.DEFAULT_CANVAS_WIDTH, 
                                    height=self.DEFAULT_CANVAS_HEIGHT)
        self.grid_canvas.pack(padx=10, pady=10)
        
        # Bind grid click events
        self.grid_canvas.bind("<Button-1>", self.grid_click)
        self.grid_canvas.bind("<B1-Motion>", self.grid_drag)
        self.grid_canvas.bind("<Motion>", self.grid_hover)
        self.grid_canvas.bind("<Leave>", self.grid_leave)
        
        # Hover state tracking
        self.hover_x = -1
        self.hover_z = -1
        self.hover_outline_id = None
    
    def get_theme_color(self, key):
        """Get color for current theme"""
        theme = 'dark' if self.dark_mode else 'light'
        return self.themes[theme][key]
    
    def toggle_dark_mode(self):
        """Toggle between light and dark mode"""
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        
        # Update button text
        button_text = "☀️ Light Mode" if self.dark_mode else "🌙 Dark Mode"
        # Find and update the dark mode button
        for widget in self.root.winfo_children():
            self._update_dark_mode_button(widget, button_text)
    
    def _update_dark_mode_button(self, widget, button_text):
        """Recursively find and update dark mode button text"""
        if isinstance(widget, ttk.Button):
            current_text = widget.cget('text')
            if '🌙' in current_text or '☀️' in current_text:
                widget.config(text=button_text)
        
        # Check children
        for child in widget.winfo_children():
            self._update_dark_mode_button(child, button_text)
    
    def apply_theme(self):
        """Apply current theme to all UI elements"""
        # Configure root window
        self.root.configure(bg=self.get_theme_color('bg'))
        
        # Update canvas backgrounds
        self.grid_canvas.configure(bg=self.get_theme_color('canvas_bg'))
        self.iso_canvas.configure(bg=self.get_theme_color('iso_canvas_bg'))
        
        # Update all frames recursively
        self._apply_theme_to_widget(self.root)
        
        # Trigger grid and isometric updates to reflect new colors
        self.schedule_grid_update()
        self.schedule_iso_update()
    
    def _apply_theme_to_widget(self, widget):
        """Recursively apply theme to widgets"""
        widget_class = widget.winfo_class()
        
        # Apply theme to different widget types
        if widget_class == 'Frame':
            widget.configure(bg=self.get_theme_color('bg'))
        elif widget_class == 'Label':
            widget.configure(bg=self.get_theme_color('bg'), fg=self.get_theme_color('text'))
        elif widget_class == 'Canvas' and widget != self.grid_canvas and widget != self.iso_canvas:
            # Don't change main canvases, but update other canvases like block preview
            if hasattr(widget, 'master') and 'preview' in str(widget):
                # Keep block preview colors as they are
                pass
        
        # Recursively apply to children
        for child in widget.winfo_children():
            self._apply_theme_to_widget(child)
    
    def change_y_layer(self, value):
        """Handle Y layer change"""
        self.current_y = int(float(value))
        self.y_label.config(text=str(self.current_y))
        self.schedule_grid_update()
    
    def change_block(self, event=None):
        """Handle block type change"""
        self.current_block = self.block_var.get()
        if self.current_block in self.blocks:
            # Update block preview color
            block_color = self.blocks[self.current_block].color
            self.block_preview.config(bg=block_color)
            self.update_info()
    
    def grid_click(self, event):
        """Handle grid click to place blocks"""
        self.place_block_at_click(event.x, event.y)
    
    def grid_drag(self, event):
        """Handle grid drag to paint blocks"""
        self.place_block_at_click(event.x, event.y)
    
    def grid_hover(self, event):
        """Handle mouse hover over grid to show red outline"""
        try:
            canvas_width, canvas_height = self.get_canvas_dimensions('grid')
            
            cell_width = canvas_width / self.build_size
            cell_height = canvas_height / self.build_size
            
            grid_x = int(event.x / cell_width)
            grid_z = int(event.y / cell_height)
            
            # Check if we're within grid bounds
            if 0 <= grid_x < self.build_size and 0 <= grid_z < self.build_size:
                # Only update if hover position changed
                if grid_x != self.hover_x or grid_z != self.hover_z:
                    # Remove old hover outline
                    if self.hover_outline_id:
                        self.grid_canvas.delete(self.hover_outline_id)
                        self.hover_outline_id = None
                    
                    # Update hover position
                    self.hover_x = grid_x
                    self.hover_z = grid_z
                    
                    # Draw new hover outline
                    x1 = grid_x * cell_width
                    y1 = grid_z * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height
                    
                    self.hover_outline_id = self.grid_canvas.create_rectangle(
                        x1, y1, x2, y2,
                        fill="",
                        outline="red",
                        width=2
                    )
            else:
                # Mouse is outside grid bounds
                self.clear_hover_outline()
                
        except Exception as e:
            print(f"Error in grid hover: {e}")
    
    def grid_leave(self, event):
        """Handle mouse leaving the grid canvas"""
        self.clear_hover_outline()
    
    def clear_hover_outline(self):
        """Clear the hover outline"""
        if self.hover_outline_id:
            self.grid_canvas.delete(self.hover_outline_id)
            self.hover_outline_id = None
        self.hover_x = -1
        self.hover_z = -1
    
    def place_block_at_click(self, click_x, click_y):
        """Place a block at the clicked position"""
        try:
            canvas_width, canvas_height = self.get_canvas_dimensions('grid')
            
            cell_width = canvas_width / self.build_size
            cell_height = canvas_height / self.build_size
            
            grid_x = int(click_x / cell_width)
            grid_z = int(click_y / cell_height)
            
            if 0 <= grid_x < self.build_size and 0 <= grid_z < self.build_size:
                if self.current_block == "air":
                    # Remove block
                    if (grid_x, grid_z, self.current_y) in self.build_data:
                        del self.build_data[(grid_x, grid_z, self.current_y)]
                else:
                    # Place block
                    self.build_data[(grid_x, grid_z, self.current_y)] = self.current_block
                
                self.schedule_grid_update()
                self.schedule_iso_update()
        except Exception as e:
            print(f"Error placing block: {e}")
    
    def get_canvas_dimensions(self, canvas_type):
        """Get canvas dimensions with caching to avoid repeated winfo calls"""
        if canvas_type == 'grid':
            canvas = self.grid_canvas
            default = (self.DEFAULT_CANVAS_WIDTH, self.DEFAULT_CANVAS_HEIGHT)
        else:
            canvas = self.iso_canvas
            default = (self.ISO_CANVAS_WIDTH, self.ISO_CANVAS_HEIGHT)
        
        # Use cached dimensions if available and canvas hasn't been resized
        cache_key = f"{canvas_type}_{canvas.winfo_width()}_{canvas.winfo_height()}"
        if cache_key not in self._cached_canvas_dimensions:
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            
            if width <= 1 or height <= 1:
                width, height = default
            
            self._cached_canvas_dimensions[cache_key] = (width, height)
        
        return self._cached_canvas_dimensions[cache_key]
    
    def schedule_grid_update(self):
        """Schedule a grid update with debouncing"""
        if not self._pending_grid_update:
            self._pending_grid_update = True
            self.root.after(self.REDRAW_DELAY, self._do_grid_update)
    
    def _do_grid_update(self):
        """Perform the actual grid update"""
        self._pending_grid_update = False
        self.update_grid()
    
    def schedule_iso_update(self):
        """Schedule an isometric update with debouncing"""
        if not self._pending_iso_update:
            self._pending_iso_update = True
            self.root.after(self.REDRAW_DELAY, self._do_iso_update)
    
    def _do_iso_update(self):
        """Perform the actual isometric update"""
        self._pending_iso_update = False
        self.update_isometric()
    
    def update_grid(self):
        """Update the 2D grid display with ghost layer"""
        try:
            # Store current hover state before clearing
            old_hover_x = self.hover_x
            old_hover_z = self.hover_z
            
            self.grid_canvas.delete("all")
            
            # Reset hover outline ID since canvas was cleared
            self.hover_outline_id = None
            
            canvas_width, canvas_height = self.get_canvas_dimensions('grid')
            
            cell_width = canvas_width / self.build_size
            cell_height = canvas_height / self.build_size
            
            # Pre-calculate grid lines
            grid_lines = []
            for i in range(self.build_size + 1):
                x = i * cell_width
                y = i * cell_height
                grid_lines.extend([
                    (x, 0, x, canvas_height),
                    (0, y, canvas_width, y)
                ])
            
            # Draw all grid lines at once
            for x1, y1, x2, y2 in grid_lines:
                self.grid_canvas.create_line(x1, y1, x2, y2, fill=self.get_theme_color('grid_line'))
            
            # Pre-filter blocks for current layer and ghost layer
            current_layer_blocks = {
                (x, z): block_type 
                for (x, z, y), block_type in self.build_data.items() 
                if y == self.current_y
            }
            
            # Get ghost layer (previous Y layer) if it exists
            ghost_layer_blocks = {}
            if self.current_y > 0:
                ghost_layer_blocks = {
                    (x, z): block_type 
                    for (x, z, y), block_type in self.build_data.items() 
                    if y == self.current_y - 1
                }
            
            # Draw ghost layer first (underneath current layer)
            for (x, z), block_type in ghost_layer_blocks.items():
                if block_type in self.blocks and (x, z) not in current_layer_blocks:
                    # Only show ghost if there's no block on current layer
                    block = self.blocks[block_type]
                    
                    x1 = x * cell_width
                    y1 = z * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height
                    
                    # Create ghost appearance with transparency effect
                    ghost_color = self.make_ghost_color(block.color)
                    
                    self.grid_canvas.create_rectangle(x1, y1, x2, y2, 
                                                    fill=ghost_color, 
                                                    outline=self.get_theme_color('ghost_outline'),
                                                    width=1,
                                                    stipple="gray25")  # Dotted pattern for ghost effect
                    
                    # Add faint text for ghost blocks if cell is large enough
                    if cell_width > 30 and cell_height > 30:
                        text_x = x1 + cell_width / 2
                        text_y = y1 + cell_height / 2
                        ghost_text_color = "#999999" if not self.dark_mode else "#666666"
                        self.grid_canvas.create_text(text_x, text_y, 
                                                   text=block_type[:3],
                                                   font=("Arial", 7),
                                                   fill=ghost_text_color)
            
            # Draw current layer blocks (on top of ghost layer)
            for (x, z), block_type in current_layer_blocks.items():
                if block_type in self.blocks:
                    block = self.blocks[block_type]
                    
                    x1 = x * cell_width
                    y1 = z * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height
                    
                    self.grid_canvas.create_rectangle(x1, y1, x2, y2, 
                                                    fill=block.color, 
                                                    outline="black")
                    
                    # Add block name text if cell is large enough
                    if cell_width > 30 and cell_height > 30:
                        text_x = x1 + cell_width / 2
                        text_y = y1 + cell_height / 2
                        self.grid_canvas.create_text(text_x, text_y, 
                                                   text=block_type[:3],
                                                   font=("Arial", 8),
                                                   fill="white")
            
            # Restore hover outline if it was active
            if old_hover_x >= 0 and old_hover_z >= 0:
                self.hover_x = old_hover_x
                self.hover_z = old_hover_z
                
                x1 = old_hover_x * cell_width
                y1 = old_hover_z * cell_height
                x2 = x1 + cell_width
                y2 = y1 + cell_height
                
                self.hover_outline_id = self.grid_canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill="",
                    outline="red",
                    width=2
                )
            
        except Exception as e:
            print(f"Error updating grid: {e}")
    
    @lru_cache(maxsize=128)
    def make_ghost_color(self, color):
        """Convert a color to a faded ghost version"""
        try:
            if color.startswith('#'):
                color = color[1:]
            
            if len(color) != 6:
                return "#E0E0E0"  # Light gray default
            
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            
            # Lighten the color significantly for ghost effect
            # Mix with white (255) to create a faded appearance
            fade_factor = 0.7  # How much to fade towards white
            r = int(r + (255 - r) * fade_factor)
            g = int(g + (255 - g) * fade_factor)
            b = int(b + (255 - b) * fade_factor)
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#E0E0E0"  # Light gray on error
    
    def update_isometric(self):
        """Update the isometric 3D preview"""
        try:
            self.iso_canvas.delete("all")
            
            canvas_width, canvas_height = self.get_canvas_dimensions('iso')
            
            center_x = canvas_width / 2 + self.iso_offset_x
            center_y = canvas_height / 2 + self.iso_offset_y
            
            # Pre-calculate constants
            tile_width = self.BLOCK_SIZE_ISO
            tile_height = tile_width / 2
            tile_width_scaled = tile_width * self.iso_zoom
            tile_height_scaled = tile_height * self.iso_zoom
            
            # Sort blocks by depth for proper rendering
            blocks_to_render = []
            
            for (x, z, y), block_type in self.build_data.items():
                if block_type not in self.blocks:
                    continue
                    
                # Apply rotation
                rx, rz = self.rotate_coordinates(x, z)
                
                iso_x = (rx - rz) * (tile_width_scaled / 2)
                iso_y = (rx + rz) * (tile_height_scaled / 2) - y * tile_height_scaled
                
                # Calculate depth for sorting (back to front rendering)
                depth = (rx + rz) + y * self.build_size * 2
                
                blocks_to_render.append((depth, iso_x, iso_y, block_type))
            
            # Sort by depth (back to front)
            blocks_to_render.sort(key=lambda x: x[0])
            
            # Render blocks
            for depth, iso_x, iso_y, block_type in blocks_to_render:
                block = self.blocks[block_type]
                
                final_x = center_x + iso_x
                final_y = center_y + iso_y
                
                self.draw_isometric_block(final_x, final_y, block)
                
        except Exception as e:
            print(f"Error updating isometric view: {e}")
    
    @lru_cache(maxsize=128)
    def rotate_coordinates(self, x, z):
        """Rotate coordinates based on current rotation - cached for performance"""
        if self.iso_rotation == 0:
            return x, z
        elif self.iso_rotation == 90:
            return z, self.build_size - 1 - x
        elif self.iso_rotation == 180:
            return self.build_size - 1 - x, self.build_size - 1 - z
        elif self.iso_rotation == 270:
            return self.build_size - 1 - z, x
        return x, z
    
    def draw_isometric_block(self, x, y, block):
        """Draw a single block in isometric view - optimized version"""
        size = self.BLOCK_SIZE_ISO * self.iso_zoom
        height = size * self.BLOCK_HEIGHT_RATIO
        
        # Round zoom to reduce texture cache size
        rounded_zoom = round(self.iso_zoom, 1)
        texture_size = max(16, int(self.BLOCK_SIZE_ISO * rounded_zoom))
        
        # Check if we have texture and PIL is available
        if block.texture_path and PIL_AVAILABLE and os.path.exists(block.texture_path):
            try:
                # Generate textures for each face
                directions = ['left', 'right', 'top']
                textures = {}
                
                for direction in directions:
                    texture = skew_to_trapezoid_optimized(
                        block.texture_path, direction, texture_size
                    )
                    if texture:
                        textures[direction] = texture
                
                # Position and draw textures
                if 'left' in textures:
                    self.iso_canvas.create_image(
                        x - size/2, y,
                        image=textures['left'],
                        anchor='nw'
                    )
                
                if 'right' in textures:
                    self.iso_canvas.create_image(
                        x, y,
                        image=textures['right'],
                        anchor='n'
                    )
                
                if 'top' in textures:
                    self.iso_canvas.create_image(
                        x, y,
                        image=textures['top'],
                        anchor='n'
                    )
                
                # Draw outlines
                self._draw_block_outlines(x, y, size, height)
                
            except Exception as e:
                print(f"Error rendering textured block: {e}")
                self.draw_fallback_block(x, y, block, size, height)
        else:
            # Use fallback polygon rendering
            self.draw_fallback_block(x, y, block, size, height)
    
    def _draw_block_outlines(self, x, y, size, height):
        """Draw block outlines for textured blocks"""
        # Calculate polygon points
        top_points = [x, y, x+size/2, y+size/4, x, y+size/2, x-size/2, y+size/4]
        left_points = [x-size/2, y+size/4, x, y+size/2, x, y+size/2+height, x-size/2, y+size/4+height]
        right_points = [x, y+size/2, x+size/2, y+size/4, x+size/2, y+size/4+height, x, y+size/2+height]
        
        # Draw outlines
        self.iso_canvas.create_polygon(left_points, fill='', outline="black", width=1)
        self.iso_canvas.create_polygon(right_points, fill='', outline="black", width=1)
        self.iso_canvas.create_polygon(top_points, fill='', outline="black", width=1)
    
    def draw_fallback_block(self, x, y, block, size, height):
        """Draw block using colored polygons (fallback method) - optimized"""
        # Use pre-calculated colors
        block_name = block.name.lower().replace(" ", "_")
        if block_name in self._color_cache:
            top_color = self._color_cache[block_name][1.2]
            left_color = self._color_cache[block_name][0.8]
            right_color = self._color_cache[block_name][0.6]
        else:
            # Fallback to runtime calculation
            top_color = self.lighten_color(block.color, 1.2)
            left_color = self.lighten_color(block.color, 0.8)
            right_color = self.lighten_color(block.color, 0.6)
        
        # Calculate polygon points
        top_points = [x, y, x+size/2, y+size/4, x, y+size/2, x-size/2, y+size/4]
        left_points = [x-size/2, y+size/4, x, y+size/2, x, y+size/2+height, x-size/2, y+size/4+height]
        right_points = [x, y+size/2, x+size/2, y+size/4, x+size/2, y+size/4+height, x, y+size/2+height]
        
        # Draw faces in correct order
        self.iso_canvas.create_polygon(left_points, fill=left_color, outline="black", width=1)
        self.iso_canvas.create_polygon(right_points, fill=right_color, outline="black", width=1)
        self.iso_canvas.create_polygon(top_points, fill=top_color, outline="black", width=1)

    @lru_cache(maxsize=256)
    def lighten_color(self, color, factor):
        """Lighten or darken a hex color - cached for performance"""
        try:
            if color.startswith('#'):
                color = color[1:]
            
            # Ensure we have a valid hex color
            if len(color) != 6:
                return "#808080"  # Default gray
            
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            
            r = max(0, min(255, int(r * factor)))
            g = max(0, min(255, int(g * factor)))
            b = max(0, min(255, int(b * factor)))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#808080"  # Default gray on error
    
    def rotate_left(self):
        """Rotate view 90 degrees left"""
        self.iso_rotation = (self.iso_rotation - 90) % 360
        # Clear coordinate cache when rotating
        self.rotate_coordinates.cache_clear()
        self.schedule_iso_update()
    
    def rotate_right(self):
        """Rotate view 90 degrees right"""
        self.iso_rotation = (self.iso_rotation + 90) % 360
        # Clear coordinate cache when rotating
        self.rotate_coordinates.cache_clear()
        self.schedule_iso_update()
    
    def reset_view(self):
        """Reset the isometric view"""
        self.iso_rotation = 0
        self.iso_zoom = 1.0
        self.iso_offset_x = 0
        self.iso_offset_y = 0
        # Clear caches
        self.rotate_coordinates.cache_clear()
        self._cached_canvas_dimensions.clear()
        self.schedule_iso_update()
    
    def start_pan(self, event):
        """Start panning the isometric view"""
        self.is_panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
    
    def do_pan(self, event):
        """Pan the isometric view"""
        if self.is_panning:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            
            self.iso_offset_x += dx
            self.iso_offset_y += dy
            
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            
            self.schedule_iso_update()
    
    def end_pan(self, event):
        """End panning the isometric view"""
        self.is_panning = False
    
    def zoom_iso(self, event):
        """Zoom the isometric view with cross-platform support - optimized"""
        try:
            # Handle different mouse wheel events across platforms
            if event.delta:
                # Windows and MacOS
                zoom_in = event.delta > 0
            elif event.num == 4:
                # Linux scroll up
                zoom_in = True
            elif event.num == 5:
                # Linux scroll down
                zoom_in = False
            else:
                return
            
            old_zoom = self.iso_zoom
            
            if zoom_in:
                self.iso_zoom *= self.ZOOM_FACTOR
            else:
                self.iso_zoom /= self.ZOOM_FACTOR
            
            self.iso_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.iso_zoom))
            
            # Only update if zoom actually changed significantly
            if abs(self.iso_zoom - old_zoom) > 0.01:
                # Clear texture cache periodically to prevent memory issues
                if not hasattr(self, '_zoom_counter'):
                    self._zoom_counter = 0
                self._zoom_counter += 1
                
                if self._zoom_counter % 20 == 0:  # Clear every 20 zoom operations
                    global _texture_cache
                    _texture_cache.clear()
                
                self.schedule_iso_update()
                
        except Exception as e:
            print(f"Error zooming: {e}")
    
    def on_window_resize(self, event=None):
        """Handle window resize events - optimized"""
        # Only update if the main window is being resized
        if event and event.widget == self.root:
            # Clear canvas dimension cache
            self._cached_canvas_dimensions.clear()
            # Schedule updates instead of immediate updates
            self.root.after_idle(self.schedule_grid_update)
            self.root.after_idle(self.schedule_iso_update)
    
    def initial_render(self):
        """Initial render after UI setup"""
        self.update_grid()
        self.update_isometric()
        self.update_info()
    
    def save_build(self):
        """Save the current build to a JSON file"""
        try:
            from tkinter import filedialog
            
            # Convert build data to serializable format
            save_data = {
                'build_data': {f"{x},{z},{y}": block_type 
                              for (x, z, y), block_type in self.build_data.items()},
                'build_size': self.build_size,
                'version': '1.0'
            }
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="Save Minecraft Build"
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(save_data, f, indent=2)
                print(f"Build saved to {filename}")
                
        except Exception as e:
            print(f"Error saving build: {e}")
    
    def load_build(self):
        """Load a build from a JSON file"""
        try:
            from tkinter import filedialog
            
            filename = filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="Load Minecraft Build"
            )
            
            if filename:
                with open(filename, 'r') as f:
                    save_data = json.load(f)
                
                # Clear current build
                self.build_data.clear()
                
                # Load build data
                if 'build_data' in save_data:
                    for coord_str, block_type in save_data['build_data'].items():
                        x, z, y = map(int, coord_str.split(','))
                        if block_type in self.blocks:
                            self.build_data[(x, z, y)] = block_type
                
                # Update build size if specified
                if 'build_size' in save_data:
                    self.build_size = save_data['build_size']
                    self.y_scale.config(to=self.build_size - 1)
                
                # Clear caches and refresh views
                self._cached_canvas_dimensions.clear()
                self.rotate_coordinates.cache_clear()
                self.schedule_grid_update()
                self.schedule_iso_update()
                print(f"Build loaded from {filename}")
                
        except Exception as e:
            print(f"Error loading build: {e}")
    
    def clear_build(self):
        """Clear all blocks from the build"""
        try:
            from tkinter import messagebox
            
            if self.build_data and messagebox.askyesno(
                "Clear Build", 
                "Are you sure you want to clear all blocks?"
            ):
                self.build_data.clear()
                # Clear caches
                self._cached_canvas_dimensions.clear()
                self.rotate_coordinates.cache_clear()
                global _texture_cache
                _texture_cache.clear()
                
                self.schedule_grid_update()
                self.schedule_iso_update()
                print("Build cleared")
                
        except Exception as e:
            print(f"Error clearing build: {e}")
    
    def update_info(self):
        """Update the build information display - optimized"""
        try:
            total_blocks = len(self.build_data)
            
            # Only calculate detailed info if there are blocks
            if total_blocks > 0:
                # Count blocks by type more efficiently
                block_counts = {}
                for block_type in self.build_data.values():
                    block_counts[block_type] = block_counts.get(block_type, 0) + 1
                
                most_used = max(block_counts, key=block_counts.get)
                info_text = f"Total Blocks: {total_blocks} | Most used: {most_used} ({block_counts[most_used]})"
            else:
                info_text = "Total Blocks: 0"
            
            self.info_label.config(text=info_text)
            
        except Exception as e:
            print(f"Error updating info: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MinecraftBuildPreview(root)
    
    # Assign textures paths to blocks (run once at initialization)
    for block_name, block_obj in app.blocks.items():
        texture_file = os.path.join('blocks', f"{block_name}.png")
        if os.path.isfile(texture_file):
            block_obj.texture_path = texture_file

    root.mainloop()