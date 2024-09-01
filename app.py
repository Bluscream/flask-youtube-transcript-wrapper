import os
from flask import Flask, request, jsonify, Response
from typing import Dict, Any
import time
from functools import wraps
from ipaddress import IPv4Address
from json import dumps

from youtube_transcript_api import YouTubeTranscriptApi, Transcript
from youtube_transcript_api.formatters import TextFormatter, JSONFormatter, WebVTTFormatter, SRTFormatter, Formatter
from youtube_transcript_api._errors import NoTranscriptFound

RATE_LIMIT = int(os.getenv('RATE_LIMIT', '60'))  # Requests per minute
MAX_VIDEOS = int(os.getenv('MAX_VIDEOS', '100'))
MAX_REQUESTS = RATE_LIMIT * 60  # Total requests per hour

app = Flask(__name__)

formatters: dict[str, Formatter] = {
    'json': JSONFormatter(),
    'txt': TextFormatter(),
    'vtt': WebVTTFormatter(),
    'srt': SRTFormatter()
}

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

def trans_dict(transcript: Transcript, formats: list[str]):
    ret = {
        # 'id': transcript.video_id,
        # 'language': transcript.language,
        'language_code': transcript.language_code,
        'is_generated': transcript.is_generated,
        'is_translatable': transcript.is_translatable,
        # 'translation_languages': transcript.translation_languages,
        'url': f"https://ytapi.minopia.de/transcript?videoId={transcript.video_id}&lang={transcript.language_code}",
        '_url': transcript._url,
        'content': {}
    }
    if len(formats) > 0:
        raw = transcript.fetch()
        if 'raw' in formats: ret["content"]['raw'] = raw
        for name, fmt in formatters.items():
            fmted = str(fmt.format_transcript(raw))
            if name in formats: ret["content"][fmt] = fmted

    return ret

def process(object):
    return jsonify(object) # dumps(dict(iter(object)), indent=True)

def add_transcript(transcript_dict: dict[str, object], video_id: str, transcript: Transcript, formats: list[str]):
    ret = { transcript.language: trans_dict(transcript, formats) }
    # print("added transcript",transcript.language)
    transcript_dict.update(ret) # [transcript.language.title()] = trans_dict(transcript)
    return ret

def add_video(ret_dict: dict, video_id: str, formats: list[str], translate_langs: list[tuple[str,str]] = [("English", "en")], translate_force: bool = False):
    transcripts = list(YouTubeTranscriptApi.list_transcripts(video_id))
    # print("Got list of",len(transcripts),"transcripts")
    transcript_dict: Dict[str, Any] = {}
    transcript: Transcript
    for transcript in transcripts:
        add_transcript(transcript_dict, video_id, transcript, formats)
    for name, code in translate_langs:
        if translate_force or not name in transcript_dict.keys():
            first: Transcript = transcripts[0]
            # print("Want translation! First", first.language,"is translatable:",first.is_translatable)
            if first.is_translatable:
                translated = first.translate(code)
                add_transcript(transcript_dict, video_id, translated, formats)
    # print(len(transcript_dict))
    if ret_dict: ret_dict["results"][video_id] = transcript_dict
    return transcript_dict

cache = {}

def FileResponse(content: str, status:int, mimetype:str, filename:str):
    resp = Response(content, status=status, mimetype=mimetype)
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    resp.headers["x-filename"] = filename
    resp.headers["Access-Control-Expose-Headers"] = 'x-filename'
    return resp

def get_transcript(_video_id: str, _lang: str, _format: str):
    # print("want get_transcript", _video_id, _lang, _format)
    transcript: Transcript
    try: transcript = YouTubeTranscriptApi.get_transcript(_video_id, [_lang])
    except NoTranscriptFound as ex: transcript = list(YouTubeTranscriptApi.list_transcripts(_video_id))[0].translate(_lang).fetch()
    # # print(transcript)
    filename = f"{_video_id} - {_lang}.{_format}"
    match _format:
        case "raw": return jsonify(transcript.fetch()), 200
        case "json": return FileResponse(formatters["json"].format_transcript(transcript), 200, "application/json", filename)
        case "srt": return FileResponse(formatters["srt"].format_transcript(transcript), 200, "application/x-subrip", filename)
        case "vtt": return FileResponse(formatters["vtt"].format_transcript(transcript), 200, "text/vtt", filename)
        case "txt": return FileResponse(formatters["txt"].format_transcript(transcript), 200, "text/plain", filename)
    return "unknown format", 400

@app.route('/', methods=['GET'])
@rate_limited
def get_transcripts():
    ret: Dict[str, Any] = {"results": {}, "errors": []}
    
    # try:
    _video_ids = request.args.get('videoIds', "")
    _video_id = request.args.get('videoId')
    _formats = request.args.get('formats', "")
    _format = request.args.get('format')
    _lang = request.args.get('lang')
    raw = request.args.get('raw', "")
    # print(raw)
    if raw:
        if _video_id and _format:
            # print("want raw", _video_id, _lang, _format)
            return get_transcript(_video_id, _lang, _format) # type: ignore
        else:
            raise Exception("Need videoId and format in raw mode!")

    if _video_ids: _video_ids = _video_ids.split(',')
    if not _video_ids and _video_id: _video_ids = [_video_id]

    if _formats: _formats = _formats.split(',')
    if not _formats and _format: _formats = [request.args.get('format')]
    if not _formats: _formats = [formatters.keys()]

    if not _video_ids or len(_video_ids) < 1: raise Exception("No video IDs provided")
    if len(_video_ids) > MAX_VIDEOS: raise Exception("Too many video IDs provided")

    for video_id in _video_ids:
        # print(video_id)
        # try:
        add_video(ret, video_id, _formats) # type: ignore
        # print(video_id)
        # except Exception as e:
        #     # print("error", video_id, e)
        #     ret["errors"] += {video_id: str(e)}
        
    return process(ret), 200
    
    # except Exception as e:
    #     # print("error", e)
    #     ret["errors"] += {str(e): ""}
    #     return process(ret), 200
# endregion flask

if __name__ == '__main__':
    app.run(debug=True,host="0.0.0.0",port=5001)
