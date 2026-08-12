"""StructuredLogger icin birim testleri (Roadmap M9.5, TDD Section 19/24).

TDD Section 19 "Loglama Stratejisi": yapilandirilmis (JSON) dosya loglari,
her satirda `{timestamp, account_id, run_id, stage, level, message, extra}`
alanlarini tasir; log seviyesi esiklemesi (INFO/WARNING/ERROR) ve secret
redaksiyonu (Section 24: yalnizca V1'in iki bilinen secret sinifi - API key,
session token/storage_state) bu modulun kendi sorumlulugudur.

Kullanicinin acikca talep ettigi uc davranis burada test edilir:
1. StructuredLogger, Orchestrator'a bagimli olmayan, bagimsiz kullanilabilir
   bir servistir (bu dosya HICBIR orchestrator/domain modulunu import etmez -
   bu, "yeniden tasarim gerektirmeden baska modullerin de kullanabilecegi"
   gereksiniminin dogrudan kaniti).
2. Dosya loglama best-effort'tur: ne kurulum ne de tekil bir log cagrisi
   HICBIR ZAMAN bir istisna firlatir (izin hatasi, eksik dizin, kapali
   stream vb. - hicbiri cagiran is mantigina sizmaz).
3. Secret redaksiyonu buyuk/kucuk harf DUYARSIZDIR (Api_Key, API_KEY,
   api_key hepsi ayni sekilde redakte edilir).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from linkedinbot.logging.structured_logger import StructuredLogger

ACCOUNT_ID = uuid4()
RUN_ID = uuid4()


def _read_lines(log_file_path):
    return [json.loads(line) for line in log_file_path.read_text(encoding="utf-8").splitlines()]


def test_info_writes_a_json_line_with_all_required_fields(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")

    logger.info(
        account_id=ACCOUNT_ID,
        run_id=RUN_ID,
        stage="Collection",
        message="5 ilan toplandi.",
        extra={"jobs_collected": 5},
    )

    lines = _read_lines(log_file)
    assert len(lines) == 1
    record = lines[0]
    assert record["account_id"] == str(ACCOUNT_ID)
    assert record["run_id"] == str(RUN_ID)
    assert record["stage"] == "Collection"
    assert record["level"] == "INFO"
    assert record["message"] == "5 ilan toplandi."
    assert record["extra"] == {"jobs_collected": 5}
    assert "timestamp" in record


def test_warning_and_error_write_correct_level_field(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")

    logger.warning(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Collection", message="kismi sonuc")
    logger.error(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Run", message="basarisiz")

    lines = _read_lines(log_file)
    assert [line["level"] for line in lines] == ["WARNING", "ERROR"]


def test_extra_defaults_to_empty_dict_when_not_provided(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")

    logger.info(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Collection", message="msg")

    lines = _read_lines(log_file)
    assert lines[0]["extra"] == {}


@pytest.mark.parametrize(
    "field_name", ["api_key", "API_KEY", "Api_Key", "session_token", "STORAGE_STATE"]
)
def test_redaction_replaces_known_secret_field_values_case_insensitively(tmp_path, field_name):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")

    logger.error(
        account_id=ACCOUNT_ID,
        run_id=RUN_ID,
        stage="Session Validation",
        message="oturum hatasi",
        extra={field_name: "sk-deliberately-invalid-secret-12345"},
    )

    raw_content = log_file.read_text(encoding="utf-8")
    assert "sk-deliberately-invalid-secret-12345" not in raw_content
    record = _read_lines(log_file)[0]
    assert record["extra"][field_name] == "[REDACTED]"


def test_redaction_does_not_affect_unknown_field_names(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")

    logger.info(
        account_id=ACCOUNT_ID,
        run_id=RUN_ID,
        stage="Collection",
        message="msg",
        extra={"jobs_collected": 5, "partial_reason": "devre kesici tetiklendi"},
    )

    record = _read_lines(log_file)[0]
    assert record["extra"] == {"jobs_collected": 5, "partial_reason": "devre kesici tetiklendi"}


def test_level_filtering_suppresses_calls_below_configured_level(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="ERROR")

    logger.info(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Collection", message="ignored")
    logger.warning(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Collection", message="ignored")
    logger.error(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Run", message="kept")

    lines = _read_lines(log_file)
    assert len(lines) == 1
    assert lines[0]["message"] == "kept"


def test_rotation_handler_configured_with_given_max_bytes_and_backup_count(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO", max_bytes=1024, backup_count=3)

    assert logger._handler is not None
    assert logger._handler.maxBytes == 1024
    assert logger._handler.backupCount == 3


def test_construction_with_an_unrecognized_level_does_not_raise(tmp_path):
    # Production bug (independent review): `.env.example` cites TDD Section
    # 19 as its authority and documents LOG_LEVEL as DEBUG|INFO|WARNING|ERROR
    # - but TDD Section 19 itself defines EXACTLY three levels (INFO/WARNING/
    # ERROR), and this class's own docstring instructs callers to pass
    # LOG_LEVEL straight through as `level`. Before this fix, ANY string
    # outside {"INFO", "WARNING", "ERROR"} (starting with the documented
    # "DEBUG") raised KeyError DURING CONSTRUCTION - before the best-effort
    # protection established later in __init__ (the try/except around file
    # setup) even applies. The best-effort contract ("a logging failure must
    # never fail the business pipeline") is violated at its very first line.
    log_file = tmp_path / "app.jsonl"

    StructuredLogger(log_file_path=log_file, level="DEBUG")
    logger = StructuredLogger(log_file_path=log_file, level="totally-invalid-value")

    # Taninmayan deger, sessizce HER SEYI yutan bir logger'a DEGIL, GUVENLI
    # bir varsayilana (INFO) duser - INFO seviyesindeki bir cagri hala
    # dosyaya yazilmalidir.
    logger.info(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Collection", message="hala calisir")
    lines = _read_lines(log_file)
    assert lines[-1]["message"] == "hala calisir"


def test_construction_with_unwritable_parent_path_does_not_raise(tmp_path):
    # `tmp_path/"not_a_directory"` bir DOSYA olarak olusturulur - bu yuzden
    # onun ALTINDA bir log dosyasi icin dizin olusturmak (mkdir) KESIN
    # basarisiz olur (ENOTDIR). Best-effort sozlesmesi: kurulum YINE DE
    # istisna firlatmaz, logger sessizce no-op olur.
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("bu bir dosyadir, dizin degil")
    unwritable_log_file = blocking_file / "app.jsonl"

    logger = StructuredLogger(log_file_path=unwritable_log_file, level="INFO")

    logger.error(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Run", message="bu asla firlatmamali")


def test_log_call_does_not_raise_when_underlying_stream_is_closed(tmp_path):
    log_file = tmp_path / "app.jsonl"
    logger = StructuredLogger(log_file_path=log_file, level="INFO")
    logger._handler.close()

    logger.error(account_id=ACCOUNT_ID, run_id=RUN_ID, stage="Run", message="bu da firlatmamali")


def test_structured_logger_module_has_no_orchestrator_or_domain_dependency():
    # Kullanicinin acikca talep ettigi mimari ozellik: StructuredLogger,
    # Orchestrator'a (veya herhangi bir domain/pipeline modulune) bagimli
    # OLMAYAN, yeniden tasarim gerektirmeden baska modullerin de (orn.
    # retry/recovery loglama) kullanabilecegi bagimsiz bir servistir.
    import ast
    from pathlib import Path

    # `Path(__file__)`'e gore (cwd'ye DEGIL) - projenin kendi yerlesik
    # deseni (bkz. tests/integration/filtering/test_department_filter_live.py
    # `_REPO_ROOT`) - testin pytest'in HANGI dizinden cagrildigina bagli
    # olmamasi icin.
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "src/linkedinbot/logging/structured_logger.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    forbidden_prefixes = ("linkedinbot.run", "linkedinbot.domain", "linkedinbot.db")
    violations = [
        module
        for module in imported_modules
        if module.startswith("linkedinbot.") and module.startswith(forbidden_prefixes)
    ]
    assert violations == []
