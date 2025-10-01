# backend/app.py
from flask import Flask, request, jsonify, send_from_directory, send_file
import os, json, requests, numpy as np
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph,
    Table, TableStyle, Spacer, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ---------------------------
# Paths
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "public"))
FUNDS_FILE = os.path.join(BASE_DIR, "funds_with_embeddings.json")
HEADER_IMAGE = os.path.join(BASE_DIR, "template.png")

# ---------------------------
# Flask app
# ---------------------------
app = Flask(
    __name__,
    static_url_path="",      # not used for /public (served by Caddy), still ok for dev
    static_folder=PUBLIC_DIR
)

# ---------------------------
# Config (env-overridable)
# ---------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "gemma3:12b")

HEADER_CM = 3.0
TOP_MARGIN_CM = 0
SIDE_CM = 0.8
BOTTOM_CM = 1.0

# ---------------------------
# Helpers: embeddings + LLM + funds
# ---------------------------
def load_funds():
    with open(FUNDS_FILE, encoding='utf-8') as f:
        return json.load(f)

def get_embedding(text):
    r = requests.post(f"{OLLAMA_URL}/api/embeddings", json={
        "model": OLLAMA_EMBED_MODEL,
        "prompt": text
    })
    r.raise_for_status()
    return r.json()['embedding']

def ollama_generate(prompt):
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_LLM_MODEL, "prompt": prompt, "stream": False}
    )
    r.raise_for_status()
    return r.json()['response']

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def recommend_funds(submission, top_k=25):
    funds = load_funds()
    if not funds:
        return []

    sub_text = (
        f"Title: {submission['project_title']}. "
        f"Location: {submission['project_location']}. "
        f"Type: {submission['project_type']}. "
        f"Description: {submission['project_desc']}. "
        f"Stage: {submission['project_stage']}. "
        f"Amount: {submission['amount_requested']}. "
        f"Needs: {', '.join(submission['support_needed'])}."
    )
    sub_emb = get_embedding(sub_text)
    sims = [cosine_similarity(sub_emb, f['embedding']) for f in funds]
    top_idxs = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
    return [funds[i] for i in top_idxs]

# ---------------------------
# Formatting helpers
# ---------------------------
def _format_support(s):
    if s is None:
        return ""
    if isinstance(s, str):
        return s
    if isinstance(s, list):
        out = []
        for x in s:
            if isinstance(x, dict):
                t = " — ".join([
                    str(x.get("type","")).strip(),
                    str(x.get("topic","")).strip()
                ]).strip(" —")
                out.append(t if t else json.dumps(x, ensure_ascii=False))
            else:
                out.append(str(x))
        return "; ".join([o for o in out if o])
    if isinstance(s, dict):
        t = " — ".join([
            str(s.get("type","")).strip(),
            str(s.get("topic","")).strip()
        ]).strip(" —")
        return t if t else json.dumps(s, ensure_ascii=False)
    return str(s)

# ---------------------------
# ReportLab page decorator (header)
# ---------------------------
def _draw_header(canv: canvas.Canvas, doc):
    w, h = canv._pagesize
    header_h = 4.0 * cm
    canv.saveState()
    try:
        if os.path.exists(HEADER_IMAGE):
            img = ImageReader(HEADER_IMAGE)
            canv.drawImage(img, 0, h - header_h, width=w, height=header_h,
                           preserveAspectRatio=False, mask='auto')
    except Exception as e:
        print(f"[WARN] Could not draw header image: {e}")
    canv.restoreState()

