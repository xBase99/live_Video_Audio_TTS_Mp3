import asyncio
import io
import json
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import edge_tts

VOICES = {
    'ko': {'female': 'ko-KR-SunHiNeural', 'male': 'ko-KR-InJoonNeural'},
    'en': {'female': 'en-US-JennyNeural', 'male': 'en-US-GuyNeural'},
}

# Separate Korean Hangul and English letters while keeping punctuation and spaces.
TOKEN = re.compile(r'[가-힣]+|[A-Za-z]+|[^가-힣A-Za-z]+')

def split_languages(text):
    parts = []
    current_lang = None
    for token in TOKEN.findall(text):
        lang = 'ko' if re.search(r'[가-힣]', token) else 'en' if re.search(r'[A-Za-z]', token) else None
        if lang is None:
            if parts:
                parts[-1][1] += token
            else:
                parts.append(['', token])
        elif parts and (current_lang == lang or parts[-1][0] == ''):
            parts[-1][0] = lang
            parts[-1][1] += token
        else:
            parts.append([lang, token])
        if lang:
            current_lang = lang
    return [(lang or 'ko', chunk) for lang, chunk in parts if chunk.strip()]

async def synthesize(text, language, gender, rate):
    segments = split_languages(text) if language == 'auto' else [(('ko' if language == 'ko-KR' else 'en'), text)]
    if len(segments) > 100:
        raise ValueError('언어 전환이 너무 많습니다. 문서를 나누어 주세요.')
    # pydub decodes each MP3 and joins PCM, avoiding corrupted MP3 concatenation.
    from pydub import AudioSegment
    combined = AudioSegment.empty()
    for lang, phrase in segments:
        voice = VOICES[lang][gender]
        audio = bytearray()
        async for item in edge_tts.Communicate(phrase, voice=voice, rate=rate).stream():
            if item['type'] == 'audio':
                audio.extend(item['data'])
        if not audio:
            raise RuntimeError('TTS 서버에서 음성을 받지 못했습니다.')
        combined += AudioSegment.from_file(io.BytesIO(audio), format='mp3')
    output = io.BytesIO()
    combined.export(output, format='mp3', bitrate='128k')
    return output.getvalue()

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path != '/tts':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 30000:
                raise ValueError('요청 크기가 올바르지 않습니다.')
            data = json.loads(self.rfile.read(length))
            text = str(data.get('text', '')).strip()
            if not 1 <= len(text) <= 5000:
                raise ValueError('1~5000자의 텍스트를 입력하세요.')
            language = data.get('language', 'auto')
            gender = data.get('gender', 'female')
            rate = data.get('rate', '+0%')
            if language not in ('auto', 'ko-KR', 'en-US') or gender not in ('female', 'male') or rate not in ('-20%', '+0%', '+20%'):
                raise ValueError('지원하지 않는 음성 설정입니다.')
            result = asyncio.run(synthesize(text, language, gender, rate))
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result)
        except Exception as e:
            body = str(e).encode('utf-8')
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

if __name__ == '__main__':
    print('Evergreen26 multilingual TTS server: http://127.0.0.1:8765')
    print('Keep this window open. Ctrl+C to stop.')
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
