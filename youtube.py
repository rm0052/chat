from youtube_transcript_api import YouTubeTranscriptApi

def get_youtube_subtitles(video_url):
    """Fetch subtitles from a YouTube video."""
    video_id = video_url.split("v=")[-1]  # Extract video ID from URL
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        subtitles = "\n".join([entry["text"] for entry in transcript])
        return subtitles
    except Exception as e:
        return f"Error: {e}"
