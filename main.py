import json
from pathlib import Path
from typing import Any, Literal

import httpx
from dynaconf import Dynaconf
from langchain.chat_models.base import init_chat_model
from langchain.prompts import ChatPromptTemplate
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


class Stage(BaseModel):
    plates: dict[str, list[NumberPlate]]
    phases: list[Phase] | None = None
    flatten: dict[str, list[str]] | None = None

    n_periods: list[int] = Field(default_factory=lambda: [5, 10, 15])


class AppConfig(BaseModel):
    version: str = Field(default="v1", description="API version")
    url: str
    params: dict[str, list[str]] = Field(default={}, description="Query parameters")
    parser: ParserProvider = Field(default="gx", description="Parser provider")

    base_url: str
    api_key: str
    model: str = Field(default="gpt-3.5-turbo", description="Model name")

    @model_validator(mode="before")
    @classmethod
    def from_dynaconf(cls, data: Any) -> Any:
        if isinstance(data, Dynaconf):
            return {k: data[k] for k in cls.model_fields.keys()}
        return data


app_config = AppConfig.model_validate(
    Dynaconf(
        envvar_prefix=(__package__ or "").upper(),
        settings_files=["app.yaml", "app.local.yaml"],
        yaml_loader="safe_load",
    )
)


http = httpx.AsyncClient()


async def fetch_data(params: dict[str, str] | None = None):
    from datetime import datetime

    date = datetime.now().strftime("%Y%m%d")
    file_path = DIR / f"{date}.html"
    if file_path.exists():
        with open(file_path, "r") as f:
            return f.read()

    resp = await http.get(app_config.url, params=params, timeout=10)
    resp.raise_for_status()

    html = resp.text

    with open(file_path, "w") as f:
        f.write(html)

    return html


async def setup_number(stage: Stage):
    dir = DIR / "data"
    dir.mkdir(parents=True, exist_ok=True)

    stage.phases = []

    for phase_name, items in stage.plates.items():
        phase = Phase(phase=phase_name, pin=[], ter=0)

        for item in items:
            match item.level:
                case "pin":
                    phase.pin.append(item.number)
                case "ter":
                    phase.ter = item.number
                case _:
                    ...
        stage.phases.append(phase)

    with open(dir / "number.json", "w") as f:
        f.write(
            json.dumps(
                it(stage.phases).map(lambda x: x.model_dump()).to_list(), indent=2
            )
        )

    stage.flatten = it(stage.phases).to_dict(lambda x: (x.phase, [*x.pin, x.ter]))

    with open(dir / "number_flatten.txt", "w") as f:
        for date, pins in stage.flatten.items():
            f.write(f"{date}: {', '.join(map(str, pins))}\n")


async def setup_counter(stage: Stage):
    for n in stage.n_periods:
        ...


async def setup_prophet(stage: Stage):
    file = PROMPT_DIR / "prophet.txt"
    prompt = ChatPromptTemplate.from_template(
        file.read_text(), template_format="jinja2"
    )

    model = init_chat_model(
        model=app_config.model,
        model_provider="openai",
        base_url=app_config.base_url,
        api_key=app_config.api_key,
        temperature=0.7,
    )

    chain = prompt | model
    result = await chain.ainvoke({"numbers": stage.flatten.values()})


SETUP_STAGES = {
    "SETUP_NUMBER": setup_number,
    "SETUP_COUNTER": setup_counter,
    "SETUP_PROPHET": setup_prophet,
    "COMPUTE": None,
}


async def main():
    content = await fetch_data()
    result = PARSER_MAP.get(app_config.parser, lambda _: None)(content)

    if result:
        stage = Stage(plates=result)
        for _, stage_func in SETUP_STAGES.items():
            if stage_func is None:
                break
            await stage_func(stage)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
