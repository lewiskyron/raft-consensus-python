# Contains the specific logic and behavior of a leader node, like sending heartbeats and handling log replication.
import logging
import time
import requests
import threading
from messages.heartbeat import HeartbeatMessage
from flask import Flask, request, jsonify


class LeaderState:
    def __init__(self, node):
        self.node = node
        self.heartbeat_interval = 1  # Sending heartbeats every 1 second
        self.send_heartbeats()

    def start(self):
        # Start sending heartbeats immediately
        pass

    def send_heartbeats(self):
        for peer in self.node.peers:
            # Construct the heartbeat message using HeartbeatMessage class
            last_log_index = len(self.node.message_log) - 1 if len(self.node.message_log) > 0 else -1
            last_log_term = (
                    self.node.message_log[last_log_index].term if last_log_index >= 0 else -1
                )

            heartbeat_message = HeartbeatMessage(
                    sender_id=self.node.node_id,
                    term=self.node.current_term,
                    prev_log_index=last_log_index,
                    prev_log_term=last_log_term,
                    leader_commit= self.node.commit_index,
                )
            message_dict = heartbeat_message.to_dict()

            # Send the heartbeat to the peer
            try:
                host,port = peer.split(":")
                response = requests.post(
                        f"http://{host}:5000/append_entries", json=message_dict
                    )
                if response.status_code == 200:
                    logging.info(f"[Node {self.node.node_id}] Sent heartbeat to {peer}.")
            except requests.ConnectionError:
                logging.warning(
                        f"[Node {self.node.node_id}] Failed to send heartbeat to {peer}."
                    )

        # Wait for the next interval before sending more heartbeats
        time.sleep(self.heartbeat_interval)


# after how long are the heartbeats sent
# how do we co-ordinate the selected time with what is received by the followers
