# Defines behavior specific to a follower, like receiving heartbeats and responding to vote requests.
# follower.py
import random
from threading import Timer
import logging
from messages.heartbeat import HeartbeatMessage
from messages.vote_request import VoteRequestMessage
from messages.vote_response import VoteResponseMessage
from flask import request, jsonify


class FollowerState:
    def __init__(self, node):
        self.node = node

    def start(self):
        # No additional action needed when starting as a follower
        pass

    def initialize(self):
        self.reset_election_timer()

    def reset_election_timer(self):
        if self.node.election_timer:
            self.node.election_timer.cancel()
        self.node.election_timer = Timer(self.node.election_timeout, self.start_election)  # Remove parentheses
        self.node.election_timer.start()

    def start_election(self):
        logging.info(f"[Node {self.node.node_id}] No leader detected, starting election.")
        self.node.become_candidate()

    def append_entries(self):
        """
        Endpoint to handle AppendEntries RPC (Heartbeat) from the leader.
        """
        data = request.get_json()
        heartbeat = HeartbeatMessage.from_dict(data)

        # Validate the term and update the state if necessary
        if heartbeat.term < self.node.current_term:
            return jsonify({"success": False, "reason": "Outdated term"}), 200

        # Update current term if heartbeat term is higher - check if this is the correct implementation !!!!
        if heartbeat.term > self.node.current_term:
            self.node.current_term = heartbeat.term
            self.node.voted_for = None  # Reset voted_for when term changes

        # Reset election timer upon receiving a valid heartbeat
        logging.info(
            f"[Node {self.node.node_id}] Received heartbeat from leader {heartbeat.sender_id}."
        )
        self.reset_election_timer()  # Reset election timer upon receiving heartbeat

        # Respond with success
        return jsonify({"success": True}), 200

    def vote_request(self):
        """
        Endpoint to handle VoteRequest RPC from a candidate.
        """
        data = request.get_json()
        vote_request = VoteRequestMessage.from_dict(data)

        # Check the term and candidate eligibility
        if vote_request.term < self.node.current_term:
            # Reject vote request due to outdated term
            response = VoteResponseMessage(
                sender_id=self.node.node_id, term=self.node.current_term, vote_granted=False
            )
            return jsonify(response.to_dict()), 200

        # Update term if the candidate's term is higher
        if vote_request.term > self.node.current_term:
            self.node.current_term = vote_request.term
            self.node.voted_for = None  # Reset voted_for when term changes

        # Grant vote if this node hasn't voted yet or is voting for the same candidate
        if self.node.voted_for is None or self.node.voted_for == vote_request.sender_id:
            logging.info(
                f"[Node {self.node.node_id}] Voting for candidate {vote_request.sender_id} in term {vote_request.term}."
            )
            self.node.voted_for = vote_request.sender_id
            self.reset_election_timer()
            response = VoteResponseMessage(
                sender_id=self.node.node_id, term=self.node.current_term, vote_granted=True
            )
            return jsonify(response.to_dict()), 200

        # Otherwise, do not grant the vote
        response = VoteResponseMessage(
            sender_id=self.node.node_id, term=self.node.current_term, vote_granted=False
        )
        return jsonify(response.to_dict()), 200