# ---------------------------
# PDF builder
# ---------------------------
def _build_content_pdf(data, funds, summary_text) -> BytesIO:
    page_w, page_h = 595.27, 841.89
    buf = BytesIO()

    doc = BaseDocTemplate(
        buf,
        pagesize=(page_w, page_h),
        leftMargin=SIDE_CM * cm,
        rightMargin=SIDE_CM * cm,
        topMargin=TOP_MARGIN_CM * cm,
        bottomMargin=BOTTOM_CM * cm,
        title="Film Funding Recommendations"
    )

    header_h = 4.0 * cm
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - header_h,
                  id="content-frame")
    doc.addPageTemplates(PageTemplate(id="content", frames=[frame], onPage=_draw_header))

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold",
                              fontSize=12.5, textColor=colors.HexColor("#4338ca"), spaceAfter=6))
    styles.add(ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=10.3, leading=14, textColor=colors.black))
    styles.add(ParagraphStyle("Chip", parent=styles["BodyText"], fontName="Helvetica-Bold",
                              fontSize=9.5, textColor=colors.HexColor("#3730a3")))
    styles.add(ParagraphStyle("Link", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=10.3, textColor=colors.blue, underline=True))

    story = []

    chips = [
        f"Title: {data['project_title']}",
        f"Location: {data['project_location']}",
        f"Type: {data['project_type']}",
        f"Stage: {data['project_stage']}",
        f"Budget: {data['currency']} {data['amount_requested']}",
    ]
    chip_cells = [[Paragraph(txt, styles["Chip"])] for txt in chips]
    chip_tbl = Table(chip_cells, colWidths=[doc.width], hAlign="LEFT")
    chip_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
        ("LINEBEFORE", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E7FF")),
        ("LINEAFTER",  (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E7FF")),
        ("BOX",        (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E7FF")),
        ("LEFTPADDING",(0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#EEF2FF"), colors.HexColor("#F5F7FF")]),
    ]))
    story += [chip_tbl, Spacer(1, 8)]

    if summary_text and str(summary_text).strip():
        story += [
            Paragraph("AI Recommendation", styles["H3"]),
            KeepTogether(Table(
                [[Paragraph(str(summary_text).replace("\n", "<br/>"), styles["Body"])]],
                colWidths=[doc.width],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDE9FE")),
                    ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#E4DDFF")),
                    ("LEFTPADDING",(0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",(0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
                ])
            )),
            Spacer(1, 10),
        ]

    COLS = [0.045, 0.18, 0.18, 0.23, 0.12, 0.10, 0.115, 0.03]
    col_widths = [doc.width * p for p in COLS]
    MINW = {6: 80, 7: 48}
    if col_widths[6] < MINW[6]:
        deficit = MINW[6] - col_widths[6]
        col_widths[6] = MINW[6]
        col_widths[3] = max(60, col_widths[3] - deficit)
    if col_widths[7] < MINW[7]:
        deficit = MINW[7] - col_widths[7]
        col_widths[7] = MINW[7]
        col_widths[3] = max(60, col_widths[3] - deficit)

    headers = ["#", "Fund Name", "Organization", "Type / Support", "Location", "Status", "Amount", "Link"]
    table_data = [[Paragraph(h, styles["Body"]) for h in headers]]

    for i, f in enumerate(funds, 1):
        link = (f.get("link") or "").strip()
        link_label = "Open" if link else ""
        link_para = Paragraph(f'<para alignment="center"><link href="{link}">{link_label}</link></para>', styles["Link"])

        row = [
            Paragraph(str(i), styles["Body"]),
            Paragraph((f.get("fund_name") or "").strip(), styles["Body"]),
            Paragraph((f.get("organization") or "").strip(), styles["Body"]),
            Paragraph(_format_support(f.get("support_type_and_topic")), styles["Body"]),
            Paragraph((f.get("location") or "").strip(), styles["Body"]),
            Paragraph((f.get("status") or "").strip(), styles["Body"]),
            Paragraph(((f.get("amount") or "").strip() or "N/A"), styles["Body"]),
            link_para
        ]
        table_data.append(row)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="LEFT", splitByRow=True)
    style_cmds = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBE7FC")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#E6E4FB")),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9.8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#F1EFFB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if len(table_data) > 1:
        style_cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FAFAFF"), colors.white]))
    tbl.setStyle(TableStyle(style_cmds))

    story += [Paragraph("Matched Funds", styles["H3"]), tbl]
    doc.build(story)
    buf.seek(0)
    return buf

# ---------------------------
# Routes
# ---------------------------

# Serve the SPA in dev (Caddy serves it in prod)
@app.get("/")
def spa_root():
    return send_from_directory(PUBLIC_DIR, "index.html")

@app.get("/<path:path>")
def spa_assets(path):
    # fallback to / if file not found (for direct link routing)
    full_path = os.path.join(PUBLIC_DIR, path)
    if os.path.isfile(full_path):
        return send_from_directory(PUBLIC_DIR, path)
    return send_from_directory(PUBLIC_DIR, "index.html")

@app.post("/api/export_pdf")
def export_pdf():
    data = request.json or {}
    required = [
        "project_title","project_location","project_type","project_desc",
        "project_stage","amount_requested","currency","support_needed"
    ]
    for field in required:
        if field not in data or not data[field]:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    provided_funds = data.get("recommended_funds")
    provided_summary = (data.get("llm_summary") or "").strip()

    if provided_funds and isinstance(provided_funds, list):
        funds = provided_funds
    else:
        funds = recommend_funds(data, top_k=25)

    if provided_summary:
        summary = provided_summary
    else:
        context = ""
        for i, f in enumerate(funds, 1):
            context += (f"{i}. {f.get('fund_name','')} ({f.get('organization','')}) - "
                        f"{f.get('description','')} [Location: {f.get('location','')}, "
                        f"Supports: {f.get('support_type_and_topic','')}]\nLink: {f.get('link','')}\n\n")
        user_proj = (
            f"Title: {data['project_title']}\n"
            f"Type: {data['project_type']}\n"
            f"Description: {data['project_desc']}\n"
            f"Stage: {data['project_stage']}\n"
            f"Location: {data['project_location']}\n"
            f"Needs: {', '.join(data['support_needed'])}\n"
            f"Amount: {data['currency']} {data['amount_requested']}\n"
        )
        prompt = (f"Given the filmmaker's project details:\n{user_proj}\n"
                  f"And the following matching film funds:\n{context}\n"
                  "Recommend which funds are most relevant for this project and briefly explain why."
                  "Dont make any style like bold underline (markdown). just plain text")
        summary = ollama_generate(prompt)

    pdf_buf = _build_content_pdf(data, funds, summary)
    return send_file(pdf_buf, mimetype="application/pdf",
                     as_attachment=True, download_name="funding_results.pdf")

@app.post("/api/submit")
def submit():
    data = request.json or {}
    required = [
        "project_title","project_location","project_type","project_desc",
        "project_stage","amount_requested","currency","support_needed"
    ]
    for field in required:
        if field not in data or not data[field]:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    recommended = recommend_funds(data, top_k=25)

    context = ""
    for i, fund in enumerate(recommended, 1):
        context += (f"{i}. {fund.get('fund_name','')} ({fund.get('organization','')}) - "
                    f"{fund.get('description','')} [Location: {fund.get('location','')}, "
                    f"Supports: {fund.get('support_type_and_topic','')}]\nLink: {fund.get('link','')}\n\n")

    user_proj = (
        f"Title: {data['project_title']}\n"
        f"Type: {data['project_type']}\n"
        f"Description: {data['project_desc']}\n"
        f"Stage: {data['project_stage']}\n"
        f"Location: {data['project_location']}\n"
        f"Needs: {', '.join(data['support_needed'])}\n"
        f"Amount: {data['currency']} {data['amount_requested']}\n"
    )

    prompt = (
        f"Given the filmmaker's project details:\n{user_proj}\n"
        f"And the following matching film funds:\n{context}\n"
        "Recommend which funds are most relevant for this project and briefly explain why."
        "Dont make any style like bold underline (markdown). just plain text"
    )

    summary = ollama_generate(prompt)
    return jsonify({"status": "ok", "recommended_funds": recommended, "llm_summary": summary})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
