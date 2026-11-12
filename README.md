# 🎙️ VaaniOS: AI-Powered Voice Ledger

> A premium, voice-first business assistant designed for seamless sales, expense tracking, and real-time financial analytics tailored for wholesale and retail operations.

VaaniOS transforms the way businesses manage their daily ledgers. Instead of typing data manually, users can simply speak naturally in Hindi, English, or Hinglish (e.g., *"5000 ki sale hui"* or *"1000 ka kharcha hua"*), and the Gnani AI engine will parse, categorize, and safely record the transaction.

## ✨ Key Features

- **🎙️ Natural Voice Engine:** Powered by Gnani AI, understands mixed-language voice commands for adding sales and expenses with high accuracy.
- **🎨 Premium UI/UX:** EmberAI-inspired premium dark-mode aesthetic with neon glowing accents, smooth micro-interactions, and a Light/Dark mode toggle.
- **📊 Real-time Analytics:** An interactive 7-Day Cashflow Trajectory chart built with Chart.js, featuring multi-colored neon area splines.
- **📅 Smart Date Picker:** Instantly fetch and view historical transaction logs and summaries for any specific day.
- **📤 1-Click Exports:** Export the daily ledger as a professional PDF invoice or share a pre-filled summary directly via WhatsApp.
- **⏪ Safe Undo System:** Gmail-style smart toast notifications allowing instant rollback of the last recorded transaction.
- **🔒 Bulletproof Confirmation:** Action UUIDs and pending-state management ensure no duplicate transactions are ever saved.

## 🛠️ Tech Stack

**Frontend:**
- HTML5, CSS3 (Glassmorphism & Custom Keyframe Animations)
- Vanilla JavaScript (ES6+)
- Chart.js (Data Visualization)
- html2pdf.js (PDF Generation)
- Lucide Icons & Plus Jakarta Sans Typography

**Backend:**
- Python 3 & Flask (REST API)
- SQLite (Local persistent database)
- Gnani AI (Speech-to-Text & Intent parsing)

## 🚀 Getting Started

### 1. Backend Setup
Navigate to the backend directory, set up your Python environment, and start the Flask server:

    cd backend
    python3 -m venv venv
    source venv/bin/activate  # On Windows use: venv\Scripts\activate
    pip install -r requirements.txt
    python3 app.py

*The backend will run on `http://127.0.0.1:5000` and automatically initialize the SQLite database.*

### 2. Frontend Setup
Open a new terminal window, navigate to the frontend directory, and serve the static files:

    cd frontend
    python3 -m http.server 5500

*Open `http://localhost:5500` in Google Chrome or Microsoft Edge.*

## 📖 Core API Routes

- `POST /api/voice/command` - Processes raw audio and returns parsed intents/amounts.
- `POST /api/voice/confirm` - Safely commits a pending transaction using its `action_id`.
- `POST /api/transaction/undo` - Removes the most recently added transaction.
- `GET /api/summary/today` - Fetches the current day's total sales, expenses, and net cash.
- `GET /api/summary/weekly` - Fetches aggregated 7-day data formatted for Chart.js.

## 👨‍💻 Author
Built with by Maheswar Nayak
