from __future__ import annotations

import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class _AssetHandler(BaseHTTPRequestHandler):
    assets: Path
    documents: dict[str, bytes]
    document_lock: threading.Lock

    def log_message(self, *_):
        pass

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Accept-Ranges','bytes')
        super().end_headers()

    def do_HEAD(self):
        self._serve(send_body=False)

    def do_GET(self):
        self._serve(send_body=True)

    def _serve(self,send_body):
        name=Path(unquote(urlsplit(self.path).path).lstrip('/')).name
        with self.document_lock:
            document = self.documents.get(name)
        if document is not None:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(document)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if send_body:
                try:
                    self.wfile.write(document)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # The user switched flights before loading finished.
            return
        path=(self.assets/name).resolve()
        if path.parent!=self.assets.resolve() or not path.is_file():
            self.send_error(404); return
        size=path.stat().st_size; start,end=0,size-1; status=200
        match=re.match(r'bytes=(\d*)-(\d*)',self.headers.get('Range',''))
        if match:
            if match.group(1):start=int(match.group(1))
            if match.group(2):end=min(int(match.group(2)),size-1)
            if start>=size or start>end:
                self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
            status=206
        length=end-start+1
        self.send_response(status)
        self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(length))
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if not send_body:return
        with path.open('rb') as source:
            source.seek(start); remaining=length
            while remaining:
                chunk=source.read(min(1024*256,remaining))
                if not chunk:break
                self.wfile.write(chunk); remaining-=len(chunk)


class MapAssetServer:
    def __init__(self,assets):
        assets=Path(assets).resolve()
        self.documents = {}
        self.document_lock = threading.Lock()
        handler=type('HELINKAssetHandler',(_AssetHandler,),{
            'assets': assets,
            'documents': self.documents,
            'document_lock': self.document_lock,
        })
        self.httpd=ThreadingHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.httpd.serve_forever,name='HELINK offline map',daemon=True)
        self.thread.start(); self.base_url=f'http://127.0.0.1:{self.httpd.server_port}/'

    def set_document(self, name: str, html: str) -> str:
        """Serve route HTML locally without WebEngine's setHtml size limit."""
        with self.document_lock:
            self.documents[name] = html.encode('utf-8')
        return self.base_url + name

    def remove_document(self, name: str):
        with self.document_lock:
            self.documents.pop(name, None)


_server=None
_lock=threading.Lock()

def get_map_server(assets):
    global _server
    with _lock:
        if _server is None:_server=MapAssetServer(assets)
    return _server
