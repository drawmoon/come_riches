from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from proto import NumberPlate


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    sections = soup.find_all("div", class_="kj-tit")

    result: dict[str, list[NumberPlate]] = {}

    for section in sections:
        title = section.get_text(strip=True)

        if title:
            import re

            ret = re.findall(r"\d+", title)
            if ret:
                title = f"{ret[0]}/{ret[1]}/{ret[2]}"

        box = section.find_next_sibling("div", class_="kj-box")

        if not box:
            continue

        result[title] = []

        numbers = box.find_all("li")

        level = "pin"

        for number in numbers:
            if "kj-jia" in number.get("class", []):
                level = "ter"
                continue

            number_elem = number.find("dt")
            number_text = number_elem.get_text(strip=True) if number_elem else ""

            first_dd = number.find("dd")
            if not first_dd:
                continue

            parts = []
            for content in first_dd.contents:
                if isinstance(content, NavigableString):
                    parts.append(content.strip())
                elif isinstance(content, Tag):
                    text = content.get_text(strip=True)
                    if text and text != "/":
                        parts.append(text)
                else:
                    ...

            hidden_dds = number.find_all("dd", style="display: none")
            for hdd in hidden_dds:
                spans = hdd.find_all("span")
                for span in spans:
                    text = span.get_text(strip=True)
                    if text and text != "/":
                        parts.append(text)

            zodiac = parts[0]
            five_elem = parts[1]
            color = parts[2]
            size = parts[3]
            sidedness = parts[4]
            sidedness_merge = parts[5]
            fauna = parts[6]
            sidedness_count = parts[7]

            plate = NumberPlate(
                number=number_text,
                level=level,
                zodiac=zodiac,
                five_elem=five_elem,
                color=color,
                fauna=fauna,
                sidedness=sidedness,
                sidedness_count=sidedness_count,
                sidedness_merge=sidedness_merge,
                size=size,
            )
            result[title].append(plate)

    return result
