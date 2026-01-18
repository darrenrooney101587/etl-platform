class BMSError(Exception):
    pass


class FormError(BMSError):
    pass


class WorkflowError(BMSError):
    pass


class LinkingError(BMSError):
    pass


class ConfigError(BMSError):
    pass
