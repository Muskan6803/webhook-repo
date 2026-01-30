"""
Flask application to receive GitHub webhook events,
store minimal required data in MongoDB,
and expose APIs for polling-based UI.
"""

from flask import Flask, request, jsonify, send_from_directory
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

# -------------------- INITIAL SETUP --------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

# -------------------- MONGODB CONNECTION (SAFE) --------------------

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("MONGO_URI environment variable not set")

client = MongoClient(MONGO_URI)
db = client.github_events
collection = db.events

# -------------------- UTILITY FUNCTIONS --------------------

def parse_github_timestamp(timestamp_str):
    """
    Convert GitHub ISO timestamp string to Python datetime (UTC).
    """
    return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

# -------------------- WEBHOOK ENDPOINT --------------------

@app.route("/webhook", methods=["POST"])
def github_webhook():
    """
    Receives GitHub webhook events (Push, Pull Request, Merge)
    and stores only required fields in MongoDB.
    """
    event_type = request.headers.get("X-GitHub-Event")
    payload = request.json

    if not payload:
        return jsonify({"error": "Invalid payload"}), 400

    data = None

    # -------------------- PUSH EVENT --------------------
    if event_type == "push":
        data = {
            "request_id": payload["head_commit"]["id"],
            "author": payload["pusher"]["name"],
            "action": "PUSH",
            "from_branch": None,
            "to_branch": payload["ref"].split("/")[-1],
            "timestamp": parse_github_timestamp(
                payload["head_commit"]["timestamp"]
            )
        }

    # -------------------- PULL REQUEST & MERGE --------------------
    elif event_type == "pull_request":
        pr = payload["pull_request"]
        action = payload["action"]

        # Pull Request opened / updated
        if action in ["opened", "synchronize"]:
            data = {
                "request_id": str(pr["id"]),
                "author": pr["user"]["login"],
                "action": "PULL_REQUEST",
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"],
                "timestamp": parse_github_timestamp(pr["created_at"])
            }

        # Merge (Brownie Points ⭐)
        elif action == "closed" and pr["merged"]:
            data = {
                "request_id": str(pr["id"]),
                "author": pr["user"]["login"],
                "action": "MERGE",
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"],
                "timestamp": parse_github_timestamp(pr["merged_at"])
            }

    if data:
        collection.insert_one(data)

    return jsonify({"status": "success"}), 200

# -------------------- EVENTS API (FOR UI POLLING) --------------------

@app.route("/events", methods=["GET"])
def get_events():
    """
    Fetch latest events for UI polling.
    """
    events = list(
        collection.find({}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(20)
    )

    return jsonify(events)

# -------------------- UI ROUTE --------------------

@app.route("/")
def serve_ui():
    """
    Serves the polling-based UI.
    """
    return send_from_directory("static", "index.html")

# -------------------- TEST DB CONNECTION --------------------

@app.route("/test-db")
def test_db():
    collection.insert_one({"test": "MongoDB connected"})
    return "MongoDB working!"

# -------------------- APP START --------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
