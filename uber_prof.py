import csv
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from tkcalendar import DateEntry
import re
import os
import sqlite3
import logging
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import pytz  # Import the pytz library
import shutil

# Constants
DB_FILE = "uber_wallet.db"
DEFAULT_FUEL_EFFICIENCY = 25
DEFAULT_PETROL_PRICE = 180.0
TRIP_FIELDS = ['date', 'time', 'end_time', 'duration', 'cash_collected', 'fare', 'service_fee', 'taxes', 'distance_km', 'tips', 'earnings', 'trip_balance', 'discount', 'discount_rate', 'earnings_per_km', 'fuel_used', 'estimated_fuel_cost', 'service_fee_percent', 'taxes_percent']
FUEL_LOG_FIELDS = ['date', 'time', 'station', 'location', 'amount', 'price_per_liter', 'liters']
MAX_TANK_CAPACITY = 60  # Example: Define your vehicle's tank capacity here

# Configure logging
logging.basicConfig(filename='uber_wallet.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def validate_positive_float(value, field_name):
    """Validates if a value is a non-negative float."""
    try:
        value = float(value)
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative.")
        return value
    except ValueError as e:
        messagebox.showerror("Error", str(e))
        return None

def add_tooltip(widget, text):
    """Adds a tooltip to a widget."""
    tooltip = tk.Toplevel(widget)
    tooltip.withdraw()
    tooltip.overrideredirect(True)
    tooltip_label = ttk.Label(tooltip, text=text, background="lightyellow", relief="solid", borderwidth=1, padding=5)
    tooltip_label.pack()

    def show_tooltip(event):
        widget.update_idletasks()
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 5
        tooltip.geometry(f"+{x}+{y}")
        tooltip.deiconify()

    def hide_tooltip(event):
        tooltip.withdraw()

    widget.bind("<Enter>", show_tooltip)
    widget.bind("<Leave>", hide_tooltip)

def populate_treeview(tree, data, columns):
    """Populates a ttk.Treeview with data."""
    tree.delete(*tree.get_children())
    for item in data:
        values = [item.get(col) for col in columns]
        tree.insert("", "end", values=values)

def sort_treeview(tree, col, reverse):
    """Sorts the treeview based on the selected column."""
    data = [(tree.set(child, col), child) for child in tree.get_children('')]
    try:
        # Attempt to sort numerically if possible
        data.sort(key=lambda item: float(item[0]), reverse=reverse)
    except ValueError:
        # Otherwise sort as strings
        data.sort(reverse=reverse)

    for index, (val, child) in enumerate(data):
        tree.move(child, '', index)

    tree.heading(col, command=lambda: sort_treeview(tree, col, not reverse))

class TimeInputDialog(tk.Toplevel):
    def __init__(self, parent, existing_start_time=None, existing_duration=None):
        super().__init__(parent)
        self.title("Time Input")
        self.result = None
        self.selected_date = None

        # Validation function for numbers only
        def validate_number(char):
            return char.isdigit() or char == ""

        vcmd = (self.register(validate_number), '%S')

        # Start Time Frame (No validation needed for combo boxes)
        ttk.Label(self, text="Start Time (HH:MM):").grid(row=0, column=0, padx=5, pady=5)
        self.start_hour_var = tk.StringVar(value=existing_start_time.split(':')[0] if existing_start_time else datetime.now(tz=datetime.now().astimezone().tzinfo).strftime("%H"))
        self.start_minute_var = tk.StringVar(value=existing_start_time.split(':')[1] if existing_start_time else datetime.now(tz=datetime.now().astimezone().tzinfo).strftime("%M"))
        hour_options = [f"{i:02d}" for i in range(24)]
        minute_options = [f"{i:02d}" for i in range(60)]
        self.start_hour_combo = ttk.Combobox(self, textvariable=self.start_hour_var, values=hour_options, width=3)
        self.start_hour_combo.grid(row=0, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(self, text=":").grid(row=0, column=1, padx=0, pady=5, sticky="e")
        self.start_minute_combo = ttk.Combobox(self, textvariable=self.start_minute_var, values=minute_options, width=3)
        self.start_minute_combo.grid(row=0, column=2, padx=2, pady=5, sticky="w")

        # Duration Frame (Apply validation to combo boxes)
        ttk.Label(self, text="Duration (HH:MM:SS):").grid(row=1, column=0, padx=5, pady=5)
        if existing_duration:
            h, m, s = existing_duration.split(':')
            self.duration_hour_var = tk.StringVar(value=h)
            self.duration_minute_var = tk.StringVar(value=m)
            self.duration_second_var = tk.StringVar(value=s)
        else:
            self.duration_hour_var = tk.StringVar(value="00")
            self.duration_minute_var = tk.StringVar(value="00")
            self.duration_second_var = tk.StringVar(value="00")
        duration_hour_options = [f"{i:02d}" for i in range(24)]
        duration_minute_options = [f"{i:02d}" for i in range(60)]
        duration_second_options = [f"{i:02d}" for i in range(60)]
        self.duration_hour_combo = ttk.Combobox(self, textvariable=self.duration_hour_var, values=duration_hour_options, width=3, validate="key", validatecommand=vcmd)
        self.duration_hour_combo.grid(row=1, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(self, text=":").grid(row=1, column=1, padx=0, pady=5, sticky="e")
        self.duration_minute_combo = ttk.Combobox(self, textvariable=self.duration_minute_var, values=duration_minute_options, width=3, validate="key", validatecommand=vcmd)
        self.duration_minute_combo.grid(row=1, column=2, padx=2, pady=5, sticky="w")
        ttk.Label(self, text=":").grid(row=1, column=2, padx=0, pady=5, sticky="e")
        self.duration_second_combo = ttk.Combobox(self, textvariable=self.duration_second_var, values=duration_second_options, width=3, validate="key", validatecommand=vcmd)
        self.duration_second_combo.grid(row=1, column=3, padx=2, pady=5, sticky="w")

        # End Time Frame
        ttk.Label(self, text="End Time:").grid(row=2, column=0, padx=5, pady=5)
        self.end_time_var = tk.StringVar()
        ttk.Label(self, textvariable=self.end_time_var).grid(row=2, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        # Buttons
        ttk.Button(self, text="Now", command=self.use_current_time).grid(row=3, column=0, padx=5, pady=5)
        ttk.Button(self, text="Calculate", command=self.calculate_time).grid(row=3, column=1, columnspan=3, padx=5, pady=5)
        ttk.Button(self, text="OK", command=self.on_ok).grid(row=4, column=0, columnspan=4, pady=5)

        # Initialize with current time if no existing data
        if not existing_start_time:
            self.use_current_time()

    def set_date(self, date_str):
        try:
            self.selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            self.selected_date = None

    def parse_duration(self):
        """Get duration from combo boxes in seconds"""
        hours = int(self.duration_hour_var.get() or 0)
        minutes = int(self.duration_minute_var.get() or 0)
        seconds = int(self.duration_second_var.get() or 0)
        return timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds()

    def format_duration_display(self):
        """Format duration for display"""
        hours = int(self.duration_hour_var.get() or 0)
        minutes = int(self.duration_minute_var.get() or 0)
        seconds = int(self.duration_second_var.get() or 0)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def calculate_time(self):
        """Calculate end time or start time based on input"""
        if not self.selected_date:
            messagebox.showerror("Error", "Date must be selected first.")
            return
        start_hour = self.start_hour_var.get()
        start_minute = self.start_minute_var.get()

        if not start_hour or not start_minute:
            messagebox.showerror("Error", "Start time is required")
            return

        try:
            start_h = int(start_hour)
            start_m = int(start_minute)
            start_time_naive = datetime.min.time().replace(hour=start_h, minute=start_m)
            start_dt_naive = datetime.combine(self.selected_date, start_time_naive)

            # Get the EAT timezone
            eat_timezone = pytz.timezone('Africa/Nairobi')

            # Make start_dt_naive timezone-aware
            start_dt_with_date = eat_timezone.localize(start_dt_naive)
            logging.info(f"Calculate Time - Start Datetime (TZ aware): {start_dt_with_date}")

            now = datetime.now(tz=datetime.now().astimezone().tzinfo)
            if start_dt_with_date > now:
                messagebox.showerror("Error", "Start time cannot be in the future.")
                return

            # Parse duration directly from StringVar values
            duration_hour = self.duration_hour_var.get()
            duration_minute = self.duration_minute_var.get()
            duration_second = self.duration_second_var.get()

            logging.info(f"Calculate Time - Duration (raw): {duration_hour}, {duration_minute}, {duration_second}")

            duration_seconds = timedelta(hours=int(duration_hour or 0),
                                         minutes=int(duration_minute or 0),
                                         seconds=int(duration_second or 0)).total_seconds()
            duration_timedelta = timedelta(seconds=duration_seconds)
            logging.info(f"Calculate Time - Duration: {duration_timedelta}")

            # Calculate end time
            end_dt_with_date = start_dt_with_date + duration_timedelta
            logging.info(f"Calculate Time - End Datetime (TZ aware): {end_dt_with_date}")

            if end_dt_with_date > now:
                messagebox.showerror("Error", "End time cannot be in the future.")
                return

            self.end_time_var.set(end_dt_with_date.strftime("%H:%M"))

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid time format: {e}")
            logging.error(f"Calculate Time - ValueError: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Calculate Time - Unexpected error: {e}")
            logging.error(f"Calculate Time - Unexpected error: {e}")

    def use_current_time(self):
        """Set end time to now and calculate start time"""
        now = datetime.now(tz=datetime.now().astimezone().tzinfo)
        self.end_time_var.set(now.strftime("%H:%M"))
        self.start_hour_var.set(now.strftime("%H"))
        self.start_minute_var.set(now.strftime("%M"))
        self.duration_hour_var.set("00")
        self.duration_minute_var.set("00")
        self.duration_second_var.set("00")

    def on_ok(self):
        """Validate and return results"""
        start_hour = self.start_hour_var.get()
        start_minute = self.start_minute_var.get()
        duration_hour = self.duration_hour_var.get()
        duration_minute = self.duration_minute_var.get()
        duration_second = self.duration_second_var.get()
        end_time = self.end_time_var.get()

        logging.info(f"TimeInputDialog - OK button clicked.")
        logging.info(f"Start Time: {start_hour}:{start_minute}")
        logging.info(f"Duration: {duration_hour}:{duration_minute}:{duration_second}") # Log raw duration components
        logging.info(f"End Time (before potential calculation): {end_time}")
        logging.info(f"Selected Date: {self.selected_date}")

        if not all([start_hour, start_minute, duration_hour, duration_minute, duration_second]):
            messagebox.showerror("Error", "Start time and duration fields are required")
            logging.warning("TimeInputDialog - Validation failed: Missing start time or duration fields.")
            return

        if not self.selected_date:
            messagebox.showerror("Error", "Date must be selected first.")
            logging.warning("TimeInputDialog - Validation failed: Date not selected.")
            return

        try:
            # Validate time format
            start_datetime_str = f"{start_hour}:{start_minute}"
            start_time_obj = datetime.strptime(start_datetime_str, "%H:%M").time()
            start_datetime_naive = datetime.combine(self.selected_date, start_time_obj)

            # Get the EAT timezone
            eat_timezone = pytz.timezone('Africa/Nairobi')
            start_datetime_with_date = eat_timezone.localize(start_datetime_naive)

            now = datetime.now(tz=datetime.now().astimezone().tzinfo)

            if start_datetime_with_date > now:
                messagebox.showerror("Error", "Start time cannot be in the future.")
                logging.warning(f"TimeInputDialog - Validation failed: Start time in future - {start_datetime_with_date}, Now - {now}")
                return

            duration_seconds = int(duration_hour) * 3600 + int(duration_minute) * 60 + int(duration_second)
            duration_timedelta = timedelta(seconds=duration_seconds)
            duration_str = f"{int(duration_hour):02d}:{int(duration_minute):02d}:{int(duration_second):02d}"

            # Calculate end time if not already set
            if not end_time:
                end_datetime_with_date = start_datetime_with_date + duration_timedelta
                end_time = end_datetime_with_date.strftime("%H:%M")
                self.end_time_var.set(end_time) # Update the variable as well
                logging.info(f"TimeInputDialog - End Time calculated: {end_time}")
            else:
                end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                end_datetime_naive = datetime.combine(self.selected_date, end_time_obj)
                end_datetime_with_date = eat_timezone.localize(end_datetime_naive)
                if end_datetime_with_date > now:
                    messagebox.showerror("Error", "End time cannot be in the future.")
                    logging.warning(f"TimeInputDialog - Validation failed: End time in future - {end_datetime_with_date}, Now - {now}")
                    return
                logging.info(f"TimeInputDialog - End Time already set: {end_time}")


            self.result = (f"{start_hour}:{start_minute}", duration_str, end_time)
            logging.info(f"TimeInputDialog - Result captured: {self.result}")
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid time format (use HH:MM): {e}")
            logging.error(f"TimeInputDialog - ValueError: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            logging.error(f"An unexpected error occurred: {e}")

class FuelDialog(tk.Toplevel):
    def __init__(self, parent, default_price=DEFAULT_PETROL_PRICE, existing_data=None):
        super().__init__(parent)
        self.title("Fuel Refill")
        self.result = None

        ttk.Label(self, text="Date:").grid(row=0, column=0, padx=5, pady=5)
        initial_date = datetime.strptime(existing_data['date'], "%Y-%m-%d").date() if existing_data and 'date' in existing_data else datetime.now().date()
        self.date_entry = DateEntry(self, width=12, background='darkblue',
                                    foreground='white', borderwidth=2,
                                    maxdate=datetime.now().date(),
                                    initialdate=initial_date)
        self.date_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(self, text="Time (HH:MM):").grid(row=1, column=0, padx=5, pady=5)
        initial_time = existing_data['time'].split(':') if existing_data and 'time' in existing_data else datetime.now(tz=datetime.now().astimezone().tzinfo).strftime("%H:%M").split(':')
        self.hour_var = tk.StringVar(value=initial_time[0])
        self.minute_var = tk.StringVar(value=initial_time[1])
        hour_options = [f"{i:02d}" for i in range(24)]
        minute_options = [f"{i:02d}" for i in range(60)]
        self.hour_combo = ttk.Combobox(self, textvariable=self.hour_var, values=hour_options, width=3)
        self.hour_combo.grid(row=1, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(self, text=":").grid(row=1, column=1, padx=0, pady=5, sticky="e")
        self.minute_combo = ttk.Combobox(self, textvariable=self.minute_var, values=minute_options, width=3)
        self.minute_combo.grid(row=1, column=2, padx=2, pady=5, sticky="w")

        ttk.Label(self, text="Station Name:").grid(row=2, column=0, padx=5, pady=5)
        self.station_entry = ttk.Entry(self)
        if existing_data:
            self.station_entry.insert(0, existing_data.get('station', ''))
        self.station_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(self, text="Location:").grid(row=3, column=0, padx=5, pady=5)
        self.location_entry = ttk.Entry(self)
        if existing_data:
            self.location_entry.insert(0, existing_data.get('location', ''))
        self.location_entry.grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(self, text="Amount (KES):").grid(row=4, column=0, padx=5, pady=5)
        self.amount_entry = ttk.Entry(self)
        if existing_data:
            self.amount_entry.insert(0, str(existing_data.get('amount', '')))
        self.amount_entry.grid(row=4, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(self, text="Price per Liter (KES):").grid(row=5, column=0, padx=5, pady=5)
        self.price_entry = ttk.Entry(self)
        if existing_data:
            self.price_entry.insert(0, str(existing_data.get('price_per_liter', default_price)))
        else:
            self.price_entry.insert(0, str(default_price))
        self.price_entry.grid(row=5, column=1, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Button(self, text="Save", command=self.on_save).grid(row=6, column=0, columnspan=3, pady=5)

        self.edit_id = existing_data.get('id') if existing_data else None

    def on_save(self):
        try:
            date_str = self.date_entry.get_date().strftime("%Y-%m-%d")
            hour_str = self.hour_var.get()
            minute_str = self.minute_var.get()
            station = self.station_entry.get().strip()
            location = self.location_entry.get().strip()

            amount_str = self.amount_entry.get()
            price_str = self.price_entry.get()

            amount = validate_positive_float(amount_str, "Amount")
            if amount is None:
                return
            price = validate_positive_float(price_str, "Price per Liter")
            if price is None:
                return

            if not station:
                messagebox.showerror("Error", "Station name is required.")
                return
            if not location:
                messagebox.showerror("Error", "Location is required.")
                return

            try:
                refuel_datetime_str = f"{date_str} {hour_str}:{minute_str}"
                refuel_datetime_naive = datetime.strptime(refuel_datetime_str, "%Y-%m-%d %H:%M")

                # Get the EAT timezone
                eat_timezone = pytz.timezone('Africa/Nairobi')

                # Make refuel_datetime timezone-aware
                refuel_datetime = eat_timezone.localize(refuel_datetime_naive)

                now = datetime.now(tz=datetime.now().astimezone().tzinfo) # Be timezone-aware
                if refuel_datetime > now:
                    messagebox.showerror("Error", "Refuel time cannot be in the future.")
                    return
                refuel_time_formatted = refuel_datetime.strftime("%H:%M")
            except ValueError:
                messagebox.showerror("Error", "Invalid time format.")
                return
            except pytz.exceptions.UnknownTimeZoneError:
                messagebox.showerror("Error", "Timezone information could not be determined.")
                return

            liters = amount / price
            if liters > MAX_TANK_CAPACITY:
                messagebox.showerror("Error", "Fuel added exceeds tank capacity.")
                return

            self.result = {
                "date": date_str,
                "time": refuel_time_formatted,
                "station": station,
                "location": location,
                "amount": amount,
                "price_per_liter": price,
                "liters": liters,
                "id": self.edit_id
            }
            self.destroy()
            logging.info(f"Fuel dialog saved: {self.result}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            logging.error(f"Error in FuelDialog save: {e}")

class UberWallet:
    def __init__(self, root):
        self.root = root
        self.balance = 0.0
        self.trips = []
        self.fuel_logs = []
        self.current_fuel = 0.0  # Liters remaining
        self.fuel_efficiency = tk.DoubleVar(value=DEFAULT_FUEL_EFFICIENCY)
        self.petrol_price = tk.DoubleVar(value=DEFAULT_PETROL_PRICE)
        self.load_data()

        # Set up main window
        self.root.title("Uber Wallet Tracker")
        self.setup_ui()

    def _create_connection(self):
        """Create a database connection to the SQLite database."""
        try:
            conn = sqlite3.connect(DB_FILE)
            return conn
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            messagebox.showerror("Database Error", f"Could not connect to the database: {e}")
            return None

    def _create_tables(self, conn):
        """Create the trips and fuel_logs tables if they don't exist."""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    end_time TEXT,
                    duration TEXT,
                    cash_collected REAL DEFAULT 0.0,
                    fare REAL NOT NULL DEFAULT 0.0,
                    service_fee REAL DEFAULT 0.0,
                    taxes REAL DEFAULT 0.0,
                    distance_km REAL NOT NULL DEFAULT 0.0,
                    tips REAL DEFAULT 0.0,
                    earnings REAL DEFAULT 0.0,
                    trip_balance REAL DEFAULT 0.0,
                    discount REAL DEFAULT 0.0,
                    discount_rate REAL DEFAULT 0.0,
                    earnings_per_km REAL DEFAULT 0.0,
                    fuel_used REAL DEFAULT 0.0,
                    estimated_fuel_cost REAL DEFAULT 0.0,
                    service_fee_percent REAL DEFAULT 0.0,
                    taxes_percent REAL DEFAULT 0.0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fuel_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    station TEXT,
                    location TEXT,
                    amount REAL DEFAULT 0.0,
                    price_per_liter REAL DEFAULT 0.0,
                    liters REAL DEFAULT 0.0
                )
            """)
            conn.commit()
            logging.info("Database tables created or already exist.")
        except sqlite3.Error as e:
            logging.error(f"Error creating tables: {e}")
            messagebox.showerror("Database Error", f"Could not create database tables: {e}")

    def load_data(self, trip_offset=0, trip_limit=100, fuel_offset=0, fuel_limit=100):
        """Load trips and fuel logs from the SQLite database with pagination."""
        conn = self._create_connection()
        if conn:
            self._create_tables(conn)
            try:
                cursor = conn.cursor()
                # Load trips with pagination
                cursor.execute("SELECT * FROM trips ORDER BY date DESC, time DESC LIMIT ? OFFSET ?", (trip_limit, trip_offset))
                rows = cursor.fetchall()
                self.trips = [dict(zip(['id'] + TRIP_FIELDS, row)) for row in rows]
                self.balance = sum(trip['trip_balance'] for trip in self.trips)
                logging.info(f"Loaded {len(self.trips)} trips from the database (offset: {trip_offset}, limit: {trip_limit}).")

                # Load fuel logs with pagination
                cursor.execute("SELECT * FROM fuel_logs ORDER BY date DESC, time DESC LIMIT ? OFFSET ?", (fuel_limit, fuel_offset))
                rows = cursor.fetchall()
                self.fuel_logs = [dict(zip(['id'] + FUEL_LOG_FIELDS, row)) for row in rows]
                logging.info(f"Loaded {len(self.fuel_logs)} fuel logs from the database (offset: {fuel_offset}, limit: {fuel_limit}).")

                # Calculate remaining fuel
                total_refueled = sum(log.get("liters", 0) for log in self.fuel_logs)
                total_used = sum(trip.get("fuel_used", 0) for trip in self.trips)
                self.current_fuel = total_refueled - total_used

            except sqlite3.Error as e:
                logging.error(f"Error loading data from database: {e}")
                messagebox.showerror("Database Error", f"Could not load data: {e}")
            finally:
                conn.close()

    def save_data(self):
        """Save all data to the SQLite database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                # Clear existing trips and save current trips
                cursor.execute("DELETE FROM trips")
                for trip in self.trips:
                    cursor.execute(f"""
                        INSERT INTO trips ({', '.join(TRIP_FIELDS)})
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [trip.get(field) for field in TRIP_FIELDS])
                logging.info(f"Saved {len(self.trips)} trips to the database.")

                # Clear existing fuel logs and save current logs
                cursor.execute("DELETE FROM fuel_logs")
                for log in self.fuel_logs:
                    cursor.execute(f"""
                        INSERT INTO fuel_logs ({', '.join(FUEL_LOG_FIELDS)})
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, [log.get(field) for field in FUEL_LOG_FIELDS])
                logging.info(f"Saved {len(self.fuel_logs)} fuel logs to the database.")

                conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Error saving data to database: {e}")
                messagebox.showerror("Database Error", f"Could not save data: {e}")
            finally:
                conn.close()

    def update_trip_in_db(self, trip_data):
        """Updates an existing trip in the database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                placeholders = ', '.join(f"{field}=?" for field in TRIP_FIELDS[1:])
                sql = f"UPDATE trips SET {placeholders} WHERE id=?"
                values = [trip_data.get(field) for field in TRIP_FIELDS[1:]] + [trip_data['id']]
                cursor.execute(sql, values)
                conn.commit()
                logging.info(f"Trip with ID {trip_data['id']} updated in the database.")
            except sqlite3.Error as e:
                logging.error(f"Error updating trip in database: {e}")
                messagebox.showerror("Database Error", f"Could not update trip: {e}")
            finally:
                conn.close()

    def delete_trip_from_db(self, trip_id):
        """Deletes a trip from the database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM trips WHERE id=?", (trip_id,))
                conn.commit()
                logging.info(f"Trip with ID {trip_id} deleted from the database.")
            except sqlite3.Error as e:
                logging.error(f"Error deleting trip from database: {e}")
                messagebox.showerror("Database Error", f"Could not delete trip: {e}")
            finally:
                conn.close()

    def update_fuel_log_in_db(self, fuel_data):
        """Updates an existing fuel log in the database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                placeholders = ', '.join(f"{field}=?" for field in FUEL_LOG_FIELDS[1:])
                sql = f"UPDATE fuel_logs SET {placeholders} WHERE id=?"
                values = [fuel_data.get(field) for field in FUEL_LOG_FIELDS[1:]] + [fuel_data['id']]
                cursor.execute(sql, values)
                conn.commit()
                logging.info(f"Fuel log with ID {fuel_data['id']} updated in the database.")
            except sqlite3.Error as e:
                logging.error(f"Error updating fuel log in database: {e}")
                messagebox.showerror("Database Error", f"Could not update fuel log: {e}")
            finally:
                conn.close()

    def delete_fuel_log_from_db(self, log_id):
        """Deletes a fuel log from the database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM fuel_logs WHERE id=?", (log_id,))
                conn.commit()
                logging.info(f"Fuel log with ID {log_id} deleted from the database.")
            except sqlite3.Error as e:
                logging.error(f"Error deleting fuel log from database: {e}")
                messagebox.showerror("Database Error", f"Could not delete fuel log: {e}")
            finally:
                conn.close()

    def setup_ui(self):
        self.style = ttk.Style()
        self.style.theme_use('clam') # Choose a modern theme

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')

        self.setup_trips_tab()
        self.setup_fuel_tab()
        self.setup_reports_tab()
        self.setup_settings_tab()

    def setup_trips_tab(self):
        self.trips_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.trips_tab, text='Trips')

        ttk.Button(self.trips_tab, text="Add Trip", command=self.add_trip).pack(pady=5, padx=10, fill='x')

        self.trips_tree = ttk.Treeview(self.trips_tab, columns=['date', 'time', 'end_time', 'duration', 'distance_km', 'fare', 'cash_collected', 'service_fee', 'taxes', 'tips', 'earnings', 'trip_balance', 'estimated_fuel_cost'], show="headings")
        columns = ['date', 'time', 'end_time', 'duration', 'distance_km', 'fare', 'cash_collected', 'service_fee', 'taxes', 'tips', 'earnings', 'trip_balance', 'estimated_fuel_cost']
        for col in columns:
            self.trips_tree.heading(col, text=col.replace('_', ' ').title(),
                                 command=lambda c=col: sort_treeview(self.trips_tree, c, False))
            self.trips_tree.column(col, width=100, anchor='center')
        self.trips_tree.pack(expand=True, fill="both")
        populate_treeview(self.trips_tree, self.trips, columns)

        edit_delete_frame = ttk.Frame(self.trips_tab)
        edit_delete_frame.pack(pady=5, padx=10, fill='x')
        ttk.Button(edit_delete_frame, text="Edit Trip", command=self.edit_selected_trip).pack(side='left', padx=5)
        ttk.Button(edit_delete_frame, text="Delete Trip", command=self.delete_selected_trip).pack(side='left', padx=5)

    def setup_fuel_tab(self):
        self.fuel_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.fuel_tab, text='Fuel')

        ttk.Button(self.fuel_tab, text="Add Fuel", command=self.add_fuel).pack(pady=5, padx=10, fill='x')

        self.fuel_tree = ttk.Treeview(self.fuel_tab, columns=FUEL_LOG_FIELDS, show="headings")
        for field in FUEL_LOG_FIELDS:
            self.fuel_tree.heading(field, text=field.replace('_', ' ').title(),
                                 command=lambda f=field: sort_treeview(self.fuel_tree, f, False))
            self.fuel_tree.column(field, width=100)
        self.fuel_tree.pack(expand=True, fill="both")
        populate_treeview(self.fuel_tree, self.fuel_logs, FUEL_LOG_FIELDS)

        edit_delete_frame = ttk.Frame(self.fuel_tab)
        edit_delete_frame.pack(pady=5, padx=10, fill='x')
        ttk.Button(edit_delete_frame, text="Edit Fuel Log", command=self.edit_selected_fuel_log).pack(side='left', padx=5)
        ttk.Button(edit_delete_frame, text="Delete Fuel Log", command=self.delete_selected_fuel_log).pack(side='left', padx=5)

    def setup_reports_tab(self):
        self.reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text='Reports')

        ttk.Button(self.reports_tab, text="Wallet Balance", command=self.show_balance).pack(pady=5, padx=10, fill='x')
        ttk.Button(self.reports_tab, text="Summary", command=self.show_summary).pack(pady=5, padx=10, fill='x')
        ttk.Button(self.reports_tab, text="Generate Reports", command=self.show_reports_dialog).pack(pady=5, padx=10, fill='x')
        ttk.Button(self.reports_tab, text="Export Reports", command=self.export_reports).pack(pady=5, padx=10, fill='x')

    def setup_settings_tab(self):
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text='Settings')

        # Fuel Efficiency
        ttk.Label(self.settings_tab, text="Default Fuel Efficiency (km/liter):").pack(pady=5, padx=10, anchor='w')
        self.fuel_efficiency_entry = ttk.Entry(self.settings_tab, textvariable=self.fuel_efficiency, width=10)
        self.fuel_efficiency_entry.pack(pady=5, padx=10, anchor='w')

        # Petrol Price
        ttk.Label(self.settings_tab, text="Default Petrol Price (KES/liter):").pack(pady=5, padx=10, anchor='w')
        self.petrol_price_entry = ttk.Entry(self.settings_tab, textvariable=self.petrol_price, width=10)
        self.petrol_price_entry.pack(pady=5, padx=10, anchor='w')

        ttk.Button(self.settings_tab, text="Save Settings", command=self.save_settings).pack(pady=10, padx=10)
        ttk.Button(self.settings_tab, text="Backup Data", command=self.backup_database).pack(pady=5, padx=10)

    def save_settings(self):
        try:
            new_fuel_efficiency = float(self.fuel_efficiency.get())
            new_petrol_price = float(self.petrol_price.get())
            if new_fuel_efficiency <= 0 or new_petrol_price <= 0:
                raise ValueError("Fuel efficiency and petrol price must be positive values.")
            global DEFAULT_FUEL_EFFICIENCY
            global DEFAULT_PETROL_PRICE
            DEFAULT_FUEL_EFFICIENCY = new_fuel_efficiency
            DEFAULT_PETROL_PRICE = new_petrol_price
            self.recalculate_trip_data() # Recalculate based on new settings
            self.update_trips_view()
            messagebox.showinfo("Success", "Settings saved successfully!")
            logging.info(f"Settings saved: Fuel Efficiency={DEFAULT_FUEL_EFFICIENCY}, Petrol Price={DEFAULT_PETROL_PRICE}")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            logging.error(f"Error saving settings: {e}")

    def recalculate_trip_data(self):
        """Recalculates derived fields for all trips based on current settings."""
        for trip in self.trips:
            trip["earnings"] = trip["fare"] - (trip["service_fee"] + trip["taxes"]) + trip["tips"]
            trip["trip_balance"] = trip["fare"] - (trip["cash_collected"] + trip["service_fee"] + trip["taxes"])
            trip["discount"] = trip["fare"] - trip["cash_collected"]
            trip["discount_rate"] = round((trip["discount"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0
            trip["earnings_per_km"] = round(trip["earnings"] / trip["distance_km"], 2) if trip["distance_km"] else 0.0
            trip["fuel_used"] = round(trip["distance_km"] / DEFAULT_FUEL_EFFICIENCY, 2) if trip["distance_km"] else 0.0
            trip["estimated_fuel_cost"] = round(trip["fuel_used"] * DEFAULT_PETROL_PRICE, 2)
            trip["service_fee_percent"] = round((trip["service_fee"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0
            trip["taxes_percent"] = round((trip["taxes"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0
        self.save_data() # Save the recalculated data

    def update_trips_view(self):
        """Updates the trips treeview with the current trip data."""
        columns = ['date', 'time', 'end_time', 'duration', 'distance_km', 'fare', 'cash_collected', 'service_fee', 'taxes', 'tips', 'earnings', 'trip_balance', 'estimated_fuel_cost']
        populate_treeview(self.trips_tree, self.trips, columns)

    def update_fuel_logs_view(self):
        """Updates the fuel logs treeview with the current fuel log data."""
        populate_treeview(self.fuel_tree, self.fuel_logs, FUEL_LOG_FIELDS)

    def is_duplicate_trip(self, new_trip):
        """Check if a trip with the same key details already exists in the database."""
        conn = self._create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM trips
                    WHERE date=? AND time=? AND distance_km=? AND fare=?
                """, (new_trip['date'], new_trip['time'], new_trip['distance_km'], new_trip['fare']))
                result = cursor.fetchone()
                return result[0] > 0
            except sqlite3.Error as e:
                logging.error(f"Error checking for duplicate trip: {e}")
                messagebox.showerror("Database Error", "Could not check for duplicate trip.")
                return False
            finally:
                conn.close()

    def add_trip(self):
        """Add a new Uber trip with enhanced time input and date selection."""
        date_dialog = tk.Toplevel(self.root)
        date_dialog.title("Select Trip Date")
        date_entry = DateEntry(date_dialog, width=12, background='darkblue',
                               foreground='white', borderwidth=2,
                               maxdate=datetime.now().date())  # Prevent future dates
        date_entry.pack(padx=10, pady=10)
        selected_date = tk.StringVar()

        def get_date():
            date = date_entry.get_date()
            if date is None:
                messagebox.showerror("Error", "Please select a valid date.")
                return
            selected_date.set(date.strftime("%Y-%m-%d"))
            date_dialog.destroy()

        ttk.Button(date_dialog, text="OK", command=get_date).pack(pady=5)
        self.root.wait_window(date_dialog)

        date = selected_date.get()
        if not date:  # User might have closed the window without selecting
            return

        time_dialog = TimeInputDialog(self.root)
        time_dialog.set_date(date) # Pass the selected date to the time dialog
        self.root.wait_window(time_dialog)

        time_info = time_dialog.result
        if not time_info:
            return

        start_time, duration, end_time = time_info

        # Create input dialog for other fields
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Trip Details")

        # Display time information
        ttk.Label(dialog, text=f"Date: {date} | Start: {start_time} | End: {end_time} | Duration: {duration}").grid(row=0, column=0, columnspan=2, padx=5, pady=5)

        # Add other fields
        fields = [
            ("Cash Collected (KES):", "cash_collected"),
            ("Fare (KES):", "fare"),
            ("Service Fee (KES):", "service_fee"),
            ("Taxes (KES):", "taxes"),
            ("Distance (km):", "distance_km"),
            ("Tips (KES):", "tips")  # New tips field
        ]

        entries = {}
        fields_dict = dict(fields)
        for i, (label, key) in enumerate(fields, start=1):
            ttk.Label(dialog, text=label).grid(row=i, column=0, padx=5, pady=5, sticky='w')
            entries[key] = ttk.Entry(dialog)
            entries[key].grid(row=i, column=1, padx=5, pady=5, sticky='ew')
            if key == "tips":
                entries[key].insert(0, "0")  # Default tip value
            add_tooltip(entries[key], f"Enter the {label.replace('(KES):', '').replace('(km):', '').strip()}")

        def save_trip():
            try:
                trip = {
                    "date": date,
                    "time": start_time,
                    "end_time": end_time,
                    "duration": duration
                }
                for key, entry in entries.items():
                    value_str = entry.get()
                    if value_str:
                        validated_value = validate_positive_float(value_str, fields_dict.get(key))
                        if validated_value is None:
                            return
                        trip[key] = validated_value
                    else:
                        trip[key] = 0.0

                # Basic validation for required fields
                if not trip['distance_km'] >= 0:
                    messagebox.showerror("Error", "Distance cannot be negative.")
                    return
                if not trip['fare'] >= 0:
                    messagebox.showerror("Error", "Fare cannot be negative.")
                    return

                # Calculate metrics
                trip["earnings"] = trip["fare"] - (trip["service_fee"] + trip["taxes"]) + trip["tips"]
                trip["trip_balance"] = trip["fare"] - (trip["cash_collected"] + trip["service_fee"] + trip["taxes"])
                trip["discount"] = trip["fare"] - trip["cash_collected"]
                trip["discount_rate"] = round((trip["discount"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0
                trip["earnings_per_km"] = round(trip["earnings"] / trip["distance_km"], 2) if trip["distance_km"] else 0.0
                trip["fuel_used"] = round(trip["distance_km"] / self.fuel_efficiency.get(), 2) if trip["distance_km"] else 0.0
                trip["estimated_fuel_cost"] = round(trip["fuel_used"] * self.petrol_price.get(), 2)
                trip["service_fee_percent"] = round((trip["service_fee"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0
                trip["taxes_percent"] = round((trip["taxes"] / trip["fare"]) * 100, 2) if trip["fare"] else 0.0

                # Check for duplicates
                if self.is_duplicate_trip(trip):
                    messagebox.showerror("Error", "Duplicate trip detected - not saved")
                    dialog.destroy()
                    return

                # Update wallet and fuel
                self.balance += trip["trip_balance"]
                self.trips.insert(0, trip)  # Add at beginning to maintain reverse chronological order
                self.current_fuel -= trip["fuel_used"]

                # Save to database
                self.save_data()
                self.update_trips_view()
                messagebox.showinfo("Success", "Trip added successfully!")
                dialog.destroy()
                logging.info(f"User added a trip: {trip}")

            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {e}")
                logging.error(f"Error saving trip: {e}")

        ttk.Button(dialog, text="Save", command=save_trip).grid(row=len(fields)+1, columnspan=2, pady=10)

    def edit_selected_trip(self):
        selected_item = self.trips_tree.selection()
        if not selected_item:
            messagebox.showinfo("Info", "Please select a trip to edit.")
            return

        selected_index = self.trips_tree.index(selected_item[0])
        trip_to_edit = self.trips[selected_index]

        date = trip_to_edit['date']

        time_dialog = TimeInputDialog(self.root, existing_start_time=trip_to_edit['time'], existing_duration=trip_to_edit['duration'])
        time_dialog.set_date(date)
        self.root.wait_window(time_dialog)

        time_info = time_dialog.result
        if not time_info:
            return

        start_time, duration, end_time = time_info

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Trip Details")

        ttk.Label(dialog, text=f"Date: {date} | Start: {start_time} | End: {end_time} | Duration: {duration}").grid(row=0, column=0, columnspan=2, padx=5, pady=5)

        fields = [
            ("Cash Collected (KES):", "cash_collected"),
            ("Fare (KES):", "fare"),
            ("Service Fee (KES):", "service_fee"),
            ("Taxes (KES):", "taxes"),
            ("Distance (km):", "distance_km"),
            ("Tips (KES):", "tips")
        ]

        entries = {}
        fields_dict = dict(fields)
        for i, (label, key) in enumerate(fields, start=1):
            ttk.Label(dialog, text=label).grid(row=i, column=0, padx=5, pady=5, sticky='w')
            entries[key] = ttk.Entry(dialog)
            entries[key].insert(0, str(trip_to_edit.get(key, '')))
            entries[key].grid(row=i, column=1, padx=5, pady=5, sticky='ew')
            add_tooltip(entries[key], f"Enter the {label.replace('(KES):', '').replace('(km):', '').strip()}")

        def update_trip():
            try:
                updated_trip = {
                    "id": trip_to_edit['id'],
                    "date": date,
                    "time": start_time,
                    "end_time": end_time,
                    "duration": duration
                }
                for key, entry in entries.items():
                    value_str = entry.get()
                    if value_str:
                        validated_value = validate_positive_float(value_str, fields_dict.get(key))
                        if validated_value is None:
                            return
                        updated_trip[key] = validated_value
                    else:
                        updated_trip[key] = 0.0

                if not updated_trip['distance_km'] >= 0:
                    messagebox.showerror("Error", "Distance cannot be negative.")
                    return
                if not updated_trip['fare'] >= 0:
                    messagebox.showerror("Error", "Fare cannot be negative.")
                    return

                updated_trip["earnings"] = updated_trip["fare"] - (updated_trip["service_fee"] + updated_trip["taxes"]) + updated_trip["tips"]
                updated_trip["trip_balance"] = updated_trip["fare"] - (updated_trip["cash_collected"] + updated_trip["service_fee"] + updated_trip["taxes"])
                updated_trip["discount"] = updated_trip["fare"] - updated_trip["cash_collected"]
                updated_trip["discount_rate"] = round((updated_trip["discount"] / updated_trip["fare"]) * 100, 2) if updated_trip["fare"] else 0.0
                updated_trip["earnings_per_km"] = round(updated_trip["earnings"] / updated_trip["distance_km"], 2) if updated_trip["distance_km"] else 0.0
                updated_trip["fuel_used"] = round(updated_trip["distance_km"] / self.fuel_efficiency.get(), 2) if updated_trip["distance_km"] else 0.0
                updated_trip["estimated_fuel_cost"] = round(updated_trip["fuel_used"] * self.petrol_price.get(), 2)
                updated_trip["service_fee_percent"] = round((updated_trip["service_fee"] / updated_trip["fare"]) * 100, 2) if updated_trip["fare"] else 0.0
                updated_trip["taxes_percent"] = round((updated_trip["taxes"] / updated_trip["fare"]) * 100, 2) if updated_trip["fare"] else 0.0

                # Update in the list
                self.trips[selected_index] = updated_trip
                self.recalculate_balance_and_fuel() # Recalculate balance and fuel
                self.update_trip_in_db(updated_trip)
                self.update_trips_view()
                messagebox.showinfo("Success", "Trip updated successfully!")
                dialog.destroy()
                logging.info(f"User updated trip: {updated_trip}")

            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {e}")
                logging.error(f"Error updating trip: {e}")

        ttk.Button(dialog, text="Update", command=update_trip).grid(row=len(fields)+1, columnspan=2, pady=10)

    def delete_selected_trip(self):
        selected_item = self.trips_tree.selection()
        if not selected_item:
            messagebox.showinfo("Info", "Please select a trip to delete.")
            return

        selected_index = self.trips_tree.index(selected_item[0])
        trip_to_delete = self.trips[selected_index]

        if messagebox.askyesno("Confirm", f"Are you sure you want to delete the trip on {trip_to_delete['date']} at {trip_to_delete['time']}?"):
            self.trips.pop(selected_index)
            self.delete_trip_from_db(trip_to_delete['id'])
            self.recalculate_balance_and_fuel()
            self.update_trips_view()
            messagebox.showinfo("Success", "Trip deleted successfully!")
            logging.info(f"User deleted trip with ID: {trip_to_delete['id']}")

    def add_fuel(self):
        """Add fuel refill record, with date and time input."""
        dialog = FuelDialog(self.root, self.petrol_price.get())
        self.root.wait_window(dialog)

        if dialog.result:
            if dialog.result["liters"] > MAX_TANK_CAPACITY:
                messagebox.showerror("Error", "Fuel added exceeds tank capacity.")
                return
            self.fuel_logs.insert(0, dialog.result)  # Add at beginning
            self.recalculate_current_fuel()
            self.save_data()
            self.update_fuel_logs_view()
            messagebox.showinfo("Success", "Fuel refill recorded!")
            logging.info(f"User added fuel: {dialog.result}")

    def edit_selected_fuel_log(self):
        selected_item = self.fuel_tree.selection()
        if not selected_item:
            messagebox.showinfo("Info", "Please select a fuel log to edit.")
            return

        selected_index = self.fuel_tree.index(selected_item[0])
        log_to_edit = self.fuel_logs[selected_index]

        dialog = FuelDialog(self.root, self.petrol_price.get(), existing_data=log_to_edit)
        self.root.wait_window(dialog)

        if dialog.result:
            self.fuel_logs[selected_index] = dialog.result
            self.recalculate_current_fuel()
            self.update_fuel_log_in_db(dialog.result)
            self.update_fuel_logs_view()
            messagebox.showinfo("Success", "Fuel log updated successfully!")
            logging.info(f"User updated fuel log with ID: {dialog.result['id']}")

    def delete_selected_fuel_log(self):
        selected_item = self.fuel_tree.selection()
        if not selected_item:
            messagebox.showinfo("Info", "Please select a fuel log to delete.")
            return

        selected_index = self.fuel_tree.index(selected_item[0])
        log_to_delete = self.fuel_logs[selected_index]

        if messagebox.askyesno("Confirm", f"Are you sure you want to delete the fuel log on {log_to_delete['date']} at {log_to_delete['time']}?"):
            self.fuel_logs.pop(selected_index)
            self.delete_fuel_log_from_db(log_to_delete['id'])
            self.recalculate_current_fuel()
            self.update_fuel_logs_view()
            messagebox.showinfo("Success", "Fuel log deleted successfully!")
            logging.info(f"User deleted fuel log with ID: {log_to_delete['id']}")

    def recalculate_balance_and_fuel(self):
        """Recalculates the wallet balance and current fuel based on the current lists."""
        self.balance = sum(trip['trip_balance'] for trip in self.trips)
        self.recalculate_current_fuel()

    def recalculate_current_fuel(self):
        """Recalculates the current fuel level."""
        total_refueled = sum(log.get("liters", 0) for log in self.fuel_logs)
        total_used = sum(trip.get("fuel_used", 0) for trip in self.trips)
        self.current_fuel = total_refueled - total_used

    def show_balance(self):
        """Show current wallet balance."""
        message = (
            f"Current Wallet Balance: KES {self.balance:.2f}\n"
            f"Total Earnings: KES {sum(trip['earnings'] for trip in self.trips):.2f}\n"
            f"Total Tips: KES {sum(trip.get('tips', 0) for trip in self.trips):.2f}"
        )
        messagebox.showinfo("Wallet Balance", message)
        logging.info("Wallet balance displayed.")

    def _generate_monthly_earnings_graph(self, month, year):
        """Generates a simple monthly earnings graph."""
        filtered_trips = [
            trip for trip in self.trips
            if datetime.strptime(trip['date'], '%Y-%m-%d').year == year and
               datetime.strptime(trip['date'], '%Y-%m-%d').month == month
        ]

        if not filtered_trips:
            messagebox.showinfo("Info", "No data available for the selected month to generate a graph.")
            return None

        earnings_by_day = {}
        for trip in filtered_trips:
            day = datetime.strptime(trip['date'], '%Y-%m-%d').day
            earnings_by_day[day] = earnings_by_day.get(day, 0) + trip['earnings']

        days = sorted(earnings_by_day.keys())
        earnings = [earnings_by_day[day] for day in days]

        fig = Figure(figsize=(8, 6), dpi=100)
        plot = fig.add_subplot(111)
        plot.plot(days, earnings, marker='o')
        plot.set_xlabel("Day")
        plot.set_ylabel("Earnings (KES)")
        plot.set_title(f"Monthly Earnings for {month:02d}/{year}")
        plot.grid(True)

        return fig

    def generate_report(self, report_type, start_date=None, end_date=None, month=None, year=None, day=None):
        """Generate daily, weekly, or monthly report with date selection."""
        if not self.trips:
            return "No trip data available."

        filtered_trips = []
        report_title = ""

        if report_type == "daily":
            if day:
                date_str = day.strftime('%Y-%m-%d')
                report_title = f"Daily Report for {date_str}"
                filtered_trips = [trip for trip in self.trips if trip['date'] == date_str]
            else:
                return "Please select a date for the daily report."
        elif report_type == "weekly":
            if start_date and end_date:
                report_title = f"Weekly Report for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                filtered_trips = [
                    trip for trip in self.trips
                    if start_date <= datetime.strptime(trip['date'], '%Y-%m-%d').date() <= end_date
                ]
            else:
                return "Please select start and end dates for the weekly report."
        elif report_type == "monthly":
            if month and year:
                report_title = f"Monthly Report for {month:02d}/{year}"
                filtered_trips = [
                    trip for trip in self.trips
                    if datetime.strptime(trip['date'], '%Y-%m-%d').year == year and
                       datetime.strptime(trip['date'], '%Y-%m-%d').month == month
                ]
            else:
                return "Please select month and year for the monthly report."
        else:
            return "Invalid report type."

        if not filtered_trips:
            return f"No trips found for the selected period."

        total_earnings = sum(trip["earnings"] for trip in filtered_trips)
        total_distance = sum(trip["distance_km"] for trip in filtered_trips)
        total_fuel_cost = sum(trip["estimated_fuel_cost"] for trip in filtered_trips)

        report = f"\n{report_title}\n{'='*len(report_title)}\n"
        report += f"Total Trips: {len(filtered_trips)}\n"
        report += f"Total Distance: {total_distance:.1f} km\n"
        report += f"Total Earnings: KES {total_earnings:.2f}\n"
        report += f"Estimated Total Fuel Cost: KES {total_fuel_cost:.2f}\n"
        report += f"Net Earnings (Earnings - Estimated Fuel Cost): KES {total_earnings - total_fuel_cost:.2f}\n"
        logging.info(f"{report_title} generated.")
        return report

    def show_monthly_report_dialog(self):
        report_window = tk.Toplevel(self.root)
        report_window.title("Select Month and Year")

        current_year = datetime.now().year
        years = list(range(2020, current_year + 2))
        months = list(range(1, 13))

        ttk.Label(report_window, text="Month:").grid(row=0, column=0, padx=5, pady=5)
        month_var = tk.IntVar(value=datetime.now().month)
        month_combo = ttk.Combobox(report_window, textvariable=month_var, values=months, width=5)
        month_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(report_window, text="Year:").grid(row=1, column=0, padx=5, pady=5)
        year_var = tk.IntVar(value=current_year)
        year_combo = ttk.Combobox(report_window, textvariable=year_var, values=years, width=7)
        year_combo.grid(row=1, column=1, padx=5, pady=5)

        def get_monthly_report():
            month = month_var.get()
            year = year_var.get()
            report_text = self.generate_report("monthly", month=month, year=year)

            # Generate and display graph (may not work directly in this environment)
            fig = self._generate_monthly_earnings_graph(month, year)
            if fig:
                graph_window = tk.Toplevel(report_window)
                graph_window.title(f"Earnings Graph for {month:02d}/{year}")
                canvas = FigureCanvasTkAgg(fig, master=graph_window)
                canvas_widget = canvas.get_tk_widget()
                canvas_widget.pack(fill='both', expand=True)
                canvas.draw()

            messagebox.showinfo("Monthly Report", report_text)
            report_window.destroy()
            logging.info(f"Monthly report requested for {month}/{year}.")

        ttk.Button(report_window, text="OK", command=get_monthly_report).grid(row=2, columnspan=2, pady=5)
        report_window.wait_window(report_window)

    def show_reports_dialog(self):
        """Display options for generating reports with date selection."""
        report_window = tk.Toplevel(self.root)
        report_window.title("Reports")

        def show_daily_report_dialog():
            date_dialog = tk.Toplevel(report_window)
            date_dialog.title("Select Date")
            cal = DateEntry(date_dialog, width=12, background='darkblue',
                            foreground='white', borderwidth=2,
                            maxdate=datetime.now().date())
            cal.pack(padx=10, pady=10)

            def get_daily_date():
                date = cal.get_date()
                if date:
                    report = self.generate_report("daily", day=date)
                    messagebox.showinfo("Daily Report", report)
                date_dialog.destroy()
                logging.info(f"Daily report requested for {date}.")

            ttk.Button(date_dialog, text="OK", command=get_daily_date).pack(pady=5)
            report_window.wait_window(date_dialog)

        def show_weekly_report_dialog():
            week_dialog = tk.Toplevel(report_window)
            week_dialog.title("Select Week Range")

            ttk.Label(week_dialog, text="Start Date:").grid(row=0, column=0, padx=5, pady=5)
            start_cal = DateEntry(week_dialog, width=12, background='darkblue',
                                   foreground='white', borderwidth=2,
                                   maxdate=datetime.now().date())
            start_cal.grid(row=0, column=1, padx=5, pady=5)

            ttk.Label(week_dialog, text="End Date:").grid(row=1, column=0, padx=5, pady=5)
            end_cal = DateEntry(week_dialog, width=12, background='darkblue',
                                 foreground='white', borderwidth=2,
                                 maxdate=datetime.now().date())
            end_cal.grid(row=1, column=1, padx=5, pady=5)

            def get_weekly_dates():
                start_date = start_cal.get_date()
                end_date = end_cal.get_date()
                if start_date and end_date and start_date <= end_date:
                    report = self.generate_report("weekly", start_date=start_date, end_date=end_date)
                    messagebox.showinfo("Weekly Report", report)
                    logging.info(f"Weekly report requested for {start_date} to {end_date}.")
                elif not start_date or not end_date:
                    messagebox.showerror("Error", "Please select both start and end dates.")
                else:
                    messagebox.showerror("Error", "Start date must be before or the same as the end date.")
                week_dialog.destroy()

            ttk.Button(week_dialog, text="OK", command=get_weekly_dates).grid(row=2, columnspan=2, pady=5)
            report_window.wait_window(week_dialog)

        ttk.Button(report_window, text="Daily Report", command=show_daily_report_dialog).pack(pady=5, padx=10, fill='x')
        ttk.Button(report_window, text="Weekly Report", command=show_weekly_report_dialog).pack(pady=5, padx=10, fill='x')
        ttk.Button(report_window, text="Monthly Report", command=self.show_monthly_report_dialog).pack(pady=5, padx=10, fill='x')

    def show_summary(self):
        """Show financial and fuel summary."""
        if not self.trips:
            messagebox.showinfo("Info", "No data for summary.")
            return

        total_earnings = sum(trip["earnings"] for trip in self.trips)
        total_trip_balance = sum(trip["trip_balance"] for trip in self.trips)
        total_discount = sum(trip["discount"] for trip in self.trips)
        total_distance = sum(trip["distance_km"] for trip in self.trips)
        total_fuel_used = sum(trip.get("fuel_used", 0) for trip in self.trips)
        total_refueled = sum(log.get("liters", 0) for log in self.fuel_logs)
        total_tips = sum(trip.get("tips", 0) for trip in self.trips)
        total_estimated_fuel_cost = sum(trip.get("estimated_fuel_cost", 0) for trip in self.trips)

        summary_text = (
            f"Total Trips: {len(self.trips)}\n"
            f"Total Distance: {total_distance:.1f} km\n"
            f"Total Earnings: KES {total_earnings:.2f}\n"
            f"Total Tips: KES {total_tips:.2f}\n"
            f"Total Trip Balance: KES {total_trip_balance:.2f}\n"
            f"Total Discounts: KES {total_discount:.2f}\n\n"
            f"Fuel Statistics:\n"
            f"Total Fuel Used: {total_fuel_used:.2f} L\n"
            f"Total Refueled: {total_refueled:.2f} L\n"
            f"Current Fuel: {self.current_fuel:.2f} L remaining\n"
            f"Estimated Total Fuel Cost: KES {total_estimated_fuel_cost:.2f}\n"
            f"Estimated Range: {self.current_fuel * self.fuel_efficiency.get():.1f} km"
        )

        messagebox.showinfo("Financial Summary", summary_text)
        logging.info("Summary displayed.")

    def backup_database(self):
        try:
            backup_file = filedialog.asksaveasfilename(defaultextension=".db",
                                                        filetypes=[("Database files", "*.db"), ("All files", "*.*")])
            if backup_file:
                shutil.copy(DB_FILE, backup_file)
                messagebox.showinfo("Success", f"Database backed up to {backup_file}")
                logging.info(f"Database backed up to: {backup_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Error backing up database: {e}")
            logging.error(f"Error backing up database: {e}")

    def export_reports(self):
        """Allows the user to choose a report type and export it to CSV."""
        export_window = tk.Toplevel(self.root)
        export_window.title("Export Reports")

        report_types = ["Daily", "Weekly", "Monthly", "Summary"]
        report_var = tk.StringVar(export_window)
        report_var.set(report_types[0]) # Default value

        ttk.Label(export_window, text="Select Report Type:").pack(pady=5)
        report_menu = ttk.Combobox(export_window, textvariable=report_var, values=report_types)
        report_menu.pack(pady=5)

        def export_to_csv():
            report_type = report_var.get().lower()
            if report_type == "summary":
                messagebox.showinfo("Info", "Summary report cannot be exported to CSV in this version.")
                return

            if report_type == "daily":
                # Implement date selection for daily report export
                date_dialog = tk.Toplevel(export_window)
                date_dialog.title("Select Date for Daily Report")
                cal = DateEntry(date_dialog, width=12, background='darkblue',
                                foreground='white', borderwidth=2,
                                maxdate=datetime.now().date())
                cal.pack(padx=10, pady=10)
                export_button = ttk.Button(date_dialog, text="Export", command=lambda: self._export_report_data_csv("daily", day=cal.get_date()))
                export_button.pack(pady=5)
                export_window.wait_window(date_dialog)
            elif report_type == "weekly":
                # Implement date range selection for weekly report export
                week_dialog = tk.Toplevel(export_window)
                week_dialog.title("Select Date Range for Weekly Report")

                ttk.Label(week_dialog, text="Start Date:").grid(row=0, column=0, padx=5, pady=5)
                start_cal = DateEntry(week_dialog, width=12, background='darkblue',
                                       foreground='white', borderwidth=2,
                                       maxdate=datetime.now().date())
                start_cal.grid(row=0, column=1, padx=5, pady=5)

                ttk.Label(week_dialog, text="End Date:").grid(row=1, column=0, padx=5, pady=5)
                end_cal = DateEntry(week_dialog, width=12, background='darkblue',
                                     foreground='white', borderwidth=2,
                                     maxdate=datetime.now().date())
                end_cal.grid(row=1, column=1, padx=5, pady=5)

                export_button = ttk.Button(week_dialog, text="Export", command=lambda: self._export_report_data_csv("weekly", start_date=start_cal.get_date(), end_date=end_cal.get_date()))
                export_button.grid(row=2, columnspan=2, pady=5)
                export_window.wait_window(week_dialog)
            elif report_type == "monthly":
                # Implement month and year selection for monthly report export
                month_year_dialog = tk.Toplevel(export_window)
                month_year_dialog.title("Select Month and Year for Monthly Report")

                current_year = datetime.now().year
                years = list(range(2020, current_year + 2))
                months = list(range(1, 13))

                ttk.Label(month_year_dialog, text="Month:").grid(row=0, column=0, padx=5, pady=5)
                month_var_export = tk.IntVar(value=datetime.now().month)
                month_combo_export = ttk.Combobox(month_year_dialog, textvariable=month_var_export, values=months, width=5)
                month_combo_export.grid(row=0, column=1, padx=5, pady=5)

                ttk.Label(month_year_dialog, text="Year:").grid(row=1, column=0, padx=5, pady=5)
                year_var_export = tk.IntVar(value=current_year)
                year_combo_export = ttk.Combobox(month_year_dialog, textvariable=year_var_export, values=years, width=7)
                year_combo_export.grid(row=1, column=1, padx=5, pady=5)

                export_button = ttk.Button(month_year_dialog, text="Export", command=lambda: self._export_report_data_csv("monthly", month=month_var_export.get(), year=year_var_export.get()))
                export_button.grid(row=2, columnspan=2, pady=5)
                export_window.wait_window(month_year_dialog)

            export_window.destroy()

        ttk.Button(export_window, text="Export", command=export_to_csv).pack(pady=10)

    def _export_report_data_csv(self, report_type, start_date=None, end_date=None, month=None, year=None, day=None):
        """Helper function to export report data to CSV."""
        if not self.trips:
            messagebox.showinfo("Info", "No trip data to export.")
            return

        filtered_trips = []
        report_title = ""
        filename = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return

        if report_type == "daily":
            if day:
                date_str = day.strftime('%Y-%m-%d')
                report_title = f"Daily Report for {date_str}"
                filtered_trips = [trip for trip in self.trips if trip['date'] == date_str]
            else:
                messagebox.showerror("Error", "Please select a date for the daily report.")
                return
        elif report_type == "weekly":
            if start_date and end_date:
                report_title = f"Weekly Report for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                filtered_trips = [
                    trip for trip in self.trips
                    if start_date <= datetime.strptime(trip['date'], '%Y-%m-%d').date() <= end_date
                ]
            else:
                messagebox.showerror("Error", "Please select start and end dates for the weekly report.")
                return
        elif report_type == "monthly":
            if month and year:
                report_title = f"Monthly Report for {month:02d}/{year}"
                filtered_trips = [
                    trip for trip in self.trips
                    if datetime.strptime(trip['date'], '%Y-%m-%d').year == year and
                       datetime.strptime(trip['date'], '%Y-%m-%d').month == month
                ]
            else:
                messagebox.showerror("Error", "Please select month and year for the monthly report.")
                return

        if not filtered_trips:
            messagebox.showinfo("Info", f"No trips found for the selected period to export.")
            return

        try:
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=TRIP_FIELDS)
                writer.writeheader()
                for trip in filtered_trips:
                    # Create a new dictionary without the 'id' key
                    trip_data_to_export = {key: value for key, value in trip.items() if key in TRIP_FIELDS}
                    writer.writerow(trip_data_to_export)
            messagebox.showinfo("Success", f"{report_title} exported to {filename}")
            logging.info(f"{report_title} exported to CSV: {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Error exporting to CSV: {e}")
            logging.error(f"Error exporting {report_title} to CSV: {e}")

def main():
    root = tk.Tk()
    app = UberWallet(root)
    root.mainloop()

if __name__ == "__main__":
    main()