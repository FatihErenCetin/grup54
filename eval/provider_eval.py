"""Gercek Gemini/Ollama judge yollarini ayni conflict fixture'larinda kosar (#78).

Bu komut offline CI kapisinin yerine gecmez. Her provider kendi ayri esik
profiline karsi degerlendirilir; canli model veya API anahtari gerektirir.

Kullanim:
    uv run python -m eval.provider_eval --provider both
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Literal

from ensemble.config import Settings
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
from ensemble.integrations.ollama.errors import OllamaError
from ensemble.ports import JudgePort
from eval.eval_runner import EvalReport, EvalRunner
from eval.gate import evaluate_gate

Provider = Literal["gemini", "ollama"]


@dataclass(frozen=True)
class ProviderThresholds:
    min_precision: float
    min_f05: float
    min_total: int = 100


# Ayri profiller kasitlidir: Ollama'nin ilk canli kalibrasyonundan sonra yalniz
# ollama satiri degisebilir. Baslangic guvenlik tabani mevcut #18 kapisidir;
# olculmemis daha gevsek bir deger uydurulmaz.
PROVIDER_THRESHOLDS: dict[Provider, ProviderThresholds] = {
    "gemini": ProviderThresholds(min_precision=0.90, min_f05=0.89),
    "ollama": ProviderThresholds(min_precision=0.90, min_f05=0.89),
}


def build_provider_judge(provider: Provider, settings: Settings) -> JudgePort:
    if provider == "ollama":
        return OllamaAdapter(settings)
    if not settings.GEMINI_API_KEY:
        raise ValueError("Gemini provider eval icin GEMINI_API_KEY gerekli")
    return GeminiJudgeAdapter(settings)


def run_provider_eval(provider: Provider, settings: Settings) -> tuple[EvalReport, list[str]]:
    judge = build_provider_judge(provider, settings)
    if provider == "ollama":
        # Servis/model yokken 118 vakanin her birinde retry beklemek yerine tek
        # embedding preflight'i ile erken ve acik hata ver.
        assert isinstance(judge, OllamaAdapter)
        judge.embed(["ensemble provider eval preflight"], "SEMANTIC_SIMILARITY")
    report = EvalRunner(judge=judge).run_eval()
    thresholds = PROVIDER_THRESHOLDS[provider]
    violations = evaluate_gate(
        report,
        min_precision=thresholds.min_precision,
        min_f05=thresholds.min_f05,
        min_total=thresholds.min_total,
    )
    return report, violations


def main() -> None:
    parser = argparse.ArgumentParser(description="Provider-duyarli canli judge eval'i")
    parser.add_argument(
        "--provider",
        choices=("gemini", "ollama", "both"),
        default="both",
    )
    args = parser.parse_args()
    providers: tuple[Provider, ...] = (
        ("gemini", "ollama") if args.provider == "both" else (args.provider,)
    )
    failed = False
    for provider in providers:
        settings = Settings(LLM_PROVIDER=provider)
        try:
            report, violations = run_provider_eval(provider, settings)
        except (ValueError, OllamaError) as exc:
            parser.error(str(exc))

        result = report.overall
        print(f"provider={provider}")
        print(
            f"precision={result.precision:.4f} recall={result.recall:.4f} "
            f"f05={result.f05:.4f} TP={result.tp} FP={result.fp} "
            f"FN={result.fn} TN={result.tn}"
        )
        if violations:
            failed = True
            for violation in violations:
                print(f"KIRILDI: {violation}")
        else:
            print("GECTI")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
