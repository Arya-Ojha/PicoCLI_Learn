from __future__ import annotations

from typing import TypeAlias, Union

JSONPrimitive: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = Union[JSONPrimitive, "JSONArray", "JSONObject"]
JSONArray: TypeAlias = list["JSONValue"]
JSONObject: TypeAlias = dict[str, "JSONValue"]
