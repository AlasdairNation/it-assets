class AccountType:
    """Enum class for user acount types"""
    PERMANENT = 2
    CONTRACT = 0
    SEASONAL = 8
    VENDOR_OR_EXTERNAL = 6
    VOLUNTEER = 7
    ALUMNI_OR_OTHER = 1
    ROLE_BASED_ACCOUNT = 9
    UNKNOWN = 14
    ADMIN_ACCOUNT = 15

class FSTicketStatus:
    """Enum class for Freshservice ticket statuses"""

    OPEN = 2
    PENDING = 3
    RESOLVED = 4
    CLOSED = 5
    WORKFLOW_PROCESSING = 28
    WORKFLOW_FAILED = 29

class FSTicketSource:
    """Enum class for Freshservice ticket sources"""
    EMPLOYEE_OFFBOARDING = 18
    MONITORING = 1001