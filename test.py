import socket
import pandas as pd
import joblib

HOST = "192.168.137.83"
PORT = 80

# Proper HTTP GET request
request = "GET /5 HTTP/1.1\r\nHost: 192.168.137.64\r\n\r\n"

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(request.encode())  # send full HTTP request
    data = s.recv(1024)

# Decode and clean response
data_str = data.decode().strip()

# NodeMCU may send HTTP headers, remove them
if "\r\n\r\n" in data_str:
    data_str = data_str.split("\r\n\r\n")[1]  # take only the body

print("Cleaned NodeMCU data:", data_str)

# Parse and predict
data_list = [float(x) for x in data_str.split(",")]
if len(data_list) != 5:
    raise ValueError("Expected 5 values, got:", data_list)

columns = ['Voltage', 'Charge_Current', 'Discharge_Current', 'Temperature', 'Humidity']
df_new = pd.DataFrame([data_list], columns=columns)

# Load model and predict
model = joblib.load("catboost_rul_model.pkl")
predicted_rul = model.predict(df_new)[0]

print(f"Predicted RUL: {predicted_rul:.2f}")
