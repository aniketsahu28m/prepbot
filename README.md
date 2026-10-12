# PrepBot: AI Interview Coach 🎙️

A practice job interviewer that runs on your own computer. You paste in a job description and your resume, and it:

1. **Plans** an interview tailored to that job and to you.
2. **Interviews** you, by typing or out loud, and asks follow-up questions when an answer is thin.
3. **Role-plays a customer.** At one point it pretends to be a non-technical customer whose software is broken, and you have to help them in plain English.
4. **Scores** each answer on technical accuracy, clarity and structure, and on whether a non-technical person would have understood it.
5. **Coaches** you with a report covering your weak spots, better sample answers and a 7-day practice plan.

It uses Google's AI (Gemini) and Google's Agent Development Kit (ADK).

---

## What you need

- A Mac, Windows or Linux computer
- **Python 3.10 or newer.** To check, open a terminal and type `python3 --version`. If it's missing, install it from [python.org](https://www.python.org/downloads/).
- **A Gemini API key.** It's free. See [Add your API key](#add-your-api-key) below.
- For voice mode: a microphone and the **Chrome** browser

## Setup (one time, about 5 minutes)

Open a terminal (on Mac: press ⌘ + Space, type "Terminal", press Enter) and run these lines one at a time:

```bash
# 1. Download the project and go into its folder
git clone https://gitlab.com/tryh4rd-26/prepbot.git
cd prepbot

# 2. Create a private Python space for this project
python3 -m venv .venv

# 3. Turn it on (Windows: .venv\Scripts\activate)
source .venv/bin/activate

# 4. Install what the project needs
pip install -e ".[dev]"

```

## Add your API key

The app needs your own Google Gemini API key to talk to the AI. You only do this once.

**Step 1: Get a key**

