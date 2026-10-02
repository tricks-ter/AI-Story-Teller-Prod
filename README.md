# 🌌 InkMind — AI Narrative Engine & Story Teller

> An advanced, interactive AI-driven narrative RPG system. InkMind allows users to create characters, define worlds, and embark on dynamic adventures guided by an AI Dungeon Master. Features deep state management, world memory, and real-time social interactions.

![Version](https://img.shields.io/badge/version-2.0.0-purple.svg)
![React](https://img.shields.io/badge/React-19-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)

---

## ✨ Key Features
- **Dynamic AI Dungeon Master**: Utilizes state-of-the-art LLMs with specialized prompt assemblers to generate responsive, context-aware narrative steps.
- **Deep World & State Management**: Tracks character inventory, HUD stats, locations, and world nodes across complex story playthroughs.
- **Interactive Story UI**: A rich React frontend featuring a Character Sheet, Inventory Panel, World Codex, Interactive Story Map, and Narrative Bubbles.
- **Optimistic Social Features**: Zero-latency likes, comments, and sharing mechanisms powered by a synchronized offline/online queue system.
- **Resilient Architecture**: Robust backend state resolvers, auto-healing PostgreSQL schemas (15+ deep migrations), and comprehensive API error handling.

---

## 🏗️ System Architecture

### Backend (Python/FastAPI)
- **State Resolution (`state_resolver.py`)**: Computes character stats, location transitions, and world triggers.
- **Prompt Assembly (`prompt_assembler.py`)**: Dynamically injects memory, lore, and current context into LLM prompts.
- **PostgreSQL Database (`db_ext.py`)**: Handles complex relational data including playthroughs, world states, and social queues.

### Frontend (React/Vite)
- **Complex State Sync (`syncQueue.js` & `hudStore.js`)**: Manages offline-first capabilities, queuing social actions and state updates until network connectivity is restored.
- **Component Ecosystem**: Modular architecture for narrative rendering (`MessageBubble`, `NarrativeBubble`) and RPG management (`InventoryPanel`, `StoryDetails`).

---

## 🚀 Quick Start Guide

### Prerequisites
- Node.js (v18+)
- Python (v3.12+)
- PostgreSQL Database

### 1. Backend Setup
```bash
cd api
pip install -r requirements.txt
```
Set your environment variables (e.g., in `.env` or exported in your terminal):
```env
DATABASE_URL=postgresql://user:pass@localhost:5432/inkmind
ZAI_API_KEY=your_llm_api_key
```
Run the migrations and start the server:
```bash
# Optional: run migrations if using a fresh DB (handled automatically by main.py in dev mode)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
*(The web UI will be available at `http://localhost:5173`)*

### 3. One-Command Start
You can also use the included bash script to spin up both environments locally:
```bash
./start.sh
```

---

## 📜 Documentation
For an in-depth dive into the system's mechanics, refer to the master docs:
- [Backend Master Doc](./BACKEND_MASTER.md)
- [Frontend Master Doc](./FRONTEND_MASTER.md)
- [Database Master Doc](./DATABASE_MASTER.md)
- [InkMind Master Context](./INKMIND_MASTER_CONTEXT.md)

---

## 🚀 Deployment
Configured for modern cloud hosting:
- **Frontend**: Deploys seamlessly to [Vercel](https://vercel.com/) via `vercel.json`.
- **Backend**: Blueprint configured for [Render.com](https://render.com/) via `render.yaml`.

## 📄 License
This project is licensed under the MIT License.
