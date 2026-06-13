from flask import Blueprint, render_template

demo_bp = Blueprint("demo", __name__, url_prefix="/demo")


@demo_bp.route("/")
def demo():
    return render_template("demo/demo.html")
