"""StructuredLogger - yapilandirilmis (JSON) dosya loglama + secret
redaksiyonu (Roadmap M9.5, TDD Section 19/24).

TDD Section 19 "Loglama Stratejisi" iki AYRI log hedefi tanimlar: bu modul
YALNIZCA birincisini (yapilandirilmis JSON dosya loglari) uygular -
`run_logs` DB tablosu (FR-15/NFR-10'un gercek, kalici gozlemlenebilirlik
sozlesmesi) zaten M1.1-M9.4'te kurulmustur ve bu modulun kapsami DISINDADIR.
Her satir `{timestamp, account_id, run_id, stage, level, message, extra}`
alanlarini tasir (TDD Section 19'un birebir alan listesi).

**Bagimsiz, capraz-kesen bir servistir (TDD Section 7 "yatay kesen katman":
"yukaridaki her kutu bu uce bagimli olabilir" - Config Service, Secrets
Provider, Structured Logger):** Bu modulun `linkedinbot.run`/`linkedinbot.domain`/
`linkedinbot.db` gibi HICBIR pipeline/orchestration modulune bagimliligi
YOKTUR (module sorumluluk tablosunun "Bagimli Oldugu Port(lar): —" satiriyla
tutarli). Bu, M9.5'in birincil entegrasyon noktasi Run Orchestrator olsa da
(kullanici talimati), gelecekte baska modullerin (orn. collection/collector.py'nin
retry/recovery loglamasi) bu servisi YENIDEN TASARIM GEREKTIRMEDEN
kullanabilmesini saglar.

**Best-effort sozlesmesi (kullanici talimati, acikca onaylandi):** Bir log
dosyasina yazma HATASI (izin, eksik dizin, disk dolu, kapali stream vb.)
HICBIR ZAMAN cagiran is mantigina sizmaz - ne kurulum (`__init__`) ne de
tekil bir `.info()/.warning()/.error()` cagrisi istisna firlatir. Kurulum
basarisiz olursa logger sessizce no-op'a duser (hicbir handler eklenmez);
bu, `logging.lastResort`'un stderr'e sizmasini da onlemek icin acikca bir
`NullHandler` eklenerek saglanir.

**Secret redaksiyonu (Section 24 "Kapsam": V1'de yalnizca IKI secret sinifi
vardir - LLM API anahtari, LinkedIn oturum durumu/Playwright `storage_state`):**
`extra` sozlugundeki BILINEN alan adlari (kullanici talimati: BUYUK/KUCUK
HARF DUYARSIZ karsilastirilir) `[REDACTED]` ile degistirilir. Bu bir metin
tarama/DLP mekanizmasi DEGILDIR - yalnizca `extra`'nin YAPISAL anahtarlarini
kontrol eder (TDD'nin "bilinen secret ALAN ADLARINI" ifadesinin birebir
karsiligi).

**Neden `logging.Logger`'in global `getLogger()` kayit defteri KULLANILMAZ:**
Bu proje test'lerin AYRI, sizdirmayan durumlar gerektirdigi bir desen
kurmustur (orn. M9.4'un `sleep: Callable` enjeksiyon deseni). Global
`logging.getLogger(name)` kayit defteri sureç-capinda paylasilan bir
durumdur - testler arasi handler sizintisina yol acabilir. Bunun yerine
her `StructuredLogger` ornegi KENDI, kayit-defterine hic KATILMAMIS
`logging.Logger` nesnesini olusturur (`propagate=False` ile).
"""

from __future__ import annotations

import json
import logging as _stdlib_logging
from collections.abc import Mapping
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import UUID

_DEFAULT_LOG_FILE_PATH = Path("logs/linkedinbot.jsonl")
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5

_REDACTED_VALUE = "[REDACTED]"

# TDD Section 24 "Kapsam": V1'de yalnizca iki secret sinifi vardir - LLM
# saglayici API anahtari, LinkedIn oturum durumu (Playwright storage_state).
# Bu liste KASITLI OLARAK kucuktur ve dogrudan bu iki sinifa baglidir -
# spekulatif/tahmini alan adlari eklenmez.
_SECRET_FIELD_NAMES = frozenset({"api_key", "session_token", "storage_state"})

_LEVEL_ORDER = {
    "INFO": _stdlib_logging.INFO,
    "WARNING": _stdlib_logging.WARNING,
    "ERROR": _stdlib_logging.ERROR,
}


