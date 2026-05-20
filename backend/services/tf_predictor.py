import numpy as np
import tensorflow as tf


class TFPredictor:
    def __init__(self):
        self.model = self.build_model()

    def build_model(self):
        model = tf.keras.Sequential([
            tf.keras.layers.InputLayer(input_shape=(3,)),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(8, activation="relu"),
            tf.keras.layers.Dense(1, activation="sigmoid"),
        ])
        model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
        return model

    def predict_failure_risk(self, features: dict):
        vector = np.array([[features.get("recent_failures", 0), features.get("success_rate", 0.0) * 100, features.get("pipeline_length", 5)]], dtype=float)
        risk = float(self.model.predict(vector, verbose=0)[0][0]) if hasattr(self.model, "predict") else 0.25
        return {"failure_risk": round(risk * 100, 1)}

    def train(self, dataset):
        x = np.array([item["features"] for item in dataset])
        y = np.array([item["label"] for item in dataset])
        self.model.fit(x, y, epochs=5, batch_size=8)
        return True
