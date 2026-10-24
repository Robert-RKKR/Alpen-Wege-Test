# Standard library
from pathlib import Path

# Third-party
from defusedxml.ElementTree import iterparse

# Local application
from .errors import GpxProcessingError


def check_gpx_root(source) -> None:
    if isinstance(source, (str, Path)):
        source = open(source, "rb")
        should_close = True
    else:
        should_close = False
    try:
        for _, elem in iterparse(source, events=("start",), forbid_dtd=True):
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local.lower() != "gpx":
                raise GpxProcessingError(
                    "invalid_xml",
                    "Not a valid GPX file: root element is not <gpx>.",
                )
            return
        raise GpxProcessingError(
            "invalid_xml", "Not a valid GPX file: the file appears to be empty."
        )
    except GpxProcessingError:
        raise
    except Exception as exc:
        raise GpxProcessingError(
            "invalid_xml", f"Not a valid GPX file: {exc}"
        ) from exc
    finally:
        if should_close:
            source.close()
