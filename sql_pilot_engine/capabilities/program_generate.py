from __future__ import annotations

from sql_pilot_engine.generation.program_generator import (
    ProductionProgramGenerator,
    ProgramGenerationResult,
)
from sql_pilot_engine.spec.models import FixedReportSpec


class ProgramGenerateCapability:
    """
    Production SQL Program Generate 的稳定应用层门面。

    与 TextToSQLCapability 分离：
    - TextToSQLCapability 面向问数 Query；
    - ProgramGenerateCapability 面向 FixedReportSpec / DataWorks Program。
    """

    def __init__(
        self,
        *,
        generator: ProductionProgramGenerator,
    ) -> None:
        self._generator = generator

    def generate(
        self,
        spec: FixedReportSpec,
        *,
        dialect: str = "maxcompute",
        metadata_provider=None,
    ) -> ProgramGenerationResult:
        return self._generator.generate(
            spec=spec,
            dialect=dialect,
            metadata_provider=metadata_provider,
        )
