from __future__ import annotations

import hashlib
import re

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pyspark.sql import (
    DataFrame,
    SparkSession,
    functions as F,
)

from sql_pilot_engine.metadata.models import (
    TableMetadata,
)
from sql_pilot_engine.program.enums import (
    ProgramAnalysisStatus,
    SourceBindingKind,
)
from sql_pilot_engine.program.models import (
    SQLProgram,
)
from sql_pilot_engine.program.service import (
    ProgramAnalysisService,
)


class MaxComputeSimulationError(
    RuntimeError,
):
    """
    本地 MaxCompute 模拟执行失败。

    注意：
    本异常只表示 Local Simulator 无法完成当前模拟，
    不代表真实 MaxCompute 环境一定执行失败。
    """


@dataclass(
    frozen=True,
    slots=True,
)
class LocalSQLResult:
    """
    一条 SQL Statement 的本地执行结果。

    SELECT:
        columns / rows 为实际查询结果。

    INSERT:
        当前返回写入完成后的目标表 DataFrame 结果。
        后续测试仍建议再 query() 目标表验证结果。
    """

    statement_index: int

    sql: str

    columns: tuple[
        str,
        ...,
    ]

    rows: tuple[
        tuple[
            Any,
            ...,
        ],
        ...,
    ]


class MaxComputeLocalSimulator:
    """
    Agent3.0 本地 MaxCompute SQL 模拟环境。

    ========================================================
    核心定位
    ========================================================

    它提供：

        MaxCompute / DataWorks SQL
                ↓
        ProgramAnalysisService
                ↓
        Parameter Rendering
                ↓
        Local Compatibility Layer
                ↓
        Spark SQL Analyzer / Executor
                ↓
        In-Memory Tables

    Spark 负责：

        - SELECT
        - JOIN
        - CTE
        - UNION ALL
        - GROUP BY
        - GROUPING SETS
        - CASE
        - Window
        - LATERAL VIEW
        - Function execution
        - Column resolution
        - Type analysis

    Simulator 负责：

        - MaxCompute physical table identity
        - project.table → local temp view 映射
        - Metadata → Spark schema
        - Fixture data
        - DataWorks ${parameter}
        - INSERT OVERWRITE table state
        - Partition overwrite semantics

    ========================================================
    为什么使用纯内存表
    ========================================================

    Windows 上 Spark Managed Table 会经过 Hadoop
    RawLocalFileSystem，从而要求：

        HADOOP_HOME
        winutils.exe

    这些与 DataAgent / MaxCompute SQL 模拟本身无关。

    因此本 Simulator 不使用：

        - CREATE DATABASE
        - CREATE TABLE
        - saveAsTable
        - insertInto
        - warehouse directory
        - Hadoop local filesystem

    所有模拟表均由：

        Spark DataFrame + Temporary View

    实现。

    ========================================================
    证据边界
    ========================================================

    Simulator PASS 可以证明：

        - SQL 在当前 fixture 上可执行；
        - SQL 逻辑在当前 fixture 上得到某个结果；
        - 大量 Hive/Spark-compatible MaxCompute SQL
          可以本地执行。

    但不能证明：

        - MaxCompute 服务端执行计划完全一致；
        - MaxCompute CU / 性能一致；
        - MaxCompute 专有 UDF 行为一致；
        - 生产任务一定成功。
    """

    def __init__(
        self,
        *,
        default_project: str = "default",
    ) -> None:

        normalized_project = (
            default_project
            .strip()
            .lower()
        )

        if not normalized_project:
            raise ValueError(
                "default_project cannot be empty."
            )

        self._default_project = (
            normalized_project
        )

        self._spark: (
            SparkSession
            | None
        ) = None

        # --------------------------------------------------
        # 权威 Metadata
        #
        # canonical full name
        #   →
        # TableMetadata
        # --------------------------------------------------

        self._metadata: dict[
            str,
            TableMetadata,
        ] = {}

        # --------------------------------------------------
        # 模拟数据库当前表数据
        #
        # canonical full name
        #   →
        # Spark DataFrame
        # --------------------------------------------------

        self._tables: dict[
            str,
            DataFrame,
        ] = {}

        # --------------------------------------------------
        # canonical physical table
        #   →
        # Spark 内部 temp view
        #
        # 例如：
        #
        # odps_prd_dwd.loan_detail
        #
        # →
        #
        # __mc_7d3a42e0c8d1
        # --------------------------------------------------

        self._internal_views: dict[
            str,
            str,
        ] = {}

        # --------------------------------------------------
        # base table name
        #   →
        # 所有 canonical owners
        #
        # loan_detail
        #
        # →
        #
        # {
        #   project_a.loan_detail,
        #   project_b.loan_detail,
        # }
        #
        # 只有一个 owner 时才建立裸表 temp view。
        # --------------------------------------------------

        self._base_name_owners: dict[
            str,
            set[
                str
            ],
        ] = {}

        self._program_service = (
            ProgramAnalysisService()
        )

    # ========================================================
    # Lifecycle
    # ========================================================

    def start(
        self,
    ) -> "MaxComputeLocalSimulator":
        """
        启动 Spark Local。

        注意：
        这里不配置 warehouse，
        不创建 database，
        不触发 Hadoop local filesystem。
        """

        if self._spark is not None:
            return self

        self._spark = (
            SparkSession
            .builder
            .master(
                "local[2]"
            )
            .appName(
                "Agent3-MaxCompute-Local"
            )
            .config(
                "spark.ui.enabled",
                "false",
            )
            .config(
                "spark.sql.shuffle.partitions",
                "2",
            )
            .config(
                "spark.sql.crossJoin.enabled",
                "true",
            )
            .getOrCreate()
        )

        return self

    def stop(
        self,
    ) -> None:
        """
        停止 Spark，并清理当前 Simulator 状态。
        """

        if self._spark is not None:

            # ----------------------------------------------
            # 清理 canonical internal views
            # ----------------------------------------------

            for view_name in tuple(
                self._internal_views.values()
            ):
                self._spark.catalog.dropTempView(
                    view_name
                )

            # ----------------------------------------------
            # 清理裸表 aliases
            # ----------------------------------------------

            for base_name in tuple(
                self._base_name_owners
            ):
                self._spark.catalog.dropTempView(
                    base_name
                )

            self._spark.stop()

            self._spark = None

        self._tables.clear()
        self._internal_views.clear()
        self._metadata.clear()
        self._base_name_owners.clear()

    def __enter__(
        self,
    ) -> "MaxComputeLocalSimulator":

        return self.start()

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:

        self.stop()

    # ========================================================
    # Metadata / Table Registration
    # ========================================================

    def register_table(
        self,
        metadata: TableMetadata,
    ) -> str:
        """
        根据权威 Metadata 注册一个本地模拟表。

        不创建 Spark managed table。

        实际创建：

            empty DataFrame
                +
            internal temp view

        返回 canonical physical table name：

            project.table
        """

        spark = (
            self._require_spark()
        )

        canonical = (
            self._canonical_table_name(
                metadata.full_name
            )
        )

        if canonical in self._metadata:
            raise MaxComputeSimulationError(
                (
                    "Table has already been "
                    "registered: "
                    f"{canonical}"
                )
            )

        # --------------------------------------------------
        # Metadata 决定 schema。
        #
        # 当前表一开始为空。
        # --------------------------------------------------

        dataframe = (
            spark.createDataFrame(
                [],
                schema=(
                    self
                    ._dataframe_schema_ddl(
                        metadata
                    )
                ),
            )
        )

        self._metadata[
            canonical
        ] = metadata

        self._tables[
            canonical
        ] = dataframe

        internal_view = (
            self._internal_view_name(
                canonical
            )
        )

        self._internal_views[
            canonical
        ] = internal_view

        dataframe.createOrReplaceTempView(
            internal_view
        )

        base_name = (
            canonical
            .rsplit(
                ".",
                1,
            )[-1]
        )

        self._base_name_owners.setdefault(
            base_name,
            set(),
        ).add(
            canonical
        )

        self._refresh_bare_alias(
            base_name
        )

        return canonical

    # ========================================================
    # Fixture Data
    # ========================================================

    def load_rows(
        self,
        table_name: str,
        rows: Sequence[
            Mapping[
                str,
                Any,
            ]
        ],
        *,
        mode: str = "overwrite",
    ) -> None:
        """
        给模拟表装载 Fixture 数据。

        Metadata:
            决定 schema。

        rows:
            只提供测试值。

        mode:

            overwrite
                完整替换当前模拟表数据。

            append
                追加到当前模拟表。
        """

        if mode not in {
            "overwrite",
            "append",
        }:
            raise ValueError(
                (
                    "mode must be "
                    "'overwrite' or 'append'."
                )
            )

        spark = (
            self._require_spark()
        )

        canonical = (
            self.resolve_table(
                table_name
            )
        )

        metadata = (
            self._metadata[
                canonical
            ]
        )

        incoming = (
            spark.createDataFrame(
                list(rows),
                schema=(
                    self
                    ._dataframe_schema_ddl(
                        metadata
                    )
                ),
            )
        )

        if mode == "overwrite":

            dataframe = incoming

        else:

            dataframe = (
                self._tables[
                    canonical
                ]
                .unionByName(
                    incoming
                )
            )

        self._replace_table_dataframe(
            canonical=canonical,
            dataframe=dataframe,
        )

    # ========================================================
    # Public SQL Execution
    # ========================================================

    def execute(
        self,
        sql: str,
        *,
        parameters: Mapping[
            str,
            str | int | float,
        ] | None = None,
    ) -> tuple[
        LocalSQLResult,
        ...,
    ]:
        """
        执行完整 MaxCompute / DataWorks SQL Program。

        ----------------------------------------------------
        SET
        ----------------------------------------------------

        顶层 SET 已由现有 Program Preprocessor 处理，
        不直接提交给 Spark。

        ----------------------------------------------------
        DataWorks Parameter
        ----------------------------------------------------

        SQL：

            WHERE dt='${p_month}'

        parameters：

            {
                "p_month": "202609"
            }

        实际 Spark SQL：

            WHERE dt='202609'

        ----------------------------------------------------
        INSERT
        ----------------------------------------------------

        SELECT：
            直接交给 Spark。

        INSERT OVERWRITE：
            transformation SELECT 交给 Spark，
            table overwrite semantics 由 Simulator 模拟。
        """

        spark = (
            self._require_spark()
        )

        analysis = (
            self
            ._program_service
            .analyze(
                sql
            )
        )

        if (
            analysis.status
            is ProgramAnalysisStatus.FAILED
            or analysis.program is None
        ):
            raise MaxComputeSimulationError(
                (
                    "Program analysis failed: "
                    f"{analysis.failure_reason}"
                )
            )

        program = (
            analysis.program
        )

        # --------------------------------------------------
        # 必须先验证 physical source。
        #
        # 防止 Spark 当前 session 中碰巧存在一个
        # 同名对象，从而绕过 Metadata 0/1/N 规则。
        # --------------------------------------------------

        self._preflight_sources(
            program
        )

        parameter_values = {
            (
                name
                .strip()
                .lower()
            ): str(value)
            for name, value
            in (
                parameters
                or {}
            ).items()
        }

        results: list[
            LocalSQLResult
        ] = []

        for statement in (
            program.statements
        ):

            statement_sql = (
                statement.normalized_sql
            )

            # ----------------------------------------------
            # DataWorks parameter token
            # →
            # 实际 fixture value
            # ----------------------------------------------

            statement_sql = (
                self._render_parameters(
                    statement_sql,
                    program=program,
                    values=(
                        parameter_values
                    ),
                )
            )

            # ----------------------------------------------
            # project.table
            # →
            # internal Spark temp view
            #
            # 裸表名不改，因为唯一时已经建立 temp alias。
            # ----------------------------------------------

            statement_sql = (
                self._rewrite_physical_sources(
                    statement_sql,
                    program=program,
                    statement_index=(
                        statement.index
                    ),
                )
            )

            try:

                if (
                    statement.write_target
                    is None
                ):

                    dataframe = (
                        spark.sql(
                            statement_sql
                        )
                    )

                else:

                    dataframe = (
                        self._execute_insert(
                            sql=statement_sql,
                            statement=statement,
                        )
                    )

                columns = tuple(
                    dataframe.columns
                )

                rows = tuple(
                    tuple(row)
                    for row
                    in dataframe.collect()
                )

            except (
                MaxComputeSimulationError
            ):
                raise

            except Exception as exc:

                raise MaxComputeSimulationError(
                    (
                        "Local MaxCompute "
                        "simulation failed for "
                        f"statement "
                        f"{statement.index}:\n\n"
                        f"{statement_sql}\n\n"
                        f"{exc}"
                    )
                ) from exc

            results.append(
                LocalSQLResult(
                    statement_index=(
                        statement.index
                    ),
                    sql=(
                        statement_sql
                    ),
                    columns=columns,
                    rows=rows,
                )
            )

        return tuple(
            results
        )

    def query(
        self,
        sql: str,
        *,
        parameters: Mapping[
            str,
            str | int | float,
        ] | None = None,
    ) -> LocalSQLResult:
        """
        执行恰好一个业务 Statement。
        """

        results = (
            self.execute(
                sql,
                parameters=parameters,
            )
        )

        if len(results) != 1:
            raise MaxComputeSimulationError(
                (
                    "query() requires exactly "
                    "one business statement."
                )
            )

        return results[0]

    # ========================================================
    # Table Resolution
    # ========================================================

    def resolve_table(
        self,
        table_name: str,
    ) -> str:
        """
        物理表身份解析。

        ----------------------------------------------------
        已带 project
        ----------------------------------------------------

            project.table

        必须 exact canonical lookup。

        ----------------------------------------------------
        裸表
        ----------------------------------------------------

            table

        Metadata：

            0 candidate
                → NOT FOUND

            1 candidate
                → 自动补全 canonical project.table

            >1 candidate
                → AMBIGUOUS
        """

        normalized = (
            table_name
            .strip()
            .lower()
        )

        if not normalized:
            raise ValueError(
                "table_name cannot be empty."
            )

        # --------------------------------------------------
        # Canonical exact lookup
        # --------------------------------------------------

        if "." in normalized:

            if (
                normalized
                not in self._metadata
            ):
                raise MaxComputeSimulationError(
                    (
                        "Unknown canonical table: "
                        f"{normalized}"
                    )
                )

            return normalized

        # --------------------------------------------------
        # Bare table 0 / 1 / N
        # --------------------------------------------------

        candidates = (
            self
            ._base_name_owners
            .get(
                normalized,
                set(),
            )
        )

        if not candidates:

            raise MaxComputeSimulationError(
                (
                    "Table not found: "
                    f"{normalized}"
                )
            )

        if len(candidates) > 1:

            raise MaxComputeSimulationError(
                (
                    "Ambiguous table name "
                    f"{normalized!r}: "
                    + ", ".join(
                        sorted(
                            candidates
                        )
                    )
                )
            )

        return next(
            iter(
                candidates
            )
        )

    # ========================================================
    # INSERT OVERWRITE Simulation
    # ========================================================

    def _execute_insert(
        self,
        *,
        sql: str,
        statement,
    ) -> DataFrame:
        """
        模拟：

            INSERT OVERWRITE TABLE target
            PARTITION(...)
            SELECT ...

        Spark 负责 transformation query。

        Simulator 负责：

            - target identity
            - static partition
            - dynamic partition
            - overwrite table state

        V1 暂时只正式支持 INSERT OVERWRITE。

        如果以后真实 benchmark 出现 INSERT INTO，
        再单独增加 append semantics。
        """

        target = (
            statement.write_target
        )

        if target is None:
            raise RuntimeError(
                (
                    "INSERT statement "
                    "has no WriteTarget."
                )
            )

        canonical_target = (
            self.resolve_table(
                target.table_name
            )
        )

        metadata = (
            self._metadata[
                canonical_target
            ]
        )

        (
            prefix,
            query_sql,
            partition_values,
        ) = (
            self._extract_insert_query(
                sql=sql,
                target_name=(
                    target.table_name
                ),
            )
        )

        # --------------------------------------------------
        # 例如：
        #
        # WITH a AS (...)
        # INSERT OVERWRITE ...
        # SELECT ...
        #
        # 转成：
        #
        # WITH a AS (...)
        # SELECT ...
        #
        # 然后真正交给 Spark。
        # --------------------------------------------------

        transformation_sql = (
            prefix
            + query_sql
        )

        dataframe = (
            self
            ._require_spark()
            .sql(
                transformation_sql
            )
        )

        partition_names = tuple(
            name.strip().lower()
            for name
            in metadata.technical.partition_fields
        )

        # --------------------------------------------------
        # Target Metadata 中的普通字段
        # --------------------------------------------------

        regular_names = tuple(
            column.name
            for column
            in metadata.columns.values()
            if (
                column.name
                .strip()
                .lower()
                not in partition_names
            )
        )

        static_partition_names = {
            name.strip().lower()
            for name
            in partition_values
        }

        # --------------------------------------------------
        # 未在 PARTITION(dt='xxx') 中静态指定的分区，
        # 需要由 SELECT 输出。
        # --------------------------------------------------

        dynamic_partition_names = tuple(
            name
            for name
            in partition_names
            if (
                name
                not in static_partition_names
            )
        )

        expected_select_columns = (
            regular_names
            + dynamic_partition_names
        )

        if (
            len(
                dataframe.columns
            )
            != len(
                expected_select_columns
            )
        ):
            raise MaxComputeSimulationError(
                (
                    "INSERT output column count "
                    "does not match target table. "
                    f"Expected "
                    f"{len(expected_select_columns)}, "
                    f"got "
                    f"{len(dataframe.columns)}."
                )
            )

        # --------------------------------------------------
        # INSERT SQL 依赖位置匹配。
        #
        # 将 Spark transformation 输出重命名为
        # Target Metadata 对应字段。
        # --------------------------------------------------

        dataframe = (
            dataframe.toDF(
                *expected_select_columns
            )
        )

        # --------------------------------------------------
        # 补 static partition fields
        # --------------------------------------------------

        for (
            partition_name,
            partition_value,
        ) in (
            partition_values.items()
        ):

            normalized_name = (
                partition_name
                .strip()
                .lower()
            )

            column_metadata = (
                metadata.get_column(
                    normalized_name
                )
            )

            if column_metadata is None:
                raise MaxComputeSimulationError(
                    (
                        "Unknown partition field "
                        f"{normalized_name!r} "
                        f"for "
                        f"{canonical_target}."
                    )
                )

            dataframe = (
                dataframe.withColumn(
                    normalized_name,
                    F.lit(
                        partition_value
                    ).cast(
                        self._spark_type(
                            column_metadata
                            .technical
                            .data_type
                        )
                    ),
                )
            )

        # --------------------------------------------------
        # 最终字段顺序严格回到 Metadata 顺序。
        # --------------------------------------------------

        final_columns = tuple(
            column.name
            for column
            in metadata.columns.values()
        )

        dataframe = (
            dataframe.select(
                *final_columns
            )
        )

        self._overwrite_target(
            canonical=(
                canonical_target
            ),
            incoming=dataframe,
            partition_fields=(
                partition_names
            ),
            static_partitions={
                (
                    name
                    .strip()
                    .lower()
                ): value
                for name, value
                in partition_values.items()
            },
        )

        return (
            self._tables[
                canonical_target
            ]
        )

    def _overwrite_target(
        self,
        *,
        canonical: str,
        incoming: DataFrame,
        partition_fields: tuple[
            str,
            ...,
        ],
        static_partitions: Mapping[
            str,
            Any,
        ],
    ) -> None:
        """
        模拟 INSERT OVERWRITE。

        ----------------------------------------------------
        非分区表
        ----------------------------------------------------

            整表覆盖。

        ----------------------------------------------------
        全静态分区
        ----------------------------------------------------

            PARTITION(
                dt='202609'
            )

        只覆盖：

            dt = 202609

        其它 partition 保留。

        ----------------------------------------------------
        动态分区
        ----------------------------------------------------

            PARTITION(
                dt='202609',
                batch_no
            )

        incoming 实际产生哪些 batch_no，
        就覆盖哪些：

            (dt, batch_no)

        partition combinations。
        """

        existing = (
            self._tables[
                canonical
            ]
        )

        # --------------------------------------------------
        # 非分区表：
        # 整表覆盖
        # --------------------------------------------------

        if not partition_fields:

            self._replace_table_dataframe(
                canonical=canonical,
                dataframe=incoming,
            )

            return

        static_names = set(
            static_partitions
        )

        partition_names = set(
            partition_fields
        )

        # --------------------------------------------------
        # 所有 partition 都是 static
        #
        # 即使 incoming 为空，也必须清掉当前 partition。
        # --------------------------------------------------

        if (
            partition_names
            == static_names
        ):

            keep_condition = None

            for (
                name,
                value,
            ) in (
                static_partitions.items()
            ):

                # ------------------------------------------
                # eqNullSafe 可以正确处理 NULL partition。
                #
                # 相同 partition：
                #     False
                #
                # 不同 partition：
                #     True
                # ------------------------------------------

                different = (
                    ~F.col(
                        name
                    )
                    .eqNullSafe(
                        F.lit(
                            value
                        )
                    )
                )

                if (
                    keep_condition
                    is None
                ):

                    keep_condition = (
                        different
                    )

                else:

                    # 任意 partition value 不同，
                    # 这行都应该保留。
                    keep_condition = (
                        keep_condition
                        | different
                    )

            if (
                keep_condition
                is None
            ):

                remaining = (
                    existing
                )

            else:

                remaining = (
                    existing.filter(
                        keep_condition
                    )
                )

        else:

            # ------------------------------------------------
            # Dynamic partition。
            #
            # incoming 实际触及哪些完整 partition combination，
            # 就覆盖哪些。
            # ------------------------------------------------

            affected = (
                incoming
                .select(
                    *partition_fields
                )
                .distinct()
            )

            remaining = (
                existing.join(
                    affected,
                    on=list(
                        partition_fields
                    ),
                    how="left_anti",
                )
            )

        combined = (
            remaining
            .unionByName(
                incoming
            )
        )

        self._replace_table_dataframe(
            canonical=canonical,
            dataframe=combined,
        )

    # ========================================================
    # INSERT Shell Parsing
    # ========================================================

    def _extract_insert_query(
        self,
        *,
        sql: str,
        target_name: str,
    ) -> tuple[
        str,
        str,
        dict[
            str,
            Any,
        ],
    ]:
        """
        只解析 INSERT OVERWRITE 外壳。

        不是 SQL Parser。

        例如：

            WITH base AS (...)
            INSERT OVERWRITE TABLE result
            PARTITION(dt='202609', batch_no)
            SELECT ...

        返回：

            prefix:
                WITH base AS (...)

            query:
                SELECT ...

            static partitions:
                {
                    "dt": "202609"
                }

        dynamic partition：

            batch_no

        不进入 static partition dict。
        """

        target_identifier_pattern = (
            self._identifier_pattern(
                target_name
            )
        )

        pattern = re.compile(
            (
                r"(?is)"
                r"^(?P<prefix>.*?)"
                r"\bINSERT\s+"
                r"OVERWRITE\s+TABLE\s+"
                + target_identifier_pattern
                + r"\s*"
                r"(?:"
                r"PARTITION\s*"
                r"\("
                r"(?P<partition>[^)]*)"
                r"\)"
                r")?"
                r"\s*"
                r"(?P<query>SELECT\b.*)$"
            )
        )

        match = (
            pattern.match(
                sql.strip()
            )
        )

        if match is None:
            raise MaxComputeSimulationError(
                (
                    "Simulator V1 could not "
                    "parse INSERT OVERWRITE "
                    "statement."
                )
            )

        partition_text = (
            match.group(
                "partition"
            )
            or ""
        )

        partitions: dict[
            str,
            Any,
        ] = {}

        if partition_text.strip():

            for part in (
                partition_text.split(
                    ","
                )
            ):

                normalized_part = (
                    part.strip()
                )

                if not normalized_part:
                    continue

                # ------------------------------------------
                # Dynamic partition：
                #
                # PARTITION(dt, batch_no)
                #
                # 不需要 static value。
                # ------------------------------------------

                if "=" not in normalized_part:
                    continue

                name, raw_value = (
                    normalized_part.split(
                        "=",
                        1,
                    )
                )

                normalized_name = (
                    name
                    .strip()
                    .strip(
                        "`"
                    )
                    .lower()
                )

                partitions[
                    normalized_name
                ] = (
                    self
                    ._parse_partition_literal(
                        raw_value
                    )
                )

        return (
            match.group(
                "prefix"
            ),
            match.group(
                "query"
            ),
            partitions,
        )

    @staticmethod
    def _parse_partition_literal(
        value: str,
    ) -> Any:
        """
        V1 static partition 只支持 literal。

        支持：

            '202609'
            "202609"
            202609
            1.5
            NULL

        不支持：

            PARTITION(
                dt=some_function(...)
            )

        遇到这类真实 MaxCompute case，
        后续再讨论兼容方式。
        """

        normalized = (
            value.strip()
        )

        if (
            len(normalized)
            >= 2
            and normalized[0]
            == normalized[-1]
            and normalized[0]
            in {
                "'",
                '"',
            }
        ):

            return (
                normalized[
                    1:-1
                ]
            )

        if (
            normalized.upper()
            == "NULL"
        ):

            return None

        try:

            return int(
                normalized
            )

        except ValueError:
            pass

        try:

            return float(
                normalized
            )

        except ValueError:
            pass

        raise MaxComputeSimulationError(
            (
                "Simulator V1 only supports "
                "literal static partition "
                "values, got: "
                f"{value}"
            )
        )

    # ========================================================
    # Physical Source Mapping
    # ========================================================

    def _preflight_sources(
        self,
        program: SQLProgram,
    ) -> None:
        """
        在真正交给 Spark 之前验证所有 Physical Source。

        使用 Simulator 已注册的权威 Metadata：

            qualified table
                → exact

            bare table
                → 0 / 1 / N

        这样不会因为 Spark session 恰好存在某个
        同名 view 而绕过 DataAgent 的 Metadata 规则。
        """

        seen: set[
            str
        ] = set()

        for scope in (
            program.scope_analyses
        ):

            for binding in (
                scope.source_bindings
            ):

                if (
                    binding.kind
                    is not (
                        SourceBindingKind
                        .PHYSICAL_TABLE
                    )
                ):
                    continue

                physical_table = (
                    binding.physical_table
                )

                if (
                    physical_table
                    is None
                ):
                    raise MaxComputeSimulationError(
                        (
                            "Physical source binding "
                            "has no table name."
                        )
                    )

                normalized = (
                    physical_table
                    .strip()
                    .lower()
                )

                if normalized in seen:
                    continue

                seen.add(
                    normalized
                )

                self.resolve_table(
                    normalized
                )

    def _rewrite_physical_sources(
        self,
        sql: str,
        *,
        program: SQLProgram,
        statement_index: int,
    ) -> str:
        """
        把 SQL 中的完整 physical table identity：

            project.table

        转成 Spark internal temp view：

            __mc_xxxxxxxxxxxx

        裸表不改写。

        原因：

            裸表在唯一 owner 时已经有：
                CREATE OR REPLACE TEMP VIEW loan_detail

            >1 owner 时：
                preflight 已经拒绝。
        """

        rewritten = (
            sql
        )

        source_names: set[
            str
        ] = set()

        for scope in (
            program.scope_analyses
        ):

            if (
                scope.statement_index
                != statement_index
            ):
                continue

            for binding in (
                scope.source_bindings
            ):

                if (
                    binding.kind
                    is not (
                        SourceBindingKind
                        .PHYSICAL_TABLE
                    )
                ):
                    continue

                if (
                    binding.physical_table
                    is None
                ):
                    continue

                source_names.add(
                    binding.physical_table
                    .strip()
                    .lower()
                )

        # --------------------------------------------------
        # 长 identifier 优先，
        # 防止未来出现部分重叠。
        # --------------------------------------------------

        for source_name in sorted(
            source_names,
            key=len,
            reverse=True,
        ):

            canonical = (
                self.resolve_table(
                    source_name
                )
            )

            # ----------------------------------------------
            # 裸表：
            # 已由 temp alias 解决。
            # ----------------------------------------------

            if "." not in source_name:
                continue

            internal_view = (
                self._internal_views[
                    canonical
                ]
            )

            pattern = re.compile(
                (
                    r"(?i)"
                    r"(?<![\w])"
                    + self._identifier_pattern(
                        source_name
                    )
                    + r"(?![\w])"
                )
            )

            rewritten = (
                pattern.sub(
                    internal_view,
                    rewritten,
                )
            )

        return rewritten

    # ========================================================
    # DataWorks Parameter
    # ========================================================

    @staticmethod
    def _render_parameters(
        sql: str,
        *,
        program: SQLProgram,
        values: Mapping[
            str,
            str,
        ],
    ) -> str:
        """
        使用 Program Preprocessor 已生成的 analyzer_token。

        不重新正则扫描 ${...}。
        """

        rendered = (
            sql
        )

        for binding in (
            program.parameters
        ):

            name = (
                binding.name
                .strip()
                .lower()
            )

            if name not in values:
                raise MaxComputeSimulationError(
                    (
                        "Missing DataWorks "
                        "parameter value: "
                        f"{name}"
                    )
                )

            value = (
                values[
                    name
                ]
            )

            for occurrence in (
                binding.occurrences
            ):

                rendered = (
                    rendered.replace(
                        occurrence
                        .analyzer_token,
                        value,
                    )
                )

        return rendered

    # ========================================================
    # In-memory Table State
    # ========================================================

    def _replace_table_dataframe(
        self,
        *,
        canonical: str,
        dataframe: DataFrame,
    ) -> None:
        """
        替换模拟数据库中的当前表数据，
        并同步刷新：

            canonical internal view
            bare table view
        """

        self._tables[
            canonical
        ] = dataframe

        internal_view = (
            self._internal_views[
                canonical
            ]
        )

        dataframe.createOrReplaceTempView(
            internal_view
        )

        base_name = (
            canonical
            .rsplit(
                ".",
                1,
            )[-1]
        )

        self._refresh_bare_alias(
            base_name
        )

    def _refresh_bare_alias(
        self,
        base_name: str,
    ) -> None:
        """
        一个 base table name 只有唯一 canonical owner 时，
        才建立裸表 view。

        例如：

            odps_prd_dwd.loan_detail

        唯一：

            loan_detail → canonical DataFrame

        如果同时存在：

            project_a.loan_detail
            project_b.loan_detail

        则：

            loan_detail

        不建立 view。
        """

        spark = (
            self._require_spark()
        )

        # --------------------------------------------------
        # 先清掉历史 alias。
        # dropTempView 在不存在时返回 False。
        # --------------------------------------------------

        spark.catalog.dropTempView(
            base_name
        )

        owners = (
            self
            ._base_name_owners
            .get(
                base_name,
                set(),
            )
        )

        if len(owners) != 1:
            return

        canonical = next(
            iter(
                owners
            )
        )

        dataframe = (
            self._tables[
                canonical
            ]
        )

        dataframe.createOrReplaceTempView(
            base_name
        )

    # ========================================================
    # Schema
    # ========================================================

    def _dataframe_schema_ddl(
        self,
        metadata: TableMetadata,
    ) -> str:
        """
        直接根据权威 Metadata 创建 Spark DataFrame schema。

        注意：

        现在没有 Spark CREATE TABLE，
        所以 partition field 不需要特殊拆出来。

        对 DataFrame 来说：

            dt

        就只是普通字段。

        Partition semantics 只在 INSERT OVERWRITE
        时由 Simulator 使用。
        """

        return ", ".join(
            (
                f"`{column.name}` "
                f"{self._spark_type(column.technical.data_type)}"
            )
            for column
            in metadata.columns.values()
        )

    @staticmethod
    def _spark_type(
        data_type: str,
    ) -> str:
        """
        第一版只做明确且安全的类型兼容。

        不认识的 MaxCompute type 原样交给 Spark。

        如果 Spark 不支持：
            明确失败。

        不自行猜测数据类型。
        """

        normalized = (
            data_type
            .strip()
            .upper()
        )

        if (
            normalized
            == "DATETIME"
        ):
            return "TIMESTAMP"

        if normalized.startswith(
            "VARCHAR"
        ):
            return "STRING"

        if normalized.startswith(
            "CHAR"
        ):
            return "STRING"

        return normalized

    # ========================================================
    # Identifier Helpers
    # ========================================================

    def _canonical_table_name(
        self,
        full_name: str,
    ) -> str:
        """
        Simulator V1：

            table
                →
            default_project.table

            project.table
                →
            原样 canonicalize

        暂时不处理：

            catalog.project.table

        真实 benchmark 若出现，再扩。
        """

        normalized = (
            full_name
            .strip()
            .lower()
        )

        parts = (
            normalized.split(
                "."
            )
        )

        if len(parts) == 1:

            return (
                f"{self._default_project}."
                f"{parts[0]}"
            )

        if len(parts) == 2:

            return (
                normalized
            )

        raise MaxComputeSimulationError(
            (
                "Simulator V1 supports "
                "table or project.table "
                "identifiers only: "
                f"{full_name}"
            )
        )

    @staticmethod
    def _identifier_pattern(
        identifier: str,
    ) -> str:
        """
        SQL identifier regex。

        支持：

            project.table
            `project`.`table`
            project.`table`
            `project`.table

        这里只做 identifier identity mapping，
        不做 SQL grammar parsing。
        """

        return (
            r"\s*\.\s*".join(
                (
                    rf"`?{re.escape(part)}`?"
                )
                for part
                in identifier.split(
                    "."
                )
            )
        )

    @staticmethod
    def _internal_view_name(
        canonical: str,
    ) -> str:
        """
        canonical physical table
        →
        stable Spark temp view。

        例如：

            odps_prd_dwd.loan_detail

        →

            __mc_7d3a42e0c8d1

        不直接把 project.table 用作 temp view，
        避免 Spark database/catalog semantics。
        """

        digest = (
            hashlib.sha1(
                canonical.encode(
                    "utf-8"
                )
            )
            .hexdigest()[
                :12
            ]
        )

        return (
            f"__mc_{digest}"
        )

    # ========================================================
    # Spark Runtime
    # ========================================================

    def _require_spark(
        self,
    ) -> SparkSession:

        if self._spark is None:
            raise RuntimeError(
                (
                    "Simulator has not "
                    "been started."
                )
            )

        return self._spark