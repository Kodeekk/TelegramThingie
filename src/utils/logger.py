import inspect

class Logger:
    _instance = None
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance.name = "App"
            cls._instance.level = cls.INFO
        return cls._instance

    def set_level(self, level_name: str) -> None:
        level_name = level_name.upper()
        if level_name == "DEV":
            self.level = self.DEBUG
        elif level_name == "PROD":
            self.level = self.INFO
        else:
            levels = {
                "DEBUG": self.DEBUG,
                "INFO": self.INFO,
                "WARNING": self.WARNING,
                "ERROR": self.ERROR
            }
            self.level = levels.get(level_name, self.INFO)

    def _get_caller_name(self) -> str:
        stack = inspect.stack()
        for frame_info in stack[2:]:
            frame = frame_info.frame
            if 'self' in frame.f_locals:
                instance = frame.f_locals['self']
                cls_name = instance.__class__.__name__
                if cls_name != "Logger":
                    return cls_name
            else:
                break
        return self.name

    def debug(self, msg: str) -> None:
        if self.level <= self.DEBUG:
            print(f"[{self._get_caller_name()}] DEBUG: {msg}")
    def format_debug(self, msg: str) -> str:
        return f"[{self._get_caller_name()}] DEBUG: {msg}"
    def error(self, msg: str) -> None:
        if self.level <= self.ERROR:
            print(f"[{self._get_caller_name()}] ERROR: {msg}")
    def format_error(self, msg: str) -> str:
        return f"[{self._get_caller_name()}] ERROR: {msg}"
    def info(self, msg: str) -> None:
        if self.level <= self.INFO:
            print(f"[{self._get_caller_name()}] INFO: {msg}")
    def format_info(self, msg: str) -> str:
        return f"[{self._get_caller_name()}] INFO: {msg}"
    def warning(self, msg: str) -> None:
        if self.level <= self.WARNING:
            print(f"[{self._get_caller_name()}] WARNING :{msg}")
    def format_warning(self, msg: str) -> str:
        return f"[{self._get_caller_name()}] WARNING: {msg}"



logger = Logger()