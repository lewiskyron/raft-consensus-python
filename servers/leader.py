# Contains the specific logic and behavior of a leader node, like sending heartbeats and handling log replication.
import logging
import time
import requests
import threading
from messages.heartbeat import HeartbeatMessage
from messages.vote_response import VoteResponseMessage
from messages.vote_request import VoteRequestMessage
from flask import Flask, request, jsonify


class LeaderState:
    def __init__(self, node):
        self.node = node
        self.heartbeat_interval = 1  # Send heartbeats every 1 second
        self.heartbeat_timer = None
        self.next_index = {peer: len(self.node.message_log) for peer in self.node.peers}
        self.match_index = {peer: 0 for peer in self.node.peers}
        self.send_heartbeats()

    def start(self):
        # Start sending heartbeats immediately
        pass

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

    def send_append_entries_to_followers(self, message):
        # Append the message to the log with the current term
        self.node.message_log.append({"term": self.node.current_term, "message": message})
        # Replicate the log entry to followers
        for peer in self.node.peers:
            host, port = peer.split(":")
            url = f"http://{host}:5000/append_entries"
            # Construct the append_entries message
            append_entries_msg = {
                "term": self.node.current_term,
                "sender_id": self.node.node_id,
                "prev_log_index": len(self.node.message_log) - 2,  # Index before new entry
                "prev_log_term": (
                    self.node.message_log[-2]["term"] if len(self.message_log) > 1 else -1
                ),
                "entries": [self.node.message_log[-1]],  # The new entry
                "leader_commit": self.node.commit_index,
            }
            try:
                response = requests.post(url, json=append_entries_msg)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
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


# after how long are the heartbeats sent
# how do we co-ordinate the selected time with what is received by the followers
