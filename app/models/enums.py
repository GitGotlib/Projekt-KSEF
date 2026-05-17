import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class ImportStatus(str, enum.Enum):
    NEW = "NEW"
    LOADED = "LOADED"
    VALIDATED = "VALIDATED"
    ERROR = "ERROR"
    EXPORTED = "EXPORTED"


class InvoiceType(str, enum.Enum):
    VAT = "VAT"
    CORRECTION = "CORRECTION"
    ADVANCE = "ADVANCE"
    PROFORMA = "PROFORMA"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    EXPORTED = "EXPORTED"
    ERROR = "ERROR"


class ValidationSeverity(str, enum.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class LogStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    INFO = "INFO"
