# candidate.py
import logging
import requests
from threading import Timer
import random
from messages.vote_request import VoteRequestMessage
from messages.vote_response import VoteResponseMessage


class CandidateState:
    def __init__(self, node):
        self.node = node
      
    def start(self):
        self.start_election()

    def start_election(self):
        logging.info(f"[Node {self.node.node_id}] Starting election.")
        self.increment_term()
        self.reset_votes()
        self.send_vote_requests()
        self.evaluate_election_result()

    def increment_term(self):
        """Increment the current term when starting a new election."""
        self.node.current_term += 1

    def reset_votes(self):
        """Reset votes and vote for self."""
        self.node.votes = 1
        self.node.voted_for = self.node.node_id  # Vote for itself

    def send_vote_requests(self):
        """Create a VoteRequestMessage, send it to all peers, and delegate response processing."""
        # Create VoteRequestMessage based on the last log index and term
        last_log_index = len(self.node.message_log) - 1 if len(self.node.message_log) > 0 else -1
        last_log_term = self.node.message_log[last_log_index]["term"] if last_log_index >= 0 else -1

        vote_request = VoteRequestMessage(
            sender_id=self.node.node_id,
            term=self.node.current_term,
            last_log_index=last_log_index,
            last_log_term=last_log_term,
        )
        request_dict = vote_request.to_dict()

        # Send VoteRequestMessage to all peers
        for peer in self.node.peers:
            try:
                host, port = peer.split(":")
                response = requests.post(f"http://{host}:5000/vote_request", json=request_dict)

                if response.status_code == 200:
                    vote_response = VoteResponseMessage.from_dict(response.json())

                    # Delegate response processing to process_vote_response
                    self.process_vote_response(vote_response, peer)

            except requests.ConnectionError:
                logging.warning(f"[Node {self.node.node_id}] Could not reach {peer} during election.")

    def process_vote_response(self, vote_response, peer):
        """Process the response to a vote request, updating votes or term as necessary."""
        if vote_response.vote_granted:
            self.node.votes += 1
        elif vote_response.term > self.node.current_term:
            logging.info(f"[Node {self.node.node_id}] Found newer term from {peer}. Transitioning back to follower.")
            self.node.current_term = vote_response.term
            self.node.become_follower()
            return  # Stop election process and transition back to follower

    def evaluate_election_result(self):
        if self.node.votes > len(self.node.peers) // 2:
            logging.info(
                f"[Node {self.node.node_id}] Won the election, transitioning to leader."
            )
            self.node.become_leader()
        else:
            logging.info(
                f"[Node {self.node.node_id}] Election lost, retrying after timeout."
            )
            # Schedule to retry election
            self.retry_election_timer = Timer(
                random.uniform(3, 5), self.start_election
            )
            self.retry_election_timer.start()

    def stop(self):
        self.node.current_state =  None
        if hasattr(self, "retry_election_timer"):
            self.retry_election_timer.cancel()
