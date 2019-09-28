from flask import Flask, escape, request
import scrape

app = Flask(__name__)


@app.route("/")
def hello():
    name = request.args.get("name", "World")
    return f"Hello, {escape(name)}!"


@app.route("/morning")
def morning():
    return scrape.get_morning_commute()


@app.route("/evening")
def evening():
    return scrape.get_evening_commute()
