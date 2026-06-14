import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, redirect, url_for

from config import Config
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    register_blueprints(app)

    @app.route("/")
    def root():
        return redirect(url_for("demo.demo"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
