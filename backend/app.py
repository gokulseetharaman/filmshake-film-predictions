import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:3b")

@app.get("/api/health")
def health():
    return {"ok": True, "ollama": OLLAMA_URL}

@app.post("/api/submit")
def submit():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"recommended_funds": [], "llm_summary": "demo", "echo": data})

@app.post("/api/export_pdf")
def export_pdf():
    from reportlab.pdfgen import canvas
    path="/tmp/funding_results.pdf"
    c = canvas.Canvas(path)
    c.drawString(72, 750, "Film Funding Results (demo)")
    c.save()
    return send_file(path, as_attachment=True, download_name="funding_results.pdf", mimetype="application/pdf")
