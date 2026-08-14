from flask import Flask, Response
from prometheus_client import generate_latest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import metrics
import config

app = Flask(__name__)
_registry = metrics.recommendation_registry

@app.route("/metrics")
def metrics_endpoint():
    return Response(generate_latest(_registry), mimetype="text/plain")

def run():
    app.run(host="0.0.0.0", port=config.RECOMMENDATION_PORT)
