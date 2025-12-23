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
from datetime import datetime, timedelta, timezone

# Streamlit App
st.title("Chatbot")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CLOUDFLARE_MEMORY_URL = os.getenv("CLOUDFLARE_MEMORY_URL")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_RLHF_URL = os.getenv("CLOUDFLARE_RLHF_URL", f"{CLOUDFLARE_MEMORY_URL}/rlhf")
supabase: Client=create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def groq_generate(prompt, chat_history=None):
    """Generate response using Groq with RLHF improvements if available"""
    system_message = "You are a helpful assistant."
    
    # Extract specific examples and patterns from feedback history
    rlhf_examples = []
    rlhf_patterns = {}
    
    if chat_history and any(entry.get("feedback") for entry in chat_history):
        # Get general RLHF learnings
        rlhf_data = get_rlhf_learnings(chat_history)
        if rlhf_data:
            system_message += f"\n\nBased on user feedback, please note these preferences:\n{rlhf_data}"
        
        # Extract specific examples of good responses
        positive_examples = [entry for entry in chat_history if entry.get("feedback") == "👍"]
        if positive_examples:
            # Use the most recent positive examples as few-shot examples
            for example in positive_examples[-2:]:  # Last 2 positive examples
                rlhf_examples.append({
                    "role": "user", 
                    "content": example["question"]
                })
                rlhf_examples.append({
                    "role": "assistant", 
                    "content": example["response"]
                })
            
            # Extract patterns from positive responses
            rlhf_patterns = extract_response_patterns(positive_examples)
    
    # Sanitize inputs to prevent prompt injection
    safe_prompt = html.escape(prompt)
    
    # Prepare messages with few-shot examples if available
    messages = [{"role": "system", "content": system_message}]
    
    # Add few-shot examples if available
    if rlhf_examples:
        messages.extend(rlhf_examples)
    
    # Add the current user query
    messages.append({"role": "user", "content": safe_prompt})
    
    # Generate initial response
    completion = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )
    
    initial_response = completion.choices[0].message.content
    
    # Apply RLHF patterns to refine the response if patterns exist
    final_response = apply_rlhf_patterns(initial_response, rlhf_patterns)
    
    return final_response

def get_rlhf_learnings(chat_history):
    """Extract learnings from feedback history to improve responses"""
    positive_examples = []
    negative_examples = []
    
    for entry in chat_history:
        if entry.get("feedback") == "👍":
            positive_examples.append(entry)
        elif entry.get("feedback") == "👎":
            negative_examples.append(entry)
    
    if not positive_examples and not negative_examples:
        return ""
        
    learnings = []
    
    # Extract patterns from positive feedback
    if positive_examples:
        learnings.append("DO: Users responded positively to these types of responses:")
        for i, example in enumerate(positive_examples[-3:], 1):  # Last 3 positive examples
            learnings.append(f"{i}. When asked: '{example['question'][:50]}...', you provided this well-received response: '{example['response'][:100]}...'")
    
    # Extract patterns from negative feedback
    if negative_examples:
        learnings.append("\nAVOID: Users responded negatively to these types of responses:")
        for i, example in enumerate(negative_examples[-3:], 1):  # Last 3 negative examples
            learnings.append(f"{i}. When asked: '{example['question'][:50]}...', this response was not well-received: '{example['response'][:100]}...'")
    
    return "\n".join(learnings)

