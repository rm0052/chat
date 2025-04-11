import streamlit as st
from serpapi.google_search import GoogleSearch
from bs4 import BeautifulSoup
import requests
import json
import os
import uuid
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi

# Initialize Google GenAI client
client = genai.Client(api_key="AIzaSyDFbnYmLQ1Q55jIYYmgQ83sxledB_MgTbw")

# Streamlit App
st.title("Chatbot")

# Chat history file
CHAT_HISTORY_FILE = "chat_history2.json"

def load_chat_history():
    """Load the chat history dictionary from a file."""
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_chat_history(chat_histories):
    """Save the chat history dictionary to a file."""
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(chat_histories, f)

# Generate or retrieve a session ID
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())  # Unique session ID

session_id = st.session_state["session_id"]

# Load chat history dictionary and retrieve session-specific history
chat_histories = load_chat_history()
if session_id not in chat_histories:
    chat_histories[session_id] = []

# Store chat history in session state
st.session_state["chat_history"] = chat_histories[session_id]

# Display Chat History
st.write("## Chat History")
for q, r in st.session_state["chat_history"]:
    with st.chat_message("user"):
        st.write(q)
    with st.chat_message("assistant"):
        st.write(r)

def get_youtube_subtitles(video_url):
    """Fetch subtitles from a YouTube video."""
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
        # SerpAPI search
        params = {
            "engine": "google",
            "q": question,
            "api_key": "1b6c33844c034b01987d113928c20e7dc77c934345ae673545479a7b77f8e7c1",
            "num": 30,
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        filtered_links = [result["link"] for result in results.get("organic_results", [])]

        # Extract articles
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

        # Generate Response with Gemini 1.5 Flash
        prompt = f"Answer only yes or no if the context is useful in answering the question: {question}. Context: {context}"
        response = client.models.generate_content(model="gemini-2.5-pro-experimental", contents=prompt)
        answer = response.text.strip()

        # Follow-up Question
        if answer.lower() == "yes":
            final_prompt = f"Answer the question: {question}. Context: {context}"
        else:
            final_prompt = f"Answer the question using your own knowledge: {question}."

        final_response = client.models.generate_content(model="gemini-2.5-pro-experimental", contents=final_prompt)
        
        response_text = final_response.text.replace("$", "\\$").replace("provided text", "available information")
        st.session_state["chat_history"].append((question, response_text))

        # Update chat history dictionary
        chat_histories[session_id] = st.session_state["chat_history"]
        save_chat_history(chat_histories)

        st.rerun()
