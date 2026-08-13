class AppError(RuntimeError):
    pass


class UploadValidationError(AppError):
    pass


class DependencyUnavailableError(AppError):
    pass


class ModelLoadError(AppError):
    pass


class InferenceError(AppError):
    pass


class CancelledError(AppError):
    pass
