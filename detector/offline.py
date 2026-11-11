"""Keep the detector fully offline.

Presidio's email and URL recognizers use the `tldextract` library, which by
default downloads the Public Suffix List from the internet the first time it
runs. That request never contains user text, but a privacy tool should not make
any outbound network calls, so we switch tldextract to its bundled snapshot.

Import this module BEFORE anything from presidio_analyzer.
"""
import tldextract

_offline_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
tldextract.extract = _offline_extract  # module-level function presidio calls
tldextract.tldextract.extract = _offline_extract
