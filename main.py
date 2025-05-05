import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import time
from exchange import ExchangeClient

class GridBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Grid Trading Bot")
        self.root.configure(bg="#121212")
        self.root.geometry("300x700")  # Increased height to accommodate symbol dropdown
        
        # Colors
        self.bg_color = "#121212"
        self.input_bg = "#1E1E1E"
        self.text_color = "#CCCCCC"
        self.accent_color = "#3D5AFE"
        self.border_color = "#333333"
        self.highlight_color = "#DAA520"  # Gold color for selected buttons
        self.tab_bg = "#1E2235"  # Darker blue for selected tab
        
        # Trading direction
        self.direction = tk.StringVar(value="Neutral")
        
        # Current tab selection
        self.current_tab = tk.StringVar(value="PNL")  # Default to PNL tab selected
        
        # Trading symbol
        self.symbol = tk.StringVar()
        
        # Initialize exchange client
        self.exchange_client = ExchangeClient()
        
        # Create UI sections
        self.create_symbol_section()
        self.create_direction_buttons()
        self.create_price_range_section()
        self.create_grid_section()
        self.create_investment_section()
        self.create_advanced_section()
        self.create_button_section()
        
        # Configure placeholder behavior for all entry fields
        self.setup_placeholders()
        
        # Load symbols in a separate thread to avoid UI freezing
        self.load_symbols_thread = threading.Thread(target=self.load_symbols)
        self.load_symbols_thread.daemon = True
        self.load_symbols_thread.start()
    
    def create_symbol_section(self):
        # Frame for symbol selection
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        frame.pack(fill=tk.X)
        
        # Symbol label
        tk.Label(frame, text="Trading Symbol:", bg=self.bg_color, fg=self.text_color).pack(side=tk.LEFT)
        
        # Symbol dropdown
        self.symbol_dropdown = ttk.Combobox(frame, textvariable=self.symbol, width=15)
        self.symbol_dropdown.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Initially populate with loading message
        self.symbol_dropdown['values'] = ["Loading symbols..."]
        self.symbol_dropdown.set("Loading symbols...")
        
        # Bind selection event
        self.symbol_dropdown.bind("<<ComboboxSelected>>", self.on_symbol_selected)
        
        # Add refresh button
        refresh_btn = tk.Button(frame, text="⟳", bg=self.bg_color, fg=self.text_color, bd=0,
                             command=self.refresh_symbols)
        refresh_btn.pack(side=tk.RIGHT, padx=5)
    
    def load_symbols(self):
        """Load symbols in background thread"""
        try:
            # Show loading state in UI
            self.root.after(0, lambda: self.update_symbol_loading_state(True))
            
            # Fetch symbols from exchange
            symbols = self.exchange_client.fetch_active_symbols()
            
            # If no symbols found, show error
            if not symbols:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error", "Failed to fetch symbols. Check your API connection."))
                self.root.after(0, lambda: self.update_symbol_loading_state(False, ["Error loading symbols"]))
                return
            
            # Update dropdown on main thread
            self.root.after(0, lambda: self.update_symbols_dropdown(symbols))
            
        except Exception as e:
            # Handle any exceptions
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load symbols: {str(e)}"))
            self.root.after(0, lambda: self.update_symbol_loading_state(False, ["Error loading symbols"]))
    
    def update_symbol_loading_state(self, is_loading, values=None):
        """Update the UI to reflect symbol loading state"""
        if is_loading:
            self.symbol_dropdown.config(state="disabled")
        else:
            self.symbol_dropdown.config(state="readonly")
            if values:
                self.symbol_dropdown['values'] = values
    
    def update_symbols_dropdown(self, symbols):
        """Update the symbols dropdown with fetched values"""
        self.symbol_dropdown['values'] = symbols
        if symbols:
            self.symbol_dropdown.set(symbols[0])  # Select first symbol
        self.symbol_dropdown.config(state="readonly")
    
    def refresh_symbols(self):
        """Refresh the symbols list"""
        if not hasattr(self, 'load_symbols_thread') or not self.load_symbols_thread.is_alive():
            self.symbol_dropdown.set("Loading symbols...")
            self.symbol_dropdown.config(state="disabled")
            self.load_symbols_thread = threading.Thread(target=self.load_symbols)
            self.load_symbols_thread.daemon = True
            self.load_symbols_thread.start()
    
    def on_symbol_selected(self, event):
        """Handle symbol selection"""
        selected_symbol = self.symbol.get()
        if selected_symbol:
            # Fetch current market price and update price range fields
            self.fetch_symbol_price(selected_symbol)
    
    def fetch_symbol_price(self, symbol):
        """Fetch current price for the selected symbol and update UI"""
        try:
            # Start a thread to fetch price in background
            threading.Thread(
                target=self._fetch_price_thread,
                args=(symbol,),
                daemon=True
            ).start()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch price: {str(e)}")
    
    def _fetch_price_thread(self, symbol):
        """Background thread to fetch price"""
        try:
            ticker = self.exchange_client.fetch_ticker(symbol)
            if ticker and 'last' in ticker:
                price = ticker['last']
                
                # Calculate price range for grid (±5% by default)
                lower_price = price * 0.95
                upper_price = price * 1.05
                
                # Update UI on main thread
                self.root.after(0, lambda: self.update_price_fields(lower_price, upper_price))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch price: {str(e)}"))
    
    def update_price_fields(self, lower_price, upper_price):
        """Update the price range fields with fetched values"""
        # Clear placeholders
        self.lower_price.delete(0, tk.END)
        self.upper_price.delete(0, tk.END)
        
        # Update with formatted prices
        self.lower_price.insert(0, f"{lower_price:.8f}")
        self.upper_price.insert(0, f"{upper_price:.8f}")
        
        # Set text color to normal (not placeholder color)
        self.lower_price.config(fg=self.lower_price.default_fg_color)
        self.upper_price.config(fg=self.upper_price.default_fg_color)
    
    def create_direction_buttons(self):
        # Direction buttons frame
        dir_frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        dir_frame.pack(fill=tk.X)
        
        # Create button style
        button_style = {"bg": self.bg_color, "fg": self.text_color, "bd": 1, 
                        "relief": tk.RAISED, "padx": 10, "pady": 5}
        
        # Direction buttons
        directions = ["Neutral", "Long", "Short"]
        self.dir_buttons = {}
        
        for i, direction in enumerate(directions):
            btn = tk.Button(dir_frame, text=direction, **button_style,
                          command=lambda d=direction: self.set_direction(d))
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
            self.dir_buttons[direction] = btn
        
        # Set initial active button
        self.update_direction_buttons()
        
        # Settings button on right
        settings_btn = tk.Button(dir_frame, text="⚙", bg=self.bg_color, fg=self.text_color, bd=0)
        settings_btn.pack(side=tk.RIGHT, padx=5)
    
    def set_direction(self, direction):
        self.direction.set(direction)
        self.update_direction_buttons()
        # Update create button text
        self.create_button.config(text=f"Create ({direction})")
    
    def update_direction_buttons(self):
        active_dir = self.direction.get()
        for dir_name, btn in self.dir_buttons.items():
            if dir_name == active_dir:
                btn.config(bg=self.highlight_color, fg="#000000")
            else:
                btn.config(bg=self.bg_color, fg=self.text_color)
    
    def create_price_range_section(self):
        # Frame for price range section
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        frame.pack(fill=tk.X)
        
        # Title and options row
        title_frame = tk.Frame(frame, bg=self.bg_color)
        title_frame.pack(fill=tk.X)
        
        # Title with trailing label
        title_label = tk.Label(title_frame, text="1. Price Range", bg=self.bg_color, fg=self.text_color, anchor='w')
        title_label.pack(side=tk.LEFT)
        
        trailing_label = tk.Label(title_frame, text="Trailing", bg=self.bg_color, fg=self.highlight_color, anchor='w')
        trailing_label.pack(side=tk.LEFT, padx=5)
        
        # Auto Fill on right
        auto_fill = tk.Label(title_frame, text="Auto Fill", bg=self.bg_color, fg=self.highlight_color, anchor='e')
        auto_fill.pack(side=tk.RIGHT)
        
        # Price inputs
        price_frame = tk.Frame(frame, bg=self.bg_color)
        price_frame.pack(fill=tk.X, pady=5)
        
        self.lower_price = tk.Entry(price_frame, bg=self.input_bg, fg=self.text_color, 
                                 width=15, bd=1, highlightbackground=self.border_color)
        self.lower_price.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        
        self.upper_price = tk.Entry(price_frame, bg=self.input_bg, fg=self.text_color, 
                                  width=15, bd=1, highlightbackground=self.border_color)
        self.upper_price.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 0))
    
    # [Rest of your existing methods...]
    # [I've omitted them for brevity but they remain unchanged]

    def create_grid_section(self):
        # Frame for grid section
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        frame.pack(fill=tk.X)
        
        # Title
        tk.Label(frame, text="2. Number of Grids", bg=self.bg_color, fg=self.text_color, anchor='w').pack(fill=tk.X)
        
        # Grid inputs
        grid_frame = tk.Frame(frame, bg=self.bg_color)
        grid_frame.pack(fill=tk.X, pady=5)
        
        self.grid_number = tk.Entry(grid_frame, bg=self.input_bg, fg=self.text_color, bd=1)
        self.grid_number.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        
        self.grid_type = ttk.Combobox(grid_frame, values=["Arithmetic", "Geometric"], width=10)
        self.grid_type.pack(side=tk.RIGHT, padx=(2, 0))
        self.grid_type.set("Arithmetic")
        
        # Profit display
        profit_frame = tk.Frame(frame, bg=self.bg_color)
        profit_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(profit_frame, text="Profit (incl fees deducted)", bg=self.bg_color, 
               fg=self.text_color, anchor='w').pack(side=tk.LEFT)
        
        tk.Label(profit_frame, text="--", bg=self.bg_color, 
               fg=self.text_color, anchor='e').pack(side=tk.RIGHT)
    
    def create_investment_section(self):
        # Frame for investment section
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        frame.pack(fill=tk.X)
        
        # Title
        tk.Label(frame, text="3. Investment", bg=self.bg_color, fg=self.text_color, anchor='w').pack(fill=tk.X)
        
        # Investment inputs
        inv_frame = tk.Frame(frame, bg=self.bg_color)
        inv_frame.pack(fill=tk.X, pady=5)
        
        # Change from Combobox to Entry for currency
        self.currency = tk.Entry(inv_frame, bg=self.input_bg, fg=self.text_color)
        self.currency.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        
        self.leverage = ttk.Combobox(inv_frame, values=["1x", "5x", "10x", "20x"], width=8)
        self.leverage.pack(side=tk.RIGHT, padx=(2, 0))
        self.leverage.set("10x")
        
        # Slider
        slider_frame = tk.Frame(frame, bg=self.bg_color)
        slider_frame.pack(fill=tk.X, pady=5)
        
        self.investment_slider = tk.Scale(slider_frame, from_=0, to=100, orient=tk.HORIZONTAL, 
                                        bg=self.bg_color, fg=self.text_color, highlightthickness=0)
        self.investment_slider.pack(fill=tk.X)
        
        # Investment info
        info_frame = tk.Frame(frame, bg=self.bg_color)
        info_frame.pack(fill=tk.X, pady=5)
        
        info_labels = [
            ("Available", "0.19 USDT"),
            ("Qty/Order", "0 USDT"),
            ("Total Investment", "0.00 USDT"),
            ("Est. Liq. Price (Long)", "--"),
            ("Est. Liq. Price (Short)", "--"),
            ("Margin Mode", "Isolated")
        ]
        
        for i, (label, value) in enumerate(info_labels):
            row = tk.Frame(info_frame, bg=self.bg_color)
            row.pack(fill=tk.X, pady=2)
            
            tk.Label(row, text=label, bg=self.bg_color, fg=self.text_color, anchor='w').pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=self.bg_color, fg=self.text_color, anchor='e').pack(side=tk.RIGHT)
    
    def create_advanced_section(self):
        # Frame for advanced section
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=5)
        frame.pack(fill=tk.X)
        
        # Header with expand/collapse
        header_frame = tk.Frame(frame, bg=self.bg_color)
        header_frame.pack(fill=tk.X)
        
        tk.Label(header_frame, text="Advanced (Optional)", bg=self.bg_color, 
               fg=self.text_color, anchor='w').pack(side=tk.LEFT)
        
        self.advanced_expanded = tk.BooleanVar(value=True)
        self.expand_btn = tk.Button(header_frame, text="▼", bg=self.bg_color, fg=self.text_color,
                                  command=self.toggle_advanced, width=2, bd=0)
        self.expand_btn.pack(side=tk.RIGHT)
        
        # Container for advanced options
        self.advanced_container = tk.Frame(frame, bg=self.bg_color)
        self.advanced_container.pack(fill=tk.X, pady=5)
        
        # Trailing Up
        self.trailing_up_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.advanced_container, text="Trailing Up", variable=self.trailing_up_var,
                     bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color).pack(anchor='w', pady=2)
        
        trailing_up_frame = tk.Frame(self.advanced_container, bg=self.bg_color)
        trailing_up_frame.pack(fill=tk.X, pady=2)
        
        self.trailing_up_limit = tk.Entry(trailing_up_frame, bg=self.input_bg, fg=self.text_color)
        self.trailing_up_limit.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        tk.Label(trailing_up_frame, text="USDT", bg=self.bg_color, fg=self.text_color).pack(side=tk.RIGHT, padx=5)
        
        # Trailing Down
        self.trailing_down_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.advanced_container, text="Trailing Down", variable=self.trailing_down_var,
                     bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color).pack(anchor='w', pady=2)
        
        trailing_down_frame = tk.Frame(self.advanced_container, bg=self.bg_color)
        trailing_down_frame.pack(fill=tk.X, pady=2)
        
        self.trailing_down_limit = tk.Entry(trailing_down_frame, bg=self.input_bg, fg=self.text_color)
        self.trailing_down_limit.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        tk.Label(trailing_down_frame, text="USDT", bg=self.bg_color, fg=self.text_color).pack(side=tk.RIGHT, padx=5)
        
        # Grid Trigger
        self.grid_trigger_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.advanced_container, text="Grid Trigger", variable=self.grid_trigger_var,
                     bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color).pack(anchor='w', pady=2)
        
        # TP/SL
        tpsl_frame = tk.Frame(self.advanced_container, bg=self.bg_color)
        tpsl_frame.pack(fill=tk.X, pady=2)
        
        self.tpsl_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tpsl_frame, text="TP/SL", variable=self.tpsl_var,
                     bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color).pack(side=tk.LEFT)
        
        self.tpsl_action = ttk.Combobox(tpsl_frame, values=["Close all positions", "Close partial positions"], width=15)
        self.tpsl_action.pack(side=tk.RIGHT)
        self.tpsl_action.set("Close all positions")
        
        # Create tab navigation and content container
        self.create_tab_navigation()
        
        # This container will hold the content based on selected tab
        self.tab_content_container = tk.Frame(self.advanced_container, bg=self.bg_color)
        self.tab_content_container.pack(fill=tk.X, pady=5)
        
        # Set initial tab content
        self.update_tab_content()
    
    def create_tab_navigation(self):
        # Tab navigation frame with rounded corners
        self.tabs_frame = tk.Frame(self.advanced_container, bg=self.bg_color, highlightthickness=1, 
                                 highlightbackground=self.border_color, bd=0)
        self.tabs_frame.pack(fill=tk.X, pady=5)
        
        # Create tab buttons
        self.tab_buttons = {}
        tab_options = ["Price", "PNL", "ROI%"]
        
        for i, tab_name in enumerate(tab_options):
            tab = tk.Label(self.tabs_frame, text=tab_name, padx=10, pady=5,
                         bg=self.bg_color, fg=self.text_color, cursor="hand2")
            tab.grid(row=0, column=i, sticky="nsew")
            tab.bind("<Button-1>", lambda e, name=tab_name: self.switch_tab(name))
            self.tab_buttons[tab_name] = tab
            self.tabs_frame.columnconfigure(i, weight=1)
        
        # Set initial active tab
        self.update_tab_buttons()
    
    def switch_tab(self, tab_name):
        # Set the current active tab
        self.current_tab.set(tab_name)
        self.update_tab_buttons()
        self.update_tab_content()
    
    def update_tab_buttons(self):
        # Update the appearance of tab buttons
        active_tab = self.current_tab.get()
        for tab_name, button in self.tab_buttons.items():
            if tab_name == active_tab:
                button.config(bg=self.tab_bg, fg=self.text_color)
            else:
                button.config(bg=self.bg_color, fg=self.text_color)
    
    def update_tab_content(self):
        # Clear existing content
        for widget in self.tab_content_container.winfo_children():
            widget.destroy()
        
        tab = self.current_tab.get()
        
        # Create different content based on tab
        if tab == "Price":
            self.create_price_tab_content()
        elif tab == "PNL":
            self.create_pnl_tab_content()
        elif tab == "ROI%":
            self.create_roi_tab_content()
    
    def create_price_tab_content(self):
        # Content for Price tab
        # Stop Loss
        stop_loss_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        stop_loss_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(stop_loss_frame, text="Stop Loss", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.stop_loss_type = ttk.Combobox(stop_loss_frame, values=["Last", "Mark"], width=10)
        self.stop_loss_type.pack(side=tk.RIGHT)
        self.stop_loss_type.set("Last")
        
        # Take Profit
        take_profit_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        take_profit_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(take_profit_frame, text="Take Profit", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.take_profit_type = ttk.Combobox(take_profit_frame, values=["Last", "Mark"], width=10)
        self.take_profit_type.pack(side=tk.RIGHT)
        self.take_profit_type.set("Last")
    
    def create_pnl_tab_content(self):
        # Content for PNL tab
        # Stop Loss
        stop_loss_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        stop_loss_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(stop_loss_frame, text="Stop Loss", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.stop_loss_pnl = tk.Entry(stop_loss_frame, bg=self.input_bg, fg=self.text_color, width=12)
        self.stop_loss_pnl.pack(side=tk.RIGHT)
        
        # Take Profit
        take_profit_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        take_profit_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(take_profit_frame, text="Take Profit", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.take_profit_pnl = tk.Entry(take_profit_frame, bg=self.input_bg, fg=self.text_color, width=12)
        self.take_profit_pnl.pack(side=tk.RIGHT)
    
    def create_roi_tab_content(self):
        # Content for ROI% tab
        # Stop Loss
        stop_loss_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        stop_loss_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(stop_loss_frame, text="Stop Loss", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.stop_loss_roi = tk.Entry(stop_loss_frame, bg=self.input_bg, fg=self.text_color, width=12)
        self.stop_loss_roi.pack(side=tk.RIGHT)
        
        # Take Profit
        take_profit_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        take_profit_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(take_profit_frame, text="Take Profit", bg=self.bg_color, 
               fg=self.text_color).pack(side=tk.LEFT)
        
        self.take_profit_roi = tk.Entry(take_profit_frame, bg=self.input_bg, fg=self.text_color, width=12)
        self.take_profit_roi.pack(side=tk.RIGHT)
        
        # Add ROI% specific explanation if needed
        roi_info_frame = tk.Frame(self.tab_content_container, bg=self.bg_color)
        roi_info_frame.pack(fill=tk.X, pady=2)
        
        roi_info = tk.Label(roi_info_frame, text="Values in percentage of investment", 
                          bg=self.bg_color, fg="#888888", font=("Arial", 8))
        roi_info.pack(anchor='w')
        
        # Close all positions on stop
        self.close_on_stop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.tab_content_container, text="Close all positions on stop", 
                     variable=self.close_on_stop_var, bg=self.bg_color, fg=self.text_color, 
                     selectcolor=self.bg_color).pack(anchor='w', pady=5)
    
    def create_button_section(self):
        # Frame for create button
        frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=10)
        frame.pack(fill=tk.X)
        
        # Create button
        self.create_button = tk.Button(frame, text=f"Create ({self.direction.get()})", 
                                     bg=self.highlight_color, fg="#000000",
                                     padx=10, pady=8, command=self.create_bot)
        self.create_button.pack(fill=tk.X)
    
    def toggle_advanced(self):
        if self.advanced_expanded.get():
            self.advanced_container.pack_forget()
            self.advanced_expanded.set(False)
            self.expand_btn.config(text="▲")
        else:
            self.advanced_container.pack(fill=tk.X, pady=5)
            self.advanced_expanded.set(True)
            self.expand_btn.config(text="▼")
    
    def setup_placeholders(self):
        # Configure placeholders for all entry fields
        self.add_placeholder(self.lower_price, "Lower")
        self.add_placeholder(self.upper_price, "Upper")
        self.add_placeholder(self.grid_number, "2-169")
        self.add_placeholder(self.currency, "USDT")
        self.add_placeholder(self.trailing_up_limit, "Trailing Up Limit")
        self.add_placeholder(self.trailing_down_limit, "Trailing Down Limit")
    
    def add_placeholder(self, entry, placeholder):
        # Function to handle placeholder text behavior
        entry.placeholder = placeholder
        entry.placeholder_color = "#666666"
        entry.default_fg_color = self.text_color
        
        entry.insert(0, placeholder)
        entry.config(fg=entry.placeholder_color)
        
        entry.bind("<FocusIn>", self.clear_placeholder)
        entry.bind("<FocusOut>", self.restore_placeholder)
    
    def clear_placeholder(self, event):
        # Clear placeholder text when field is focused
        if event.widget.get() == event.widget.placeholder:
            event.widget.delete(0, tk.END)
            event.widget.config(fg=event.widget.default_fg_color)
    
    def restore_placeholder(self, event):
        # Restore placeholder text if field is empty and focus is lost
        if event.widget.get() == "":
            event.widget.insert(0, event.widget.placeholder)
            event.widget.config(fg=event.widget.placeholder_color)
    
    def get_value(self, entry):
        # Helper method to get actual value, ignoring placeholder
        if entry.get() == entry.placeholder:
            return ""
        return entry.get()
    
    def get_tab_values(self):
        # Get the values from the current tab
        tab = self.current_tab.get()
        
        if tab == "Price":
            return {
                "type": "Price",
                "stop_loss_type": self.stop_loss_type.get(),
                "take_profit_type": self.take_profit_type.get()
            }
        elif tab == "PNL":
            return {
                "type": "PNL",
                "stop_loss": self.get_value(self.stop_loss_pnl) if hasattr(self, 'stop_loss_pnl') else "",
                "take_profit": self.get_value(self.take_profit_pnl) if hasattr(self, 'take_profit_pnl') else ""
            }
        elif tab == "ROI%":
            return {
                "type": "ROI%",
                "stop_loss": self.get_value(self.stop_loss_roi) if hasattr(self, 'stop_loss_roi') else "",
                "take_profit": self.get_value(self.take_profit_roi) if hasattr(self, 'take_profit_roi') else ""
            }
    
    def create_bot(self):
        # Get the selected symbol
        symbol = self.symbol.get()
        if not symbol or symbol == "Loading symbols..." or symbol == "Error loading symbols":
            messagebox.showerror("Error", "Please select a valid trading symbol")
            return
            
        # Collect all settings from UI, handling placeholder values
        config = {
            "symbol": symbol,
            "direction": self.direction.get(),
            "price_range": {
                "lower": self.get_value(self.lower_price),
                "upper": self.get_value(self.upper_price),
                "trailing": True  # From the trailing label in the UI
            },
            "grid": {
                "number": self.get_value(self.grid_number),
                "type": self.grid_type.get()
            },
            "investment": {
                "currency": self.get_value(self.currency),
                "leverage": self.leverage.get(),
                "amount": self.investment_slider.get()
            },
            "advanced": {
                "trailing_up": {
                    "enabled": self.trailing_up_var.get(),
                    "limit": self.get_value(self.trailing_up_limit)
                },
                "trailing_down": {
                    "enabled": self.trailing_down_var.get(),
                    "limit": self.get_value(self.trailing_down_limit)
                },
                "grid_trigger": self.grid_trigger_var.get(),
                "tpsl": {
                    "enabled": self.tpsl_var.get(),
                    "action": self.tpsl_action.get(),
                    "values": self.get_tab_values()
                },
                "close_on_stop": self.close_on_stop_var.get()
            }
        }
        
        # Print config for now (will be passed to grid_logic.py to create and start the bot)
        print(json.dumps(config, indent=2))
        
        # TODO: Pass to grid_logic.py to create and start the bot
        messagebox.showinfo("Bot Created", f"Grid Bot for {symbol} created successfully!")

def main():
    root = tk.Tk()
    app = GridBotApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()