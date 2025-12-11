import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from catboost import CatBoostRegressor
import joblib
import matplotlib.pyplot as plt

# Load dataset
df = pd.read_csv("data.csv")

# Features and target
X = df.drop(columns=["RUL"])
y = df["RUL"]

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Define CatBoost Regressor
model = CatBoostRegressor(
    verbose=0,
    iterations=1000,
    depth=6,
    learning_rate=0.05,
    random_seed=42
)

# Train model
model.fit(X_train, y_train)

# Predictions
y_pred = model.predict(X_test)

# --- Evaluation Metrics ---
mae = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2 = r2_score(y_test, y_pred)

print("\n--- Regression Performance ---")
print(f"MAE   : {mae:.4f}")
print(f"RMSE  : {rmse:.4f}")
print(f"R²    : {r2:.4f}")

# --- Visualization ---
plt.figure(figsize=(7,5))
plt.scatter(y_test, y_pred, alpha=0.7)
plt.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], "r--")
plt.xlabel("Actual RUL")
plt.ylabel("Predicted RUL")
plt.title("Actual vs Predicted RUL")
plt.savefig("actual_vs_predicted.png")
plt.show()

# --- Save Model ---
joblib.dump(model, "catboost_rul_model.pkl")
print("\nModel saved as 'catboost_rul_model.pkl'")