1. Go to **[aistudio.google.com/apikey](https://aistudio.google.com/apikey)** and sign in with a Google account.
2. Click **Create API key**. If it asks for a project, choose the default one.
3. Click the copy button next to the new key. It's a long line of letters and numbers.

**Step 2: Put the key in the project**

In the terminal, still inside the `prepbot` folder, run:

```bash
cp .env.example .env
```

This makes a file called `.env` from the example. Open it:

- **Mac:** `open -e .env`
- **Windows:** `notepad .env`
- **Linux:** `nano .env`

> Can't see `.env` in Finder or Explorer? Files that start with a dot are hidden. Use the commands above, or press ⌘ + Shift + . in Finder to show hidden files.

You'll see this line:

```
GOOGLE_API_KEY=paste-your-key-here
```

Replace `paste-your-key-here` with your key, so the line looks like `GOOGLE_API_KEY=AIzaSyB...yourkey`:

- no spaces around the `=`
- no quote marks
- the whole key on one line

Save and close the file. That's it.

**Changing the key later:** edit the same line in `.env`, save, then stop the app (`Ctrl + C`) and start it again.

> 🔒 **Keep your key secret.** It works like a password, and anyone who has it can use your Google quota. The `.env` file is listed in `.gitignore`, so Git will never upload it. Don't paste the key into chats, screenshots or code. If it leaks, delete it in AI Studio and create a new one.

> 💳 **Free keys have a daily limit** (about 20 requests per AI model per day, and one interview uses 30–50). For regular practice, turn on billing for the key in AI Studio. Pay-as-you-go costs very little for this.

## Start a practice interview

Each time you want to practise, open a terminal and run:

```bash
cd prepbot
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python app.py
```

When it says **PrepBot is running**, open **http://localhost:8000** in Chrome.

1. **Setup.** Paste the job description and your resume into the two boxes, or click **📄 Upload PDF** next to either box to fill it from a PDF (check the text, and fix it if needed). Then click **Plan my interview**. This takes 20–40 seconds.
2. **Choose how to answer.**
   - **⌨️ Type my answers:** a chat. Press Enter to send each answer.
   - **🎤 Speak my answers:** allow the microphone when Chrome asks, then just talk. The interviewer answers out loud. Tap the red button to mute yourself and tap it again to talk.
3. **Interview.** You'll get one question at a time, with follow-ups if an answer is thin. At one point the interviewer pretends to be a confused customer with a broken app. Help them in plain English.
4. **Report.** Click **End & get my report** whenever you're done. After about a minute you'll see your overall score, a score for each answer, and a coaching report.

To stop the app, go back to the terminal and press `Ctrl + C`.

## Where are my results?

Every finished interview is saved in the `sessions/` folder, in a subfolder named with the date and time:

| File | What's in it |
|---|---|
| `report.md` | Your coaching report: start here |
| `scores.json` | Score for every answer |
| `transcript.json` | Every question and answer |
| `plan.json` | The interview plan made from the job description |

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named ...` or `command not found` | You skipped `source .venv/bin/activate`. Run it and try again. |
| "No API key found" | You haven't added your key yet. See [Add your API key](#add-your-api-key). |
| "API key not valid" | Check the key in `.env`: no spaces, no quotes, and the whole key. |
| "429 RESOURCE_EXHAUSTED" / "quota exceeded" | Free Gemini keys allow only about 20 requests per model per day, and one interview uses 30–50. Turn on billing for your key in [AI Studio](https://aistudio.google.com/apikey) (pay-as-you-go is cheap for this), or wait until the next day. |
| "503 high demand" or "UNAVAILABLE" | Google's servers are busy. The app retries automatically. If it still fails, wait a minute and try again. |
| "model not found" / 404 | Google renamed a model. Set `TEXT_MODEL` or `LIVE_MODEL` in `.env` to a current name from [the model list](https://ai.google.dev/gemini-api/docs/models). |
| "Couldn't read text from …pdf" | The PDF is probably a scanned image with no selectable text. Open it, copy the text, and paste it into the box instead. |
| Mic doesn't work | Use Chrome and open `http://localhost:8000` exactly. Click the 🔒 icon next to the address, allow the microphone, and reload. |
| Port 8000 already in use | Run `PORT=8001 python app.py` and open `http://localhost:8001`. |

---

## For developers

### How it works

```
interview_coach (root coordinator, chat)
├── tools: parse_resume, save_session
├── jd_analyst   mode=single_turn  output_schema=InterviewPlan → state["plan"]
├── interviewer  mode=task         tools: record_turn, get_questions → state["transcript"]
├── evaluator    mode=single_turn  output_schema=Evaluation    → state["scores"]
└── coach        mode=single_turn  Markdown report             → state["report"]
```

- It uses the ADK 2.x **collaborative workflow** pattern. The root agent calls `single_turn` agents as tools. The `task`-mode interviewer takes over the conversation and hands control back with `finish_task`.
- Agents pass data through **session state**: `output_key` writes to state, and instructions read it with `{plan}`, `{transcript?}` and so on.
- In **voice**, only the agents that speak (root and interviewer) use a Gemini Live model. The analyst, evaluator and coach stay on a text model because they produce JSON and Markdown, not speech.
- **Web app (`app.py`):** typed interviews go through the full root agent. Voice interviews stream mic audio over a WebSocket to `run_live`, with the interviewer running on its own (`build_interviewer(..., standalone=True)`) in the same session, so there's no hand-off between agents mid-call. **End & get my report** asks the root agent to run the evaluator, then the coach, then `save_session`.
- Scoring runs once, after the interview, so there's no pause between voice answers.

### Layout

```
agents/
  interview_coach/         text app; all agent + tool code lives here
    agent.py               agents, JSON schemas, build_root()
    tools.py               parse_resume, get_questions, record_turn, save_session
    questions.json         question bank (edit freely)
  interview_coach_voice/   voice app: build_root() with a Live model
app.py                     web app server (FastAPI, comes with ADK)
static/index.html          the web app page (plain HTML/JS, no build step)
tests/                     offline pytest suite (no API key needed)
```

### Commands

```bash
pytest                    # run tests
python app.py             # the PrepBot web app
adk web agents            # ADK's developer UI (shows every agent step and the state)
adk run agents/interview_coach   # terminal chat, text only
```

### Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `TEXT_MODEL` | `gemini-flash-latest` | Text and JSON agents |
| `LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Voice agents (Live API) |
