# This runner is appended to the existing validated curl helpers by build_delivery.py.
# PHOTO_INPUTS is inserted from the user's photograph into the private delivery only.

def show_photo_replay(report, path):
    print("사진 샘플 확인 파일:", path.resolve())
    print("상태:", report["status"])
    print("요청:", report["request"]["method"], report["request"]["relay_url"])
    print("target_url:", report["request"]["target_url"])
    print("조회 조건:", report["request"]["params_without_OC"])
    print("사진 OC 포함:", report["request"]["photo_oc_present"])
    print("사진 Cookie 포함:", report["request"]["photo_cookie_present"])
    print("사진 전사값의 문자 단위 일치·현재 세션 유효성: 미검증")
    print("curl:", json.dumps(report.get("curl", {}), ensure_ascii=False))
    print("방화벽 차단 확정:", report["firewall_block_confirmed"])
    print("판정:", report.get("interpretation", "실행이 끝나지 않았습니다. 저장된 상태를 확인하세요."))
    if report["uses_existing_check_folder"]:
        print("저장: 기존 Notebook의 8번 Managed Folder 셀만 실행하면 이 JSON도 저장됩니다.")
    else:
        print("독립 Notebook 결과는 위 로컬 경로에 저장됐습니다. 기존 check/Managed Folder와 자동 연결되지 않습니다.")


def collect_photo_replay(parent=None):
    origin = PHOTO_INPUTS["relay_origin"]
    p = urlsplit(origin)
    if p.scheme != "https" or p.hostname != PHOTO_HOST or p.port != PHOTO_PORT or p.path or p.query or p.username:
        raise ValueError("사진의 개발 중계 주소와 다릅니다. 목적지를 자동 변경하지 않습니다.")
    if PHOTO_INPUTS["target_url"] != "https://opinion.lawmaking.go.kr/rest/ptcpAdmPp.xml":
        raise ValueError("사진의 target_url과 다릅니다.")
    if PHOTO_INPUTS["method"] != "GET":
        raise ValueError("사진 샘플은 GET 요청입니다.")
    if parent is not None:
        if parent.mode != "relay" or parent.origin != origin:
            raise ValueError("기존 Notebook의 중계 환경이 사진과 다릅니다.")
        out = Path(parent.out)
    else:
        out = Path("law_api_photo_replay_20261015_r1")
        out.mkdir(exist_ok=True, mode=0o700)
    path = out / "photo_sample_replay_r1.json"
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        print("저장된 결과입니다. 값을 바꿔도 같은 폴더에서는 추가 호출하지 않습니다.")
        show_photo_replay(report, path)
        return report
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("Dataiku 실행 환경에 curl이 없습니다. 네트워크 호출 전 중단합니다.")
    oc = PHOTO_INPUTS["OC"]
    cookie = PHOTO_INPUTS["Cookie"]
    if not oc or not cookie or "JSESSIONID=" not in cookie or "elevisor_for_j2ee_uid=" not in cookie:
        raise ValueError("사진 OC와 두 Cookie 값이 채워진 원본 실행 TXT를 사용하세요.")
    for value in (oc, cookie):
        evidence_config_value(value)
    session = parent.session if parent is not None else requests.Session()
    try:
        settings = session.merge_environment_settings(origin + "/law/making", {}, True,
                                                      parent.verify if parent is not None else True, None)
    finally:
        if parent is None:
            session.close()
    proxy = requests.utils.select_proxy(origin + "/law/making", settings["proxies"]) or ""
    ca = settings["verify"]
    if ca is False or (isinstance(ca, str) and not Path(ca).is_file()):
        raise ValueError("TLS CA 설정을 확인하세요. 인증서 검증을 끄지 않습니다.")
    evidence_config_value(proxy)
    version = subprocess.run([curl, "--disable", "--version"], capture_output=True, timeout=5, check=False)
    report = {
        "schema": "dataiku-photo-sample-replay-v1", "status": "PREPARED", "started": evidence_clock(),
        "hostname": socket.gethostname(), "parent_run_id": getattr(parent, "run_id", None),
        "parent_calls_preserved": getattr(parent, "calls", None), "uses_existing_check_folder": parent is not None,
        "physical_curl_attempts": 0, "max_curl_attempts": 1, "automatic_retries": 0,
        "firewall_block_confirmed": False, "legal_data_success": False,
        "photo_transcription_byte_identity_verified": False, "photo_credentials_current_validity": "UNKNOWN",
        "curl_version": version.stdout.decode("utf-8", "replace").splitlines()[:1],
        "proxy_enabled": bool(proxy), "existing_network_evidence_present": (out / "network_evidence_r1.json").exists(),
        "request": {"method": "GET", "relay_url": origin + "/law/making", "target_url": PHOTO_TARGET,
                    "params_without_OC": PHOTO_PARAMS, "photo_oc_present": True, "photo_cookie_present": True,
                    "credential_values_saved_in_report": False},
        "differences_from_photo": ["한글 검색어 URL 인코딩; 의미 동일", "연결 8초/전체 20초 한도와 자동 재시도 0",
                                   "--location 포함, --max-redirs 0으로 최초 응답 뒤 추가 요청 중단",
                                   ".curlrc 미사용, 실효 프록시/CA 명시, 응답 본문 저장 안 함"],
        "credential_source": "User explicitly requested all original photographed sample inputs, including OC and Cookie",
    }
    def save():
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    path.chmod(0o600)
    try:
        report.update(status="CURL_IN_FLIGHT", physical_curl_attempts=1)
        save()
        report["curl"] = evidence_curl(curl, origin, oc, cookie, proxy, ca)
        report["status"] = "EVIDENCE_COLLECTED"
        status = report["curl"]["status"]
        if status == "CURL_CONNECT_PHASE_TIMEOUT":
            report["interpretation"] = "사진 OC/Cookie를 포함한 요청도 연결 단계 시간초과. HTTP 응답 없음. Cookie 오류 판정이 아니라 네트워크/서버 경로 확인 대상. 방화벽 로그와 대조 필요."
        elif status.startswith("HTTP_RESPONSE_"):
            report["interpretation"] = "이번 경로에서 HTTP 응답 수신. 상태 코드와 응답 주체를 확인해야 하며, 인증/예고 데이터 수신 성공은 아직 미확인."
        else:
            report["interpretation"] = "curl 상태·종료코드·연결 시간을 확인. 전송 실패를 인증 오류나 방화벽 차단 확정으로 해석하지 않음."
    except KeyboardInterrupt:
        report["status"] = "INTERRUPTED_NO_AUTORETRY"
        raise
    except Exception as exc:
        report.update(status="DIAGNOSTIC_ERROR_NO_AUTORETRY", exception_class=type(exc).__name__,
                      error=evidence_scrub(str(exc), (oc, cookie, proxy))[:800])
        raise RuntimeError("사진 샘플 진단 중 오류가 발생했습니다. 비밀값을 제외한 오류와 상태는 결과 JSON에 저장됩니다.") from None
    finally:
        report["ended"] = evidence_clock()
        save()
    show_photo_replay(report, path)
    return report


_photo_replay_result = collect_photo_replay(globals().get("check"))
