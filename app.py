import streamlit as st
from serpapi import GoogleSearch
from bs4 import BeautifulSoup
import requests
import time
import os
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi 
# import youtube
# Initialize Google GenAI client
def get_youtube_subtitles(video_url): 
    """Fetch subtitles from a YouTube video.""" 
    video_id = video_url.split("v=")[-1]  
    # Extract video ID from URL 
    try: 
        transcript = YouTubeTranscriptApi.get_transcript(video_id) 
        subtitles = "\n".join([entry["text"] for entry in transcript]) 
        return subtitles 
    except Exception as e: 
        return f"Error: {e}"
        
client = genai.Client(api_key="AIzaSyDFbnYmLQ1Q55jIYYmgQ83sxledB_MgTbw")

# Streamlit App
st.title("Chatbot")


# User Input: Question
question = st.text_input("Enter your question")

# Search Button
if st.button("Get Answer") and question:
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
        filtered_links = [
            result["link"] for result in results.get("organic_results", [])
        ]

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
        response = client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt
        )
        answer = response.text.strip()

        # Follow-up Question
        if answer.lower() == "yes":
            final_prompt = f"Answer the question: {question}. Context: {context}"
        else:
            final_prompt = f"Answer the question using your own knowledge: {question}."

        final_response = client.models.generate_content(
            model="gemini-1.5-flash", contents=final_prompt
        )

    st.write(final_response.text.replace("$", "\\$").replace("provided text", "available information"))
