import tkinter as tk
from tkinter import ttk
import math
import json
import os

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL not available - textures will not be supported")

class MinecraftBlock:
    """Represents a Minecraft block with its properties"""
    def __init__(self, name, color, texture_path=None):
        self.name = name
        self.color = color
        self.texture_path = texture_path
        self.texture_image = None
        
    def load_texture(self, size=(16, 16)):
        """Load and cache the texture image"""
        if not PIL_AVAILABLE:
            return
            
        if self.texture_path and os.path.exists(self.texture_path):
            try:
                self.texture_image = Image.open(self.texture_path).resize(size)
            except Exception as e:
                print(f"Failed to load texture {self.texture_path}: {e}")
                self.texture_image = None

class MinecraftBuildPreview:
    # Constants
    BLOCK_SIZE_ISO = 16
    BLOCK_HEIGHT_ISO = 8
    BLOCK_HEIGHT_RATIO = 0.5  # or try 0.4

    DEFAULT_CANVAS_WIDTH = 400
    DEFAULT_CANVAS_HEIGHT = 400
    ISO_CANVAS_WIDTH = 500
    ISO_CANVAS_HEIGHT = 500
    MIN_ZOOM = 0.1
    MAX_ZOOM = 3.0
    ZOOM_FACTOR = 1.1
    
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Build Preview")
        self.root.geometry("1200x800")
        
        # Build data - 3D array [x][z][y]
        self.build_size = 16
        self.build_data = {}  # Dictionary with (x,z,y) as keys
        self.current_y = 0
        self.current_block = "stone"
        
        # Isometric view settings
        self.iso_rotation = 0  # 0, 90, 180, 270 degrees
        self.iso_zoom = 1.0
        self.iso_offset_x = 0
        self.iso_offset_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        
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
    
    def setup_ui(self):
        """Setup the user interface"""
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
        
        # Isometric canvas
        self.iso_canvas = tk.Canvas(left_frame, bg="lightblue", 
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
        
        self.grid_canvas = tk.Canvas(grid_frame, bg="white", 
                                    width=self.DEFAULT_CANVAS_WIDTH, 
                                    height=self.DEFAULT_CANVAS_HEIGHT)
        self.grid_canvas.pack(padx=10, pady=10)
        
        # Bind grid click events
        self.grid_canvas.bind("<Button-1>", self.grid_click)
        self.grid_canvas.bind("<B1-Motion>", self.grid_drag)
    
    def change_y_layer(self, value):
        """Handle Y layer change"""
        self.current_y = int(float(value))
        self.y_label.config(text=str(self.current_y))
        self.update_grid()
    
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
    
    def place_block_at_click(self, click_x, click_y):
        """Place a block at the clicked position"""
        try:
            canvas_width = self.grid_canvas.winfo_width()
            canvas_height = self.grid_canvas.winfo_height()
            
            # Handle case where canvas hasn't been rendered yet
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = self.DEFAULT_CANVAS_WIDTH
                canvas_height = self.DEFAULT_CANVAS_HEIGHT
            
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
                
                self.update_grid()
                self.update_isometric()
        except Exception as e:
            print(f"Error placing block: {e}")
    
    def update_grid(self):
        """Update the 2D grid display"""
        try:
            self.grid_canvas.delete("all")
            
            canvas_width = self.grid_canvas.winfo_width()
            canvas_height = self.grid_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = self.DEFAULT_CANVAS_WIDTH
                canvas_height = self.DEFAULT_CANVAS_HEIGHT
            
            cell_width = canvas_width / self.build_size
            cell_height = canvas_height / self.build_size
            
            # Draw grid lines
            for i in range(self.build_size + 1):
                x = i * cell_width
                y = i * cell_height
                self.grid_canvas.create_line(x, 0, x, canvas_height, fill="gray")
                self.grid_canvas.create_line(0, y, canvas_width, y, fill="gray")
            
            # Draw blocks
            for z in range(self.build_size):
                for x in range(self.build_size):
                    if (x, z, self.current_y) in self.build_data:
                        block_type = self.build_data[(x, z, self.current_y)]
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
        except Exception as e:
            print(f"Error updating grid: {e}")
    
    def update_isometric(self):
        """Update the isometric 3D preview"""
        try:
            self.iso_canvas.delete("all")
            
            canvas_width = self.iso_canvas.winfo_width()
            canvas_height = self.iso_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = self.ISO_CANVAS_WIDTH
                canvas_height = self.ISO_CANVAS_HEIGHT
            
            center_x = canvas_width / 2 + self.iso_offset_x
            center_y = canvas_height / 2 + self.iso_offset_y
            
            # Sort blocks by depth for proper rendering
            blocks_to_render = []
            
            for (x, z, y), block_type in self.build_data.items():
                if block_type not in self.blocks:
                    continue
                    
                # Apply rotation
                rx, rz = self.rotate_coordinates(x, z)
                
                tile_width = self.BLOCK_SIZE_ISO  # typically 16
                tile_height = tile_width / 2      # 8 for true isometric look
                
                iso_x = (rx - rz) * (tile_width / 2) * self.iso_zoom
                iso_y = (rx + rz) * (tile_height / 2) * self.iso_zoom - y * tile_height * self.iso_zoom

                
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
    
    def rotate_coordinates(self, x, z):
        """Rotate coordinates based on current rotation"""
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
        """Draw a single block in isometric view"""
        try:
            size = self.BLOCK_SIZE_ISO * self.iso_zoom
            height = size * self.BLOCK_HEIGHT_RATIO

            
            # Block faces with different shading
            top_color = self.lighten_color(block.color, 1.2)
            left_color = self.lighten_color(block.color, 0.8)
            right_color = self.lighten_color(block.color, 0.6)
            
            # Top face (diamond shape)
            top_points = [
                x, y,
                x + size/2, y + size/4,
                x, y + size/2,
                x - size/2, y + size/4
            ]
            
            # Left face
            left_points = [
                x - size/2, y + size/4,
                x, y + size/2,
                x, y + size/2 + height,
                x - size/2, y + size/4 + height
            ]
            
            # Right face
            right_points = [
                x, y + size/2,
                x + size/2, y + size/4,
                x + size/2, y + size/4 + height,
                x, y + size/2 + height
            ]
            
            # Draw faces (order matters for proper layering)
            self.iso_canvas.create_polygon(left_points, fill=left_color, 
                                          outline="black", width=1)
            self.iso_canvas.create_polygon(right_points, fill=right_color, 
                                          outline="black", width=1)
            self.iso_canvas.create_polygon(top_points, fill=top_color, 
                                          outline="black", width=1)
        except Exception as e:
            print(f"Error drawing isometric block: {e}")
    
    def lighten_color(self, color, factor):
        """Lighten or darken a hex color"""
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
        self.update_isometric()
    
    def rotate_right(self):
        """Rotate view 90 degrees right"""
        self.iso_rotation = (self.iso_rotation + 90) % 360
        self.update_isometric()
    
    def reset_view(self):
        """Reset the isometric view"""
        self.iso_rotation = 0
        self.iso_zoom = 1.0
        self.iso_offset_x = 0
        self.iso_offset_y = 0
        self.update_isometric()
    
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
            
            self.update_isometric()
    
    def end_pan(self, event):
        """End panning the isometric view"""
        self.is_panning = False
    
    def zoom_iso(self, event):
        """Zoom the isometric view with cross-platform support"""
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
            
            if zoom_in:
                self.iso_zoom *= self.ZOOM_FACTOR
            else:
                self.iso_zoom /= self.ZOOM_FACTOR
            
            self.iso_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.iso_zoom))
            self.update_isometric()
        except Exception as e:
            print(f"Error zooming: {e}")
    
    def on_window_resize(self, event=None):
        """Handle window resize events"""
        # Only update if the main window is being resized
        if event and event.widget == self.root:
            self.root.after_idle(self.update_grid)
            self.root.after_idle(self.update_isometric)
    
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
                
                # Refresh views
                self.update_grid()
                self.update_isometric()
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
                self.update_grid()
                self.update_isometric()
                print("Build cleared")
                
        except Exception as e:
            print(f"Error clearing build: {e}")
    
    def update_info(self):
        """Update the build information display"""
        try:
            total_blocks = len(self.build_data)
            
            # Count blocks by type
            block_counts = {}
            for block_type in self.build_data.values():
                block_counts[block_type] = block_counts.get(block_type, 0) + 1
            
            # Update info label
            info_text = f"Total Blocks: {total_blocks}"
            if block_counts:
                most_used = max(block_counts, key=block_counts.get)
                info_text += f" | Most used: {most_used} ({block_counts[most_used]})"
            
            self.info_label.config(text=info_text)
            
        except Exception as e:
            print(f"Error updating info: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = MinecraftBuildPreview(root)
    root.mainloop()
