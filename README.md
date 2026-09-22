# ForgeMind

> *Hi, I'm Riham Hussain, I'm an AI and data enthusiast.*

**ForgeMind**
Industrial breakdown knowledge capture and RAG AI platform for plant engineers, technicians, and artisans.

ForgeMind provides a structured workflow to log equipment breakdowns, analyze root causes, and capture corrective actions. Powered by a hybrid vector-based RAG engine and an Excel-like data management experience, ForgeMind allows engineers to instantly query past failure modes and maintenance solutions.

---
## 📁 Repository Structure

```text
forgemind/
├── instance/               # SQLite database instance folder
│   └── forgemind.db        # Local SQLite database file
├── routes/                 # Flask route blueprints
│   ├── __init__.py
│   ├── admin.py            # Admin user management & account approval routes
│   ├── api.py              # REST API & RAG chat endpoints
│   ├── assets.py           # Asset management & breakdown profiles
│   ├── auth.py             # User authentication (Manual & OAuth)
│   ├── knowledge.py        # Breakdown knowledge capture & grid views
│   └── main.py             # Main application views & landing routes
├── services/               # Core business logic & external integrations
├── static/                 # Static assets
│   ├── css/
│   │   └── app.css         # Custom CSS & Tailwind styles
│   └── uploads/            # File & photo attachments (.gitkeep)
├── templates/              # Jinja2 HTML templates
│   ├── admin/
│   │   └── users.html      # Admin dashboard & user status management
│   ├── assets/
│   │   └── index.html      # Equipment deep-dive view
│   ├── auth/               # Auth UI templates
│   │   ├── layout.html
│   │   ├── login.html
│   │   ├── pending.html
│   │   └── register.html
│   └── knowledge/          # Main application views
│       ├── base.html       # Primary layout container
│       ├── chat.html       # RAG AI Chatbot UI ("Ask ForgeMind AI")
│       ├── dashboard.html  # Excel-style knowledge data grid
│       └── error.html
├── tests/                  # Automated test suite
│   ├── __init__.py
│   └── test_forgemind.py   # Unit & integration tests
├── .env                    # Environment variables (Ignored by Git)
├── .gitignore              # Git ignore file configuration
├── app.py                  # Flask application entry point
├── config.py               # Environment configuration settings
├── extensions.py           # Flask extensions initialization (SQLAlchemy, LoginManager, etc.)
├── forgemind.db            # Default SQLite database fallback
├── models.py               # Database schemas (User, BreakdownRecord, Asset)
├── README.md               # Project documentation
├── requirements.txt        # Python dependency manifest
├── reset_admin.py          # Administrative utility script
├── seed.py                 # Database seeding & Excel import script
├── utils.py                # Helper functions & utilities
└── vector_store.json       # Local JSON vector store for RAG embeddings
```

---

## ⚡ Features

- **Knowledge Capture & Asset Intelligence**: Log breakdown events, corrective steps, root cause analysis, downtime, and lessons learned.
- **Interactive RAG AI Chatbot ("Ask ForgeMind AI")**: Perform semantic searches on past records (e.g., *"Who fixed the flow detection issue on 21-CV-1013 and how?"*).
- **Excel-Style Management Grid**: Dense, interactive tabular views with filtering, status updates, inline edits, and `.xlsx` / CSV exports.
- **Role-Based Access Control (RBAC)**: Enforces role boundaries (`ADMIN`, `ENGINEER`, `ARTISAN`, `VIEWER`) and administrative approval workflows for pending accounts.
- **OAuth 2.0 Integration**: Supports social sign-in with **Google**, **Microsoft**, and **Apple**, alongside traditional email/password login.

---

## 🛠️ Tech Stack

- **Backend**: Flask 3, SQLAlchemy, Flask-Login, Flask-Migrate, Authlib
- **Database**: SQLite (default) / PostgreSQL (`DATABASE_URL`)
- **Vector Search & Embeddings**: ChromaDB + hashed n-gram embeddings (or OpenAI `text-embedding-3-small` / `gpt-4o-mini` when `OPENAI_API_KEY` is provided)
- **Frontend**: Jinja2 Templates, Tailwind CSS (CDN), Alpine.js, HTMX, Chart.js

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have **Python 3.10+** installed.

### 2. Installation & Setup

```bash
# Clone the repository
git clone [https://github.com/YOUR_USERNAME/forgemind.git](https://github.com/YOUR_USERNAME/forgemind.git)
cd forgemind

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Environment configuration
cp .env.example .env

# Seed initial database & test records
python seed.py

# Run the application
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`

---

## 🔐 Default Seed Accounts
After running python seed.py, you can log in with any of the pre-configured accounts below:
| **Role**	| **Email	Password** |	**Account Status** |
|-------|----------------|-----------------|
| ADMIN |	admin@forgemind.local | Admin123! |	APPROVED |
| ENGINEER |	engineer@forgemind.local | Engineer123!	| APPROVED |
| ARTISAN |	safuan@forgemind.local |	Artisan123! |	APPROVED |
| VIEWER |	viewer@forgemind.local |	Viewer123! |	APPROVED |
| ARTISAN |	pending@forgemind.local	| Pending123! |	PENDING |

Try the AI Chatbot: Log in and ask:
*"Who fixed the flow detection issue on 21-CV-1013 and how?"*

---

## ⚙️ OAuth Configuration
To enable OAuth logins for Google, Microsoft, or Apple, set your OAuth client IDs and secrets in .env:
```code snippet
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret

APPLE_CLIENT_ID=your_apple_client_id
APPLE_CLIENT_SECRET=your_apple_client_secret
```
Note: Unconfigured OAuth providers gracefully display an informational error without crashing the server.

---

## 🤖 RAG Engine Architecture
When new breakdown records are submitted and approved, their contents (asset_code, description, work_performed, notes) are auto-indexed into a vector embeddings store (vector_store.json / ChromaDB).
When querying Ask ForgeMind AI:
The system embeds the query.
Retrieves top-k relevant breakdown records using cosine similarity.
Injects the relevant context into the LLM system prompt.
Returns actionable technical advice alongside interactive source citation cards.

---

## 📄 License
Distributed under the MIT License. See LICENSE for more information.