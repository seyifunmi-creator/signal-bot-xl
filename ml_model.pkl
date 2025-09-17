# create_test_model.py
import pickle
from sklearn.ensemble import RandomForestClassifier

# 4 dummy features: ['Open','High','Low','Close']
X = [
    [0, 0, 0, 0],
    [1, 1, 1, 1],
    [2, 2, 2, 2],
    [3, 3, 3, 3]
]
y = [0, 1, 1, 0]  # 0=SELL, 1=BUY

model = RandomForestClassifier()
model.fit(X, y)

# Save with protocol 4 for PyInstaller
with open("ml_model.pkl", "wb") as f:
    pickle.dump(model, f, protocol=4)

print("✅ Clean ml_model.pkl created with 4 features (protocol 4)")
