import tkinter as tk
from tkinter import ttk
import pandas as pd
import joblib
import socket
import time
import requests
import numpy as np
from threading import Thread
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

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
# Virtual Battery Model (Digital Twin)
# -----------------------------
class DigitalTwin:
    def __init__(self):
        self.voltage = 11.7
        self.soc = 1.0
        self.temperature = 25
        self.capacity = 3000  # mAh
        self.internal_resistance = 0.05  # ohms
        self.learn_rate = 0.01

    def update_from_real(self, real_voltage, real_current, real_temp):
        # Calibrate twin parameters slowly to match real data
        self.voltage += self.learn_rate * (real_voltage - self.voltage)
        self.temperature += self.learn_rate * (real_temp - self.temperature)
        return self.voltage, self.temperature

    def predict_next_state(self, current):
        # Simple model: dV = -IR, dSOC = current / capacity
        self.voltage -= current * self.internal_resistance * 0.001
        self.soc -= (current / self.capacity) * 0.001
        self.temperature += abs(current) * 0.0005
        return self.voltage, self.soc, self.temperature

    def project_future_rul(self, steps=10):
        # Predict SOC for next N steps
        soc_projection = [self.soc - i * 0.01 for i in range(steps)]
        return np.clip(soc_projection, 0, 1)

digital_twin = DigitalTwin()

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
def monitoring_loop():
    while True:
        data_list = fetch_status_data()
        if data_list:
            temperature, humidity, voltage, current = data_list

            # Update GUI
            voltage_var.set(f"{voltage:.2f} V")
            current_var.set(f"{current:.2f} mAh")
            temp_var.set(f"{temperature:.2f} °C")
            humid_var.set(f"{humidity:.2f} %")

            # ---- Digital Twin ----
            twin_voltage, twin_temp = digital_twin.update_from_real(voltage, current, temperature)
            predicted_v, predicted_soc, predicted_t = digital_twin.predict_next_state(current)

            # Detect deviation
            deviation = abs(voltage - predicted_v)
            if deviation > 0.05:
                status_var.set(f"⚠ Anomaly Detected! ΔV={deviation:.3f}V")
                status_label.config(foreground="red")
            else:
                status_var.set("Normal Operation")
                status_label.config(foreground="blue")

            # Update projection plot
            future_soc = digital_twin.project_future_rul()
            ax.clear()
            ax.plot(range(len(future_soc)), future_soc, marker='o')
            ax.set_ylim(0, 1)
            ax.set_title("Future SOC Projection")
            canvas.draw()

        time.sleep(UPDATE_INTERVAL)

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

# -----------------------------
# GUI
# -----------------------------
root = tk.Tk()
root.title("Li-ion Battery Digital Twin Monitor")
root.geometry("700x600")
root.resizable(False, False)

# Variables
voltage_var = tk.StringVar(value="--")
current_var = tk.StringVar(value="--")
temp_var = tk.StringVar(value="--")
humid_var = tk.StringVar(value="--")
rul_var = tk.StringVar(value="--")
status_var = tk.StringVar(value="Waiting for data...")

# Labels
ttk.Label(root, text="Voltage:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=voltage_var).grid(row=0, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Current:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=current_var).grid(row=1, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Temperature:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=temp_var).grid(row=2, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Humidity:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
ttk.Label(root, textvariable=humid_var).grid(row=3, column=1, sticky="w", padx=10, pady=5)

ttk.Label(root, text="Predicted RUL:").grid(row=4, column=0, sticky="w", padx=10, pady=15)
ttk.Label(root, textvariable=rul_var, font=("Arial", 16, "bold")).grid(row=4, column=1, sticky="w", padx=10, pady=15)

ttk.Label(root, text="Status:").grid(row=5, column=0, sticky="w", padx=10, pady=5)
status_label = ttk.Label(root, textvariable=status_var, foreground="blue")
status_label.grid(row=5, column=1, sticky="w", padx=10, pady=5)

# Matplotlib Figure for SOC projection
fig, ax = plt.subplots(figsize=(4, 2))
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().grid(row=6, column=0, columnspan=2, pady=10)

# Start button
def start_rul_and_monitor():
    start_btn.config(state="disabled")
    data_list, rul = get_initial_rul()
    if data_list:
        voltage, charge_current, discharge_current, temperature, humidity = data_list
        voltage_var.set(f"{voltage:.2f} V")
        temp_var.set(f"{temperature:.2f} °C")
        humid_var.set(f"{humidity:.2f} %")
        rul_var.set(f"{rul:.2f}")
        update_thingspeak(voltage, charge_current, discharge_current, temperature, humidity, rul)
        Thread(target=monitoring_loop, daemon=True).start()

start_btn = ttk.Button(root, text="Start Digital Twin", command=start_rul_and_monitor)
start_btn.grid(row=7, column=0, columnspan=2, pady=20)

root.mainloop()
