import re
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, session, url_for

from models.models import (
    add_chat_message,
    create_chat,
    delete_chat,
    get_user_chat,
    list_chat_messages,
    list_user_chats,
    rename_chat,
)
from services.ai_service import AIService
from services.search_service import SearchService
from routes.main import validate_csrf


teddy_bp = Blueprint("teddy", __name__)
ai_service = AIService()
search_service = SearchService()


def teddy_api_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({
                "error": "Please log in to chat with AI Teddy.",
                "auth_required": True,
                "login_url": url_for("main.login", next=url_for("teddy.chat_page")),
            }), 401
        if not validate_csrf(request.headers.get("X-CSRF-Token")):
            return jsonify({"error": "Your session expired. Refresh the page and try again."}), 400
        return f(*args, **kwargs)
    return wrapped


def make_title(message: str) -> str:
    text = re.sub(r"\s+", " ", (message or "").strip())
    text = re.sub(r"^(please|can you|could you|help me|tell me|explain)\s+", "", text, flags=re.I)
    text = text.rstrip("?.! ")
    if not text:
        return "New Chat"
    words = text.split()
    if len(words) <= 7:
        title = text
    else:
        title = " ".join(words[:7]) + "…"
    return title[:70].strip().capitalize()


@teddy_bp.route("/ai-teddy")
def chat_page():
    if not session.get("user_id"):
        return render_template("teddy.html", chats=[], active_chat=None, messages=[])
    user_id = session["user_id"]
    chats = list_user_chats(user_id)
    active_chat = chats[0] if chats else None
    messages = list_chat_messages(user_id, active_chat["id"]) if active_chat else []
    return render_template("teddy.html", chats=chats, active_chat=active_chat, messages=messages)


@teddy_bp.route("/api/teddy/chats", methods=["GET", "POST"])
@teddy_api_required
def chats_api():
    user_id = session["user_id"]
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "New Chat")).strip()[:100] or "New Chat"
        chat = create_chat(user_id, title)
        return jsonify({"chat": chat, "messages": []}), 201
    return jsonify({"chats": list_user_chats(user_id)})


@teddy_bp.route("/api/teddy/chats/<int:chat_id>", methods=["GET", "PATCH", "DELETE"])
@teddy_api_required
def chat_detail_api(chat_id):
    user_id = session["user_id"]
    chat = get_user_chat(user_id, chat_id)
    if not chat:
        return jsonify({"error": "That conversation could not be found."}), 404

    if request.method == "GET":
        return jsonify({"chat": chat, "messages": list_chat_messages(user_id, chat_id)})

    if request.method == "DELETE":
        delete_chat(user_id, chat_id)
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "A chat title is required."}), 400
    rename_chat(user_id, chat_id, title)
    return jsonify({"chat": get_user_chat(user_id, chat_id)})


@teddy_bp.route("/api/teddy/chats/<int:chat_id>/messages", methods=["POST"])
@teddy_api_required
def send_message(chat_id):
    user_id = session["user_id"]
    chat = get_user_chat(user_id, chat_id)
    if not chat:
        return jsonify({"error": "That conversation could not be found.", "error_type": "not_found"}), 404

    data = request.get_json(silent=True) or {}
    content = str(data.get("message", "")).strip()
    use_web = bool(data.get("use_web"))
    if not content:
        return jsonify({"error": "Please type a message for Teddy.", "error_type": "invalid_request"}), 400
    if len(content) > 12000:
        return jsonify({"error": "That message is too long. Please shorten it and try again.", "error_type": "message_too_long"}), 400

    # The server loads the history from the authenticated user's chat. The browser
    # cannot supply arbitrary history, so one user's messages cannot be injected into another chat.
    previous = list_chat_messages(user_id, chat_id)

    web_context = ""
    sources = []
    if use_web:
        try:
            web = search_service.search(content)
            extract = web.get("extract", "") or ""
            pieces = []
            if extract:
                pieces.append("Search summary:\n" + extract[:9000])
            for item in (web.get("web") or [])[:6]:
                title = item.get("title", "Source")
                snippet = item.get("snippet", "")
                url = item.get("url", "")
                pieces.append(f"Source: {title}\n{snippet}\nURL: {url}")
                sources.append({"title": title, "snippet": snippet, "url": url})
            web_context = "\n\n".join(pieces)
        except Exception:
            # Web search is optional; Teddy can still answer from the configured LLM.
            web_context = ""
            sources = []

    # Call the provider before writing anything to the database. A failed provider
    # request therefore cannot create a phantom user message in chat history.
    result = ai_service.teddy_chat(previous, content, web_context=web_context)
    if "error" in result:
        status = 503
        if result.get("error_type") in {"not_configured", "invalid_api_key", "permission_error"}:
            status = 503
        return jsonify(result), status

    user_message = add_chat_message(user_id, chat_id, "user", content)
    if not user_message:
        return jsonify({
            "error": "Teddy generated a response, but your message could not be saved. Please try again.",
            "error_type": "database_error",
        }), 500

    teddy_message = add_chat_message(user_id, chat_id, "teddy", result["result"])
    if not teddy_message:
        return jsonify({
            "error": "Teddy answered, but the response could not be saved. Please refresh the chat.",
            "error_type": "database_error",
        }), 500

    if chat["title"] == "New Chat" and not previous:
        rename_chat(user_id, chat_id, make_title(content))

    return jsonify({
        "user_message": user_message,
        "teddy_message": teddy_message,
        "chat": get_user_chat(user_id, chat_id),
        "sources": sources,
        "provider": result.get("provider"),
    })