def extract_response_patterns(positive_examples):
    """Extract patterns from positively rated responses to guide future responses"""
    if not positive_examples:
        return {}
    
    patterns = {
        "tone": [],
        "structure": [],
        "length": 0,
        "keywords": set()
    }
    
    # Analyze tone, structure, and length patterns
    total_length = 0
    for example in positive_examples:
        response = example["response"]
        total_length += len(response)
        
        # Simple tone analysis
        if "?" in response:
            patterns["tone"].append("inquisitive")
        if any(phrase in response.lower() for phrase in ["i think", "perhaps", "maybe", "possibly"]):
            patterns["tone"].append("thoughtful")
        if any(phrase in response.lower() for phrase in ["definitely", "certainly", "absolutely"]):
            patterns["tone"].append("confident")
            
        # Structure analysis
        if response.count("\n") > 3:
            patterns["structure"].append("multi-paragraph")
        if any(marker in response for marker in ["1.", "2.", "*", "-"]):
            patterns["structure"].append("bullet-points")
            
        # Extract potential keywords (simple implementation)
        words = response.lower().split()
        for word in words:
            if len(word) > 5 and word.isalpha():  # Simple filter for meaningful words
                patterns["keywords"].add(word)
    
    # Calculate average length
    if positive_examples:
        patterns["length"] = total_length // len(positive_examples)
        
    # Count frequencies and keep only the most common patterns
    for key in ["tone", "structure"]:
        if patterns[key]:
            # Get the most common elements
            from collections import Counter
            counter = Counter(patterns[key])
            patterns[key] = [item for item, count in counter.most_common(2)]
    
    # Limit keywords to most relevant ones
    patterns["keywords"] = list(patterns["keywords"])[:10]
    
    return patterns

def apply_rlhf_patterns(response, patterns):
    """Apply learned patterns to refine the response"""
    if not patterns:
        return response
        
    # Don't modify the response if we don't have enough pattern data
    if not patterns.get("tone") and not patterns.get("structure"):
        return response
    
    # Apply length pattern (if the response is too short)
    target_length = patterns.get("length", 0)
    if target_length > 0 and len(response) < target_length * 0.7:
        # Ask Groq to expand the response
        expansion_prompt = f"The following response is too brief. Please expand it to be more detailed while maintaining the same meaning: {response}"
        try:
            expansion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": expansion_prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            response = expansion.choices[0].message.content
        except Exception:
            # If expansion fails, keep original response
            pass
    
    # Apply structure patterns
    if "bullet-points" in patterns.get("structure", []) and not any(marker in response for marker in ["1.", "2.", "*", "-"]):
        # Ask Groq to restructure with bullet points
        restructure_prompt = f"Please restructure this response to use bullet points or numbered lists where appropriate: {response}"
        try:
            restructured = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": restructure_prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            response = restructured.choices[0].message.content
        except Exception:
            # If restructuring fails, keep original response
            pass
    
    return response

def load_chat_history_cf(user_id):
    """Load chat history from Cloudflare"""
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
    """Save chat history to Cloudflare"""
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

def submit_rlhf_feedback(user_id, feedback_data):
    """Submit RLHF feedback to Cloudflare for model improvement"""
    try:
        # Add metadata to help with RLHF analysis
        feedback_data["metadata"] = {
            "user_id": user_id,
            "session_id": session_id,
            "feedback_time": datetime.now(timezone.utc).isoformat()
        }
        
        # Submit to Cloudflare RLHF endpoint
        response = requests.post(
            CLOUDFLARE_RLHF_URL,
            params={"user_id": user_id},
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json=feedback_data,
            timeout=10,
        )
        
        if response.status_code != 200:
            st.warning(f"RLHF feedback submission returned status code: {response.status_code}")
            return False
            
        return True
    except Exception as e:
        st.warning(f"RLHF feedback submission failed: {e}")
        return False

# Initialize session state
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

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

# Load user data and chat history
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

def get_youtube_subtitles(video_url):
    video_id = video_url.split("v=")[-1]
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        subtitles = "\n".join([entry["text"] for entry in transcript])
        return subtitles
    except Exception as e:
        return f"Error: {e}"

# Display chat history
for i, message in enumerate(st.session_state["chat_history"]):
    with st.chat_message("user"):
        st.write(message["question"])
    with st.chat_message("assistant"):
        st.write(message["response"])
        if "feedback" in message and message["feedback"]:
            st.info(f"You gave this response: {message['feedback']}")

# User Input
question = st.chat_input("Type your question and press Enter...")
st.write("Questions or feedback? Email hello@stockdoc.biz.")

