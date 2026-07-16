import os
import torch
import torch.nn as nn
import joblib
import numpy as np
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Define the Model architecture (must match the trained model)
class ANN(nn.Module):
    def __init__(self):
        super(ANN, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(4, 6),
            nn.ReLU(),
            nn.Linear(6, 6),
            nn.ReLU(),
            nn.Linear(6, 1),
        )

    def forward(self, x):
        return self.model(x)

# Load model and scaler
model = ANN()
model.load_state_dict(torch.load("best_model.pt", map_location=torch.device('cpu')))
model.eval()

scaler = joblib.load("scaler.pkl")

@app.route("/", methods=["GET", "POST"])
def index():
    prediction = None
    error = None
    input_data = {}
    
    if request.method == "POST":
        try:
            # Extract inputs
            at = float(request.form.get("at"))
            v = float(request.form.get("v"))
            ap = float(request.form.get("ap"))
            rh = float(request.form.get("rh"))
            
            input_data = {"at": at, "v": v, "ap": ap, "rh": rh}
            
            # Preprocess and Scale
            features = np.array([[at, v, ap, rh]])
            features_scaled = scaler.transform(features)
            
            # Convert to PyTorch Tensor
            features_tensor = torch.tensor(features_scaled, dtype=torch.float32)
            
            # Predict
            with torch.no_grad():
                pred_tensor = model(features_tensor)
                prediction = round(float(pred_tensor.item()), 2)
        except Exception as e:
            error = str(e)
            
    return render_template("index.html", prediction=prediction, error=error, input_data=input_data)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
