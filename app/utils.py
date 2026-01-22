class Logger:
    def __init__(self, name: str):
        self.name: str = name

    def debug(self, msg: str) -> None:
        print(f"[{self.name}] DEBUG:{msg}")
    def format_debug(self, msg: str) -> str:
        return f"[{self.name}] DEBUG:{msg}"

    def error(self, msg: str) -> None:
        print(f"[{self.name}] ERROR:{msg}")
    def format_error(self, msg: str) -> str:
        return f"[{self.name}] ERROR:{msg}"

    def info(self, msg: str) -> None:
        print(f"[{self.name}] INFO:{msg}")
    def format_info(self, msg: str) -> str:
        return f"[{self.name}] INFO:{msg}"