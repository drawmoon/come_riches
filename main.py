import json
from pathlib import Path
from typing import Any, Literal

import httpx
from dynaconf import Dynaconf
from langchain.chat_models.base import init_chat_model
from langchain.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, model_validator
from pyiter import it

from gx_parser import parse as gx_parse
from proto import NumberPlate, Phase

DIR = Path(__file__).parent / "work"
PROMPT_DIR = DIR / "prompt"

DIR.mkdir(parents=True, exist_ok=True)
PROMPT_DIR.mkdir(parents=True, exist_ok=True)


ParserProvider = Literal["gx"]


PARSER_MAP: dict[ParserProvider, callable] = {"gx": gx_parse}


class ModelArgs(BaseModel):
    model: str
    base_url: str
    api_key: str


class AppConfig(BaseModel):
    version: str = Field(default="v1")

    url: str
    years: list[str] = Field(default=[])

    parser: ParserProvider = Field(default="gx")
    lssue_numbers: list[int] = Field(default=[5, 10, 15])

    model_args: ModelArgs

    @model_validator(mode="before")
    @classmethod
    def from_dynaconf(cls, data: Any) -> Any:
        if isinstance(data, Dynaconf):
            return {k: data[k] for k in cls.model_fields.keys() if k in data}
        return data


app_config = AppConfig.model_validate(
    Dynaconf(
        envvar_prefix=(__package__ or "").upper(),
        settings_files=["app.yaml", "app.local.yaml"],
        yaml_loader="safe_load",
    )
)


http = httpx.AsyncClient()


def make_model() -> BaseChatModel:
    return init_chat_model(
        model_provider="openai",
        temperature=1e-8,
        **app_config.model_args.model,
    )


async def fetch_data(params: dict[str, str] | None = None):
    from datetime import datetime

    date = datetime.now().strftime("%Y%m%d")

    file_path = DIR / f"{date}.html"
    if params:
        file_path = (
            DIR
            / f"{date}_{it(params.items()).map(lambda x: f'{x[0]}_{x[1]}').join('_')}.html"
        )

    if file_path.exists():
        with open(file_path, "r") as f:
            return f.read()

    resp = await http.get(app_config.url, params=params, timeout=10)
    resp.raise_for_status()

    html = resp.text

    with open(file_path, "w") as f:
        f.write(html)

    return html


async def get_numbers(
    params: dict[str, str] | None = None, flatten: bool = False
) -> list[Phase] | dict[str, list[str]]:
    content = await fetch_data(params)
    plates: dict[str, list[NumberPlate]] | None = PARSER_MAP.get(
        app_config.parser, lambda _: None
    )(content)

    dir = DIR / "data"
    dir.mkdir(parents=True, exist_ok=True)

    numbers: list[Phase] = []

    for phase_name, items in plates.items():
        phase = Phase(phase=phase_name, pin=[], ter=0)

        for item in items:
            match item.level:
                case "pin":
                    phase.pin.append(item.number)
                case "ter":
                    phase.ter = item.number
                case _:
                    ...
        numbers.append(phase)

    with open(dir / "number.json", "w") as f:
        f.write(
            json.dumps(it(numbers).map(lambda x: x.model_dump()).to_list(), indent=2)
        )

    flatten_numbers = it(numbers).to_dict(lambda x: (x.phase, [*x.pin, x.ter]))

    with open(dir / "number_flatten.txt", "w") as f:
        for date, pins in flatten_numbers.items():
            f.write(f"{date}: {', '.join(map(str, pins))}\n")

    return flatten_numbers if flatten is True else numbers


async def pattern_analysis(flatten_phases: dict[str, list[str]]):
    for n in app_config.lssue_numbers:
        ...


async def prophet(flatten_phases: dict[str, list[str]]):
    file = PROMPT_DIR / "prophet.txt"
    prompt = ChatPromptTemplate.from_template(
        file.read_text(), template_format="jinja2"
    )

    model = make_model()

    chain = prompt | model
    result = await chain.ainvoke({"numbers": flatten_phases.values()})


async def hot_cold_numbers(take_numbers: int = 50) -> tuple[list, list]:
    from collections import Counter

    flatten_phases = await get_numbers(flatten=True)

    draws = (
        it(flatten_phases.values())
        .take(take_numbers)
        .map(lambda x: it(x).map(lambda s: int(s)).to_list())
        .to_list()
    )

    flat = it(draws).flat_map(lambda x: x).to_list()
    freq = Counter(flat)

    most_common = freq.most_common()

    hot_numbers = [(num, count) for num, count in most_common[:10]]

    last_seen = {n: None for n in range(1, 50)}
    for i, draw in enumerate(draws):
        for n in draw:
            if last_seen[n] is None:
                last_seen[n] = i
    miss = {k: (v if v is not None else len(draws)) for k, v in last_seen.items()}
    cold_numbers = sorted(miss.items(), key=lambda x: x[1], reverse=True)[:10]

    return hot_numbers, cold_numbers


async def print_hot_cold_numbers():
    take_numbers = 50
    hot_numbers, cold_numbers = await hot_cold_numbers(take_numbers=take_numbers)

    print(f"最近{take_numbers}期的冷热数字:\n")

    print("最热10个数字:")
    for n, c in hot_numbers:
        print(f"{n}: {c}次")

    print("\n最冷10个数字:")
    for n, t in cold_numbers:
        print(f"{n}: {t}期未出现")


async def main():
    await print_hot_cold_numbers()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
