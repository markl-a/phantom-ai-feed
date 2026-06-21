"""Source resolvers: turn platform identifiers into RSS/Atom feed URLs.

Each resolver is a pure-stdlib, offline-unit-testable utility that reuses
``phantom_ai_feed.fetch`` for the network layer (retry/backoff/UA/offline).
They are tools to GENERATE feeds.toml entries; the runtime pipeline still only
reads feeds.toml.
"""
