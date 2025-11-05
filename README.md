# GenAI Appointment-Booking Agent

An intelligent, multi-step conversational SQL agent for automated hospital appointment booking. This agent uses RAG (via Pinecone) to recommend specialists from a medical knowledge base and a secure, tool-based SQL agent (LangChain) to perform CRUD operations on a PostgreSQL database.

This agent is secure against common prompt injection attacks, prevents data leakage, and is robust against user-generated hallucinations. 

---

## Conversation Logs (Demonstrations)

To see the agent in action, please see the 'output' directory where conversation_logs.pdf is present. The logs in the pdf demonstrate the agent's capabilities including security.

---

## Key Features

* **Dual-Task Conversational AI:** The agent can handle two distinct user goals: (1) booking a new appointment and (2) checking an existing one.
* **RAG for Medical Recommendations:** Uses a Pinecone vector database populated with a `knowledge_base.pdf` to provide accurate specialist recommendations based on user-described symptoms.
* **Secure, Custom SQL Tools:** Does not use a generic SQL agent. Instead, it uses 7 custom, secure `@tool` functions (e.g., `book_appointment`, `lookup_upcoming_appointment` etc) that are validated, sanitized, and prevent SQL injection.
* **Robust Prompt-Engineering:** The `AGENT_SYSTEM_PROMPT` is highly-detailed, teaching the agent to follow complex, multi-step logic, manage two different tasks, and securely refuse malicious requests.
* **Built-in Security & Privacy:**
    * **Data Leak Prevention:** The agent will not share doctors’ personal phone numbers or email addresses.
    * **Prompt Injection Defense:** The agent will not follow user commands to modify the database or list all data.
    * **Hallucination Prevention:** The agent is "grounded" in its tools and will not invent doctors or specialties that aren't in the database.

---

## Tech Stack

* **AI & Orchestration:** LangChain (v1), LangGraph
* **LLM:** OpenAI (gpt-5-nano)
* **Vector Database:** Pinecone
* **Database:** PostgreSQL (Containerized with Docker)
* **Core:** Python, Jupyter

---

## Setup and Installation

Follow these steps to get the project running on your local machine.

### 1. Prerequisites

* [Python 3.10+](https://www.python.org/downloads/)
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (to run the database)
* [Git](https://git-scm.com/downloads)

### 2. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/GenAI-Appointment-Agent.git
cd GenAI-Appointment-Agent
```

### 3. Set Up the Virtual Environment

It is crucial to use a virtual environment to manage dependencies.

**On macOS/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**

```bash
python -m venv venv
.env\Scriptsctivate
```

### 4. Install Dependencies

Install all required Python libraries :

```bash
pip install langchain langchain-openai langchain-community langchain-pinecone langchain-text-splitters langgraph pinecone-client psycopg2-binary pypdf
```

Additionally, requirements.txt file is also provided.

### 5. Set Up API Keys & Environment

You will need API keys from OpenAI and Pinecone.

* **OpenAI:** Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) to create your secret key.
* **Pinecone:** Go to [app.pinecone.io](https://app.pinecone.io) and create a free account.
    1. Create an **Index** with the following details:
        * **Name:** `hospitalbot`
        * **Dimensions:** `1536` (for OpenAI's `text-embedding-3-small`)
        * **Metric:** `cosine`
    2. Go to the **"API Keys"** section to find your key.

Now, create your environment file:

1. Create a file named `.env` in the root of the project.
2. Copy and paste the following, filling in your own values. The `DB_URI` is set to connect to the Docker container we'll create next.

```env
# .env

# === AI KEYS ===
OPENAI_API_KEY="sk-..."
PINECONE_API_KEY="..."

# === DATABASE CONNECTION ===
# This connects to the Docker container we are launching in Step 6
DB_URI="postgresql://postgres:mysecretpassword@localhost:5432/hospital_db"
```

### 6. Start the Database (Docker)

Run the PostgreSQL database:

1. Make sure Docker Desktop is running.
2. Run the following command in your terminal to **start a new containerized PostgreSQL database**:

```bash
docker run --name hospital-db -d -p 5432:5432 -e POSTGRES_DB=hospital_db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=mysecretpassword postgres
```

* `--name hospital-db`: Gives your container a name.
* `-p 5432:5432`: Maps your computer's port 5432 to the container's port.
* `-e ...`: Sets the database name, user, and password to match our `.env` file.
* `postgres`: Tells Docker to use the official Postgres image.

3. The database is now running. To **populate it with the schema**, run this command:

```bash
psql -d hospital_db -U postgres -W -f hospital_schema.sql
```

* It will ask for your password. Type `mysecretpassword` (it will be invisible) and press Enter.

> **(Optional) Viewing the DB in VS Code:**
> You can install the [PostgreSQL VS Code extension](https://marketplace.visualstudio.com/items?itemName=ms-ossdata.vscode-postgresql) to connect to and view your running database container. Use the `localhost`, `5432`, `postgres`, and `mysecretpassword` to connect.

### 7. Run the Agent

You are now ready to run the chatbot!

1. Put all the code from your `.ipynb` file into a single file named `main.py`.
2. Execute the file from your terminal:

```bash
python main.py
```

3. The script will initialize the RAG system (you'll see the logs) and then start the chatbot.

-----


## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details.
