import joblib
import os
import numpy as np
from flask import Flask, jsonify, request


model_path = os.getenv('MODEL_PATH')
model = joblib.load(model_path)

app = Flask(__name__)


@app.route('/healthcheck')
def healthcheck():
    return 'OK\n'


@app.route('/reload-model', methods=['POST'])
def reload_model():

    global model
    global model_path

    model = joblib.load(model_path)

    return 'Model reloaded'


@app.route('/predict', methods=['POST'])
def predict():

    data = request.get_json(force=True)
    predict_request = data['data']
    predict_request = np.array(predict_request)
    predict_request = model.predict(predict_request)
    output = {'predictions': predict_request.tolist()}

    return jsonify(output)


if __name__ == '__main__':

    app.run(host='0.0.0.0', port=9000, debug=True)
