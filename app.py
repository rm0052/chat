import streamlit as st
from serpapi import GoogleSearch
from bs4 import BeautifulSoup
import asyncio
import httpx
from google import genai

# Initialize Google GenAI client
client = genai.Client(api_key="AIzaSyDFbnYmLQ1Q55jIYYmgQ83sxledB_MgTbw")

# Streamlit App
st.title("Chatbot")

# User Input: Question
question = st.text_input("Enter your question")
# Search Button
if st.button("Get Answer"):
    with st.spinner("Running..."):
        # SerpAPI search
        params = {
            "engine": "google",
            "q": question,
            "api_key": "your-serpapi-key",
            "num": 30,  # Limit the number of results
        }

        @st.cache_data
        def get_search_results():
            search = GoogleSearch(params)
            return search.get_dict()

        results = get_search_results()
        filtered_links = [
            result["link"] for result in results.get("organic_results", [])
        ]

        # Fetch articles asynchronously
        async def fetch_article(link):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(link, timeout=10)
                    soup = BeautifulSoup(response.text, "html.parser")
                    paragraphs = soup.find_all("p")
                    return "\n".join(p.get_text(strip=True) for p in paragraphs)[:500]
            except:
                return ""

        async def fetch_all_articles(links):
            tasks = [fetch_article(link) for link in links]
            return await asyncio.gather(*tasks)

        context = ""
        fetched_articles = asyncio.run(fetch_all_articles(filtered_links))
        for article in fetched_articles:
            context += " " + article
            if len(context) >= 2000:
                break

        # Generate Response with Gemini 1.5 Flash
        prompt = f"Answer only yes or no if the context is useful in answering the question: {question}. Context: {context}"
        response = client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt
        )
        answer = response.text.strip()

        # Follow-up Question
        final_prompt = (
            f"Answer the question: {question}. Context: {context}"
            if answer.lower() == "yes"
            else f"Answer the question using your own knowledge: {question}."
        )
        final_response = client.models.generate_content(
            model="gemini-1.5-flash", contents=final_prompt
        )
    st.write(final_response.text)