class _PassthroughFormatter(_stdlib_logging.Formatter):
    """Kayit mesaji ZATEN tam bicimlendirilmis JSON'dur - stdlib'in kendi
    zaman damgasi/seviye onekleme davranisini devre disi birakir."""

    def format(self, record: _stdlib_logging.LogRecord) -> str:
        return record.getMessage()


def _redact(extra: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (_REDACTED_VALUE if key.lower() in _SECRET_FIELD_NAMES else value)
        for key, value in extra.items()
    }


class StructuredLogger:
    """TDD Section 19'un yapilandirilmis JSON dosya log hedefinin somut
    uygulamasi. `level`, TDD Section 23 geregi (env var yalnizca altyapi
    ayarlari icindir - DB URL, log seviyesi) cagiran tarafindan
    `LOG_LEVEL` ortam degiskeninden okunup gecirilir; bu modulun kendisi
    ortam degiskenlerini OKUMAZ (saf, enjekte-edilebilir parametreler)."""

    def __init__(
        self,
        log_file_path: Path | str = _DEFAULT_LOG_FILE_PATH,
        level: str = "INFO",
        max_bytes: int = _DEFAULT_MAX_BYTES,
        backup_count: int = _DEFAULT_BACKUP_COUNT,
    ) -> None:
        # Best-effort sozlesmesi kurulumun ILK satirinda bile gecerlidir
        # (independent review bulgusu, gercek defect): `level`, harici,
        # insan-tarafindan-duzenlenebilir bir girdiden (.env LOG_LEVEL) gelir
        # - TDD Section 19'un tanimladigi UC seviye (INFO/WARNING/ERROR)
        # DISINDAKI herhangi bir deger (ornegin .env.example'in KENDI
        # belgeledigi ama TDD Section 19'da KARSILIGI olmayan "DEBUG")
        # kurulumu ASLA cokertmemelidir - taninmayan bir deger, guvenli bir
        # varsayilana (INFO) sessizce duser.
        self._level = _LEVEL_ORDER.get(level.upper(), _stdlib_logging.INFO)
        self._logger = _stdlib_logging.Logger(name=f"linkedinbot.structured.{id(self)}")
        self._logger.propagate = False
        self._logger.setLevel(_stdlib_logging.DEBUG)

        self._handler: RotatingFileHandler | None = None
        try:
            path = Path(log_file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
            handler.setFormatter(_PassthroughFormatter())
            self._logger.addHandler(handler)
            self._handler = handler
        except OSError:
            # Best-effort kurulum: dosya loglama kullanilamiyorsa (izin,
            # eksik/olusturulamayan dizin vb.) pipeline HICBIR ZAMAN
            # engellenmez - logger sessizce no-op'a duser.
            self._logger.addHandler(_stdlib_logging.NullHandler())

    def info(
        self,
        *,
        account_id: UUID,
        run_id: UUID,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._log(
            "INFO", account_id=account_id, run_id=run_id, stage=stage, message=message, extra=extra
        )

    def warning(
        self,
        *,
        account_id: UUID,
        run_id: UUID,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._log(
            "WARNING",
            account_id=account_id,
            run_id=run_id,
            stage=stage,
            message=message,
            extra=extra,
        )

    def error(
        self,
        *,
        account_id: UUID,
        run_id: UUID,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._log(
            "ERROR", account_id=account_id, run_id=run_id, stage=stage, message=message, extra=extra
        )

    def _log(
        self,
        level_name: str,
        *,
        account_id: UUID,
        run_id: UUID,
        stage: str,
        message: str,
        extra: dict[str, Any] | None,
    ) -> None:
        level_no = _LEVEL_ORDER[level_name]
        if level_no < self._level:
            return
        try:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "account_id": str(account_id),
                "run_id": str(run_id),
                "stage": stage,
                "level": level_name,
                "message": message,
                "extra": _redact(extra or {}),
            }
            self._logger.log(level_no, json.dumps(payload, default=str))
        except Exception:  # noqa: BLE001, S110
            # Best-effort sozlesmesi (kullanici talimati, acikca onaylandi):
            # loglama HICBIR ZAMAN is mantigina sizmamalidir - burada
            # yutulan bir hatayi AYRICA loglamaya calismak (S110'un onerdigi
            # gibi) ayni riski (yeni bir I/O basarisizligi) tekrar
            # yaratir; bu yuzden kasitli olarak sessizce yutulur.
            pass
