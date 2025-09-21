import json
from pathlib import Path
from typing import Any, Literal

import httpx
from dynaconf import Dynaconf
from pydantic import BaseModel, Field, model_validator
from pyiter import it

from proto import NumberPlate, Phase

DIR = Path(__file__).parent / "work"
PROMPT_DIR = DIR / "prompt"

DIR.mkdir(parents=True, exist_ok=True)
PROMPT_DIR.mkdir(parents=True, exist_ok=True)


ParserProvider = Literal["gx"]


class AppConfig(BaseModel):
    version: str = Field(default="v1", description="API version")
    url: str
    params: dict[str, list[str]] = Field(default={}, description="Query parameters")
    parser: ParserProvider = Field(default="gx", description="Parser provider")

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


async def setup_number(data: dict[str, list[NumberPlate]]):
    dir = DIR / "data"
    dir.mkdir(parents=True, exist_ok=True)

    result: list[Phase] = []
    for phase_name, items in data.items():
        phase = Phase(phase=phase_name, pin=[], ter=0)

        for item in items:
            match item.level:
                case "pin":
                    phase.pin.append(item.number)
                case "ter":
                    phase.ter = item.number
                case _:
                    ...
        result.append(phase)

    with open(dir / "number.json", "w") as f:
        f.write(
            json.dumps(it(result).map(lambda x: x.model_dump()).to_list(), indent=2)
        )

    flatten_data = it(result).to_dict(lambda x: (x.phase, [*x.pin, x.ter]))

    with open(dir / "number_flatten.txt", "w") as f:
        for date, pins in flatten_data.items():
            f.write(f"{date}: {', '.join(map(str, pins))}\n")


async def main():
    content = await fetch_data()

    if app_config.parser == "gx":
        from gx_parser import parse

        result = parse(content)
    else:
        ...

    if result:
        await setup_number(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
