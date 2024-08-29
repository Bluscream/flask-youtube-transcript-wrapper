import os
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, Transcript
from typing import Dict, Any

app = Flask(__name__)

@app.route('/', methods=['GET'])
def get_transcript():
    try:
        video_ids = request.args.getlist('videoIds')
        
        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400

        ret: Dict[str, Any] = { "results": {}, "errors": {}}

        for video_id in video_ids:
            try:
                transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript_dict: Dict[str, Any] = {}
                transcript: Transcript
                for transcript in transcripts:
                    key = transcript.language_code
                    if transcript.is_generated: key += "_generated"
                    transcript_dict[key] = {
                        "meta": transcript,
                        "script": transcript.fetch()
                    }
                ret[video_id] = transcript_dict
            except Exception as e:
                ret["errors"] += jsonify(str(e))
                
        return jsonify(ret), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True)
