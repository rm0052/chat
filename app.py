import streamlit as st
from serpapi.google_search import GoogleSearch
from bs4 import BeautifulSoup
import requests
import json
import os
import uuid
import html
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi
from streamlit_js_eval import streamlit_js_eval
from supabase import create_client, Client
from datetime import datetime, timezone

# ---------------------------
# CONFIG
# ---------------------------
st.title("Chatbot")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CLOUDFLARE_MEMORY_URL = os.getenv("CLOUDFLARE_MEMORY_URL")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------
# SESSION STATE INIT
# ---------------------------
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "user_email" not in st.session_state:
    st.session_state["user_email"] = None

session_id = st.session_state["session_id"]

# ---------------------------
# EMAIL STORAGE
# ---------------------------
def save_email(email):
    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    existing = supabase.table("emails_chat").select("*").eq("email", email).execute()
    if existing.data:
        user = existing.data[0]
        supabase.table("emails_chat").update({
            "last_visit": now,
            "num_visits": user["num_visits"] + 1
        }).eq("email", email).execute()
    else:
        supabase.table("emails_chat").insert([{
            "email": email,
            "first_visit": now,
            "last_visit": now,
            "num_visits": 1
        }]).execute()

# ---------------------------
# EMAIL GATE (FIXED)
# ---------------------------
if not st.session_state["user_email"]:
    email_input = st.text_input("Enter your email to continue:")

    if email_input and "@" in email_input:
        clean_email = email_input.strip().lower()

        st.session_state["user_email"] = clean_email
        save_email(clean_email)

        # Persist in browser
        streamlit_js_eval(
            js_expressions=f"window.localStorage.setItem('user_id', '{clean_email}')",
            key="set_user_id"
        )

        st.success("✅ Email saved. You can now chat.")
        st.rerun()
    else:
        st.stop()

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def groq_generate(prompt):
    safe_prompt = html.escape(prompt)

    completion = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": safe_prompt}
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    return completion.choices[0].message.content

def get_youtube_subtitles(video_url):
    try:
        video_id = video_url.split("v=")[-1]
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return "\n".join([entry["text"] for entry in transcript])
    except:
        return ""

# ---------------------------
# DISPLAY CHAT HISTORY
# ---------------------------
for msg in st.session_state["chat_history"]:
    with st.chat_message("user"):
        st.write(msg["question"])
    with st.chat_message("assistant"):
        st.write(msg["response"])

# ---------------------------
# CHAT INPUT
# ---------------------------
question = st.chat_input("Type your question and press Enter...")

if question:
    user_email = st.session_state["user_email"]

    with st.chat_message("user"):
        st.write(question)

    with st.spinner("Thinking..."):

        question = html.escape(question.strip())

        # ---------------------------
        # SEARCH CONTEXT
        # ---------------------------
        params = {
            "engine": "google",
            "q": question,
            "api_key": "YOUR_SERPAPI_KEY",
            "num": 10,
        }

        context = ""
        try:
            search = GoogleSearch(params)
            results = search.get_dict()

            for result in results.get("organic_results", []):
                link = result.get("link", "")

                try:
                    if "youtube.com" in link:
                        context += get_youtube_subtitles(link)[:300]
                    else:
                        r = requests.get(link, timeout=5)
                        soup = BeautifulSoup(r.text, "html.parser")
                        paragraphs = soup.find_all("p")
                        text = " ".join(p.get_text() for p in paragraphs)
                        context += text[:300]
                except:
                    continue

                if len(context) > 1500:
                    break
        except:
            pass

        # ---------------------------
        # FINAL PROMPT (EMAIL INCLUDED)
        # ---------------------------
        final_prompt = f"""
User Email: {user_email}

Question: {question}

Context: {context}

Answer clearly and helpfully.
"""

        response_text = groq_generate(final_prompt)

        # ---------------------------
        # STORE CHAT (PAYLOAD STYLE)
        # ---------------------------
        chat_entry = {
            "email": user_email,
            "question": question,
            "response": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        st.session_state["chat_history"].append(chat_entry)

        # ---------------------------
        # DISPLAY RESPONSE
        # ---------------------------
        with st.chat_message("assistant"):
            st.write(response_text)
