"""Production labeling stack shared by the batch harness and the API (spec 0012, AD-12).

Manual constructor injection only: no `pywire` import may appear anywhere in this
package (ADR 0015). Every component here is synchronous — the API calls it through
`asyncio.to_thread` rather than an async duplicate (AD-25).
"""
