from routes.auth import auth_bp
from routes.cases import cases_bp
from routes.dashboard import dashboard_bp
from routes.demo import demo_bp
from routes.research import research_bp
from routes.settings import settings_bp
from routes.api_proxy import api_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
