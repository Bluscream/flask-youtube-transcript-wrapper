# app.py

from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, Transcript

app = Flask(__name__)

@app.route('/', methods=['GET'])
def get_transcript():
    video_ids = request.args.get('videoIds', '').split(',')
    ret = {}
    try:
        for video_id in video_ids:
            ret[video_id] = {}
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript: Transcript
            for transcript in transcripts:
                key = transcript.language_code
                if transcript.is_generated: key += "_generated"
                ret[video_id][key] = {
                    "meta": transcript,
                    "script": transcript.fetch()
                }
            
        return jsonify(ret), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
