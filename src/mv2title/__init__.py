"""mv2title — ノイズの多い音楽動画タイトルから曲名を推論するライブラリ。

典型的な使い方:

	from mv2title import Config, LLMClient, TitleInput, extract_titles

	client = LLMClient(Config.from_env())
	results = extract_titles(["アーティスト『曲名』(Official Music Video)"], client)
"""

from .connect import (
	Config,
	ConnectionCheckError,
	LLMClient,
	ModelCheckedClient,
	ModelMismatchError,
	check_endpoint,
	fetch_model_ids,
	make_client,
	model_aliases,
	resolve_model,
)
from .models import TitleInput, TitleResult
from .pipeline import extract_titles

# pyproject.toml の [project] version と同期させること。
__version__ = "0.5.0"

__all__ = [
	"Config",
	"ConnectionCheckError",
	"LLMClient",
	"ModelCheckedClient",
	"ModelMismatchError",
	"TitleInput",
	"TitleResult",
	"__version__",
	"check_endpoint",
	"extract_titles",
	"fetch_model_ids",
	"make_client",
	"model_aliases",
	"resolve_model",
]
