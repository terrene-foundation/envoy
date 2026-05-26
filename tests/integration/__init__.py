"""tests/integration — Wave-4 runtime-facade integration tests.

Per `specs/grant-moment.md` § Test location "Runtime layer (deferred to
Wave-4 facade)" these files exercise ``EnvoyGrantMomentRuntime`` against
real ``InMemoryKeyManager`` + real ``EnvoyLedger`` + real ``ChannelHandoff``
with structural adapter stubs (no ``unittest.mock``).
"""
