import os
from flask import Flask, render_template

from config.config import Config
from models.models import init_db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db()

    from routes.main import main_bp
    from routes.search import search_bp
    from routes.coding import coding_bp
    from routes.teddy import teddy_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(coding_bp)
    app.register_blueprint(teddy_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    app.run(debug=debug, host="0.0.0.0", port=5000)
