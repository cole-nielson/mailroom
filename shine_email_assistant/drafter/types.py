from dataclasses import dataclass


@dataclass(frozen=True)
class Draft:
    body_markdown: str
    tokens_input: int = 0
    tokens_output: int = 0
    model_used: str = ""
