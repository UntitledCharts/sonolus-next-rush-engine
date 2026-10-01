import hashlib
import json
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from sonolus.build.collection import validate_item_name

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / "next-sekai"
SERVER_URL = "https://coconut.sonolus.com/next-sekai/"
type AssetCategory = Literal["skins", "backgrounds", "effects", "particles"]
ASSET_FIELDS: dict[AssetCategory, tuple[str, ...]] = {
    "skins": ("thumbnail", "data", "texture"),
    "backgrounds": ("thumbnail", "data", "image", "configuration"),
    "effects": ("thumbnail", "data", "audio"),
    "particles": ("thumbnail", "data", "texture"),
}
ASSET_KINDS: dict[str, AssetCategory] = {
    "Skin": "skins",
    "Background": "backgrounds",
    "Effect": "effects",
    "Particle": "particles",
}
DEFAULT_ASSETS: dict[AssetCategory, tuple[int, ...]] = {
    "skins": (1, 2),
    "backgrounds": (1,),
    "effects": (1, 2),
    "particles": (1,),
}

TEST_LEVEL_IDS = (
    10,
    11,
    21,
    24,
    47,
    100,
    103,
    185,
    262,
    263,
    312,
    497,
    674,
    1224,
    1283,
    1451,
    15003,
    15152,
    15856,
    16471,
    18317,
    19131,
    21506,
    22212,
)


def _write(path: Path, data: bytes) -> None:
    """Atomically write changed files."""
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_bytes(data)
        temporary.replace(path)


class NextSekaiClient:
    """Cache Next SEKAI resources locally."""

    def __init__(self, cache_dir: Path = CACHE_DIR, *, refresh: bool = False):
        self.cache_dir = Path(cache_dir)
        self.resources = self.cache_dir / "resources"
        self.refresh = refresh
        self._assets: set[tuple[str, str]] = set()
        self._files: set[Path] = set()

    def _write_resource(self, path: Path, data: bytes) -> None:
        _write(path, data)
        self._files.add(path)

    @staticmethod
    def _name(name: str | int) -> str:
        name = f"coconut-next-sekai-{name}" if isinstance(name, int) else name
        validate_item_name(name, "Next SEKAI item")
        return name

    @staticmethod
    def _download(url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Sonolus-Version": "1.0.0"})
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except OSError as exc:
            exc.add_note(f"Unable to download {url}")
            raise

    def _item(self, category: str, name: str) -> dict:
        path = self.cache_dir / "metadata" / category / f"{name}.json"
        url = urljoin(SERVER_URL, f"sonolus/{category}/{quote(name, safe='')}?localization=en")
        if path.is_file() and not self.refresh:
            details = json.loads(path.read_bytes())
        else:
            data = self._download(url)
            details = json.loads(data)
            if not isinstance(details.get("item"), dict) or details["item"].get("name") != name:
                raise ValueError(f"Unexpected {category} response from {url}")
            _write(path, data)
        item = dict(details["item"])
        if "description" in details:
            item["description"] = details["description"]
        return item

    def _binary(self, resource: dict) -> bytes:
        url = urljoin(SERVER_URL, resource["url"].replace(" ", "%20"))
        digest = resource.get("hash")
        if digest and (len(digest) != 40 or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError(f"Invalid resource SHA-1: {digest!r}")
        key = digest or hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / "repository" / key
        if path.is_file():
            data = path.read_bytes()
            if not digest or hashlib.sha1(data).hexdigest() == digest:
                return data
        data = self._download(url)
        if digest and hashlib.sha1(data).hexdigest() != digest:
            raise ValueError(f"Resource SHA-1 mismatch: {url}")
        _write(path, data)
        return data

    def _save(self, category: str, item: dict, fields: tuple[str, ...]) -> Path:
        path = self.resources / category / item["name"]
        metadata = {key: value for key, value in item.items() if key not in fields}
        for field in fields:
            if item.get(field):
                # No extension: Sonolus.py would gzip .json and .bin files again.
                self._write_resource(path / field, self._binary(item[field]))
            else:
                (path / field).unlink(missing_ok=True)
        self._write_resource(path / "item.json", json.dumps(metadata, ensure_ascii=False).encode())
        return path

    def load_asset(self, category: AssetCategory, name: str | int) -> Path:
        if category not in ASSET_FIELDS:
            raise ValueError(f"Unsupported asset category: {category}")
        name = self._name(name)
        key = (category, name)
        if key not in self._assets:
            self._save(category, self._item(category, name), ASSET_FIELDS[category])
            self._assets.add(key)
        return self.resources / category / name

    def load_level(self, name: str | int) -> Path:
        """Cache a level and its assets."""
        item = self._item("levels", self._name(name))
        for kind, category in ASSET_KINDS.items():
            selection = item.get(f"use{kind}", {"useDefault": True})
            asset = item["engine"][kind.lower()] if selection["useDefault"] else selection["item"]
            asset_name = asset["name"] if isinstance(asset, dict) else asset
            self.load_asset(category, asset_name)
            item[f"use{kind}"] = {"useDefault": False, "item": asset_name}
        item["engine"] = "next-rush-dev"
        return self._save("levels", item, ("cover", "bgm", "preview", "data"))


def load_resources(*, cache_dir: Path = CACHE_DIR, refresh: bool = False) -> Path:
    client = NextSekaiClient(cache_dir, refresh=refresh)
    for category, names in DEFAULT_ASSETS.items():
        for name in names:
            client.load_asset(category, name)
    for name in TEST_LEVEL_IDS:
        client.load_level(name)
    for source in (ROOT / "resources").rglob("*"):
        if source.is_file() and source.suffix != ".scp":
            client._write_resource(client.resources / source.relative_to(ROOT / "resources"), source.read_bytes())
    for path in client.resources.rglob("*"):
        if path.is_file() and path not in client._files:
            path.unlink()
    return client.resources
