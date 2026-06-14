from routes.demo import demo_bp


def register_blueprints(app):
    app.register_blueprint(demo_bp)