if question and question != st.session_state.get("last_question"):
    # Display user question
    with st.chat_message("user"):
        st.write(question)
        
    with st.spinner("Running..."):
        # Validate and sanitize the input
        question = html.escape(question.strip())
        
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

        # Scrape Articles with proper error handling and sanitization
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
            except Exception as e:
                continue
            if len(context) >= 2000:
                break
                
        final_prompt = f"Answer the question: {question}. Context: {context}"
        
        # Generate response using RLHF-enhanced model with feedback history
        response_text = groq_generate(final_prompt, st.session_state["chat_history"])
        
        # Log that RLHF was applied (for debugging)
        st.session_state["rlhf_applied"] = any(entry.get("feedback") for entry in st.session_state["chat_history"])
        
        st.session_state.last_question = question 
        st.session_state.last_response = response_text
        
        # Create a new chat entry (without feedback yet)
        chat_entry = {
            "question": question,
            "response": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feedback": None
        }
        
        # Add to session state
        st.session_state["chat_history"].append(chat_entry)
        
        # Display assistant response with feedback buttons
        with st.chat_message("assistant"): 
            st.write(response_text)
            col1, col2 = st.columns(2)
            
            # Define feedback functions
            def thumbs_up():
                # Update the latest chat entry with positive feedback
                if st.session_state["chat_history"]:
                    st.session_state["chat_history"][-1]["feedback"] = "👍"
                    
                    # Submit feedback to RLHF system with detailed analysis
                    feedback_data = {
                        "entry_id": len(st.session_state["chat_history"]) - 1,
                        "question": question,
                        "response": response_text,
                        "feedback": "positive",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "analysis": {
                            "response_length": len(response_text),
                            "question_type": "informational" if "?" in question else "directive",
                            "contains_links": "http" in response_text,
                            "contains_formatting": "\n" in response_text or "*" in response_text
                        }
                    }
                    submit_rlhf_feedback(user_id, feedback_data)
                    
                    # Update Cloudflare storage
                    chat_histories[session_id] = st.session_state["chat_history"]
                    save_chat_history_cf(user_id, chat_histories)
                    st.rerun()
            
            def thumbs_down():
                # Update the latest chat entry with negative feedback
                if st.session_state["chat_history"]:
                    st.session_state["chat_history"][-1]["feedback"] = "👎"
                    
                    # Submit feedback to RLHF system with detailed analysis
                    feedback_data = {
                        "entry_id": len(st.session_state["chat_history"]) - 1,
                        "question": question,
                        "response": response_text,
                        "feedback": "negative",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "analysis": {
                            "response_length": len(response_text),
                            "question_type": "informational" if "?" in question else "directive",
                            "contains_links": "http" in response_text,
                            "contains_formatting": "\n" in response_text or "*" in response_text
                        }
                    }
                    submit_rlhf_feedback(user_id, feedback_data)
                    
                    # For negative feedback, immediately request an improved response
                    try:
                        improvement_prompt = f"""
                        The user was not satisfied with this response to their question.
                        
                        Question: {question}
                        
                        Response that received negative feedback: {response_text}
                        
                        Please provide an improved response that addresses potential issues with the original.
                        """
                        
                        improved_response = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=[{"role": "user", "content": improvement_prompt}],
                            temperature=0.3,
                            max_tokens=1024,
                        )
                        
                        # Store the improved response for future learning
                        st.session_state["improved_responses"] = st.session_state.get("improved_responses", [])
                        st.session_state["improved_responses"].append({
                            "original_question": question,
                            "original_response": response_text,
                            "improved_response": improved_response.choices[0].message.content,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    except Exception as e:
                        st.warning(f"Failed to generate improved response: {e}")
                    
                    # Update Cloudflare storage
                    chat_histories[session_id] = st.session_state["chat_history"]
                    save_chat_history_cf(user_id, chat_histories)
                    st.rerun()
            
            # Display feedback buttons
            with col1:
                st.button("👍", on_click=thumbs_up, key=f"thumbs_up_{len(st.session_state['chat_history'])}")
            with col2:
                st.button("👎", on_click=thumbs_down, key=f"thumbs_down_{len(st.session_state['chat_history'])}")
        
        # Save to Cloudflare
        chat_histories[session_id] = st.session_state["chat_history"]
        save_chat_history_cf(user_id, chat_histories)
