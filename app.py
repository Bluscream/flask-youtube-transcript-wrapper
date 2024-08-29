import os
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, Transcript
from typing import Dict, Any
import time
from functools import wraps
from ipaddress import IPv4Address
from json import dumps

app = Flask(__name__)
RATE_LIMIT = int(os.getenv('RATE_LIMIT', '60'))  # Requests per minute
MAX_VIDEOS = int(os.getenv('MAX_VIDEOS', '100'))
MAX_REQUESTS = RATE_LIMIT * 60  # Total requests per hour

def is_local_ip(ip):
    """Check if the IP address is a local network address."""
    return ip.startswith(('192.168.', '10.')) or IPv4Address(ip).is_loopback
def rate_limited(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip_address = request.remote_addr
        last_request_time = cache.get(ip_address, 0)
        current_time = time.time()

        if not is_local_ip(ip_address):  # Only apply rate limiting to non-local IPs
            if current_time - last_request_time < MAX_REQUESTS / RATE_LIMIT:
                return process({"results": {}, "errors": [f"Rate limit exceeded. Try again later."]}), 429

        cache[ip_address] = current_time
        return f(*args, **kwargs)
    return decorated

def trans_dict(transcript: Transcript):
    return {
        'id': transcript.video_id,
        'language': transcript.language,
        'language_code': transcript.language_code,
        'is_generated': transcript.is_generated,
        'translation_languages': transcript.translation_languages,
        'url': transcript._url,
        'data': transcript.fetch(),
    }

def process(object):
    return jsonify(object) # dumps(dict(iter(object)), indent=True)

cache = {}

@app.route('/', methods=['GET'])
@rate_limited
def get_transcript():
    ret: Dict[str, Any] = {"results": {}, "errors": []}
    try:
        video_ids = request.args.get('videoIds')
        if video_ids: video_ids = video_ids.split(',')
        if not video_ids: video_ids = [request.args.get('videoId')]

        if not video_ids or len(video_ids) < 1: raise Exception("No video IDs provided")
        if len(video_ids) > MAX_VIDEOS: raise Exception("Too many video IDs provided")

        for video_id in video_ids:
            try:
                transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript_dict: Dict[str, Any] = {}
                transcript: Transcript
                for transcript in transcripts:
                    key = transcript.language_code
                    if transcript.is_generated: key += "_generated"
                    transcript_dict[key] = trans_dict(transcript)
                ret["results"][video_id] = transcript_dict
            except Exception as e:
                ret["errors"] += (video_id, str(e))
        
        return process(ret), 200
    
    except Exception as e:
        ret["errors"] += str(e)
        return process(ret), 200

if __name__ == '__main__':
    app.run(debug=True)
