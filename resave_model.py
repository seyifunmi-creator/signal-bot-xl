import pickle

with open("ml_model.pkl", "rb") as f:
    model = pickle.load(f)

with open("ml_model.pkl", "wb") as f:
    pickle.dump(model, f, protocol=4)
