# Multi-Agent Coding Assistant

<p align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Frontend-FF4B4B?logo=streamlit&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent_Workflow-6A5ACD)
![Cerebras](https://img.shields.io/badge/Cerebras-LLM-orange)
![Podman](https://img.shields.io/badge/Podman-Sandbox-892CA0?logo=podman&logoColor=white)
![REST API](https://img.shields.io/badge/REST_API-FastAPI-success)

</p>

Multi-Agent Coding Assistant is an AI-driven software generation platform built with FastAPI, Streamlit, and LangGraph. It leverages multiple specialized agents for planning, architecture design, code generation, execution, testing, and review, enabling end-to-end project generation from natural language requirements. Generated code is executed inside an isolated Podman sandbox before being returned to the user, while the system can optionally perform web searches to gather additional implementation context. The Streamlit frontend tracks execution progress in real time using a polling-based architecture.

---

## Features

### AI Agents

- Planner Agent
- Architecture Agent
- Coder Agent
- Executor Agent
- QA Agent
- Reviewer Agent
- Orchestrator Agent

### Core Features

- Multi-Agent Workflow
- LangGraph Orchestration
- Polling-based Progress Tracking
- Podman Sandbox Execution
- File Upload Support
- Web Search Integration
- Download Generated Projects

---

## Tech Stack

| Category | Technologies |
|-----------|--------------|
| Programming Language | Python |
| Frontend | Streamlit |
| Backend | FastAPI |
| AI Workflow | LangGraph |
| LLM Provider | Cerebras API |
| Execution Environment | Podman |
| Testing | PyTest |
| API Communication | REST API |
| Environment Management | python-dotenv |
| Data Validation | Pydantic |
| Server | Uvicorn |

---

## Project Architecture / Workflow

The application follows a collaborative multi-agent software development workflow.

```
                    User Request
                          │
                          ▼
                  Planner Agent
                          │
                          ▼
               Architecture Agent
                          │
                          ▼
                   Coder Agent
                          │
                          ▼
                Executor Sandbox
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
       QA Agent                  Reviewer Agent
            └─────────────┬─────────────┘
                          ▼
                  Orchestrator Agent
            ┌─────────────┴─────────────┐
            ▼                           ▼
     Retry Generation           Final Project
```
The backend processes user requests asynchronously. Once a request is submitted, the backend immediately returns a job ID while executing the workflow in the background. The Streamlit frontend periodically polls the `/status/{job_id}` endpoint to display live progress updates, active agent information, execution logs, and the final generated output.

### Workflow

1. User submits a project requirement.
2. Planner Agent creates an implementation plan.
3. Architecture Agent designs the project structure.
4. Coder Agent generates the project files.
5. Code executes inside a secure Podman sandbox.
6. QA and Reviewer agents validate the generated project.
7. The Orchestrator decides whether to regenerate or return the final output.
8. The frontend continuously polls the backend using `/status/{job_id}` to display real-time workflow progress.

---

## Folder Structure

```
Multi-Agent-Coding-Assistant/
│
├── backend/
│   ├── agents/
│   ├── api/
│   ├── graph/
│   ├── models/
│   ├── services/
│   ├── terminal/
│   └── utils/
│
├── frontend/
│   └── streamlit_app.py
│
├── tests/
│
├── app.py
├── main.py
├── requirements.txt
├── sandbox.Dockerfile
└── README.md
```

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/Nikita-kumar-15/Multi-Agent-Coding-Assistant.git

cd Multi-Agent-Coding-Assistant
```

### Create Virtual Environment

```bash
python -m venv venv
```

### Activate Virtual Environment

**Windows**

```bash
venv\Scripts\activate
```

**macOS/Linux**

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file in the project root.
A valid Cerebras API key is required to run the project.
```env
CEREBRAS_API_KEY=your_api_key
FAST_MODEL=your_fast_model
HEAVY_MODEL=your_heavy_model
```

---

## Requirements

- Python 3.11+
- Podman
- Git
- Cerebras API Key

---

## Usage

Start the FastAPI backend.

```bash
uvicorn main:app --reload
```

Launch the Streamlit frontend.

```bash
streamlit run frontend/streamlit_app.py
```

Open the application in your browser and submit a natural language prompt to generate a software project.

---

## Results

### Current Capabilities

- Generates complete multi-file software projects
- Produces frontend applications from natural language prompts
- Executes generated code inside an isolated Podman sandbox
- Performs automated QA and code review
- Refines code through an orchestrated retry loop
- Displays real-time workflow progress using polling APIs

### Example Generated Projects

- Netflix Landing Page
- Shopping Website
- Portfolio Website
- Dashboard UI
- Todo Application

---

## Screenshots

The following images demonstrate the user interface, multi-agent workflow, execution dashboard, and examples of projects generated by the assistant.

## Streamlit Dashboard

The Streamlit interface where users submit prompts, upload files, monitor agent execution, and download generated projects.
<img width="900" alt="image" src="https://github.com/user-attachments/assets/60cb7a95-9b8d-4c05-853f-e1905f3d2832" />

---

## Multi-Agent Workflow

<img width="900" alt="image" src="https://github.com/user-attachments/assets/ae479d51-4fd9-4da1-afbd-ffa8a47f8ece" />

---

## Agent Execution

<img width="900" alt="image" src="https://github.com/user-attachments/assets/3849ce99-c9f8-4e88-8b26-ebe25a9a0170" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/4bffb8f5-3c03-45d8-8cb3-9380a4d0bc91" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/3f5ea26d-e127-458f-ac09-1cc70c73c475" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/83ea4da4-32e5-4137-93ea-97b1bf3c690e" />

---

## Generated Netflix Landing Page

<img width="900" alt="image" src="https://github.com/user-attachments/assets/20df84b3-276f-4b00-9996-3a3cdd012aea" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/0e4d882e-5f95-417e-93dc-ee81171746ba" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/ae1c7680-ac10-4326-9a8b-2aaab2c194c7" />




<img width="900" alt="image" src="https://github.com/user-attachments/assets/af1e3fb7-bfdd-4aec-a792-c02bf080dce9" />




---

## Challenges Faced

- Designing communication between multiple autonomous agents.
- Maintaining project context across long-running workflows.
- Securely executing generated code using Podman.
- Managing asynchronous workflow execution through a polling API.
- Coordinating parallel QA and Reviewer agents.
- Handling automatic retries without losing project state.

---

## Future Improvements

- Docker deployment
- Cloud deployment (AWS/Azure/GCP)
- Multi-language code generation
- Persistent vector memory
- Real-time collaboration
- Voice-based project generation
- WebSocket support for live updates
- CI/CD integration
- Support for additional LLM providers

---

# Acknowledgements

- Cerebras AI for LLM inference.
- LangGraph for workflow orchestration.
- FastAPI for backend development.
- Streamlit for the interactive user interface.
- Podman for secure sandbox execution.
- Open-source Python ecosystem.
