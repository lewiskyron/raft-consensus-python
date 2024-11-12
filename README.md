# Raft Consensus Algorithm in Python

This project implements the Raft Consensus Protocol in Python. The Raft algorithm is a consensus algorithm designed for managing a replicated log, commonly used in distributed systems. This README will guide you through the folder structure, the Docker setup for simulating nodes, and how to run the application.

## Project Structure

Here's a breakdown of the project folder structure:

```plaintext
raft-consensus-python/
├── client/
│   ├── static/                  # Static files for the client side.
│   ├── templates/
│   │   └── index.html           # HTML template for client UI
│   └── client.py                # Client code interacting with nodes(The leader node in this case)
├── disk/
│   └── leader_logs.db           # Persistent log storage
├── messages/
│   ├── __init__.py
│   ├── base_message.py          # Base class for messages between nodes
│   ├── heartbeat.py             # Heartbeat messages for leader health check
│   ├── vote_request.py          # Messages for requesting votes in an election
│   └── vote_response.py         # Response messages for vote requests
├── servers/
│   ├── candidate.py             # Logic for candidate node state
│   ├── follower.py              # Logic for follower node state
│   └── leader.py                # Logic for leader node state
│   └── node.py                  # Logic for shared node functinalities
├── tests/
│   ├── test_message_sending.py  # Some basic tests for testing inter-node communication
├── .gitignore                   # Git ignore file
├── Dockerfile                   # Dockerfile to build the application image
├── docker-compose.yml           # Docker Compose file to spin up nodes
├── main.py                      # Entry point for running the Raft protocol
├── README.md                    # Project documentation (this file)
└── requirements.txt             # Dependencies
```

## Setting Up the Project

**Create a Python Virtual Environment**

To manage dependencies locally can create a Python virtual environment. Run the following command:

```bash
python3 -m venv venv
```

**Activate the Virtual Environment**
- On macOS/Linux:
```bash
source venv/bin/activate
```
- On windows:
```bash
venv\Scripts\activate
```

## Running the Project

To simulate a Raft cluster, we use Docker and Docker Compose. The `docker-compose.yml` file defines three nodes, each running as an independent service and communicating over a bridge network.

### Docker Compose Configuration

The `docker-compose.yml` file defines three services:

- **node1**, **node2**, and **node3**: Each node has its own ID and communicates with its peers to simulate a cluster network. The environment variables define the node ID and the list of peers each node can communicate with.
- **Ports**: Each node exposes port `5000` internally, mapped to an external port (`6500`, `6501`, `6502` for each node respectively) for inter-node communication.
- **Volumes**: Each node mounts the `disk` directory to persist log data across container restarts.

### Build and Start the Cluster

Use the following command to build the Docker images and start the cluster:

```bash
docker-compose up --build
```

### Stopping the cluster 
```bash
docker-compose down
```
### Starting the Client
Navigate to the Client project directory:
```bash
cd raft-consensus-python
cd client
```
To run the client program run:
```bash
python client.py
```
