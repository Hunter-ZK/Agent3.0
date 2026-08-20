from enum import Enum


class RuntimeEventType(str, Enum):

    USER_MESSAGE = "user_message"

    PLAN = "plan"

    CONTEXT = "context"

    GENERATION = "generation"

    VALIDATION = "validation"

    RESULT = "result"