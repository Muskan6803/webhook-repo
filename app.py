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

# -------------------- INITIAL SETUP --------------------

load_dotenv()

app = Flask(__name__)

client = MongoClient(os.getenv("MONGO_URI"))
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
    Fetch events newer than the provided timestamp.
    Prevents duplicate UI rendering.
    """
    since = request.args.get("since")

    query = {}
    if since:
        query["timestamp"] = {
            "$gt": datetime.fromisoformat(since)
        }

    events = list(
        collection.find(query, {"_id": 0})
        .sort("timestamp", -1)
    )

    return jsonify(events)


# -------------------- UI ROUTE --------------------

@app.route("/")
def serve_ui():
    """
    Serves the polling-based UI.
    """
    return send_from_directory("static", "index.html")


# -------------------- APP START --------------------

if __name__ == "__main__":
    app.run(debug=True)
