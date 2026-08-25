from flask import Blueprint, render_template, request, jsonify

from services.search_service import SearchService
from services.ai_service import AIService
from models.models import log_search
from routes.main import login_required_api

search_bp = Blueprint("search", __name__)
search_service = SearchService()
ai_service = AIService()


@search_bp.route("/search")
def search_page():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("search.html", query="", results=None, notes=None, error=None, auto_action="")

    # Calculations are answered directly and never touch the web.
    # If a real AI model is configured, Student Hub is AI-first: the model
    # answers the student's question directly instead of turning every query
    # into a Wikipedia/web lookup. Web resources remain available when the
    # model is not configured or when the user explicitly browses resources.
    notes = ai_service.try_direct_answer(query)
    if notes:
        results = {"query": query, "web": [], "pdfs": [], "videos": [],
                   "provider": "calculator", "error": None, "extract": ""}
        log_search(query, "calculator")
        return render_template("search.html", query=query, results=results,
                                notes=notes, error=None, auto_action=request.args.get("ai_action", ""))

    if ai_service.model_enabled and request.args.get("web") != "1":
        notes = ai_service.generate_study_notes(query, {})
        results = {"query": query, "web": [], "pdfs": [], "videos": [],
                   "provider": "ai", "error": None, "extract": ""}
        log_search(query, "ai")
    else:
        results = search_service.search(query)
        log_search(query, results.get("provider", "mock"))
        notes = ai_service.generate_study_notes(query, results) if not results.get("error") else None

    return render_template(
        "search.html",
        query=query,
        results=results,
        notes=notes,
        error=results.get("error"),
        auto_action=request.args.get("ai_action", ""),
    )


@search_bp.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    results = search_service.search(query)
    return jsonify(results)


@search_bp.route("/api/ai-helper", methods=["POST"])
@login_required_api
def api_ai_helper():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "explain")).strip()
    topic = str(data.get("topic", "")).strip()
    context = str(data.get("context", "")).strip()
    allowed_actions = {"explain", "simplify", "mcqs", "questions", "flashcards", "exam_notes", "summarize", "test_me"}
    if action not in allowed_actions:
        return jsonify({"error": "That AI action is not available."}), 400
    if not topic:
        return jsonify({"error": "Please enter or search for a question/topic first."}), 400
    result = ai_service.helper_action(action, topic, context)
    if "error" in result:
        return jsonify(result), 503
    return jsonify(result)
