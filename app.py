import streamlit as st
from serpapi.google_search import GoogleSearch
from bs4 import BeautifulSoup
import requests
import json
import os
import uuid
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi
from streamlit_js_eval import streamlit_js_eval

# Initialize Google GenAI client
client = genai.Client(api_key="AIzaSyDFbnYmLQ1Q55jIYYmgQ83sxledB_MgTbw")

# Streamlit App
st.title("Chatbot")

# Chat history file
CHAT_HISTORY_FILE = "chat_history2.json"

def load_chat_history():
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_chat_history(chat_histories):
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(chat_histories, f)

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

session_id = st.session_state["session_id"]

# Load chat histories from file
chat_histories = load_chat_history()

import streamlit as st
from streamlit_js_eval import streamlit_js_eval

EMAIL_FILE = "emails.txt"

def save_email(email):
    with open(EMAIL_FILE, "a") as f:
        f.write(email + "\n")

# Get user ID (unique per browser, stored in local storage)
user_id = streamlit_js_eval(js_expressions="window.localStorage.getItem('user_id')", key="get_user_id")

if not user_id:
    # Ask for email only if user_id not found
    email = st.text_input("Enter your email to continue:")

    if email and "@" in email:
        save_email(email)
        # Store user_id in browser
        streamlit_js_eval(js_expressions=f"window.localStorage.setItem('user_id', '{email}')", key="set_user_id")
        st.success("✅ You're all set! Reload to start chatting.")
        st.stop()
    else:
        st.warning("Please enter a valid email to start.")
        st.stop()
else:
    st.success("✅ Welcome back!")
    # Proceed to chatbot



# Ensure session-specific history exists
if session_id not in chat_histories:
    chat_histories[session_id] = []

# Sync with session state
st.session_state["chat_history"] = chat_histories[session_id]

# Display Chat History
st.write("## Chat History")
for i, chat in enumerate(st.session_state["chat_history"]):
    with st.chat_message("user"):
        st.write(chat["question"])
    with st.chat_message("assistant"):
        st.write(chat["response"])
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("👍", key=f"thumbs_up_{i}"):
                chat["feedback"] = "👍"
                save_chat_history(chat_histories)
                st.rerun()
        with col2:
            if st.button("👎", key=f"thumbs_down_{i}"):
                chat["feedback"] = "👎"
                save_chat_history(chat_histories)
                st.rerun()
        if chat.get("feedback"):
            st.caption(f"Feedback: {chat['feedback']}")

def get_youtube_subtitles(video_url):
    video_id = video_url.split("v=")[-1]
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        subtitles = "\n".join([entry["text"] for entry in transcript])
        return subtitles
    except Exception as e:
        return f"Error: {e}"

# User Input
question = st.chat_input("Type your question and press Enter...")

if question:
    with st.spinner("Running..."):
        # Google Search via SerpAPI
        params = {
            "engine": "google",
            "q": question,
            "api_key": "1b6c33844c034b01987d113928c20e7dc77c934345ae673545479a7b77f8e7c1",
            "num": 30,
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        filtered_links = [result["link"] for result in results.get("organic_results", [])]

        # Scrape Articles
        context = ""
        for link in filtered_links:
            try:
                if "youtube.com" in link:
                    context += " " + get_youtube_subtitles(link)[:500]
                else:
                    response = requests.get(link, timeout=10)
                    soup = BeautifulSoup(response.text, "html.parser")
                    paragraphs = soup.find_all("p")
                    article_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
                    context += " " + article_text[:500]
            except:
                continue
            if len(context) >= 2000:
                break

        # Determine if context is useful
        prompt = f"Answer only yes or no if the context is useful in answering the question: {question}. Context: {context}"
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        answer = response.text.strip()

        if answer.lower() == "yes":
            final_prompt = f"Answer the question: {question}. Context: {context}"
        else:
            final_prompt = f"Answer the question using your own knowledge: {question}."

        final_response = client.models.generate_content(model="gemini-2.0-flash", contents=final_prompt)
        response_text = final_response.text.replace("$", "\\$").replace("provided text", "available information")

        # Append to chat history (with feedback placeholder)
        chat_entry = {
            "question": question,
            "response": response_text,
            "feedback": None
        }
        st.session_state["chat_history"].append(chat_entry)
        chat_histories[session_id] = st.session_state["chat_history"]
        save_chat_history(chat_histories)

        st.rerun()
