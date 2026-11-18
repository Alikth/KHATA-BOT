"""
Validated asset operations. All balance changes must occur in database transactions
and create an audit record; direct untracked edits are forbidden.
"""
