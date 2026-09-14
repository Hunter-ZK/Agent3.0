from __future__ import annotations

import re
from dataclasses import dataclass


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_IDENTIFIER = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
_SETTING_NAME = _DOTTED_IDENTIFIER


def _identifier(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if not normalized or _IDENTIFIER.fullmatch(normalized) is None:
        raise ValueError(f"{field} must be a SQL identifier.")
    return normalized


def _dotted_identifier(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if not normalized or _DOTTED_IDENTIFIER.fullmatch(normalized) is None:
        raise ValueError(f"{field} must be a dotted SQL identifier.")
    return normalized


def _safe_composed_value(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty.")
    if ";" in normalized or "\x00" in normalized:
        raise ValueError(
            f"{field} cannot contain statement terminators or NUL bytes."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class FixedReportField:
    name: str
    business_definition: str = ""
    expression_hint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _identifier(self.name, field="FixedReportField.name"),
        )


@dataclass(frozen=True, slots=True)
class FixedReportPartition:
    name: str
    value: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _identifier(self.name, field="FixedReportPartition.name"),
        )
        if self.value is not None:
            object.__setattr__(
                self,
                "value",
                _safe_composed_value(
                    self.value,
                    field="FixedReportPartition.value",
                ),
            )

    @property
    def is_dynamic(self) -> bool:
        return self.value is None


@dataclass(frozen=True, slots=True)
class FixedReportWriteTarget:
    table_name: str
    fields: tuple[FixedReportField, ...]
    partitions: tuple[FixedReportPartition, ...] = ()

    def __post_init__(self) -> None:
        normalized = _dotted_identifier(
            self.table_name,
            field="FixedReportWriteTarget.table_name",
        )
        if not self.fields:
            raise ValueError("FixedReportWriteTarget requires at least one field.")
        if len({item.name for item in self.fields}) != len(self.fields):
            raise ValueError("FixedReportWriteTarget field names must be unique.")
        if len({item.name for item in self.partitions}) != len(self.partitions):
            raise ValueError("FixedReportWriteTarget partition names must be unique.")
        object.__setattr__(self, "table_name", normalized)


@dataclass(frozen=True, slots=True)
class FixedReportSpec:
    """
    Production Program Generate 的稳定知识面输入。

    它描述“要得到什么”，不描述 SQL 应该怎么写。
    Planner / Generator 可以消费它，但 SQLProgram 不依赖它。

    partitions.value / session_settings.value 是由可信 Spec 提供的 SQL value/expression，
    系统会直接拼装，因此这里拒绝语句终止符，避免把 Program composition 变成注入边界。
    """

    report_name: str
    business_requirement: str
    source_tables: tuple[str, ...]
    write_targets: tuple[FixedReportWriteTarget, ...]
    parameters: tuple[str, ...] = ()
    session_settings: tuple[tuple[str, str], ...] = ()
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        report_name = self.report_name.strip()
        requirement = self.business_requirement.strip()
        if not report_name:
            raise ValueError("FixedReportSpec.report_name cannot be empty.")
        if not requirement:
            raise ValueError("FixedReportSpec.business_requirement cannot be empty.")
        if not self.source_tables:
            raise ValueError("FixedReportSpec requires source_tables.")
        if not self.write_targets:
            raise ValueError("FixedReportSpec requires write_targets.")

        normalized_sources = tuple(
            _dotted_identifier(
                table,
                field="FixedReportSpec.source_tables item",
            )
            for table in self.source_tables
        )
        if len(set(normalized_sources)) != len(normalized_sources):
            raise ValueError("FixedReportSpec.source_tables must be unique.")

        normalized_parameters = tuple(
            _identifier(
                item,
                field="FixedReportSpec.parameters item",
            )
            for item in self.parameters
        )
        if len(set(normalized_parameters)) != len(normalized_parameters):
            raise ValueError("FixedReportSpec.parameters must be unique.")

        settings: list[tuple[str, str]] = []
        for name, value in self.session_settings:
            normalized_name = name.strip().lower()
            if _SETTING_NAME.fullmatch(normalized_name) is None:
                raise ValueError(
                    "FixedReportSpec.session_settings name must be a dotted identifier."
                )
            settings.append(
                (
                    normalized_name,
                    _safe_composed_value(
                        value,
                        field="FixedReportSpec.session_settings value",
                    ),
                )
            )

        object.__setattr__(self, "report_name", report_name)
        object.__setattr__(self, "business_requirement", requirement)
        object.__setattr__(self, "source_tables", normalized_sources)
        object.__setattr__(self, "parameters", normalized_parameters)
        object.__setattr__(self, "session_settings", tuple(settings))

    def to_prompt_payload(self) -> dict:
        return {
            "report_name": self.report_name,
            "business_requirement": self.business_requirement,
            "source_tables": list(self.source_tables),
            "write_targets": [
                {
                    "table_name": target.table_name,
                    "fields": [
                        {
                            "name": field.name,
                            "business_definition": field.business_definition,
                            "expression_hint": field.expression_hint,
                        }
                        for field in target.fields
                    ],
                    "partitions": [
                        {
                            "name": item.name,
                            "value": item.value,
                            "dynamic": item.is_dynamic,
                        }
                        for item in target.partitions
                    ],
                }
                for target in self.write_targets
            ],
            "parameters": list(self.parameters),
            "session_settings": [
                {"name": name, "value": value}
                for name, value in self.session_settings
            ],
            "constraints": list(self.constraints),
        }
