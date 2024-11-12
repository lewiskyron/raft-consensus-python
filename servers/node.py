# Base node class that defines general behavior for all nodes, as well as state transitions.
from flask import Flask, request, jsonify
import requests
import threading
import time
import logging
import random
from servers.follower import FollowerState
from servers.candidate import CandidateState
from servers.leader import LeaderState
from threading import Timer
import docker


logging.basicConfig(
    level=logging.INFO,  # Set default level to INFO (can change as needed)
    format="[%(asctime)s] %(levelname)s - %(message)s",
)

class Node:
    def __init__(self, node_id, peers):
        self.node_id = node_id  # Unique ID for this node
        self.peers = (
            peers  # List of peer nodes in the format ["node2:5001", "node3:5002"]
        )
        self.app = Flask(__name__)
        self.is_leader = False  # Role flag (Leader or Follower)
        self.message_log = []
        self.election_timer = None
        self.state = "Follower"
        self.is_leader = False
        self.election_timeout = random.uniform(3, 5)
        self.current_term = 0
        self.commit_index = 0
        self.current_state = None
        self.docker_client = docker.from_env()
        self.container_name = f"raft-consensus-python-node{node_id}-1"

        # Define API endpoints
        self.app.add_url_rule(
            "/receive_message", "receive_message", self.receive_message, methods=["POST"]
        )
        self.app.add_url_rule(
            "/send_message", "send_message", self.send_message, methods=["POST"]
        )

        # this is here for testing and not used in the prod environment.
        self.app.add_url_rule(
            "/message_log", "get_message_log", self.get_message_log, methods=["GET"]
        )
        self.app.add_url_rule("/state", "get_state", self.get_state, methods=["GET"])

        self.app.add_url_rule(
            "/append_entries", "append_entries", self.append_entries, methods=["POST"]
        )

        self.app.add_url_rule(
            "/vote_request", "vote_request", self.vote_request, methods=["POST"]
        )

        self.app.add_url_rule("/shutdown", "shutdown", self.shutdown, methods=["POST"])

        # handles client requests
        self.app.add_url_rule(
            "/client_request", "client_request", self.client_request, methods=["POST"]
        )

    def initialize(self):
        self.become_follower()  # This method should set the current_state

    def start_node(self, port):
        threading.Thread(target=self.run_flask_server, args=(port,)).start()
        time.sleep(1)
        self.initialize()

    def shutdown(self):
        """Endpoint to shut down the node for a specified duration."""
        try:
            duration = 30  # Default to 30 seconds

            logging.info(
                f"[Node {self.node_id}] Shutdown requested for {duration} seconds."
            )

            def delayed_restart():
                try:
                    container = self.docker_client.containers.get(self.container_name)
                    container.stop()
                    logging.info(f"[Node {self.node_id}] Container stopped.")
                    
                    # Wait for the specified duration before restarting
                    time.sleep(duration)
                    
                    container.start()
                    logging.info(f"[Node {self.node_id}] Container restarted after {duration} seconds.")
                    
                except docker.errors.NotFound:
                    logging.error(
                        f"[Node {self.node_id}] Container not found: {self.container_name}"
                    )
                except Exception as e:
                    logging.error(f"[Node {self.node_id}] Error during shutdown/restart: {str(e)}")

            threading.Thread(target=delayed_restart).start()

            return (
                jsonify({"status": f"Node shutdown initiated for {duration} seconds"}),
                200,
            )
        except Exception as e:
            logging.error(f"[Node {self.node_id}] Error during shutdown: {str(e)}")
            return jsonify({"error": str(e)}), 500

    def run_flask_server(self, port):
        try:
            logging.info(f"[Node {self.node_id}] Starting Flask server on port {port}")
            self.app.run(host="0.0.0.0", port=port, threaded=True)
        except Exception as e:
            logging.error(f"Server error: {e}")

    def become_follower(self):
        if self.current_state and hasattr(self.current_state, "stop"):
            self.current_state.stop()
        self.state = "Follower"
        self.current_state = FollowerState(self)
        logging.info(f"[Node {self.node_id}] Transitioned to Follower state.")
        self.current_state.initialize()

    def become_candidate(self):
        if self.current_state and hasattr(self.current_state, "stop"):
            self.current_state.stop()
        self.state = "Candidate"
        self.current_state = CandidateState(self)
        logging.info(f"[Node {self.node_id}] Transitioned to Candidate state.")
        self.current_state.start()

    def become_leader(self):
        if self.current_state and hasattr(self.current_state, "stop"):
            self.current_state.stop()
        self.state = "Leader"
        self.current_state = LeaderState(self)
        logging.info(f"[Node {self.node_id}] Transitioned to Leader state.")
        self.current_state.start_leader()

    def receive_message(self):
        """
        Endpoint to receive messages from other nodes.
        """
        data = request.get_json()
        sender = data.get("sender")
        message = data.get("message")

        # Log the received message
        self.message_log.append((sender, message))

        logging.info(
            f"[Node {self.node_id}] Received message from Node {sender}: {message}"
        )
        return jsonify({"status": "Message received"}), 200

    def send_message(self):
        """
        Sends a message to all peer nodes.
        """
        data = request.get_json()
        message = data.get("message")

        for peer in self.peers:
            host, port = peer.split(":")
            url = f"http://{host}:5000/receive_message"
            try:
                response = requests.post(
                    url,
                    json={"sender": self.node_id, "message": message},
                )
                if response.status_code == 200:
                    logging.info(
                        f"[Node {self.node_id}] Sent message to {peer}: {message}"
                    )
            except requests.ConnectionError:
                logging.info(f"[Node {self.node_id}] Could not reach {peer}")

        return jsonify({"status": "Message sent to peers"}), 200

    def get_message_log(self):
        """
        Endpoint to retrieve the message log for testing.
        """
        return jsonify({"messages": self.message_log}), 200

    def get_state(self):
        """
        Endpoint to determine the state of a Node.
        """
        return jsonify({"state": self.state, "node_id": self.node_id}), 200

    def append_entries(self):
        return self.current_state.append_entries()

    def vote_request(self):
        return self.current_state.vote_request()

    def process_client_request(self,message):
        self.current_state.send_append_entries_to_followers(message)

    # we can move this to the leader state
    def client_request(self):
        data = request.get_json()
        message = data.get('message')
        logging.info(f"Leader [Node{self.node_id}] received a client request")
        if self.state != 'Leader' or not isinstance(self.current_state, LeaderState):
            # Inform the client about the leader's address if known
            if hasattr(self, 'leader_id') and self.leader_id:
                leader_peer = next((peer for peer in self.peers if peer.startswith(f'node{self.leader_id}:')), None)
                if leader_peer:
                    host, port = leader_peer.split(':')
                    leader_address = f'http://{host}:5000'  # Adjust the port if necessary
                    return jsonify({'error': 'Not the leader', 'leader': leader_address}), 400
            return jsonify({'error': 'Not the leader, leader unknown'}), 400
        else:
            # Process the message and replicate it to followers
            self.process_client_request(message)
            return jsonify({'status': 'Message received and replicated'}), 200
