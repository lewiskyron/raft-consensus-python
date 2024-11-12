import os
from servers.node import Node

if __name__ == "__main__":
    node_id = os.getenv("NODE_ID")
    peers = os.getenv("PEERS", "").split(",")
    port = int(os.getenv("NODE_PORT", "5000"))

    # Start each node as a follower
    node = Node(node_id, peers)
    node.start_node(port=5000)
