import streamlit as st
import json
import os
import uuid
from google import genai
from bs4 import BeautifulSoup
import requests
from serpapi import GoogleSearch
from scrapingbee import ScrapingBeeClient
from youtube_transcript_api import YouTubeTranscriptApi

# Initialize Google GenAI client
GENAI_API_KEY = "AIzaSyDFbnYmLQ1Q55jIYYmgQ83sxledB_MgTbw"
client = genai.Client(api_key=GENAI_API_KEY)

# ScrapingBee API key
SCRAPINGBEE_API_KEY = "U3URPLPZWZ3QHVGEEP5HTXJ95873G9L58RJ3EHS4WSYTXOZAIE71L278CF589042BBMKNXZTRY23VYPF"

# File paths for saving chat history
CHAT_HISTORY_FILE = "chat_history_combined.json"

# Generate or retrieve a session ID
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())  # Unique session ID

session_id = st.session_state["session_id"]

# Load chat history from file
def load_chat_history():
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

# Save chat history to file
def save_chat_history(chat_histories):
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(chat_histories, f)

# Load data into session state at startup
chat_histories = load_chat_history()
if session_id not in chat_histories:
    chat_histories[session_id] = {"chat_history": [], "news_articles": "", "news_links": []}

st.session_state["chat_history"] = chat_histories[session_id]["chat_history"]
st.session_state["news_articles"] = chat_histories[session_id]["news_articles"]
st.session_state["news_links"] = chat_histories[session_id]["news_links"]

# Sidebar Selection
chatbot_option = st.sidebar.radio("Choose a Chatbot:", ["SerpAPI + Gemini", "ScrapingBee + Gemini"])

# 🧠 --- CHATBOT 1: SerpAPI + Gemini ---
def chatbot_one():
    st.title("Chatbot 1 (SerpAPI + Gemini)")

    # Display Chat History
    st.write("## Chat History")
    for q, r in st.session_state["chat_history"]:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            st.write(r)

    # Function to get YouTube subtitles
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
        with st.spinner("Fetching data..."):
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

            # Generate Response
            prompt = f"Answer only yes or no if the context is useful in answering the question: {question}. Context: {context}"
            response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
            answer = response.text.strip()

            if answer.lower() == "yes":
                final_prompt = f"Answer the question: {question}. Context: {context}"
            else:
                final_prompt = f"Answer the question using your own knowledge: {question}."

            final_response = client.models.generate_content(model="gemini-1.5-flash", contents=final_prompt)

            # Update history
            st.session_state["chat_history"].append((question, final_response.text))
            chat_histories[session_id]["chat_history"] = st.session_state["chat_history"]
            save_chat_history(chat_histories)

            st.rerun()

# 📰 --- CHATBOT 2: ScrapingBee + Gemini ---
def chatbot_two():
    st.title("Chatbot 2 (ScrapingBee + Gemini)")

    # Fetch News Button
    if st.button("Fetch News"):
        client = ScrapingBeeClient(api_key=SCRAPINGBEE_API_KEY)
        url = "https://finance.yahoo.com/topic/latest-news/"
        response = client.get(url, params={"ai_query": "Extract all article headlines and their links."})
        st.session_state["news_articles"] = response.text
        chat_histories[session_id]["news_articles"] = response.text
        save_chat_history(chat_histories)
        st.write("✅ News fetched.")

    # Display Chat History
    st.write("## Chat History")
    for q, r in st.session_state["chat_history"]:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            st.write(r)

    # User Input
    question = st.chat_input("Type your question and press Enter...")

    if question:
        prompt = f"Extract the most useful links from this text: {st.session_state['news_articles']}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        links = response.text.strip().split("\n")

        st.session_state["news_links"] = links
        chat_histories[session_id]["news_links"] = links
        save_chat_history(chat_histories)

        # Follow-up
        prompt = f"Answer based on the latest news: {question}. Links: {links}"
        final_response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)

        st.session_state["chat_history"].append((question, final_response.text))
        chat_histories[session_id]["chat_history"] = st.session_state["chat_history"]
        save_chat_history(chat_histories)

        st.rerun()

# 🚦 --- Select Which Chatbot to Run ---
if chatbot_option == "SerpAPI + Gemini":
    chatbot_one()
else:
    chatbot_two()
