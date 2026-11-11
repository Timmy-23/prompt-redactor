"""Local web interface for the prompt redactor.

Runs only on 127.0.0.1 (this computer). Text is processed in this process and
never sent to an external service. Nothing is written to disk or logged.

    python app.py            -> http://127.0.0.1:5000
"""
import logging

from flask import Flask, jsonify, render_template, request

from detector import ENTITIES, LABELS, METHODS, MODES, Detection, apply, detect, get_analyzer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB of text is plenty

# Don't write request details (which could include prompt text) to the console.
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.get("/")
def index():
    return render_template("index.html", labels=LABELS, entities=ENTITIES, modes=MODES)


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(force=True)
    text = data.get("text", "")
    mode = data.get("mode", "hybrid")
    threshold = float(data.get("threshold", 0.4))
    if mode not in MODES:
        return jsonify(error=f"mode must be one of {MODES}"), 400
    dets = detect(text, mode=mode, threshold=threshold)
    return jsonify(detections=[d.to_dict() for d in dets])


@app.post("/api/transform")
def api_transform():
    """Apply the chosen method: "pseudonymize" ([PERSON_1] placeholders), "redact" ([REDACTED]) or the optional "surrogate" (realistic fake values)."""
    data = request.get_json(force=True)
    text = data.get("text", "")
    method = data.get("method", "pseudonymize")
    if method not in METHODS:
        return jsonify(error=f"method must be one of {METHODS}"), 400
    dets = []
    for d in data.get("detections", []):
        start, end = int(d["start"]), int(d["end"])
        if not (0 <= start < end <= len(text)):
            return jsonify(error="detection outside text"), 400
        dets.append(Detection(d["entity"], start, end, text[start:end], float(d.get("score", 1.0)), d.get("source", "user")))
    return jsonify(apply(text, dets, method=method))


if __name__ == "__main__":
    print("Loading detection models (first run takes ~10 s)...")
    for m in MODES:
        get_analyzer(m)
    print("Ready: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
