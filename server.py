from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import time
import webbrowser
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from report_engine import Dataset, build_report, read_upload


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
SESSION_TTL_SECONDS = 2 * 60 * 60
UPLOAD_STORE: dict[str, dict[str, object]] = {}
STORE_LOCK = threading.Lock()


def cleanup_sessions() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    with STORE_LOCK:
        expired = [token for token, value in UPLOAD_STORE.items() if value["created"] < cutoff]
        for token in expired:
            UPLOAD_STORE.pop(token, None)


class ReportHandler(BaseHTTPRequestHandler):
    server_version = "AdReport/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json(self, payload: object, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("업로드 파일 합계는 30MB 이하여야 합니다.")
        return self.rfile.read(length)

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in target.parents and target != STATIC_DIR:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"ok": True, "service": "광고 리포트 자동화"})
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/inspect":
                self._inspect_uploads()
            elif path == "/api/generate":
                self._generate_report()
            else:
                self._error("요청 경로를 찾을 수 없습니다.", 404)
        except ValueError as exc:
            self._error(str(exc), 400)
        except Exception as exc:
            print(f"ERROR: {exc!r}")
            self._error("파일을 처리하는 중 오류가 발생했습니다. 파일 형식과 열 구성을 확인해주세요.", 500)

    def _inspect_uploads(self) -> None:
        cleanup_sessions()
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("업로드 형식이 올바르지 않습니다.")
        body = self._read_body()
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        files: list[tuple[str, bytes]] = []
        for part in message.iter_parts():
            file_name = part.get_filename()
            if file_name:
                files.append((Path(file_name).name, part.get_payload(decode=True) or b""))
        if not files:
            raise ValueError("업로드할 파일을 선택해주세요.")

        datasets: dict[str, Dataset] = {}
        warnings: list[str] = []
        for file_index, (file_name, data) in enumerate(files):
            try:
                for dataset in read_upload(data, file_name, f"f{file_index}"):
                    datasets[dataset.dataset_id] = dataset
            except ValueError as exc:
                warnings.append(f"{file_name}: {exc}")
        if not datasets:
            raise ValueError(warnings[0] if warnings else "읽을 수 있는 데이터가 없습니다.")

        token = secrets.token_urlsafe(18)
        with STORE_LOCK:
            UPLOAD_STORE[token] = {"created": time.time(), "datasets": datasets}
        self._json(
            {
                "ok": True,
                "token": token,
                "datasets": [dataset.public_summary() for dataset in datasets.values()],
                "warnings": warnings,
            }
        )

    def _generate_report(self) -> None:
        body = self._read_body()
        payload = json.loads(body.decode("utf-8"))
        token = payload.get("token")
        with STORE_LOCK:
            session = UPLOAD_STORE.get(token)
        if not session:
            raise ValueError("업로드 세션이 만료되었습니다. 파일을 다시 올려주세요.")
        datasets: dict[str, Dataset] = session["datasets"]  # type: ignore[assignment]
        campaign_id = payload.get("campaignDatasetId")
        product_id = payload.get("productDatasetId")
        if campaign_id not in datasets or product_id not in datasets:
            raise ValueError("사용할 데이터 시트를 선택해주세요.")
        report = build_report(
            datasets[campaign_id],
            datasets[product_id],
            payload.get("campaignMapping") or {},
            payload.get("productMapping") or {},
            payload.get("meta") or {},
        )
        self._json({"ok": True, "report": report})


def open_browser(port: int) -> None:
    time.sleep(0.8)
    webbrowser.open(f"http://127.0.0.1:{port}")


def main() -> None:
    host = "127.0.0.1"
    port = int(os.environ.get("AD_REPORT_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), ReportHandler)
    print("광고 리포트 자동화가 실행되었습니다.")
    print(f"브라우저 주소: http://{host}:{port}")
    print("종료하려면 이 창에서 Ctrl+C를 누르세요.")
    if os.environ.get("AD_REPORT_NO_BROWSER") != "1":
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
