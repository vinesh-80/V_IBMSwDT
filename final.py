import tkinter as tk
from tkinter import ttk
import pandas as pd
import joblib
import socket
import time
import requests
from threading import Thread

# -----------------------------
# Configuration
# -----------------------------
HOST = "192.168.137.86"
STATUS_URL = f"http://{HOST}/status"
ACTION1_URL = f"http://{HOST}/1"
ACTION2_URL = f"http://{HOST}/2"
MODEL_PATH = "catboost_rul_model.pkl"
UPDATE_INTERVAL = 2  # seconds

# ThingSpeak Configuration
THINGSPEAK_API_KEY = "GNRSRJK8C2GWOPAC"
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# Load trained model
model = joblib.load(MODEL_PATH)

# -----------------------------
# ThingSpeak update function
# -----------------------------
def update_thingspeak(voltage, charge_current, discharge_current, temperature, humidity, rul):
    try:
        payload = {
            "api_key": THINGSPEAK_API_KEY,
            "field1": voltage,
            "field2": charge_current,
            "field3": discharge_current,
            "field4": temperature,
            "field5": humidity,
            "field6": rul
        }
        requests.get(THINGSPEAK_URL, params=payload, timeout=2)
    except Exception as e:
        print("ThingSpeak update failed:", e)

# -----------------------------
# Original RUL prediction code
# -----------------------------
def get_initial_rul():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, 80))
            request = f"GET /5 HTTP/1.1\r\nHost: {HOST}\r\n\r\n"
            s.sendall(request.encode())
            data = s.recv(1024)
        
        data_str = data.decode().strip()
        if "\r\n\r\n" in data_str:
            data_str = data_str.split("\r\n\r\n")[1]
        
        data_list = [float(x) for x in data_str.split(",")]
        if len(data_list) != 5:
            raise ValueError("Expected 5 values from /5, got:", data_list)
        
        columns = ['Voltage', 'Charge_Current', 'Discharge_Current', 'Temperature', 'Humidity']
        df_new = pd.DataFrame([data_list], columns=columns)
        rul = model.predict(df_new)[0]
        return data_list, rul
    except Exception as e:
        print("Error fetching initial RUL:", e)
        return None, None

# -----------------------------
# Continuous monitoring loop
# -----------------------------
def fetch_status_data():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, 80))
            request = f"GET /status HTTP/1.1\r\nHost: {HOST}\r\n\r\n"
            s.sendall(request.encode())
            data = s.recv(1024)

        data_str = data.decode().strip()
        if "\r\n\r\n" in data_str:
            data_str = data_str.split("\r\n\r\n")[1]
        data_list = [float(x) for x in data_str.split(",")]
        if len(data_list) != 4:
            return None
        return data_list  # temperature, humidity, voltage, current
    except:
        return None

def monitoring_loop():
    current_low_start = None
    action1_done = False
    action2_done = False
    action1_time = None

    while True:
        data_list = fetch_status_data()
        if data_list:
            temperature, humidity, voltage, current = data_list

            # Update GUI values
            voltage_var.set(f"{voltage:.2f} V")
            current_var.set(f"{current:.2f} mAh")
            temp_var.set(f"{temperature:.2f} °C")
            humid_var.set(f"{humidity:.2f} %")

            # -----------------------------
            # 🔍 FAULT DETECTION LOGIC
            # -----------------------------
            if temperature > 40:
                status_label.config(foreground="red")
                status_var.set("⚠ Thermal Fault Detected! Temperature > 40°C")
            elif voltage < 9:
                status_label.config(foreground="red")
                status_var.set("⚠ Cell Imbalance Fault! Voltage < 9V")
            else:
                status_label.config(foreground="blue")
                status_var.set(f"Current: {current:.2f} mAh - Normal Operation")
            # -----------------------------

            # Check low current condition for /1 trigger
            if current > -500:
                if current_low_start is None:
                    current_low_start = time.time()
                elif time.time() - current_low_start >= 30 and not action1_done:
                    try:
                        requests.get(ACTION1_URL, timeout=2)
                        action1_done = True
                        action1_time = time.time()
                        status_var.set("Triggered /1")
                    except:
                        action1_done = True
                        status_var.set("Failed to trigger /1")
            else:
                current_low_start = None

            # Trigger /2 after /1
            if action1_done and not action2_done:
                try:
                    requests.get(ACTION2_URL, timeout=2)
                    action2_done = True
                    status_var.set("Triggered /2")
                except:
                    action2_done = True
                    status_var.set("Failed to trigger /2")

            # Reset actions
            if action1_done and action2_done and current <= -500:
                action1_done = False
                action2_done = False
                current_low_start = None

        time.sleep(UPDATE_INTERVAL)

# -----------------------------
# GUI
# -----------------------------
def start_rul_and_monitor():
    start_btn.config(state="disabled")
    data_list, rul = get_initial_rul()
    if data_list:
        voltage, charge_current, discharge_current, temperature, humidity = data_list

        # Display initial RUL and other values
        voltage_var.set(f"{voltage:.2f} V")
        charge_var.set(f"{charge_current:.2f} mAh")
        discharge_var.set(f"{discharge_current:.2f} mAh")
        current_var.set(f"{charge_current - discharge_current:.2f} mAh")  # net current
        temp_var.set(f"{temperature:.2f} °C")
        humid_var.set(f"{humidity:.2f} %")
        rul_var.set(f"{rul:.2f}")
        
        # Upload to ThingSpeak once
        update_thingspeak(voltage, charge_current, discharge_current, temperature, humidity, rul)

        # Start monitoring thread
        Thread(target=monitoring_loop, daemon=True).start()
    else:
        rul_var.set("Error")

# -----------------------------
# Main Window
# -----------------------------
root = tk.Tk()
root.title("Li-ion Battery RUL Monitor")
root.geometry("520x460")
root.resizable(False, False)

# Variables
voltage_var = tk.StringVar(value="--")
charge_var = tk.StringVar(value="--")
discharge_var = tk.StringVar(value="--")
current_var = tk.StringVar(value="--")
temp_var = tk.StringVar(value="--")
humid_var = tk.StringVar(value="--")
rul_var = tk.StringVar(value="--")
status_var = tk.StringVar(value="Waiting for data...")

# Labels
ttk.Label(root, text="Voltage:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=voltage_var).grid(row=0, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Charge Current:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=charge_var).grid(row=1, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Discharge Current:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=discharge_var).grid(row=2, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Current:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=current_var).grid(row=3, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Temperature:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=temp_var).grid(row=4, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Humidity:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=humid_var).grid(row=5, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Predicted RUL:").grid(row=6, column=0, sticky="w", padx=10, pady=15)
ttk.Label(root, textvariable=rul_var, font=("Arial", 16, "bold")).grid(row=6, column=1, sticky="w", padx=10, pady=15)

ttk.Label(root, text="Status:").grid(row=7, column=0, sticky="w", padx=10, pady=5)
status_label = ttk.Label(root, textvariable=status_var, foreground="blue")
status_label.grid(row=7, column=1, sticky="w", padx=10, pady=5)

# Start button
start_btn = ttk.Button(root, text="Start Predict RUL", command=start_rul_and_monitor)
start_btn.grid(row=8, column=0, columnspan=2, pady=20)

root.mainloop()
