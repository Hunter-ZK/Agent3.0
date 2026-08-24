SAFETY_RULES = [
    Rule(
        rule_id="DROP_OR_TRUNCATE",
        name="Detect drop or truncate",
        severity=Severity.HIGH,
        category="safety",
        description="检测 DROP/TRUNCATE 高危操作。",
        check=check_drop_or_truncate,
        modes={"debug", "prod", "backfill"},
    ),
    Rule(
        rule_id="NON_ASCII_WHITESPACE",
        name="Detect non-ascii whitespace",
        severity=Severity.LOW,
        category="style",
        description="检测全角或不可见空白。",
        check=check_non_ascii_whitespace,
        modes={"debug", "prod", "backfill"},
    ),
]