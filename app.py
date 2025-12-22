import streamlit as st
from serpapi.google_search import GoogleSearch
from bs4 import BeautifulSoup
import requests
import json
import os
import uuid
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from streamlit_js_eval import streamlit_js_eval
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
# Streamlit App
st.title("Chatbot")

# Chat history file

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CLOUDFLARE_MEMORY_URL = os.getenv("CLOUDFLARE_MEMORY_URL")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
supabase: Client=create_client(SUPABASE_URL, SUPABASE_KEY)

def load_chat_history_cf(user_id):
    try:
        r = requests.get(
            CLOUDFLARE_MEMORY_URL,
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            timeout=10,
        )
        if r.status_code == 200 and r.text:
            data = json.loads(r.text)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        st.warning(f"Cloudflare load failed: {e}")
    return {}
    
def save_chat_history_cf(user_id, history):
    try:
        requests.post(
            CLOUDFLARE_MEMORY_URL,
            params={"user_id": user_id},
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json=history,
            timeout=10,
        )
    except Exception as e:
        st.warning(f"Cloudflare save failed: {e}")

@st.cache_data
def generate_cached(prompt):
    genai.configure(api_key="AIzaSyAUGzXVbqKi0d6QL2NDkQd64ocfdleEpuE")
    model = genai.GenerativeModel("gemini-1.5-pro")
    return model.generate_content(prompt)
    
def show_feedback():
    CHAT_HISTORY_FILE = "chat_history2.json"
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r") as f:
            try:
                chat_histories = json.load(f)
                st.write("### User Feedback")
                for session_id, chats in chat_histories.items():
                    for chat in chats:
                        if chat.get("feedback"):
                            st.markdown(f"""
                            **Session ID**: `{session_id}`  
                            **Question**: {chat['question']}  
                            **Feedback**: {chat['feedback']}  
                            ---
                            """)
            except json.JSONDecodeError:
                st.error("Failed to load chat history.")
    else:
        st.info("No chat history found.")

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

session_id = st.session_state["session_id"]


EMAIL_LOG = "emails.json"

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

# Secret code required to even see the admin panel
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "letmein")

query_params = st.query_params
admin_code = query_params.get("admin", None)
def show_admin_panel():
    st.title("🔐 Admin Panel")
    if "admin_authenticated" not in st.session_state:
        st.session_state["admin_authenticated"] = False
    if not st.session_state["admin_authenticated"]:
        password = st.text_input("Enter Admin Password", type="password")
        if password == os.getenv("ADMIN_PASSWORD", "qwmnasfjfuifgf"):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        elif password:
            st.error("Incorrect password.")
        st.stop()
    st.success("Welcome Admin!")
    response = supabase.table("emails_chat").select("*").execute()
    if response.data:
        st.json(response.data)
    else:
        st.info("No emails collected.")
    st.write("### Collected Feedback")
    show_feedback()
user_id = streamlit_js_eval(js_expressions="window.localStorage.getItem('user_id')", key="get_user_id")
if user_id:
    chat_histories = load_chat_history_cf(user_id)
else:
    chat_histories = {}
if session_id not in chat_histories:
    chat_histories[session_id] = []
# Sync to Streamlit
st.session_state["chat_history"] = chat_histories[session_id]
    
if not user_id:
    if admin_code == SECRET_ADMIN_CODE:
        show_admin_panel()
    email = st.text_input("Enter your email to continue:")
# Show admin panel ONLY if user_id is not set (i.e., user hasn't entered their email yet)
    if email and "@" in email:
        save_email(email)
        # Store user_id in browser
        streamlit_js_eval(js_expressions=f"window.localStorage.setItem('user_id', '{email}')", key="set_user_id")
        st.success("✅ Thanks! You're now connected.")
    else:
        st.warning("Please enter a valid email to start.")
        st.stop()
else:
    st.success("✅ Welcome back!")
    user_email = st.session_state.get("get_user_id")
    try:
        response = supabase.table("emails").select("email").eq("email", user_email).execute()
        if response.data:
            save_email(user_email)
    except Exception as e:
        st.warning(f"Could not load visit data from Supabase: {e}")
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
                save_chat_history_cf(user_id, st.session_state["chat_history"])
                st.rerun()
        with col2:
            if st.button("👎", key=f"thumbs_down_{i}"):
                chat["feedback"] = "👎"
                save_chat_history_cf(chat_histories)
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
st.write("Questions or feedback? Email hello@stockdoc.biz.")
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
        response = generate_cached(prompt)
        answer = response.text.strip()

        if answer.lower() == "yes":
            final_prompt = f"Answer the question: {question}. Context: {context}"
        else:
            final_prompt = f"Answer the question using your own knowledge: {question}."

        final_response = generate_cached(final_prompt)
        response_text = final_response.text.replace("$", "\\$").replace("provided text", "available information")

        # Append to chat history (with feedback placeholder)
        chat_entry = {
            "question": question,
            "response": response_text,
            "feedback": None
        }
        st.session_state["chat_history"].append(chat_entry) 
        chat_histories[session_id] = st.session_state["chat_history"] 
        save_chat_history_cf(user_id, chat_histories)
        st.rerun()




















