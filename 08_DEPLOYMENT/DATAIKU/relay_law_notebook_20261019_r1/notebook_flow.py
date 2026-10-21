"""Two-stage notebook coordinator around the unchanged, sealed RelayCheck."""
from contextlib import contextmanager
import fcntl


class NotebookRun:
    SCHEMA = "dataiku-relay-law-two-stage-v1"

    def __init__(self, config):
        self.config = dict(config)
        run_id = self.config["run_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            raise ValueError("run_id에는 영문·숫자·밑줄·하이픈만 사용하세요.")
        origin = self.config["relay_origin"].rstrip("/")
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("relay_origin은 https://호스트:포트 형식이어야 합니다.")
        if self.config["law_origin"] not in ("http://www.law.go.kr", "https://www.law.go.kr"):
            raise ValueError("법제처 원본 주소를 확인하세요.")
        if not str(self.config["law_id"]).isdigit() or not self.config["law_name"].strip():
            raise ValueError("법령 ID와 법령명을 확인하세요.")
        self.verify = self.config["ca_bundle"] or True
        if self.config["ca_bundle"] is False or (self.verify is not True and not Path(self.verify).is_file()):
            raise ValueError("ca_bundle은 실제 CA 파일 경로 또는 빈 문자열이어야 합니다.")
        self.url = origin + "/law/DRF"
        self.binding = digest(json_bytes({"config": self.config, "code": NOTEBOOK_CODE_SHA256}))
        self.out = Path(self.config["output_root"]) / run_id
        self.out.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.out / "connection_result.json"
        with self.transaction():
            pass

    def ensure_config(self, config):
        if dict(config) != self.config:
            raise ValueError("설정이 바뀌었습니다. run_id도 바꾼 뒤 1단계부터 실행하세요.")

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(json_bytes(self.state))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    @contextmanager
    def transaction(self):
        with (self.out / "run.lock").open("a") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("같은 run_id가 실행 중입니다. 완료 후 결과를 확인하세요.") from None
            try:
                if self.path.exists():
                    self.state = json.loads(self.path.read_text(encoding="utf-8"))
                    if (self.state.get("schema") != self.SCHEMA or self.state.get("binding") != self.binding):
                        raise ValueError("저장된 실행과 코드·설정이 다릅니다. 기존 기록을 보존하고 run_id를 바꾸세요.")
                    if self.state.get("attempts") not in (0, 1, 2):
                        raise ValueError("저장된 요청 횟수가 올바르지 않습니다.")
                else:
                    self.state = {"schema": self.SCHEMA, "binding": self.binding,
                                  "created_at": time.time(), "deadline": time.time() + 900,
                                  "attempts": 0, "max_attempts": 2, "automatic_retries": 0,
                                  "relay": None, "law": None}
                    self.save()
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def begin(self, stage):
        existing = self.state[stage]
        if existing is not None:
            print("저장된 결과 사용 — 추가 요청 없음:", stage, existing["status"])
            if existing["status"] in ("IN_FLIGHT", "INTERRUPTED"):
                print("이전 요청의 완료 여부가 불명확합니다. 자동으로 다시 호출하지 않습니다.")
            return False
        if time.time() >= self.state["deadline"] or self.state["attempts"] >= 2:
            self.state[stage] = {"status": "BUDGET_EXHAUSTED", "reason": "15분 또는 총 2회 요청 한도"}
            self.save()
            return False
        self.state["attempts"] += 1
        self.state[stage] = {"status": "IN_FLIGHT", "started_at": time.time()}
        self.save()
        return True

    def preflight(self):
        with self.transaction():
            if not self.begin("relay"):
                return self.state["relay"]
            row = self.state["relay"]
            start = time.monotonic()
            session = requests.Session()
            session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            try:
                settings = session.merge_environment_settings(self.url, {}, True, self.verify, None)
                row["proxy_enabled"] = bool(requests.utils.select_proxy(self.url, settings["proxies"]))
                # HEAD has no OC, Cookie, target_url or upstream API parameters.
                with session.request("HEAD", self.url, timeout=(8, 10), verify=self.verify,
                                     allow_redirects=False, stream=True) as response:
                    row.update(status="HTTP_RESPONSE_RECEIVED", http_status=response.status_code,
                               reason="현재 중계 주소/프록시 경로에서 HTTP 응답 수신. 법제처 성공은 2단계에서 확인.")
            except requests.exceptions.SSLError:
                row.update(status="TLS_ERROR", reason="인증서·호스트명·CA를 확인하세요.")
            except requests.exceptions.ConnectTimeout:
                row.update(status="CONNECT_TIMEOUT", reason="중계 연결 단계 시간 초과")
            except requests.exceptions.ReadTimeout:
                row.update(status="READ_TIMEOUT", reason="HTTP 응답 대기 시간 초과")
            except requests.exceptions.Timeout:
                row.update(status="TIMEOUT", reason="연결 또는 응답 시간 초과")
            except requests.exceptions.ConnectionError as exc:
                row.update(status="CONNECTION_ERROR", error_class=type(exc).__name__,
                           reason="주소·포트·실행 노드 네트워크·프록시를 확인하세요.")
            except requests.exceptions.RequestException as exc:
                row.update(status="REQUEST_ERROR", error_class=type(exc).__name__)
            except KeyboardInterrupt:
                row.update(status="INTERRUPTED")
                raise
            except Exception as exc:
                row.update(status="LOCAL_ERROR", error_class=type(exc).__name__)
                raise RuntimeError("통신 확인 중 로컬 오류입니다. 저장된 오류 종류를 확인하세요.") from None
            finally:
                session.close()
                row["elapsed_seconds"] = round(time.monotonic() - start, 3)
                self.save()
            print("1단계:", row["status"], "HTTP", row.get("http_status", "응답 없음"))
            print(row.get("reason", ""))
            return row

    def law_ready(self):
        with self.transaction():
            if self.state["law"] is not None:
                print("2단계는 이미 시도했습니다. 결과 셀에서 저장된 결과를 확인하세요.")
                return False
            if not self.state["relay"] or self.state["relay"]["status"] != "HTTP_RESPONSE_RECEIVED":
                print("먼저 1단계에서 HTTP 응답을 확인하세요. 법제처 요청은 보내지 않았습니다.")
                return False
            if time.time() >= self.state["deadline"] or self.state["attempts"] >= 2:
                print("실행 한도가 끝났습니다. 새 확인이 필요하면 run_id를 바꿔 1단계부터 실행하세요.")
                return False
            return True

    def call_law(self, law_oc, cookie=""):
        # Credential validation occurs before reserving the only upstream attempt.
        if not law_oc.strip() or law_oc.strip().lower() == "test":
            raise ValueError("법제처에 등록된 OC를 입력하세요.")
        if any(c in law_oc + cookie for c in "\r\n"):
            raise ValueError("OC·Cookie에 줄바꿈이 있습니다.")
        with self.transaction():
            if self.state["law"] is not None:
                return self.state["law"]
            if not self.state["relay"] or self.state["relay"]["status"] != "HTTP_RESPONSE_RECEIVED":
                print("중계 HTTP 응답이 확인되지 않아 법제처 요청을 보내지 않았습니다.")
                return None
            if not self.begin("law"):
                return self.state["law"]
            client = None
            try:
                cfg = dict(self.config, mode="relay", output_root=str(self.out / "law_response"))
                client = RelayCheck(cfg, law_oc, cookie=cookie)
                self.state["law"]["receipt_folder"] = str(client.out)
                self.save()
                # Existing sealed transport and XML identity validation, one GET only.
                result = client.request("law_published_body", "lawService.do", "law",
                                        {"ID": str(cfg["law_id"]), "type": "XML"},
                                        "law_body", cfg["law_name"], str(cfg["law_id"]))
                self.state["law"] = dict(result, receipt_folder=str(client.out))
            except KeyboardInterrupt:
                self.state["law"]["status"] = "INTERRUPTED"
                raise
            except Exception as exc:
                self.state["law"].update(status="LOCAL_ERROR", error_class=type(exc).__name__)
                raise RuntimeError("법제처 확인 중 로컬 오류입니다. 기록된 오류 종류와 receipt_folder를 확인하세요.") from None
            finally:
                if client is not None:
                    client.session.close()
                self.save()
            row = self.state["law"]
            print("2단계:", row["status"], "HTTP", row.get("http_status", "응답 없음"))
            if row["status"] == "BODY_OK":
                print("법령명:", row["document_name"], "/ 법령 ID:", row["id"])
                print("조문 블록:", row["article_blocks"], "/ 수신 바이트:", row["received_bytes"])
            else:
                print("법령 본문 수신 성공으로 확인되지 않았습니다:", row.get("reason", row["status"]))
            return row

    def show(self):
        with self.transaction():
            print("단계 | 상태 | HTTP | 시간(초)")
            for name, title in (("relay", "1. 중계 통신"), ("law", "2. 법제처 본문")):
                row = self.state[name] or {"status": "NOT_RUN"}
                print(title, "|", row["status"], "|", row.get("http_status", "-"), "|", row.get("elapsed_seconds", "-"))
            law = self.state["law"] or {}
            if law.get("status") == "BODY_OK":
                print("확인 완료: 중계를 통해 요청한 법령의 XML 본문·ID·이름·조문을 확인했습니다.")
                print("본문 예시:", law.get("sample", ""))
            else:
                print("법제처 본문 확인은 아직 완료되지 않았습니다.")
            print("시도한 HTTP 요청:", self.state["attempts"], "/ 최대 2회")
            print("결과 JSON:", self.path.resolve())
            if law.get("receipt_folder"):
                print("본문/개별 기록:", law["receipt_folder"])
            return self.state
