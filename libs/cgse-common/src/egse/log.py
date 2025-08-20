__all__ = [
    "LOG_FORMAT_FULL",
    "logger",
]

import logging
import textwrap

import rich

LOG_FORMAT_FULL = (
    "{asctime:23s} : {processName:20s} : {levelname:8s} : {name:^25s} : {lineno:6d} : {filename:20s} : {message}"
)

logger = logging.getLogger("egse")
logger.propagate = True
logger.level = logging.INFO
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt=LOG_FORMAT_FULL, style="{")
handler.setFormatter(formatter)
logger.addHandler(handler)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT_FULL,
    )
    root_logger = logging.getLogger()

    rich.print(
        textwrap.dedent(
            """
            Example logging statements
              - logging level set to INFO
              - fields are separated by a colon ':'
              - fields: date & time: process name : level : logger name : lineno : filename : message
            """
        )
    )

    rich.print(
        f"[b]{'Date & Time':^23s} : {'Process Name':20s} : {'Level':8s} : {'Logger Name':^25s} : {' Line '} : "
        f"{'Filename':20s} : {'Message'}[/]"
    )
    rich.print("-" * 150)
    for name, level in logging.getLevelNamesMapping().items():
        logger.log(level, f"{name} logging message")
