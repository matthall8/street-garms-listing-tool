"""Flask app factory for the label capture UI."""

from flask import Flask


def create_app() -> Flask:
    from dotenv import load_dotenv

    load_dotenv()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # phone photos are big

    from app.routes import bp

    app.register_blueprint(bp)
    return app
