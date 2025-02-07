import streamlit as st
from serpapi import GoogleSearch
from bs4 import BeautifulSoup
import requests
import time
import os
from google import genai
import youtube

# Initialize Google GenAI client
API_KEY = "AIzaSyB_Z2Idk40FQtTxz-OC443vcGS5KHpI8Q4"
client = genai.Client(api_key=API_KEY)

# Streamlit App
st.title("Chatbot")

# User Input: Question
question = st.text_input("Enter your question")

# Search Button
if st.button("Get Answer") and question:
    with st.spinner("Running..."):
        try:
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
                        context += " " + youtube.get_youtube_subtitles(link)[:500]
                    else:
                        response = requests.get(link, timeout=10)
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, "html.parser")
                            paragraphs = soup.find_all("p")
                            article_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
                            context += " " + article_text[:500]
                except Exception as e:
                    st.warning(f"Skipping link due to error: {e}")
                    continue

                if len(context) >= 2000:
                    break

            # Generate Response with Gemini 1.5 Pro
            prompt = f"Answer only yes or no if the context is useful in answering the question: {question}. Context: {context}"
            
            try:
                response = client.models.generate_content(
                    model="gemini-1.5-pro", contents=prompt
                )
                answer = response.text.strip()
            except Exception as e:
                st.error(f"Error generating response from Gemini: {e}")
                answer = "no"

            # Follow-up Question
            if answer.lower() == "yes":
                final_prompt = f"Answer the question: {question}. Context: {context}"
            else:
                final_prompt = f"Answer the question using your own knowledge: {question}."

            try:
                final_response = client.models.generate_content(
                    model="gemini-1.5-pro", contents=final_prompt
                )
                st.write(final_response.text.replace("$", "\\$").replace("provided text", "available information"))
            except Exception as e:
                st.error(f"Error generating final response: {e}")

        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
