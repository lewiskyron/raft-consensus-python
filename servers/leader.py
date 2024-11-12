# Contains the specific logic and behavior of a leader node, like sending heartbeats and handling log replication.
import logging
import time
import requests
import threading
from messages.heartbeat import HeartbeatMessage
from messages.vote_response import VoteResponseMessage
from messages.vote_request import VoteRequestMessage
from flask import Flask, request, jsonify
import sqlite3


class LeaderState:
    def __init__(self, node):
        self.node = node
        self.heartbeat_interval = 1  # Send heartbeats every 1 second
        self.heartbeat_timer = None
        self.next_index = {peer: len(self.node.message_log) for peer in self.node.peers}
        self.match_index = {peer: 0 for peer in self.node.peers}
        self.replication_threshold = 1

    def start_leader(self):
        self.send_heartbeats()
        self.initialize_database()

    def send_heartbeats(self):
        for peer in self.node.peers:
            # Construct the heartbeat message
            next_idx = self.next_index[peer]
            prev_log_index = next_idx - 1
            prev_log_term = (
                self.node.message_log[prev_log_index]["term"]
                if prev_log_index >= 0
                else -1
            )
            entries = self.node.message_log[next_idx:]  # Entries to send

            heartbeat_message = HeartbeatMessage(
                sender_id=self.node.node_id,
                term=self.node.current_term,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                leader_commit=self.node.commit_index,
                entries=entries,
            )
            message_dict = heartbeat_message.to_dict()

            # Send the heartbeat to the peer
            try:
                host, port = peer.split(":")
                response = requests.post(
                    f"http://{host}:5000/append_entries", json=message_dict
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.match_index[peer] = prev_log_index + len(entries)
                        self.next_index[peer] = self.match_index[peer] + 1
                        logging.info(
                            f"[Node {self.node.node_id}] Sent heartbeat to {peer}."
                        )
                    else:
                        self.next_index[peer] -= 1  # Decrement next_index and retry
                        logging.warning(
                            f"[Node {self.node.node_id}] Failed to append entries to {peer}. Reason: {data.get('reason')}"
                        )
                else:
                    logging.warning(
                        f"[Node {self.node.node_id}] Failed to send heartbeat to {peer}. HTTP Status: {response.status_code}"
                    )
            except requests.ConnectionError:
                logging.warning(
                    f"[Node {self.node.node_id}] Failed to send heartbeat to {peer}."
                )

        # Schedule the next heartbeat
        self.heartbeat_timer = threading.Timer(
            self.heartbeat_interval, self.send_heartbeats
        )
        self.heartbeat_timer.start()

    def initialize_database(self):
        """Create the logs table in the SQLite database if it doesn't exist."""
        db_path = "/app/disk/leader_logs.db"  # Database file path
        self.db_path = db_path  # Save the path for later use in save_to_disk
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT,
                    term INTEGER,
                    message TEXT,
                    commit_index INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    leader_id TEXT
            )
            """
            )
            conn.commit()
            conn.close()
            logging.info("Database initialized and table created if it didn't exist.")
        except sqlite3.Error as e:
            logging.error(f"Failed to initialize database: {e}")

    def send_append_entries_to_followers(self, message):
        # Append the message to the log with the current term
        self.node.message_log.append(
            {
                "node_id": self.node.node_id,
                "term": self.node.current_term,
                "message": message,
            }
        )

        current_entry_index = len(self.node.message_log) - 1
        logging.warning(f"[Node {self.node.node_id}] has current_entry index {current_entry_index}")
        success_count = 0

        # Replicate the log entry to followers
        for peer in self.node.peers:
            host, port = peer.split(":")
            url = f"http://{host}:5000/append_entries"
            prev_log_index = current_entry_index - 1
            prev_log_term = (
                self.node.message_log[prev_log_index]["term"] if prev_log_index >= 0 else -1
            )
            entries = [self.node.message_log[current_entry_index]]

            # Use HeartbeatMessage for consistency
            append_entries_msg = HeartbeatMessage(
                sender_id=self.node.node_id,
                term=self.node.current_term,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                leader_commit=self.node.commit_index,
                entries=entries
            )
            try:
                response = requests.post(url, json=append_entries_msg.to_dict())
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.match_index[peer] = current_entry_index
                        success_count += 1
                        logging.info(
                            f"[Node {self.node.node_id}] Successfully replicated entry to {peer}."
                        )
                    else:
                        logging.warning(
                            f"[Node {self.node.node_id}] Failed to replicate entry to {peer}. Reason: {data.get('reason')}"
                        )
                else:
                    logging.warning(
                        f"[Node {self.node.node_id}] Failed to replicate entry to {peer}. HTTP Status: {response.status_code}"
                    )
            except requests.exceptions.RequestException:
                logging.warning(
                    f"[Node {self.node.node_id}] Exception when replicating to {peer}."
                )

        # Check if the majority has acknowledged this entry
        if success_count >= 1:
            # Update commit index
            self.node.commit_index = current_entry_index
            logging.info(f"Leader [Node {self.node.node_id}] Commit index updated to {self.node.commit_index}.")
            # Save to disk
            self.save_to_disk(self.node.message_log[current_entry_index])

    def save_to_disk(self, entry):
        """Save a log entry to the SQLite database."""
        entry_data = {
            "node_id": entry["node_id"],
            "term": entry["term"],
            "message": entry["message"],
            "commit_index": self.node.commit_index,
            "leader_id": self.node.node_id,
        }
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO logs (node_id, term, message, commit_index, leader_id)
                VALUES (:node_id, :term, :message, :commit_index, :leader_id)
                """,
                entry_data,
            )
            conn.commit()
            conn.close()
            logging.info(f"Entry successfully added to SQLite: {entry}")
        except sqlite3.Error as e:
            logging.error(f"Failed to write to SQLite database. Error: {e}")

    def stop(self):
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None

    def vote_request(self):
        data = request.get_json()
        vote_request = VoteRequestMessage.from_dict(data)
        if vote_request.term > self.node.current_term:
            self.node.current_term = vote_request.term
            self.node.become_follower()
            return self.node.current_state.vote_request()
        else:
            response = VoteResponseMessage(
                sender_id=self.node.node_id,
                term=self.node.current_term,
                vote_granted=False,
            )
            return jsonify(response.to_dict()), 200
