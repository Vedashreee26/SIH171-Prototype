import logging

from flask import Flask, render_template

from routes.api import api_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# POST /analyze lives on this blueprint (no URL prefix).
app.register_blueprint(api_bp)


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
